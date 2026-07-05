"""Base entity for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import GrowattCoordinator


class GrowattEntity(CoordinatorEntity[GrowattCoordinator]):
    """Common base: device info, unique_id, translated names."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GrowattCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=coordinator.profile.name,
            sw_version=coordinator.firmware_version(),
        )
