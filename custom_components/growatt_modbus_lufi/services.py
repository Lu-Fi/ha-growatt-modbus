"""Support services: raw register dump and a user-triggered write test."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from . import diag_tools
from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .modbus_client import GrowattModbusError

_LOGGER = logging.getLogger(__name__)

SERVICE_DUMP = "dump_registers"
SERVICE_WRITE_TEST = "battery_first_write_test"

ATTR_ENTRY = "config_entry_id"
ATTR_INCLUDE_INPUT = "include_input"
ATTR_WINDOW = "window"
ATTR_METHOD = "method"
ATTR_CONFIRM = "confirm"

DUMP_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional(ATTR_INCLUDE_INPUT, default=False): cv.boolean,
    }
)
WRITE_TEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional(ATTR_WINDOW, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=3)
        ),
        vol.Optional(ATTR_METHOD, default="both"): vol.In(
            ["single", "block", "both"]
        ),
        vol.Required(ATTR_CONFIRM): cv.boolean,
    }
)

WRITE_TEST_WARNING = (
    "This test WRITES to the inverter: it temporarily changes the Battery "
    "First time window, then restores the original values. While it runs "
    "(about 2.5 minutes) do not change any inverter settings. Confirm to "
    "continue."
)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> GrowattCoordinator:
    found = {
        key: value
        for key, value in hass.data.get(DOMAIN, {}).items()
        if isinstance(value, GrowattCoordinator)
    }
    entry_id = call.data.get(ATTR_ENTRY)
    if entry_id:
        if entry_id not in found:
            raise ServiceValidationError(f"Unknown config entry {entry_id}")
        return found[entry_id]
    if len(found) == 1:
        return next(iter(found.values()))
    raise ServiceValidationError(
        f"{len(found)} inverters are configured, pass {ATTR_ENTRY}"
    )


async def _save(hass: HomeAssistant, kind: str, payload: dict[str, Any]) -> str:
    stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
    path = Path(hass.config.path(f"growatt_modbus_lufi_{kind}_{stamp}.json"))
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    await hass.async_add_executor_job(path.write_text, text, "utf-8")
    return path.name


def _meta(coordinator: GrowattCoordinator) -> dict[str, Any]:
    return {
        "profile": coordinator.profile.key,
        "slave_id": coordinator.slave_id,
        "firmware": coordinator.firmware_version(),
        "generated": dt_util.now().isoformat(),
    }


async def _handle_dump(hass: HomeAssistant, call: ServiceCall) -> dict[str, Any]:
    coordinator = _coordinator(hass, call)
    result = await diag_tools.dump_registers(
        coordinator.client,
        coordinator.slave_id,
        coordinator.profile,
        call.data[ATTR_INCLUDE_INPUT],
    )
    payload = {**_meta(coordinator), **result}
    filename = await _save(hass, "dump", payload)
    windows = "\n".join(
        f"- {key}: {w['start_decoded']} - {w['stop_decoded']}, enable {w['enable']}"
        for key, w in result["time_windows"].items()
    )
    persistent_notification.async_create(
        hass,
        f"Register dump written to `{filename}` in the Home Assistant config "
        f"folder. Please attach it to the GitHub issue.\n\n{windows}",
        title="Growatt register dump",
        notification_id=f"{DOMAIN}_dump",
    )
    return payload


async def _handle_write_test(
    hass: HomeAssistant, call: ServiceCall
) -> dict[str, Any]:
    if call.data[ATTR_CONFIRM] is not True:
        raise ServiceValidationError(WRITE_TEST_WARNING)
    coordinator = _coordinator(hass, call)
    persistent_notification.async_create(
        hass,
        "Write test running. Do not change any inverter settings for the "
        "next ~3 minutes. The original values are restored at the end.",
        title="Growatt write test",
        notification_id=f"{DOMAIN}_write_test",
    )
    try:
        result = await diag_tools.battery_first_write_test(
            coordinator.client,
            coordinator.slave_id,
            coordinator.profile,
            call.data[ATTR_WINDOW],
            call.data[ATTR_METHOD],
        )
    except (GrowattModbusError, ValueError) as err:
        persistent_notification.async_dismiss(hass, f"{DOMAIN}_write_test")
        raise HomeAssistantError(f"Write test failed: {err}") from err
    finally:
        await coordinator.async_refresh_settings()

    payload = {**_meta(coordinator), **result}
    filename = await _save(hass, "write_test", payload)
    restored = result["final_restore"]["restored"]
    lines = "\n".join(f"- {hint}" for hint in result["hints"])
    persistent_notification.async_create(
        hass,
        f"Write test finished, report in `{filename}` (config folder). "
        f"Original values restored: {'yes' if restored else 'NO - check the Battery First window'}.\n\n"
        f"{lines}\n\nPlease attach the file to the GitHub issue.",
        title="Growatt write test",
        notification_id=f"{DOMAIN}_write_test",
    )
    return payload


def async_register_services(hass: HomeAssistant) -> None:
    """Register the support services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_DUMP):
        return

    async def dump(call: ServiceCall) -> dict[str, Any]:
        return await _handle_dump(hass, call)

    async def write_test(call: ServiceCall) -> dict[str, Any]:
        return await _handle_write_test(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_DUMP, dump, schema=DUMP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_WRITE_TEST, write_test, schema=WRITE_TEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def async_remove_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_DUMP)
    hass.services.async_remove(DOMAIN, SERVICE_WRITE_TEST)
