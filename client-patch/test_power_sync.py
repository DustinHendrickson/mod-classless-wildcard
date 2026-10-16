"""Runs the rewritten power-update guard (exepatch.CLASS_GATES, power sync) on
the CPU, from a patched copy of the client's own bytes.

UnitPowerUpdateHandler (0x7234D0) decides whether a server power value replaces
the client's prediction. After the patch, the block at 0x72354A must:
  - take any server value above the prediction (jump to 0x723577, the store);
  - keep the prediction for health (type -2) and for the pool on the main bar
    (jump to 0x7235A9, the return);
  - take the server's value for every other pool, even when it is lower.

Usage: python test_power_sync.py "C:/path/to/World of Warcraft"
Needs unicorn (python -m pip install --user unicorn).
"""

import os
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EIP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import exepatch  # noqa: E402

START, TAKE, KEEP = 0x72354A, 0x723577, 0x7235A9
TEXT_VA, TEXT_DELTA = 0x401000, 0x400C00
UNIT, DESC, CVAR = 0x00200000, 0x00300000, 0x00400000

FAILURES = []


def check(label, ok, detail=""):
    print("  [%s] %s%s" % ("ok  " if ok else "FAIL", label, (" -- " + detail) if detail else ""))
    if not ok:
        FAILURES.append(label)


def run(code_page, power_type, server, predicted, display):
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    page = START & ~0xFFF
    mu.mem_map(page, 0x2000)
    mu.mem_write(page, code_page)
    mu.mem_map(UNIT, 0x2000)
    mu.mem_map(DESC, 0x1000)
    mu.mem_write(UNIT + 0xD0, DESC.to_bytes(4, "little"))
    if power_type >= 0:
        mu.mem_write(UNIT + 0xFB4 + power_type * 4, (predicted & 0xFFFFFFFF).to_bytes(4, "little"))
    else:
        mu.mem_write(UNIT + 0xFB4 - 8, (predicted & 0xFFFFFFFF).to_bytes(4, "little"))
    mu.mem_write(DESC + 0x47, bytes([display]))
    # the stock block re-reads the predictedPower cvar through edx (loaded
    # just before it at 0x723544); the patched one never touches it
    mu.mem_map(CVAR, 0x1000)
    mu.mem_write(CVAR + 0x30, (1).to_bytes(4, "little"))
    mu.reg_write(UC_X86_REG_EDX, CVAR)
    mu.reg_write(UC_X86_REG_ECX, server & 0xFFFFFFFF)
    mu.reg_write(UC_X86_REG_ESI, power_type & 0xFFFFFFFF)
    mu.reg_write(UC_X86_REG_EDI, UNIT)
    landed = []

    def hook(uc, address, size, _):
        if address in (TAKE, KEEP):
            landed.append(address)
            uc.emu_stop()

    mu.hook_add(UC_HOOK_CODE, hook)
    mu.emu_start(START, page + 0x2000, count=64)
    return landed[0] if landed else mu.reg_read(UC_X86_REG_EIP)


def main():
    wow = sys.argv[1] if len(sys.argv) > 1 else r"B:\World.of.Warcraft.3.3.5a"
    exe = os.path.join(wow, "Wow.exe")
    src = exepatch.backup_path(exe) if os.path.isfile(exepatch.backup_path(exe)) else exe
    data = bytearray(open(src, "rb").read())
    state = exepatch._group_state(data, exepatch.CLASS_GATES)
    check("the class-check group fits this client", state in ("apply", "done"), state)
    if state == "apply":
        exepatch._group_write(data, exepatch.CLASS_GATES, patched=True)
    page = START & ~0xFFF
    code_page = bytes(data[page - TEXT_DELTA:page - TEXT_DELTA + 0x2000])

    MANA, RAGE, ENERGY, RUNIC, HEALTH = 0, 1, 3, 6, -2
    cases = [
        # (what, type, server, predicted, bar, expected)
        ("a higher server value always lands", RAGE, 500, 200, MANA, TAKE),
        ("rage off the bar takes a LOWER server value", RAGE, 0, 400, MANA, TAKE),
        ("runic power off the bar takes a lower server value", RUNIC, 100, 800, ENERGY, TAKE),
        ("energy off the bar takes a lower server value", ENERGY, 40, 60, MANA, TAKE),
        ("mana off the bar takes a lower server value", MANA, 900, 1000, RAGE, TAKE),
        ("the bar's own pool keeps its prediction (mana)", MANA, 900, 1000, MANA, KEEP),
        ("the bar's own pool keeps its prediction (rage)", RAGE, 0, 400, RAGE, KEEP),
        ("an equal value on the bar is kept, as stock", ENERGY, 60, 60, ENERGY, KEEP),
        ("health keeps its prediction", HEALTH, 100, 200, MANA, KEEP),
    ]
    for what, ptype, server, predicted, bar, want in cases:
        got = run(code_page, ptype, server, predicted, bar)
        check(what, got == want, "landed at %#x, wanted %#x" % (got, want))

    # falsify: the stock bytes keep EVERY lower value, which is the bug
    stock_page = bytes(open(src, "rb").read()[page - TEXT_DELTA:page - TEXT_DELTA + 0x2000]) \
        if state == "apply" else None
    if stock_page:
        got = run(stock_page, RAGE, 0, 400, MANA)
        check("the stock bytes drop the lower rage value (the bug this fixes)", got == KEEP,
              "landed at %#x" % got)

    if FAILURES:
        print("\nFAILED: " + ", ".join(FAILURES))
        return 1
    print("\nall power sync checks pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
