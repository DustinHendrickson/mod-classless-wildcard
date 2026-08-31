#!/usr/bin/env python3
r"""Standalone control over the Wow.exe custom-glue patch.

install.py already does this as part of a normal install; this exists for
troubleshooting, and for putting the exe back without touching anything else.

    python3 patch_client_exe.py --status  "C:\WoW\Wow.exe"
    python3 patch_client_exe.py           "C:\WoW\Wow.exe"
    python3 patch_client_exe.py --restore "C:\WoW\Wow.exe"
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import exepatch  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("exe", help="path to Wow.exe")
    parser.add_argument("--status", action="store_true", help="report and exit")
    parser.add_argument("--restore", action="store_true", help="undo the patch")
    args = parser.parse_args()

    if not os.path.isfile(args.exe):
        print("not found: %s" % args.exe, file=sys.stderr)
        return 1

    state, offset, digest, label = exepatch.inspect(args.exe)
    print("SHA-256 : %s" % digest)
    print("build   : %s" % (label or "unrecognised"))
    print("state   : %s%s" % (state, "" if offset is None else
                              " (patch site at 0x%X)" % offset))

    if args.status:
        return 0
    try:
        print(exepatch.restore(args.exe) if args.restore
              else exepatch.apply(args.exe))
    except RuntimeError as error:
        print("\n%s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
