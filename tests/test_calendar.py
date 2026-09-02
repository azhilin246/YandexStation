import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from custom_components.yandex_station.calendar import (
    event_to_onetime_command,
    onetime_action_summary,
    onetime_scenario_to_event,
)
from custom_components.yandex_station.core.yandex_quasar import (
    YandexQuasar,
    parse_onetime_targets,
)


def test_event_to_delayed_command():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    event = {
        "summary": "закрой шторы",
        "dtstart": now + timedelta(minutes=10),
        "dtend": now + timedelta(minutes=11),
    }

    assert event_to_onetime_command(event, now) == "закрой шторы через 10 минут"


def test_event_to_duration_command():
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    event = {
        "summary": "включи свет",
        "dtstart": now,
        "dtend": now + timedelta(hours=1),
    }

    assert event_to_onetime_command(event, now) == "включи свет на 1 час"


def test_onetime_scenario_to_event():
    event = onetime_scenario_to_event(
        {
            "id": "launch-id",
            "name": "Люстра",
            "created_time": "2026-09-01T08:15:22+03:00",
            "scheduled_time": "2026-09-02T04:15:22+03:00",
            "initial_timer_value": 72000,
            "targets": [
                {
                    "entity_id": "light.office_ceiling_light",
                    "room_name": "Кабинет",
                    "capabilities": [
                        {
                            "type": "devices.capabilities.on_off",
                            "state": {"instance": "on", "value": False},
                        }
                    ],
                }
            ],
        }
    )

    assert event.uid == "launch-id"
    assert event.summary == "Выключить Люстра"
    assert event.description == "light.office_ceiling_light"
    assert event.location == "Кабинет"
    assert event.start.isoformat() == "2026-09-01T08:15:22+03:00"
    assert event.end.isoformat() == "2026-09-02T04:15:22+03:00"
    assert event.end - event.start == timedelta(hours=20)


def test_onetime_scenario_uses_initial_timer_without_created_time():
    event = onetime_scenario_to_event(
        {
            "id": "launch-id",
            "name": "Люстра",
            "scheduled_time": "2026-09-03T00:16:19Z",
            "initial_timer_value": 72000,
        }
    )

    assert event.start.isoformat() == "2026-09-02T04:16:19+00:00"
    assert event.end.isoformat() == "2026-09-03T00:16:19+00:00"


def test_onetime_scenario_uses_minute_fallback_without_timer_metadata():
    event = onetime_scenario_to_event(
        {
            "id": "launch-id",
            "name": "Люстра",
            "scheduled_time": "2026-09-03T00:16:19Z",
        }
    )

    assert event.start.isoformat() == "2026-09-03T00:16:19+00:00"
    assert event.end - event.start == timedelta(minutes=1)


def test_onetime_action_summary_for_cover():
    assert (
        onetime_action_summary(
            [
                {
                    "type": "devices.types.openable.curtain",
                    "capabilities": [
                        {
                            "type": "devices.capabilities.on_off",
                            "state": {"instance": "on", "value": False},
                        }
                    ],
                }
            ]
        )
        == "Закрыть"
    )


def test_parse_onetime_targets():
    launch = {
        "steps": [
            {
                "type": "scenarios.steps.actions.v2",
                "parameters": {
                    "items": [
                        {
                            "id": "target-id",
                            "value": {
                                "id": "target-id",
                                "name": "Люстра",
                                "type": "devices.types.light.ceiling",
                                "item_type": "device",
                                "capabilities": [
                                    {
                                        "type": "devices.capabilities.on_off",
                                        "state": {"instance": "on", "value": False},
                                    }
                                ],
                            },
                        }
                    ]
                },
            }
        ]
    }
    devices = [
        {
            "id": "target-id",
            "external_id": "light.office_ceiling_light",
            "name": "Люстра",
            "type": "devices.types.light.ceiling",
            "item_type": "device",
            "room_name": "Кабинет",
            "house_name": "Дом",
        }
    ]

    assert parse_onetime_targets(launch, devices) == [
        {
            "id": "target-id",
            "entity_id": "light.office_ceiling_light",
            "external_id": "light.office_ceiling_light",
            "name": "Люстра",
            "type": "devices.types.light.ceiling",
            "item_type": "device",
            "room_name": "Кабинет",
            "house_name": "Дом",
            "capabilities": [
                {
                    "type": "devices.capabilities.on_off",
                    "state": {"instance": "on", "value": False},
                }
            ],
        }
    ]


def test_load_onetime_scenarios():
    list_response = AsyncMock()
    list_response.json.return_value = {
        "status": "ok",
        "scenarios": [{"id": "regular"}],
        "onetime_scenarios": [{"id": "launch-id"}],
    }
    detail_response = AsyncMock()
    detail_response.json.return_value = {
        "status": "ok",
        "launch": {"id": "launch-id", "steps": []},
    }
    session = AsyncMock()
    session.get.side_effect = [list_response, detail_response]
    quasar = YandexQuasar(session)
    quasar.devices = []

    result = asyncio.run(quasar.load_onetime_scenarios())

    assert result == [{"id": "launch-id", "targets": []}]
    assert quasar.scenarios == [{"id": "regular"}]
    assert session.get.await_args_list[1].args == (
        "https://iot.quasar.yandex.ru/m/v3/user/launches/launch-id/edit",
    )


def test_cancel_onetime_scenario():
    response = AsyncMock()
    response.json.return_value = {"request_id": "request-id", "status": "ok"}
    session = AsyncMock()
    session.delete.return_value = response
    quasar = YandexQuasar(session)

    assert asyncio.run(quasar.cancel_onetime_scenario("launch/id")) is True
    session.delete.assert_awaited_once_with(
        "https://iot.quasar.yandex.ru/m/user/launches/launch%2Fid"
    )


def test_create_onetime_scenario_uses_named_speaker():
    quasar = YandexQuasar(AsyncMock())
    kitchen = {
        "id": "kitchen",
        "name": "Кухня",
        "quasar_info": {"platform": "yandexmini"},
        "capabilities": [{}],
    }
    bedroom = {
        "id": "bedroom",
        "name": "Спальня",
        "quasar_info": {"platform": "yandexmini"},
        "capabilities": [{}],
    }
    quasar.devices = [kitchen, bedroom]
    quasar.send = AsyncMock()

    assert (
        asyncio.run(
            quasar.create_onetime_scenario("закрой шторы через 10 минут", "спальня")
        )
        is True
    )
    quasar.send.assert_awaited_once_with(bedroom, "закрой шторы через 10 минут")
