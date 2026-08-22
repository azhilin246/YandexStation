from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import MAJOR_VERSION, MINOR_VERSION

from custom_components.yandex_station.fan import YandexFan
from . import false, true, update_ha_state


def fan_device(on: bool, speed: str, oscillation: bool) -> dict:
    return {
        "id": "xxx",
        "name": "Mijia Smart Tower Fan 2",
        "type": "devices.types.ventilation.fan",
        "icon_url": "https://avatars.mds.yandex.net/get-iot/icons-devices-devices.types.fan.svg/orig",
        "capabilities": [
            {
                "reportable": true,
                "retrievable": true,
                "type": "devices.capabilities.on_off",
                "state": {"instance": "on", "value": on},
                "parameters": {"split": false},
                "can_be_deferred": true,
            },
            {
                "reportable": true,
                "retrievable": true,
                "type": "devices.capabilities.mode",
                "state": {"instance": "fan_speed", "value": speed},
                "parameters": {
                    "instance": "fan_speed",
                    "name": "скорость вентиляции",
                    "modes": [
                        {"value": "low", "name": "Низкая"},
                        {"value": "medium", "name": "Средняя"},
                        {"value": "high", "name": "Высокая"},
                        {"value": "turbo", "name": "Турбо"},
                    ],
                },
            },
            {
                "reportable": true,
                "retrievable": true,
                "type": "devices.capabilities.toggle",
                "state": {"instance": "controls_locked", "value": false},
                "parameters": {
                    "instance": "controls_locked",
                    "name": "блокировка управления",
                },
            },
            {
                "reportable": true,
                "retrievable": true,
                "type": "devices.capabilities.toggle",
                "state": {"instance": "oscillation", "value": oscillation},
                "parameters": {"instance": "oscillation", "name": "вращение"},
            },
        ],
        "properties": [],
        "item_type": "device",
        "skill_id": "ad26f8c2-fc31-4928-a653-d829fda7e6c2",
        "room_name": "Спальня",
        "state": "online",
        "parameters": {
            "device_info": {
                "manufacturer": "dmaker",
                "model": "dmaker.fan.p45",
                "sw_version": "1.1.1.0007",
            }
        },
    }


def expected_features() -> FanEntityFeature:
    features = FanEntityFeature.SET_SPEED | FanEntityFeature.OSCILLATE
    if (MAJOR_VERSION, MINOR_VERSION) >= (2024, 8):
        features |= FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
    return features


def test_fan_on():
    device = fan_device(on=true, speed="low", oscillation=true)

    state = update_ha_state(YandexFan, device, config={})
    assert state.state == "on"
    assert state.attributes == {
        "friendly_name": "Mijia Smart Tower Fan 2",
        "oscillating": True,
        "percentage": 25,
        "percentage_step": 25.0,
        "preset_mode": None,
        "preset_modes": None,
        "supported_features": expected_features(),
    }


def test_fan_off():
    device = fan_device(on=false, speed="high", oscillation=false)

    state = update_ha_state(YandexFan, device, config={})
    assert state.state == "off"
    # a turned off fan reports 0%, not the last speed
    assert state.attributes["percentage"] == 0
    assert state.attributes["oscillating"] is False
