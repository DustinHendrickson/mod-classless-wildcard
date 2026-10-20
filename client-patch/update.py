#!/usr/bin/env python3
"""Fetch the latest client patch and addon from GitHub, in place.

Run it from the client-patch folder players are given, with client-addon
beside it. It downloads the repository's main branch, replaces client-patch/
and client-addon/ClasslessWildcard/ with the copies in it, and writes down
which commit it installed. Then run install.bat (or ./install.sh) as usual.

What it leaves alone:

  * install_path.txt, the WoW folder install.bat remembered
  * anything the installer built here (out/, mpqtool, StormLib, *.MPQ)
  * update.bat and update.sh themselves. A script cannot safely rewrite the
    file the shell is still reading, so a changed wrapper is written as
    update.bat.new / update.sh.new and the wrapper swaps it in when it next
    starts.

Files this script put here on an earlier run and that the repository no
longer has are removed, so a renamed manifest does not linger. Files it never
touched are never removed.

Requires Python 3.7+ and an internet connection. No other packages.

  --check    say whether an update is available and stop
  --force    download and reinstall even when already on the latest commit
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

REPO = "DustinHendrickson/mod-classless-wildcard"
BRANCH = "main"
ZIP_URL = "https://codeload.github.com/%s/zip/refs/heads/%s" % (REPO, BRANCH)
API_URL = "https://api.github.com/repos/%s/commits/%s" % (REPO, BRANCH)
USER_AGENT = "ClasslessWildcard-updater"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADDON_NAME = "ClasslessWildcard"

# repository folder -> where it lands on this PC
TARGETS = {
    "client-patch": HERE,
    "client-addon/" + ADDON_NAME: os.path.join(ROOT, "client-addon", ADDON_NAME),
}
# one player's own files and this script's own bookkeeping, never replaced
KEEP = {"install_path.txt", "version.txt", "update_manifest.txt"}
# the shells are reading these while this runs
WRAPPERS = {"update.bat", "update.sh"}

VERSION_FILE = os.path.join(HERE, "version.txt")
MANIFEST_FILE = os.path.join(HERE, "update_manifest.txt")


def fetch(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def latest_commit():
    """(sha, date) of the branch head, or (None, None) when GitHub's API is
    unreachable or rate limited. The download itself does not need it."""
    try:
        with fetch(API_URL, timeout=15) as response:
            data = json.load(response)
        return data["sha"], data["commit"]["committer"]["date"]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None, None


def installed_commit():
    try:
        with open(VERSION_FILE, encoding="utf-8") as fh:
            first = fh.readline().split()
        return first[0] if first else None
    except OSError:
        return None


def download_zip():
    """The whole branch as a zip, in memory. About 30 MB."""
    with fetch(ZIP_URL, timeout=60) as response:
        total = response.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else 0
        chunks, got, shown = [], 0, -1
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            got += len(chunk)
            if total:
                percent = got * 100 // total
                if percent // 10 != shown:
                    shown = percent // 10
                    print("  %3d%%" % percent, end="\r", flush=True)
            else:
                print("  %.1f MB" % (got / 1048576), end="\r", flush=True)
    print("  %.1f MB downloaded" % (got / 1048576))
    return b"".join(chunks)


def read_manifest():
    try:
        with open(MANIFEST_FILE, encoding="utf-8") as fh:
            return {line.rstrip("\n") for line in fh if line.strip()}
    except OSError:
        return set()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def normalise(name, data):
    # a batch file with bare LF line endings misbehaves in cmd; the repository
    # stores LF and git converts on checkout, so convert here the same way
    if name.lower().endswith(".bat"):
        return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return data


def same_bytes(path, data):
    try:
        with open(path, "rb") as fh:
            return fh.read() == data
    except OSError:
        return False


def place(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def keep_executable(path, member):
    """Give a file the executable bit the repository gives it. GitHub's zip
    stores each file's mode, and a file written by place() has none, so
    install.sh would stop running as ./install.sh after an update."""
    if os.name == "nt" or not (member.external_attr >> 16) & 0o111:
        return
    try:
        mode = os.stat(path).st_mode
        if mode & 0o111 != 0o111:
            os.chmod(path, mode | 0o111)
    except OSError:
        pass


def apply(archive):
    """Write the two folders out of the zip. Returns (written, changed,
    wrappers_pending, removed)."""
    names = archive.namelist()
    if not names:
        raise SystemExit("The download is empty. Try again later.")
    top = names[0].split("/")[0]

    written = set()
    changed = 0
    pending = []
    for member in archive.infolist():
        if member.is_dir():
            continue
        parts = member.filename.split("/")
        if parts[0] != top:
            continue
        rel = "/".join(parts[1:])
        for folder, dest_root in TARGETS.items():
            prefix = folder + "/"
            if not rel.startswith(prefix):
                continue
            inner = rel[len(prefix):]
            inner_parts = inner.split("/")
            if any(p in ("", ".", "..") for p in inner_parts):
                continue                        # never outside the target
            if folder == "client-patch" and inner in KEEP:
                continue
            data = normalise(inner, archive.read(member))
            dest = os.path.join(dest_root, *inner_parts)
            if folder == "client-patch" and inner in WRAPPERS:
                if not same_bytes(dest, data):
                    place(dest + ".new", data)
                    pending.append(inner)
                written.add(rel)
                continue
            if not same_bytes(dest, data):
                place(dest, data)
                changed += 1
            # an unchanged file too: an older updater wrote it without the bit
            keep_executable(dest, member)
            written.add(rel)

    # what an earlier run put here that the repository no longer has
    removed = 0
    for rel in sorted(read_manifest() - written):
        for folder, dest_root in TARGETS.items():
            prefix = folder + "/"
            if rel.startswith(prefix):
                path = os.path.join(dest_root, *rel[len(prefix):].split("/"))
                if os.path.isfile(path):
                    os.remove(path)
                    removed += 1
    write_text(MANIFEST_FILE, "\n".join(sorted(written)) + "\n")
    return len(written), changed, pending, removed


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch the latest Classless Wildcard client patch and addon.")
    parser.add_argument("--check", action="store_true",
                        help="report whether an update is available, change nothing")
    parser.add_argument("--force", action="store_true",
                        help="reinstall even when already on the latest commit")
    args = parser.parse_args(argv)

    print("Classless Wildcard client updater")
    print("  from  https://github.com/%s (%s)" % (REPO, BRANCH))
    print("  into  %s" % HERE)
    print("        %s" % TARGETS["client-addon/" + ADDON_NAME])
    print()

    sha, date = latest_commit()
    have = installed_commit()
    if sha:
        print("Latest commit: %s (%s)" % (sha[:12], date))
    else:
        print("Latest commit: could not ask GitHub, downloading anyway")
    print("Installed:     %s" % (have[:12] if have else "unknown (first update)"))
    print()

    if sha and have == sha and not args.force:
        print("Already up to date. Nothing downloaded.")
        if args.check:
            return 0
        print("Run with --force to reinstall anyway.")
        return 0
    if args.check:
        print("An update is available. Run update.bat (or ./update.sh) to get it.")
        return 0

    print("Downloading...")
    try:
        blob = download_zip()
    except (urllib.error.URLError, OSError) as error:
        print()
        print("Download failed: %s" % error)
        print("Check the internet connection and try again.")
        return 1

    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        print("The download was not a zip file. Try again later.")
        return 1

    written, changed, pending, removed = apply(archive)
    stamp = "%s %s\n" % (sha or "unknown", date or time.strftime("%Y-%m-%dT%H:%M:%S"))
    write_text(VERSION_FILE, stamp)

    print()
    print("Done. %d files checked, %d updated, %d removed." % (written, changed, removed))
    for name in pending:
        print("  %s itself changed. It is swapped in the next time you run it." % name)
    print()
    print("Now run install.bat (Windows) or ./install.sh (Linux, macOS) with WoW closed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
