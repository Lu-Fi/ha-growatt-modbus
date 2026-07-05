"""Constants for the Growatt Modbus integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "growatt_modbus"

MANUFACTURER = "Growatt"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Config entry keys
CONF_CONNECTION_TYPE = "connection_type"
CONNECTION_SERIAL = "serial"
CONNECTION_TCP = "tcp"

CONF_SERIAL_PORT = "serial_port"
CONF_BAUDRATE = "baudrate"
CONF_SLAVE_ID = "slave_id"
CONF_PROFILE = "profile"

# Options
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_BAUDRATE = 9600
DEFAULT_TCP_PORT = 502
DEFAULT_SLAVE_ID = 1
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_PROFILE = "sph"
PROFILE_AUTO = "auto"

BAUDRATES = [9600, 19200, 38400, 57600, 115200]

# Internal storage key for shared modbus clients (one per physical bus)
DATA_CLIENTS = "_clients"
