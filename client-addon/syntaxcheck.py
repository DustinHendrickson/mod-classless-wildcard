#!/usr/bin/env python3
"""Syntax-check the addon's Lua against the interpreter the game actually runs.

WoW 3.3.5a embeds Lua 5.1. Checking against anything newer is worse than not
checking: 5.2+ accept syntax 5.1 rejects (goto, integer division, \\z escapes),
so a file could pass here and still error out on login.

This only COMPILES the chunk. Nothing is executed, so the WoW API being absent
does not matter -- undefined globals are a runtime concern, not a syntax one.

Run:  python3 syntaxcheck.py            (checks every .lua beside this script)
      python3 syntaxcheck.py FILE ...   (checks the files named)

Needs lupa:  python3 -m pip install --user lupa
"""
import glob
import os
import sys

try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    sys.exit("lupa with Lua 5.1 is required: python3 -m pip install --user lupa")

HERE = os.path.dirname(os.path.abspath(__file__))


def check(path):
    """Return None if the chunk compiles, else the Lua error string."""
    with open(path, "rb") as fh:
        source = fh.read()
    rt = LuaRuntime(unpack_returned_tuples=True)
    # loadstring compiles without running, returning nil plus a message on a
    # syntax error. Wrapping it Lua-side keeps the arity fixed at two, since a
    # successful call otherwise returns the chunk alone and unpacking breaks.
    compile_chunk = rt.eval("""
        function(src, name)
            local chunk, err = loadstring(src, name)
            if chunk then return true, "" end
            return false, tostring(err)
        end
    """)
    ok, err = compile_chunk(source, "@" + os.path.basename(path))
    return None if ok else (err or "unknown compile error")


def main(argv):
    targets = argv[1:] or sorted(
        glob.glob(os.path.join(HERE, "**", "*.lua"), recursive=True))
    if not targets:
        sys.exit("no .lua files found")

    failed = 0
    for path in targets:
        err = check(path)
        try:
            name = os.path.relpath(path, HERE)
        except ValueError:  # different drive on Windows
            name = path
        if err:
            failed += 1
            print("FAIL  %s\n      %s" % (name, err))
        else:
            lines = sum(1 for _ in open(path, "rb"))
            print("ok    %s  (%d lines, Lua 5.1)" % (name, lines))

    print()
    if failed:
        print("%d of %d file(s) failed to compile" % (failed, len(targets)))
        return 1
    print("all %d file(s) compile under Lua 5.1" % len(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
