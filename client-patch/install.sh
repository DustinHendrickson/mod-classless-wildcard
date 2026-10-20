#!/usr/bin/env bash
# Installs the mod-classless-wildcard client patch and addon.
# Usage: ./install.sh ["/path/to/World of Warcraft"] [options]
set -e
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys; sys.exit(sys.version_info[0] != 3)' >/dev/null 2>&1; then
        PYTHON="$candidate"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Python 3 is required and was not found. Install it and run this again." >&2
    exit 1
fi

# The install paints icons, which needs Pillow. Homebrew's Python refuses
# `pip install --user` (it is "externally managed"), so when that fails a
# private Python is set up in .venv beside this script and used from then on.
if [ -x .venv/bin/python ] && .venv/bin/python -c "import PIL" >/dev/null 2>&1; then
    PYTHON=.venv/bin/python
elif ! "$PYTHON" -c "import PIL" >/dev/null 2>&1; then
    echo "Installing the Python library Pillow (needed to paint the icons)..."
    if ! "$PYTHON" -m pip install --user pillow || ! "$PYTHON" -c "import PIL" >/dev/null 2>&1; then
        echo "Setting up a Python of its own in client-patch/.venv for it instead..."
        "$PYTHON" -m venv .venv
        .venv/bin/python -m pip install pillow
        PYTHON=.venv/bin/python
    fi
fi

exec "$PYTHON" install.py "$@"
