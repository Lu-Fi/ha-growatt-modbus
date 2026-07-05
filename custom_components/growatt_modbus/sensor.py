"""Sensor platform for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GrowattCoordinator
from .entity import GrowattEntity
from .registers import EnumDef, FaultDef, SensorDef

FAULT_STATES = ["ok", "warning", "fault"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all sensors of one inverter."""
    coordinator: GrowattCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        GrowattSensor(coordinator, defn) for defn in coordinator.profile.sensors
    ]
    entities.extend(
        GrowattEnumSensor(coordinator, defn) for defn in coordinator.profile.enums
    )
    entities.extend(
        GrowattFaultSensor(coordinator, defn) for defn in coordinator.profile.faults
    )
    async_add_entities(entities)


class GrowattSensor(GrowattEntity, SensorEntity):
    """Numeric sensor backed by one or two modbus registers."""

    def __init__(self, coordinator: GrowattCoordinator, defn: SensorDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        self._attr_native_unit_of_measurement = defn.unit
        if defn.device_class:
            self._attr_device_class = SensorDeviceClass(defn.device_class)
        if defn.state_class:
            self._attr_state_class = SensorStateClass(defn.state_class)
        if defn.precision is not None:
            self._attr_suggested_display_precision = defn.precision
        if defn.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = defn.enabled_default

    @property
    def native_value(self) -> float | int | None:
        return self.coordinator.sensor_value(self._defn)


class GrowattEnumSensor(GrowattEntity, SensorEntity):
    """Sensor with translated enum states (status, mode, ...)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: GrowattCoordinator, defn: EnumDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn
        # Preserve definition order, drop duplicates (e.g. repeated "normal").
        self._attr_options = list(dict.fromkeys(defn.options.values()))

    @property
    def native_value(self) -> str | None:
        return self.coordinator.enum_value(self._defn)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {
            "raw_value": self.coordinator.raw_value(
                self._defn.register_type, self._defn.address
            )
        }


class GrowattFaultSensor(GrowattEntity, SensorEntity):
    """Decoded fault/warning bitfield register."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = FAULT_STATES

    def __init__(self, coordinator: GrowattCoordinator, defn: FaultDef) -> None:
        super().__init__(coordinator, defn.key)
        self._defn = defn

    @property
    def native_value(self) -> str | None:
        return self.coordinator.fault_state(self._defn)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "raw_value": self.coordinator.raw_value("input", self._defn.address),
            "active_faults": self.coordinator.fault_bits(self._defn) or [],
        }
