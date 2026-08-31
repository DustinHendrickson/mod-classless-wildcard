#!/usr/bin/env bash
# Installs the mod-classless-wildcard client patch and addon.
# Usage: ./install.sh "/path/to/World of Warcraft"
set -e
cd "$(dirname "$0")"

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        exec "$candidate" install.py "$@"
    fi
done

echo "Python 3 is required and was not found. Install it and run this again." >&2
exit 1
