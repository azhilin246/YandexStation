import logging
from datetime import date, datetime, time, timedelta
from math import ceil

from dateutil.rrule import rrulestr
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .core.const import DOMAIN
from .core.yandex_quasar import YandexQuasar

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    quasar: YandexQuasar = hass.data[DOMAIN][entry.unique_id]
    # can't use update_before_add because it works for disabled entities
    async_add_entities(
        [YandexCalendar(quasar, sp) for sp in quasar.speakers]
        + [YandexTemporaryScenariosCalendar(quasar, entry.unique_id)]
    )


class YandexCalendar(CalendarEntity):
    _attr_entity_registry_enabled_default = False
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, quasar: YandexQuasar, device: dict):
        self.quasar = quasar
        self.device = device

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device["quasar_info"]["device_id"])},
            name=self.device["name"],
        )
        self._attr_name = device["name"] + " Будильники"
        self._attr_unique_id = device["quasar_info"]["device_id"] + f"_calendar"

        self.entity_id = f"calendar.yandex_station_{slugify(self._attr_unique_id)}"

        self.events: list[CalendarEvent] = []
        self.next_event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        return self.next_event

    async def async_update(self):
        try:
            alarms = await self.quasar.get_alarms(self.device)
            self.events = [alarm_to_event(i) for i in alarms]
            dt = datetime.now().astimezone()
            for event in sorted(self.events, key=lambda x: x.start):
                if event.start >= dt:
                    self.next_event = event
                    break
            else:
                self.next_event = None
        except:
            pass

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [i for i in self.events if start_date <= i.start and i.end <= end_date]

    async def async_create_event(self, **kwargs) -> None:
        if await self.quasar.create_alarm(self.device, event_to_alarm(kwargs)):
            await self.async_update_ha_state(force_refresh=True)

    async def async_delete_event(self, uid: str, **kwargs) -> None:
        if await self.quasar.cancel_alarms(self.device, uid):
            await self.async_update_ha_state(force_refresh=True)

    async def async_update_event(self, uid: str, event: dict, **kwargs) -> None:
        if await self.quasar.change_alarm(self.device, event_to_alarm(event, uid)):
            await self.async_update_ha_state(force_refresh=True)


class YandexTemporaryScenariosCalendar(CalendarEntity):
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, quasar: YandexQuasar, account_id: str):
        self.quasar = quasar
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{account_id}_scenarios")},
            name="Сценарии",
            manufacturer="Yandex",
        )
        self._attr_name = "Временные сценарии"
        self._attr_unique_id = f"{account_id}_temporary_scenarios_calendar"
        self.entity_id = f"calendar.yandex_station_{slugify(self._attr_unique_id)}"

        self.events: list[CalendarEvent] = []
        self.next_event: CalendarEvent | None = None

    @property
    def event(self) -> CalendarEvent | None:
        return self.next_event

    async def async_update(self):
        try:
            scenarios = await self.quasar.load_onetime_scenarios()
            self.events = [
                onetime_scenario_to_event(item, self.hass) for item in scenarios
            ]
            now = dt_util.now()
            self.next_event = next(
                (
                    item
                    for item in sorted(self.events, key=lambda event: event.start)
                    if item.start >= now
                ),
                None,
            )
        except Exception:
            _LOGGER.exception("Не удалось обновить временные сценарии")

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            item
            for item in self.events
            if start_date <= item.start and item.end <= end_date
        ]

    async def async_create_event(self, **kwargs) -> None:
        command = event_to_onetime_command(kwargs)
        if await self.quasar.create_onetime_scenario(command, kwargs.get("location")):
            await self.async_update_ha_state(force_refresh=True)

    async def async_delete_event(self, uid: str, **kwargs) -> None:
        if await self.quasar.cancel_onetime_scenario(uid):
            await self.async_update_ha_state(force_refresh=True)


DAYS_ALARM = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
DAYS_EVENT = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
DURATION = timedelta(minutes=1)


def _event_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min, dt_util.DEFAULT_TIME_ZONE)


def _russian_interval(value: timedelta) -> str:
    minutes = max(1, ceil(value.total_seconds() / 60))
    if minutes % 60 == 0:
        count = minutes // 60
        forms = ("час", "часа", "часов")
    else:
        count = minutes
        forms = ("минуту", "минуты", "минут")

    remainder = count % 100
    if 11 <= remainder <= 14:
        form = forms[2]
    elif count % 10 == 1:
        form = forms[0]
    elif 2 <= count % 10 <= 4:
        form = forms[1]
    else:
        form = forms[2]
    return f"{count} {form}"


def event_to_onetime_command(event: dict, now: datetime | None = None) -> str:
    """Преобразует событие календаря в естественную команду Алисе."""
    command = event["summary"].strip()
    if not command:
        raise ValueError("Название события должно содержать команду Алисе")

    start = _event_datetime(event["dtstart"])
    end = _event_datetime(event["dtend"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    if end < start:
        raise ValueError("Конец события не может быть раньше начала")

    if now is None:
        now = dt_util.now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)

    delay = start - now.astimezone(start.tzinfo)
    if delay > timedelta(seconds=30):
        command += f" через {_russian_interval(delay)}"

    duration = end - start
    if duration > DURATION:
        command += f" на {_russian_interval(duration)}"
    return command


def resolve_target_entity_id(
    target: dict, hass: HomeAssistant | None = None
) -> str | None:
    """Связывает цель Яндекса с сущностью Home Assistant."""
    if entity_id := target.get("entity_id"):
        return entity_id
    if hass is None or not (target_id := target.get("id")):
        return None

    unique_id = target_id.replace("-", "")
    registry = er.async_get(hass)
    return next(
        (
            entry.entity_id
            for entry in registry.entities.values()
            if entry.platform == DOMAIN and entry.unique_id == unique_id
        ),
        None,
    )


def onetime_scenario_to_event(
    scenario: dict, hass: HomeAssistant | None = None
) -> CalendarEvent:
    dt = _onetime_scenario_datetime(scenario["scheduled_time"])
    start = None

    if value := scenario.get("created_time"):
        try:
            start = _onetime_scenario_datetime(value)
        except (TypeError, ValueError):
            pass

    if start is None or start >= dt:
        timer = scenario.get("initial_timer_value")
        if (
            isinstance(timer, (int, float))
            and not isinstance(timer, bool)
            and timer > 0
        ):
            start = dt - timedelta(seconds=timer)

    if start is None or start >= dt:
        start = dt
        end = dt + DURATION
    else:
        end = dt

    targets = scenario.get("targets", [])
    action = onetime_action_summary(targets)
    name = scenario.get("name") or "Временный сценарий"
    summary = f"{action} {name}" if action else name
    entity_ids = [
        entity_id
        for target in targets
        if (entity_id := resolve_target_entity_id(target, hass))
    ]
    rooms = sorted(
        {target["room_name"] for target in targets if target.get("room_name")}
    )

    return CalendarEvent(
        start,
        end,
        summary,
        "\n".join(entity_ids),
        location=", ".join(rooms) or None,
        uid=scenario["id"],
    )


def _onetime_scenario_datetime(value: str | int | float) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, dt_util.UTC)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)


def onetime_action_summary(targets: list[dict]) -> str | None:
    """Возвращает краткое описание действия временного сценария."""
    actions = []
    for target in targets:
        target_type = target.get("type") or ""
        for capability in target.get("capabilities", []):
            state = capability.get("state") or {}
            instance = state.get("instance")
            value = state.get("value")
            capability_type = capability.get("type")

            if (
                capability_type == "devices.capabilities.on_off"
                and target_type.startswith("devices.types.openable")
                and value is True
            ):
                action = "Открыть"
            elif (
                capability_type == "devices.capabilities.on_off"
                and target_type.startswith("devices.types.openable")
                and value is False
            ):
                action = "Закрыть"
            elif capability_type == "devices.capabilities.on_off" and value is True:
                action = "Включить"
            elif capability_type == "devices.capabilities.on_off" and value is False:
                action = "Выключить"
            elif capability_type == "devices.capabilities.lock" and value is True:
                action = "Закрыть замок"
            elif capability_type == "devices.capabilities.lock" and value is False:
                action = "Открыть замок"
            elif capability_type == "devices.capabilities.range" and instance == "open":
                if value == 0:
                    action = "Закрыть"
                elif value == 100:
                    action = "Открыть"
                elif isinstance(value, (int, float)):
                    action = f"Открыть на {value}%"
                else:
                    action = None
            elif (
                capability_type == "devices.capabilities.range"
                and instance == "brightness"
                and isinstance(value, (int, float))
            ):
                action = f"Яркость {value}%"
            else:
                action = None

            if action and action not in actions:
                actions.append(action)

    return ", ".join(actions) or None


def alarm_to_event(alarm: dict) -> CalendarEvent:
    if r := alarm.get("recurring"):
        days = [DAYS_EVENT[DAYS_ALARM.index(i)] for i in r["days_of_week"]]
        r = "FREQ=WEEKLY;BYDAY=" + ",".join(days)
        dt = datetime.strptime(alarm["time"], "%H:%M")
        rule = rrulestr(r).replace(dtstart=dt)
        dt = datetime.now()
        dt = rule.after(dt) if alarm["enabled"] else rule.before(dt)
    else:
        dt = datetime.strptime(f'{alarm["date"]}T{alarm["time"]}', "%Y-%m-%dT%H:%M")

    dt = dt.astimezone()  # add current timezone
    summary = "Будильник" if alarm["enabled"] else "Выключен"
    return CalendarEvent(dt, dt + DURATION, summary, "", uid=alarm["alarm_id"], rrule=r)


def event_to_alarm(event: dict, uid: str = "") -> dict:
    alarm = {
        "alarm_id": uid,
        "enabled": event["summary"] != "Выключен",
        "time": event["dtstart"].strftime("%H:%M"),
    }

    if "rrule" in event:
        r: dict[str, str] = dict(s.split("=", 1) for s in event["rrule"].split(";"))
        days = [DAYS_ALARM[DAYS_EVENT.index(i)] for i in r["BYDAY"].split(",")]
        alarm["recurring"] = {"days_of_week": days}
    else:
        alarm["date"] = event["dtstart"].strftime("%Y-%m-%d")

    return alarm
