"""Config flow for the Growatt Modbus integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PROFILE,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ID,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    DEFAULT_BAUDRATE,
    DEFAULT_PROFILE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DEFAULT_TCP_PORT,
    DOMAIN,
    PROFILE_AUTO,
)
from .modbus_client import GrowattModbusClient, GrowattModbusError
from .registers import (
    PROFILES,
    REG_DEVICE_TYPE_CODE,
    parse_tracker_phase,
    profile_for_phase_count,
)

_LOGGER = logging.getLogger(__name__)


def _profile_schema() -> vol.In:
    choices = {PROFILE_AUTO: "Automatisch erkennen / Auto detect"}
    choices.update({key: profile.name for key, profile in PROFILES.items()})
    return vol.In(choices)


async def _validate_connection(data: dict[str, Any]) -> tuple[str | None, str]:
    """Try to reach the inverter.

    Returns (error_key, resolved_profile). When the profile is set to
    "auto", the inverter type is detected from holding registers 43/44
    (device type code + tracker/phase count).
    """
    if data[CONF_CONNECTION_TYPE] == CONNECTION_SERIAL:
        client = GrowattModbusClient(
            CONNECTION_SERIAL,
            serial_port=data[CONF_SERIAL_PORT],
            baudrate=data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        )
    else:
        client = GrowattModbusClient(
            CONNECTION_TCP,
            host=data[CONF_HOST],
            port=data.get(CONF_PORT, DEFAULT_TCP_PORT),
        )
    profile = data.get(CONF_PROFILE, PROFILE_AUTO)
    try:
        await client.test_connection(data[CONF_SLAVE_ID])
        if profile == PROFILE_AUTO:
            profile = DEFAULT_PROFILE
            try:
                regs = await client.read_registers(
                    "holding", REG_DEVICE_TYPE_CODE, 2, data[CONF_SLAVE_ID]
                )
                trackers, phases = parse_tracker_phase(regs[1])
                profile = profile_for_phase_count(phases)
                _LOGGER.info(
                    "Detected Growatt inverter: DTC=%s, %s tracker(s), "
                    "%s phase(s) -> profile '%s'",
                    regs[0],
                    trackers,
                    phases,
                    profile,
                )
            except GrowattModbusError as err:
                _LOGGER.warning(
                    "Auto detection failed (%s), falling back to profile '%s'",
                    err,
                    profile,
                )
    except GrowattModbusError as err:
        _LOGGER.warning("Connection test failed: %s", err)
        return "cannot_connect", profile
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error during connection test")
        return "unknown", profile
    finally:
        client.close()
    return None, profile


class GrowattModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow (one entry per inverter)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the connection type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[CONNECTION_SERIAL, CONNECTION_TCP],
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a serial RTU connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_SERIAL,
                CONF_SERIAL_PORT: user_input[CONF_SERIAL_PORT].strip(),
                CONF_BAUDRATE: user_input[CONF_BAUDRATE],
                CONF_SLAVE_ID: user_input[CONF_SLAVE_ID],
                CONF_PROFILE: user_input[CONF_PROFILE],
            }
            unique_id = f"serial-{data[CONF_SERIAL_PORT]}-{data[CONF_SLAVE_ID]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            error, resolved_profile = await _validate_connection(data)
            if error is None:
                data[CONF_PROFILE] = resolved_profile
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=data
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Growatt SPH"): str,
                vol.Required(
                    CONF_SERIAL_PORT, default="/dev/ttyUSB0"
                ): str,
                vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(
                    BAUDRATES
                ),
                vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=247)
                ),
                vol.Required(CONF_PROFILE, default=PROFILE_AUTO): _profile_schema(),
            }
        )
        return self.async_show_form(
            step_id="serial", data_schema=schema, errors=errors
        )

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a Modbus TCP connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_TCP,
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_PORT: user_input[CONF_PORT],
                CONF_SLAVE_ID: user_input[CONF_SLAVE_ID],
                CONF_PROFILE: user_input[CONF_PROFILE],
            }
            unique_id = (
                f"tcp-{data[CONF_HOST]}-{data[CONF_PORT]}-{data[CONF_SLAVE_ID]}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            error, resolved_profile = await _validate_connection(data)
            if error is None:
                data[CONF_PROFILE] = resolved_profile
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=data
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Growatt SPH"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_TCP_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=247)
                ),
                vol.Required(CONF_PROFILE, default=PROFILE_AUTO): _profile_schema(),
            }
        )
        return self.async_show_form(step_id="tcp", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GrowattOptionsFlow:
        """Return the options flow."""
        return GrowattOptionsFlow()


class GrowattOptionsFlow(OptionsFlow):
    """Handle options (polling interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
