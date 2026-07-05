"""Diagnostics support for the Growatt Modbus integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_SERIAL_PORT, DOMAIN
from .coordinator import GrowattCoordinator

TO_REDACT = {CONF_HOST, CONF_SERIAL_PORT}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "profile": coordinator.profile.key,
        "read_blocks": coordinator.profile.read_blocks(),
        "registers": {
            reg_type: {str(addr): value for addr, value in regs.items()}
            for reg_type, regs in (coordinator.data or {}).items()
        },
    }
