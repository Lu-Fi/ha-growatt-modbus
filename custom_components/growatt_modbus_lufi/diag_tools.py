"""Register dump and Battery First write test for support requests.

Home Assistant independent: both functions only need a client with
``read_registers``, ``write_register`` and ``write_registers``.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .modbus_client import GrowattModbusError
from .registers import REG_HOLDING, REG_INPUT, DeviceProfile, TimeWindowDef

# (first address, count) of the ranges the SPH register map defines.
HOLDING_RANGES = ((0, 125), (1000, 125))
INPUT_RANGES = ((0, 125), (1000, 125), (1125, 125))
CHUNK = 10
# A gap longer than this many failing blocks in a row ends the range early.
MAX_FAILED_CHUNKS = 6

# Seconds after the write at which the value is read back.
SETTLE_POINTS = (0, 5, 60)
TEST_TIMES = ((21, 30, 22, 30), (21, 31, 22, 31))

Sleep = Callable[[float], Awaitable[None]]


def _decode_time(raw: int | None) -> str | None:
    if raw is None:
        return None
    hour, minute = (raw >> 8) & 0xFF, raw & 0xFF
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


async def _read_block(
    client: Any, reg_type: str, start: int, count: int, unit: int
) -> tuple[dict[int, int | str], int]:
    """Read one chunk; fall back to single registers so one bad address
    does not hide its neighbours. Returns (values, failed register count)."""
    try:
        block = await client.read_registers(reg_type, start, count, unit)
    except GrowattModbusError:
        pass
    else:
        return {start + i: value for i, value in enumerate(block)}, 0

    values: dict[int, int | str] = {}
    failed = 0
    for address in range(start, start + count):
        try:
            values[address] = (
                await client.read_registers(reg_type, address, 1, unit)
            )[0]
        except GrowattModbusError as err:
            values[address] = f"error: {err}"
            failed += 1
    return values, failed


async def dump_registers(
    client: Any,
    unit: int,
    profile: DeviceProfile,
    include_input: bool = False,
) -> dict[str, Any]:
    """Read the holding (and optionally input) register ranges raw."""
    redact: set[int] = set()
    if profile.serial_registers is not None:
        first, count = profile.serial_registers
        redact.update(range(first, first + count))

    plan = [(REG_HOLDING, rng) for rng in HOLDING_RANGES]
    if include_input:
        plan += [(REG_INPUT, rng) for rng in INPUT_RANGES]

    result: dict[str, Any] = {REG_HOLDING: {}, REG_INPUT: {}, "notes": []}
    for reg_type, (first, count) in plan:
        target = result[reg_type]
        failed_chunks = 0
        for chunk in range(first, first + count, CHUNK):
            size = min(CHUNK, first + count - chunk)
            values, failed = await _read_block(client, reg_type, chunk, size, unit)
            for address, value in values.items():
                target[str(address)] = (
                    "redacted" if address in redact and isinstance(value, int) else value
                )
            failed_chunks = failed_chunks + 1 if failed == size else 0
            if failed_chunks >= MAX_FAILED_CHUNKS:
                result["notes"].append(
                    f"{reg_type} {first}-{first + count - 1}: stopped at "
                    f"{chunk + size - 1} after {MAX_FAILED_CHUNKS} unreadable blocks"
                )
                break

    result["time_windows"] = {}
    for window in profile.time_windows:
        raw = {
            "start": result[REG_HOLDING].get(str(window.start_address)),
            "stop": result[REG_HOLDING].get(str(window.stop_address)),
            "enable": result[REG_HOLDING].get(str(window.stop_address + 1)),
        }
        result["time_windows"][window.key] = {
            **raw,
            "start_decoded": _decode_time(raw["start"]) if isinstance(raw["start"], int) else None,
            "stop_decoded": _decode_time(raw["stop"]) if isinstance(raw["stop"], int) else None,
        }
    return result


def _find_window(profile: DeviceProfile, window_index: int) -> TimeWindowDef:
    key = f"battery_first_{window_index}"
    for window in profile.time_windows:
        if window.key == key:
            return window
    raise ValueError(f"profile {profile.key} has no time window {key}")


async def _read_triple(
    client: Any, window: TimeWindowDef, unit: int
) -> list[int] | None:
    try:
        return await client.read_registers(
            REG_HOLDING, window.start_address, 3, unit
        )
    except GrowattModbusError:
        return None


async def _restore(
    client: Any, window: TimeWindowDef, unit: int, original: list[int]
) -> dict[str, Any]:
    """Put the original start/stop/enable back; block write first."""
    info: dict[str, Any] = {"errors": []}
    try:
        await client.write_registers(window.start_address, list(original), unit)
    except GrowattModbusError as err:
        info["errors"].append(f"block write: {err}")
        for offset, value in enumerate(original):
            try:
                await client.write_register(window.start_address + offset, value, unit)
            except GrowattModbusError as err2:
                info["errors"].append(f"single write +{offset}: {err2}")
    after = await _read_triple(client, window, unit)
    info["read_back"] = after
    info["restored"] = after == original
    return info


async def battery_first_write_test(
    client: Any,
    unit: int,
    profile: DeviceProfile,
    window_index: int = 1,
    method: str = "both",
    sleep: Sleep = asyncio.sleep,
    settle_points: tuple[int, ...] = SETTLE_POINTS,
) -> dict[str, Any]:
    """Write a test window with single and/or block writes and watch
    whether the inverter keeps it. Always restores the original values."""
    window = _find_window(profile, window_index)
    enable_address = window.stop_address + 1
    if window.start_address + 2 != enable_address:
        raise ValueError("start/stop/enable registers are not contiguous")

    original = await _read_triple(client, window, unit)
    if original is None:
        raise GrowattModbusError("Cannot read the current Battery First window")

    start_h, start_m, stop_h, stop_m = next(
        t for t in TEST_TIMES
        if [(t[0] << 8) | t[1], (t[2] << 8) | t[3]] != original[:2]
    )
    new_start = (start_h << 8) | start_m
    new_stop = (stop_h << 8) | stop_m

    methods = ["single", "block"] if method == "both" else [method]
    report: dict[str, Any] = {
        "window": window.key,
        "addresses": {
            "start": window.start_address,
            "stop": window.stop_address,
            "enable": enable_address,
        },
        "original": {
            "start": original[0], "stop": original[1], "enable": original[2],
            "start_decoded": _decode_time(original[0]),
            "stop_decoded": _decode_time(original[1]),
        },
        "test_values": {
            "start": new_start, "stop": new_stop,
            "start_decoded": _decode_time(new_start),
            "stop_decoded": _decode_time(new_stop),
        },
        "trials": [],
    }

    try:
        for index, name in enumerate(methods):
            trial: dict[str, Any] = {"method": name, "read_backs": []}
            try:
                if name == "single":
                    await client.write_register(window.start_address, new_start, unit)
                    await client.write_register(window.stop_address, new_stop, unit)
                else:
                    await client.write_registers(
                        window.start_address, [new_start, new_stop, original[2]], unit
                    )
            except GrowattModbusError as err:
                trial["write_error"] = str(err)
            else:
                elapsed = 0
                for point in settle_points:
                    await sleep(point - elapsed)
                    elapsed = point
                    values = await _read_triple(client, window, unit)
                    trial["read_backs"].append({
                        "after_s": point,
                        "values": values,
                        "matches": values is not None
                        and values[:2] == [new_start, new_stop],
                    })
                trial["held"] = all(rb["matches"] for rb in trial["read_backs"])
            report["trials"].append(trial)
            if index < len(methods) - 1:
                report["trials"][-1]["restore"] = await _restore(
                    client, window, unit, original
                )
                await sleep(5)
    finally:
        report["final_restore"] = await _restore(client, window, unit, original)

    report["hints"] = _hints(report["trials"])
    return report


def _hints(trials: list[dict[str, Any]]) -> list[str]:
    by_method = {t["method"]: t for t in trials}
    hints: list[str] = []
    for name, trial in by_method.items():
        if "write_error" in trial:
            hints.append(f"{name} write was rejected: {trial['write_error']}")
        elif trial.get("held"):
            hints.append(f"{name} write was kept for the whole observation")
        else:
            first = trial["read_backs"][0] if trial["read_backs"] else None
            if first and first["matches"]:
                hints.append(f"{name} write was accepted but reverted later")
            else:
                hints.append(f"{name} write was accepted but never read back")
    if len(by_method) == 2:
        single, block = by_method["single"], by_method["block"]
        if block.get("held") and not single.get("held"):
            hints.append("only the block write (function 16) persists")
        elif not block.get("held") and not single.get("held"):
            hints.append("neither method persists - check cloud/app schedules")
    return hints
