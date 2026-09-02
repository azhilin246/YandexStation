import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from custom_components.yandex_station.calendar import (
    event_to_onetime_command,
    onetime_scenario_to_event,
)
from custom_components.yandex_station.core.yandex_quasar import YandexQuasar


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
            "scheduled_time": "2026-09-02T04:15:22+03:00",
        }
    )

    assert event.uid == "launch-id"
    assert event.summary == "Люстра"
    assert event.start.isoformat() == "2026-09-02T04:15:22+03:00"
    assert event.end - event.start == timedelta(minutes=1)


def test_load_onetime_scenarios():
    response = AsyncMock()
    response.json.return_value = {
        "status": "ok",
        "scenarios": [{"id": "regular"}],
        "onetime_scenarios": [{"id": "launch-id"}],
    }
    session = AsyncMock()
    session.get.return_value = response
    quasar = YandexQuasar(session)

    result = asyncio.run(quasar.load_onetime_scenarios())

    assert result == [{"id": "launch-id"}]
    assert quasar.scenarios == [{"id": "regular"}]


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
