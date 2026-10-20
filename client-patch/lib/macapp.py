"""World of Warcraft.app, the Mac client: find it, patch it, sign it again.

The Mac client is wowdecomp's macOS build, installed beside Data the way
Blizzard's Mac client sat in its game folder, and every player of a realm gets
the same build. lib/machopatch.py knows the bytes to change in it; this does
the rest. The app is copied to World of Warcraft.app.classless-bak first (the
Mac twin of Wow.exe.classless-bak), patched, then signed again: an Apple
Silicon Mac will not start an executable whose signature no longer matches it,
so a patch that cannot be signed is taken back out.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess

from . import machopatch

APP_NAME = "World of Warcraft.app"
BUNDLE_ID = "org.wowdecomp.wow"
# where the app remembers a game folder chosen at launch (WoW/Source/Mac/main.mm)
DEFAULTS = os.path.join("~", "Library", "Preferences", BUNDLE_ID + ".plist")
GAME_FOLDER_KEY = "GameFolder"
# what wowdecomp's own build runs on the bundle (WoW/Source/CMakeLists.txt)
SIGN = ["codesign", "--force", "--sign", "-"]


class AppError(Exception):
    """The app could not be patched, signed or put back; the message says why."""


def remembered_game_folder():
    """The game folder the app asked for once and remembers, or None."""
    try:
        with open(os.path.expanduser(DEFAULTS), "rb") as handle:
            folder = plistlib.load(handle).get(GAME_FOLDER_KEY)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    return folder if isinstance(folder, str) else None


def find_app(wow_dir):
    """The app beside Data, else where macOS keeps apps (it can run from
    anywhere once it knows the game folder)."""
    for folder in (wow_dir, "/Applications", os.path.expanduser("~/Applications")):
        if folder:
            path = os.path.join(folder, APP_NAME)
            if os.path.isdir(path):
                return path
    return None


def is_wowdecomp(app) -> bool:
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as handle:
            return plistlib.load(handle).get("CFBundleIdentifier") == BUNDLE_ID
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False


def executable(app):
    return machopatch.app_executable(app)


def inspect(app):
    """(state, uuid, label), machopatch's states."""
    return machopatch.inspect(executable(app))


def backup_path(app):
    # not ending in .app, so Finder and Spotlight do not list a second game
    return app + ".classless-bak"


def can_sign() -> bool:
    return shutil.which("codesign") is not None


def sign(app):
    """Sign the app again, ad hoc, as its own build did."""
    for command in (SIGN + [app], ["codesign", "--verify", app]):
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as error:
            raise AppError("codesign could not start: %s" % error)
        if result.returncode:
            raise AppError("%s failed: %s" % (" ".join(command[:2]),
                                              result.stdout.decode("utf-8", "replace").strip()))


def patch(app):
    """Patch and sign the app. Returns a summary line; raises AppError with the
    app left as it was."""
    state, uuid, label = inspect(app)
    if state == machopatch.PATCHED:
        return "already has the Hero changes (%s)" % label
    if state == machopatch.UNKNOWN:
        raise AppError("this World of Warcraft.app is not a build the Hero patch knows "
                       "(build %s), so it was not touched" % (uuid or "unreadable"))
    if not can_sign():
        raise AppError("codesign was not found, and a patched app that is not signed again "
                       "will not start. Patch the app on the Mac it runs on")
    backup = backup_path(app)
    kept = not os.path.exists(backup)
    if kept:
        shutil.copytree(app, backup, symlinks=True)
    try:
        machopatch.write_executable(executable(app), patched=True)
        sign(app)
    except (OSError, RuntimeError, AppError) as error:
        _put_back(app, backup, kept)
        raise AppError("%s. The app was put back as it was" % error)
    return "Hero changes written and the app signed again (%s)%s" % (
        label, "; the stock app is kept as %s" % os.path.basename(backup) if kept else "")


def _put_back(app, backup, made_now):
    if made_now and os.path.isdir(backup):
        shutil.rmtree(app, ignore_errors=True)
        os.rename(backup, app)
    else:
        try:
            machopatch.write_executable(executable(app), patched=False)
            sign(app)
        except (OSError, RuntimeError, AppError):
            pass


def has_changes(app) -> bool:
    return os.path.isdir(backup_path(app)) or inspect(app)[0] == machopatch.PATCHED


def restore(app):
    """Put the stock app back: the copy kept on install, or the bytes reverted
    in place and the app signed again. Returns a summary line."""
    backup = backup_path(app)
    if os.path.isdir(backup):
        shutil.rmtree(app)
        os.rename(backup, app)
        return "stock app put back"
    if inspect(app)[0] != machopatch.PATCHED:
        return "has no Hero changes; left alone"
    if not can_sign():
        raise AppError("codesign was not found; restore the app on the Mac it runs on")
    machopatch.write_executable(executable(app), patched=False)
    sign(app)
    return "Hero changes taken out and the app signed again (no stock copy was kept)"
