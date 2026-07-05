"""Binary sensor platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the fault binary sensor."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.profile.faults:
        async_add_entities([GrowattAnyFaultSensor(coordinator)])


class GrowattAnyFaultSensor(GrowattEntity, BinarySensorEntity):
    """On when any fault register reports a non-zero value."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: GrowattCoordinator) -> None:
        super().__init__(coordinator, "any_fault")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.any_fault()
