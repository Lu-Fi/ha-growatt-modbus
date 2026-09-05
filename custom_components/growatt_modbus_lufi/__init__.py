"""The Growatt Modbus integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PROFILE,
    CONF_SERIAL_PORT,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    DATA_CLIENTS,
    DEFAULT_BAUDRATE,
    DEFAULT_PROFILE,
    DEFAULT_TCP_PORT,
    DOMAIN,
    PLATFORMS,
    bus_key,
)
from .coordinator import GrowattCoordinator
from .modbus_client import GrowattModbusClient
from .registers import PROFILES

_LOGGER = logging.getLogger(__name__)


def _get_or_create_client(
    hass: HomeAssistant, entry: ConfigEntry
) -> GrowattModbusClient:
    """Return the shared client for the entry's bus (create if needed)."""
    clients: dict[str, list] = hass.data.setdefault(DOMAIN, {}).setdefault(
        DATA_CLIENTS, {}
    )
    key = bus_key(entry.data)
    if key in clients:
        clients[key][1] += 1
        return clients[key][0]

    if entry.data[CONF_CONNECTION_TYPE] == CONNECTION_SERIAL:
        client = GrowattModbusClient(
            CONNECTION_SERIAL,
            serial_port=entry.data[CONF_SERIAL_PORT],
            baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        )
    else:
        client = GrowattModbusClient(
            CONNECTION_TCP,
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, DEFAULT_TCP_PORT),
        )
    clients[key] = [client, 1]
    return client


def _release_client(hass: HomeAssistant, entry: ConfigEntry) -> None:
    clients: dict[str, list] = hass.data.get(DOMAIN, {}).get(DATA_CLIENTS, {})
    key = bus_key(entry.data)
    if key not in clients:
        return
    clients[key][1] -= 1
    if clients[key][1] <= 0:
        clients[key][0].close()
        del clients[key]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Growatt inverter from a config entry."""
    profile_key = entry.data.get(CONF_PROFILE, DEFAULT_PROFILE)
    profile = PROFILES.get(profile_key)
    if profile is None:
        _LOGGER.error("Unknown device profile: %s", profile_key)
        return False

    client = _get_or_create_client(hass, entry)
    coordinator = GrowattCoordinator(hass, entry, client, profile)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        _release_client(hass, entry)
        raise

    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        # Without this the client's reference count stays elevated and the
        # shared bus client is never closed on the final unload.
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _release_client(hass, entry)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _release_client(hass, entry)
    return unload_ok
