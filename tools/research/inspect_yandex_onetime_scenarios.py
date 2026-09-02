"""Read-only inspection of Yandex temporary scenario device references.

A JSON list of cookie records is read from stdin and is never printed.
"""

import argparse
import json
import sys
from collections.abc import Iterable

import requests

SCENARIOS_URL = "https://iot.quasar.yandex.ru/m/user/scenarios"
DEVICES_URL = "https://iot.quasar.yandex.ru/m/v3/user/devices"
LAUNCH_EDIT_URL = "https://iot.quasar.yandex.ru/m/v3/user/launches/{launch_id}/edit"


def set_cookies(session: requests.Session, records: Iterable[dict]) -> None:
    root_yandex_cookies = {}
    for record in records:
        session.cookies.set(
            record["name"],
            record["value"],
            domain=record.get("domain"),
            path=record.get("path", "/"),
        )
        if record.get("domain") == "yandex.ru" and record.get("path") in ("", "/"):
            root_yandex_cookies[record["name"]] = record["value"]

    session.headers["Cookie"] = "; ".join(
        f"{name}={value}" for name, value in root_yandex_cookies.items()
    )


def load_cookie(session: requests.Session, value: str) -> None:
    set_cookies(session, json.loads(value.strip()))


def iter_household_items(response: dict) -> Iterable[dict]:
    for household in response.get("households", []):
        house_name = household.get("name")
        for value in household.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict) and item.get("id"):
                    yield {**item, "house_name": item.get("house_name", house_name)}


def scenario_devices(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.get("id") if isinstance(item, dict) else item
        for item in value
        if (isinstance(item, str) or isinstance(item, dict))
    ]


def device_summary(device: dict) -> dict:
    external_id = device.get("external_id")
    return {
        "id": device.get("id"),
        "external_id": external_id,
        "ha_entity_id": (
            external_id if isinstance(external_id, str) and "." in external_id else None
        ),
        "name": device.get("name"),
        "type": device.get("type"),
        "item_type": device.get("item_type"),
        "room_name": device.get("room_name"),
        "house_name": device.get("house_name"),
        "skill_id": device.get("skill_id"),
    }


def launch_target_summary(item: dict, indexed_devices: dict[str, dict]) -> dict:
    value = item.get("value") or {}
    device_id = value.get("id") or item.get("id")
    return {
        "id": device_id,
        "name": value.get("name"),
        "type": value.get("type"),
        "item_type": value.get("item_type"),
        "capabilities": [
            {"type": capability.get("type"), "state": capability.get("state")}
            for capability in value.get("capabilities", [])
        ],
        "matched_device": (
            device_summary(indexed_devices[device_id])
            if device_id in indexed_devices
            else None
        ),
    }


def launch_targets(details: dict, indexed_devices: dict[str, dict]) -> list[dict]:
    result = []
    for step in details.get("launch", {}).get("steps", []):
        for item in step.get("parameters", {}).get("items", []):
            if isinstance(item, dict):
                result.append(launch_target_summary(item, indexed_devices))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--include-launch-details", action="store_true")
    args = parser.parse_args()

    cookie = sys.stdin.read().strip()
    if not cookie:
        raise SystemExit("Expected JSON YandexStation cookie records on stdin")

    session = requests.Session()
    load_cookie(session, cookie)
    scenarios_response = session.get(SCENARIOS_URL, timeout=args.timeout)
    scenarios_response.raise_for_status()
    devices_response = session.get(DEVICES_URL, timeout=args.timeout)
    devices_response.raise_for_status()

    scenarios = scenarios_response.json()
    devices = devices_response.json()
    if scenarios.get("status") != "ok" or devices.get("status") != "ok":
        raise SystemExit("Yandex API returned a non-ok status")

    indexed_devices = {}
    for device in iter_household_items(devices):
        indexed_devices[device["id"]] = device

    result = []
    for scenario in scenarios.get("onetime_scenarios", []):
        listed_devices = scenario_devices(scenario.get("devices"))
        item = {
            "id": scenario.get("id"),
            "name": scenario.get("name"),
            "created_time": scenario.get("created_time"),
            "scheduled_time": scenario.get("scheduled_time"),
            "initial_timer_value": scenario.get("initial_timer_value"),
            "current_timer_value": scenario.get("current_timer_value"),
            "status": scenario.get("status"),
            "device_type": scenario.get("device_type"),
            "trigger_type": scenario.get("trigger_type"),
            "schedule_type": scenario.get("schedule_type"),
            "listed_devices": listed_devices,
        }
        if args.include_launch_details:
            details_response = session.get(
                LAUNCH_EDIT_URL.format(launch_id=scenario["id"]),
                timeout=args.timeout,
            )
            details_response.raise_for_status()
            details = details_response.json()
            details.pop("request_id", None)
            item["launch_targets"] = launch_targets(details, indexed_devices)
            item["launch_details"] = details
        result.append(item)

    print(json.dumps({"onetime_scenarios": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
