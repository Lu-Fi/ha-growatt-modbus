"""Checks for diag_tools against a simulated inverter (no Home Assistant needed).

Run: python3 -m unittest discover -s tests
"""
import asyncio
import importlib
import sys
import types
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "growatt_modbus_lufi"
pkg = types.ModuleType("gm")
pkg.__path__ = [str(PKG)]
sys.modules["gm"] = pkg
diag = importlib.import_module("gm.diag_tools")
registers = importlib.import_module("gm.registers")
GrowattModbusError = importlib.import_module("gm.modbus_client").GrowattModbusError


class FakeInverter:
    """Holding registers with optional quirks."""

    def __init__(self, single_ok=True, revert_after_s=None, bad=()):
        self.regs = {a: 0 for a in range(0, 1125)}
        self.regs[1100], self.regs[1101], self.regs[1102] = (8 << 8) | 0, (9 << 8) | 0, 1
        for i, ch in enumerate("ABCDE"):
            self.regs[23 + i] = ord(ch)
        self.single_ok = single_ok
        self.revert_after_s = revert_after_s
        self.bad = set(bad)
        self.now = 0.0
        self.pending = None  # (address, original, write time)
        self.log = []

    def _check(self, address, count):
        if any(a in self.bad for a in range(address, address + count)):
            raise GrowattModbusError(f"exception code 2 at {address}+{count}")

    async def read_registers(self, reg_type, address, count, unit):
        self._check(address, count)
        if self.pending and self.revert_after_s is not None:
            if self.now - self.pending[2] >= self.revert_after_s:
                for a, v in self.pending[1].items():
                    self.regs[a] = v
                self.pending = None
        return [self.regs.get(address + i, 0) for i in range(count)]

    async def write_register(self, address, value, unit):
        self.log.append(("single", address, value))
        if not self.single_ok:
            raise GrowattModbusError("exception code 4")
        self._write({address: value})

    async def write_registers(self, address, values, unit):
        self.log.append(("block", address, tuple(values)))
        self._write({address + i: v for i, v in enumerate(values)})

    def _write(self, mapping):
        original = {a: self.regs[a] for a in mapping}
        self.regs.update(mapping)
        self.pending = (None, original, self.now)


def run(coro):
    return asyncio.run(coro)


class DumpTests(unittest.TestCase):
    def test_bad_block_falls_back_per_register_and_redacts_serial(self):
        inv = FakeInverter(bad={1105})
        result = run(diag.dump_registers(inv, 1, registers.SPH_TL3_PROFILE))
        holding = result["holding"]
        self.assertEqual(holding["1101"], (9 << 8))
        self.assertTrue(str(holding["1105"]).startswith("error"))
        self.assertEqual(holding["24"], "redacted")
        self.assertEqual(holding["1102"], 1)
        self.assertIn("battery_first_1", result["time_windows"])

    def test_unreadable_range_stops_early(self):
        inv = FakeInverter(bad=range(1000, 1125))
        result = run(diag.dump_registers(inv, 1, registers.SPH_TL3_PROFILE))
        self.assertTrue(result["notes"])
        self.assertLess(len(result["holding"]), 125 + 125)


class WriteTestTests(unittest.TestCase):
    def _run(self, inv, method="both"):
        async def sleep(seconds):
            inv.now += seconds

        return run(diag.battery_first_write_test(
            inv, 1, registers.SPH_TL3_PROFILE, 1, method, sleep=sleep))

    def test_value_that_reverts_is_reported_and_original_restored(self):
        inv = FakeInverter(revert_after_s=30)
        original = [inv.regs[a] for a in (1100, 1101, 1102)]
        report = self._run(inv)
        self.assertEqual([inv.regs[a] for a in (1100, 1101, 1102)], original)
        self.assertTrue(report["final_restore"]["restored"])
        self.assertFalse(report["trials"][0]["held"])
        self.assertTrue(any("reverted later" in h for h in report["hints"]))

    def test_single_rejected_block_persists(self):
        inv = FakeInverter(single_ok=False)
        report = self._run(inv)
        self.assertIn("write_error", report["trials"][0])
        self.assertTrue(report["trials"][1]["held"])
        self.assertTrue(any("only the block write" in h for h in report["hints"]))
        self.assertTrue(report["final_restore"]["restored"])

    def test_enable_is_not_changed_by_block_write(self):
        inv = FakeInverter()
        self._run(inv, "block")
        block_writes = [e for e in inv.log if e[0] == "block"]
        self.assertEqual(block_writes[0][2][2], 1)


if __name__ == "__main__":
    unittest.main()
