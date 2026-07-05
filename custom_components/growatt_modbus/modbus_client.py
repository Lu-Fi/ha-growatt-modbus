"""Async Modbus client wrapper (serial RTU and TCP) for Growatt inverters.

One client instance is shared per physical bus (serial port or TCP
endpoint), so several inverters (config entries with different slave IDs)
can safely talk over the same RS485 bus. All transactions are serialized
through an asyncio lock and separated by a small inter-frame delay.

The wrapper is compatible with pymodbus 3.x across the ``slave`` ->
``device_id`` keyword rename by inspecting the installed client signature.
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Minimum pause between two modbus transactions on the same bus (seconds).
INTER_FRAME_DELAY = 0.05


class GrowattModbusError(Exception):
    """Raised when a modbus transaction fails."""


class GrowattModbusClient:
    """Shared async modbus client for one physical bus."""

    def __init__(
        self,
        connection_type: str,
        *,
        serial_port: str | None = None,
        baudrate: int = 9600,
        host: str | None = None,
        port: int = 502,
        timeout: float = 5.0,
    ) -> None:
        self._connection_type = connection_type
        self._lock = asyncio.Lock()
        self._unit_kw: str | None = None

        if connection_type == "serial":
            self._client = AsyncModbusSerialClient(
                port=serial_port,
                baudrate=baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=timeout,
            )
        else:
            self._client = AsyncModbusTcpClient(
                host=host,
                port=port,
                timeout=timeout,
            )

    def _unit_kwargs(self, unit: int) -> dict[str, int]:
        """Build the unit/slave keyword for the installed pymodbus version."""
        if self._unit_kw is None:
            try:
                params = inspect.signature(
                    self._client.read_input_registers
                ).parameters
            except (TypeError, ValueError):
                params = {}
            for candidate in ("device_id", "slave", "unit"):
                if candidate in params:
                    self._unit_kw = candidate
                    break
            else:
                # Signature uses **kwargs; modern pymodbus expects device_id.
                self._unit_kw = "device_id"
            _LOGGER.debug("Using pymodbus unit keyword '%s'", self._unit_kw)
        return {self._unit_kw: unit}

    async def _ensure_connected(self) -> None:
        if self._client.connected:
            return
        connected = await self._client.connect()
        if not connected and not self._client.connected:
            raise GrowattModbusError(
                f"Cannot connect to modbus {self._connection_type} endpoint"
            )

    async def read_registers(
        self, register_type: str, address: int, count: int, unit: int
    ) -> list[int]:
        """Read a block of input or holding registers."""
        async with self._lock:
            await self._ensure_connected()
            try:
                if register_type == "input":
                    response = await self._client.read_input_registers(
                        address, count=count, **self._unit_kwargs(unit)
                    )
                else:
                    response = await self._client.read_holding_registers(
                        address, count=count, **self._unit_kwargs(unit)
                    )
            except Exception as err:  # noqa: BLE001 - pymodbus raises various types
                self._client.close()
                raise GrowattModbusError(
                    f"Read of {register_type} {address}+{count} failed: {err}"
                ) from err
            finally:
                await asyncio.sleep(INTER_FRAME_DELAY)
            if response.isError():
                raise GrowattModbusError(
                    f"Read of {register_type} {address}+{count} "
                    f"returned error: {response}"
                )
            return list(response.registers)

    async def write_register(self, address: int, value: int, unit: int) -> None:
        """Write a single holding register."""
        async with self._lock:
            await self._ensure_connected()
            try:
                response = await self._client.write_register(
                    address, value, **self._unit_kwargs(unit)
                )
            except Exception as err:  # noqa: BLE001
                self._client.close()
                raise GrowattModbusError(
                    f"Write of holding {address}={value} failed: {err}"
                ) from err
            finally:
                await asyncio.sleep(INTER_FRAME_DELAY)
            if response.isError():
                raise GrowattModbusError(
                    f"Write of holding {address}={value} returned error: {response}"
                )

    async def test_connection(self, unit: int) -> None:
        """Probe the inverter by reading input register 0 (status)."""
        await self.read_registers("input", 0, 1, unit)

    def close(self) -> None:
        """Close the underlying connection."""
        self._client.close()
