#!/usr/bin/env bash
# Fetches the latest client patch and addon from GitHub into this folder and
# client-addon beside it. Run ./install.sh afterwards.
set -e
cd "$(dirname "$0")"

# update.py cannot rewrite this file while the shell is reading it, so a
# newer copy is left beside it as update.sh.new. Swap it in and start over.
if [ -f update.sh.new ]; then
    mv -f update.sh.new update.sh
    chmod +x update.sh
    exec ./update.sh "$@"
fi

for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        exec "$candidate" update.py "$@"
    fi
done

echo "Python 3 is required and was not found. Install it and run this again." >&2
exit 1
