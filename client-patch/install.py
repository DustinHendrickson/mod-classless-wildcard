#!/usr/bin/env python3
"""One-step client setup for mod-classless-wildcard.

Point this at a World of Warcraft 3.3.5a folder and it does everything the
client side needs:

  * builds a data patch from the player's OWN client files and drops it in
    Data/ (every class shows as Hero; the creation screen lists one class)
  * installs the ClasslessWildcard addon
  * clears the client Cache so the new data is picked up

The install also rewrites the creation-screen class blurb. That is a signed
interface file, so the installer applies the well-known "allow custom
interface" patch to Wow.exe (backed up first) so the client loads it. Confirmed
working on a stock 3.3.5a build 12340 client. --no-creation-text skips both.

On a Mac the client is World of Warcraft.app, and on a Switch WoW.nro, both
wowdecomp's arm64 builds. The same changes are made to them (lib/armpatch.py,
from arm64_patch.json); the Mac app is then signed again (lib/macapp.py).

Everything is reversible with --uninstall.

Requires nothing but Python 3.7+. No compiler, no StormLib, no other packages.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import (blp, charcreate, clientfs, dbc, dkfaces, elemental, exepatch, framexml,  # noqa: E402
                 forged, gluestrings, armpatch, macapp, mpq, outfit)

MANIFEST_NAME = "ClasslessWildcard-install.json"
ADDON_NAME = "ClasslessWildcard"

CHRCLASSES = "DBFilesClient\\ChrClasses.dbc"
CHARBASEINFO = "DBFilesClient\\CharBaseInfo.dbc"
CHARSTARTOUTFIT = "DBFilesClient\\CharStartOutfit.dbc"
CHARSECTIONS = "DBFilesClient\\CharSections.dbc"
SKILLRACECLASSINFO = "DBFilesClient\\SkillRaceClassInfo.dbc"
SKILLLINEABILITY = "DBFilesClient\\SkillLineAbility.dbc"
SKILLLINE = "DBFilesClient\\SkillLine.dbc"
# No longer patched: opening every tree to every class emptied the stock
# talent window (Blizzard_TalentUI reads GetNumTalentTabs off this table).
# The name stays here and in _OUR_FILES so an archive written by the version
# that DID patch it is still recognised as ours by uninstall.
# Read only -- the cost floor needs the talent list. Never written, so it is
# deliberately absent from _OUR_FILES.
TALENT = "DBFilesClient\\Talent.dbc"
# read only, for the glyph spells the cost and cooldown floors must count
GLYPHPROPERTIES = "DBFilesClient\\GlyphProperties.dbc"
ITEM = "DBFilesClient\\Item.dbc"
# Written, unlike TALENT two lines up: the category split appends a row per
# new cooldown group, so this one IS in _OUR_FILES.
SPELLCATEGORY = "DBFilesClient\\SpellCategory.dbc"
TALENTTAB = "DBFilesClient\\TalentTab.dbc"
SPELLSHAPESHIFTFORM = "DBFilesClient\\SpellShapeshiftForm.dbc"
# the same path elemental.py uses, kept in one place so the two never diverge
SPELL = elemental.SPELL
GLUESTRINGS = "Interface\\GlueXML\\GlueStrings.lua"
CHARCREATE_LUA = "Interface\\GlueXML\\CharacterCreate.lua"
CLASSICONS_INGAME = "Interface\\TargetingFrame\\UI-Classes-Circles.blp"
CLASSICONS_CREATE = "Interface\\Glues\\CharacterCreate\\UI-CharacterCreate-Classes.blp"
# the battleground scoreboard's class column
CLASSICONS_SCORE = "Interface\\WorldStateFrame\\Icons-Classes.blp"

COMMON_INSTALL_DIRS = [
    r"C:\World of Warcraft",
    r"C:\Games\World of Warcraft",
    r"C:\Program Files (x86)\World of Warcraft",
    r"C:\Program Files\World of Warcraft",
    os.path.expanduser("~/World of Warcraft"),
    os.path.expanduser("~/Games/World of Warcraft"),
    os.path.expanduser("~/Applications/World of Warcraft"),
    "/Applications/World of Warcraft",
]


class Abort(Exception):
    """A clean, explained failure -- printed without a traceback."""


# ---------------------------------------------------------------- discovery

def resolve_child(parent, name):
    """Find `name` inside `parent` ignoring case, for Linux and macOS.

    Returns the existing path if there is one, otherwise the plain join so the
    caller can create it with the spelling we prefer.
    """
    direct = os.path.join(parent, name)
    if os.path.exists(direct):
        return direct
    try:
        entries = os.listdir(parent)
    except OSError:
        return direct
    lowered = name.lower()
    for entry in entries:
        if entry.lower() == lowered:
            return os.path.join(parent, entry)
    return direct


def resolve_path(root, *parts):
    path = root
    for part in parts:
        path = resolve_child(path, part)
    return path


def looks_like_client(path) -> bool:
    if not path or not os.path.isdir(path):
        return False
    data = resolve_child(path, "Data")
    if not os.path.isdir(data):
        return False
    if find_wow_exe(path) or find_wow_nro(path) or os.path.isdir(resolve_child(path, macapp.APP_NAME)):
        return True
    # World of Warcraft.app can live anywhere once it knows the game folder,
    # which it takes to be any folder whose Data holds MPQs (WoW/Source/Mac/main.mm)
    return sys.platform == "darwin" and any(name.lower().endswith(".mpq")
                                            for name in os.listdir(data))


def find_wow_nro(wow_dir):
    """WoW.nro, the Switch client, in sdmc:/switch/wow beside Data."""
    try:
        entries = os.listdir(wow_dir)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == "wow.nro" and os.path.isfile(os.path.join(wow_dir, entry)):
            return os.path.join(wow_dir, entry)
    return None


def find_wow_exe(wow_dir):
    try:
        entries = os.listdir(wow_dir)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == "wow.exe":
            candidate = os.path.join(wow_dir, entry)
            if os.path.isfile(candidate):
                return candidate
    return None


# The folder a player installed to, so later runs need no path. install.bat
# writes it when it has to ask; on a Mac or Linux the first install does.
PATH_FILE = os.path.join(HERE, "install_path.txt")


def remembered_client():
    try:
        with open(PATH_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.strip('"')
    except OSError:
        pass
    return None


def remember_client(wow_dir):
    if os.name == "nt" or os.path.exists(PATH_FILE):
        return
    try:
        with open(PATH_FILE, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# The World of Warcraft folder install.sh patches.\n"
                         "# Delete this file, or clear the line below, to be asked again.\n"
                         "%s\n" % wow_dir)
    except OSError:
        pass


def autodetect_client():
    """Look in the obvious places before asking the player to type a path."""
    candidates = []
    if remembered_client():
        candidates.append(remembered_client())

    # the installer may have been copied into the client folder itself
    probe = HERE
    for _ in range(4):
        candidates.append(probe)
        probe = os.path.dirname(probe)

    candidates.append(os.getcwd())
    if sys.platform == "darwin" and macapp.remembered_game_folder():
        candidates.append(macapp.remembered_game_folder())
    candidates.extend(COMMON_INSTALL_DIRS)

    seen = set()
    for path in candidates:
        real = os.path.abspath(path)
        if real in seen:
            continue
        seen.add(real)
        if looks_like_client(real):
            return real
    return None


def prompt_for_client():
    if not sys.stdin or not sys.stdin.isatty():
        return None
    print("Could not find your World of Warcraft folder automatically.")
    print("It is the folder that contains the Data folder (and Wow.exe, World of Warcraft.app or WoW.nro).")
    print()
    try:
        raw = input("Path to your WoW 3.3.5a folder (or blank to cancel): ")
    except (EOFError, KeyboardInterrupt):
        return None
    raw = raw.strip()
    if os.name != "nt" and raw:
        # a folder dragged into a Mac or Linux terminal arrives shell-escaped
        try:
            raw = " ".join(shlex.split(raw))
        except ValueError:
            pass
    raw = raw.strip().strip('"').strip("'")
    return raw or None


# ------------------------------------------------------------------- build

# The one class the creation screen offers, shown as "Hero". This IS the chassis
# class (Paladin): a Hero is created as a Paladin directly, so there is no
# runtime class conversion, mana is native, and the Paladin class icon (which
# the client patch reskins to the Hero emblem) shows from creation onward.
# Paladin is not vanilla-creatable by every race, so the module's
# cw_world_hero_races.sql adds the missing playercreateinfo rows server-side.
SHELL_CLASS = 2


def build_data_patch(files, name, report, theme=False, keep_totems=False):
    """Assemble the base patch archive contents from the client's own DBCs.

    theme=True (with --creation-text) also gives the Hero the armored starting
    outfit via CharStartOutfit.dbc.
    """
    payload = {}

    raw, source = files.find(CHRCLASSES)
    patched, renamed = dbc.rename_all_classes(raw, name)
    # Slot 17 is a RELIC slot for Paladin, Death Knight, Shaman and Druid, and
    # the client never draws a relic. With the default Paladin chassis that
    # made every bow, gun and wand invisible on the character. Turn it back
    # into an ordinary ranged slot.
    patched, unrelic = dbc.clear_relic_slot(patched)
    payload[CHRCLASSES] = patched
    report.append("  ChrClasses.dbc   %d classes renamed to %s (from %s)"
                  % (len(renamed), name, os.path.basename(source)))
    report.append("  ChrClasses.dbc   ranged slot restored on %d relic classes "
                  "(bows, guns and wands now show)" % len(unrelic))

    # A stance pages the action bar out, and a Warrior's stances cannot be
    # clicked off (a Warrior is never out of one). A Hero with one stance had no
    # way back to their normal bar.
    raw, source = files.find(SPELLSHAPESHIFTFORM)
    patched, stances = dbc.open_stance_cancel(raw)
    if stances:
        payload[SPELLSHAPESHIFTFORM] = patched
    report.append("  SpellShapeshiftForm.dbc  %d stances can be clicked off (from %s)"
                  % (len(stances), os.path.basename(source)))

    raw, source = files.find(CHARBASEINFO)
    patched, races = dbc.single_class_combos(raw, SHELL_CLASS)
    payload[CHARBASEINFO] = patched
    report.append("  CharBaseInfo.dbc all %d races, one cosmetic class "
                  "(shown as %s)" % (races, name))

    # Every Hero is created on the Paladin chassis, so the creation screen hid
    # the three extra skin colours, the second set of faces and the extra hair
    # colours that Blizzard reserved for Death Knights. The server never checks
    # appearance against this table, so only the client needs telling.
    # Those skins were drawn for three faces per race, with the Death Knight's
    # glowing eyes painted in, and the skin arrows skip a colour the current
    # face has no row for. Every normal face is painted in each Death Knight
    # tone from this client's own textures (lib/dkfaces.py; nothing of
    # Blizzard's is stored in the repository), and the glowing faces borrow
    # Blizzard's glowing art (Wow.exe keeps those borrowed rows out of the
    # Face arrow). If painting fails, every face borrows instead.
    raw, source = files.find(CHARSECTIONS)
    try:
        face_textures, painted = dkfaces.generate(files, raw)
    except (ImportError, dkfaces.FaceError, dbc.DbcError, FileNotFoundError,
            ValueError) as error:
        face_textures, painted = {}, []
        report.append("  CharSections.dbc Death Knight-tone faces not painted (%s); "
                      "normal faces borrow the drawn ones" % error)
    filled, borrowed = dbc.fill_death_knight_skin_faces(raw, normal_faces=not painted)
    added = retextured = 0
    if painted:
        filled, added, retextured = dbc.add_generated_faces(filled, painted)
        payload.update(face_textures)
    patched, opened_looks = dbc.open_death_knight_appearance(filled)
    payload[CHARSECTIONS] = patched
    report.append("  CharSections.dbc %d Death Knight skin, face and hair rows "
                  "offered to every class (from %s)"
                  % (len(opened_looks) - len(borrowed), os.path.basename(source)))
    report.append("  CharSections.dbc %d normal faces painted in the Death Knight "
                  "tones (%d textures), %d glowing faces borrow the drawn ones"
                  % (added + retextured, len(face_textures), len(borrowed)))

    # The client decides spellbook tabs from its OWN copy of this table, so
    # the server opening every class skill line to every class was invisible
    # to it: a Hero given Balance for a rolled Moonfire still had no Balance
    # tab, because the client's table said Balance is for Druids. Open the
    # client the same way the server was opened.
    raw, source = files.find(SKILLRACECLASSINFO)
    patched, opened, already = dbc.open_class_skill_lines(raw)
    payload[SKILLRACECLASSINFO] = patched
    report.append("  SkillRaceClassInfo.dbc  %d class skill lines opened to every class "
                  "(from %s)" % (len(opened), os.path.basename(source)))

    # This is the one that actually decides spellbook tabs. The client fixes a
    # class's tab set from SkillLineAbility's ClassMask and files a known spell
    # under a tab only if the spell's own row says it belongs to this class --
    # so a rolled Eviscerate sat in General while its row said "Rogue". Make
    # every class spell belong to every class; empty tabs stay hidden.
    categories = dbc.skill_line_categories(files.find(SKILLLINE)[0])
    sla_raw, source = files.find(SKILLLINEABILITY)
    patched, changed, already = dbc.open_class_abilities(sla_raw, categories)
    payload[SKILLLINEABILITY] = patched
    report.append("  SkillLineAbility.dbc  %d class spells now belong to every class "
                  "(spellbook tabs for cross-class spells; from %s)"
                  % (changed, os.path.basename(source)))

    # A class tool is the one requirement a Hero can never meet: Stoneskin
    # Totem wants an Earth Totem, which is handed to shamans alone. The server
    # clears the requirement on its side; the client has to agree, or the
    # tooltip keeps the red "Tools:" line and the cast is refused before it is
    # ever sent.
    class_spells = dbc.class_spell_ids(sla_raw, categories)
    raw, source = files.find(SPELL)
    # a totem keeps its element only when the exe patch makes it read as carried
    patched, cleared = dbc.clear_spell_tools(raw, class_spells, keep_totem_categories=keep_totems)
    payload[SPELL] = patched
    report.append("  Spell.dbc        class tool requirement cleared from %d spells "
                  "(%s; reagents untouched; from %s)"
                  % (cleared, "relics; totems keep their element for the totem bar" if keep_totems
                     else "totems, relics", os.path.basename(source)))

    # Auto Shot is taught to every Hero at level 1, sword in hand, so its own
    # icon shows where a hunter would see their bow.
    icon_raw, _icon_source = files.find(elemental.SPELLICON)
    payload[SPELL], reiconed = dbc.set_spell_icons(payload[SPELL], icon_raw)
    report.append("  Spell.dbc        icon replaced on %d stock spell(s) (Auto Shot, the nemesis mark)"
                  % reiconed)
    # The nemesis mark is a stock spell every nearby player sees on the
    # creature's debuffs; it reads "Nemesis" rather than its internal name.
    payload[SPELL], renamed = dbc.rename_spells(payload[SPELL])
    report.append("  Spell.dbc        %d stock spell(s) renamed (the nemesis mark, Swear Vendetta)" % renamed)
    payload[SPELL], refielded = dbc.set_spell_fields(payload[SPELL])
    report.append("  Spell.dbc        %d stock spell(s) given the module's own values (Swear Vendetta)" % refielded)

    # The cost floor used to run here. It runs in apply_client_floors() now, after
    # the generated rows have been appended -- see that function for why.

    # Our own items, so the client can draw them before it has ever asked the
    # server about one. Without a row here GetItemIcon returns nothing for a
    # custom item and a bag addon rendering from its own saved slot list shows a
    # question mark -- which clearing the client's Cache only makes worse.
    manifest = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "items_manifest.json")
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as handle:
            wanted = json.load(handle).get("items", [])
        item_raw, item_source = files.find(ITEM)
        payload[ITEM], item_added, item_skipped = dbc.append_items(item_raw, wanted)
        report.append("  Item.dbc         %d classless item(s) registered "
                      "(so their icons draw before the server is asked; from %s)"
                      % (item_added, os.path.basename(item_source)))
    else:
        report.append("  Item.dbc         skipped (no items_manifest.json shipped)")

    if theme:
        try:
            raw, source = files.find(CHARSTARTOUTFIT)
            patched, updated, added = outfit.build_hero_outfit(raw, SHELL_CLASS)
            payload[CHARSTARTOUTFIT] = patched
            report.append("  CharStartOutfit.dbc  starter gear on the preview, %d "
                          "rows updated + %d added (from %s)"
                          % (updated, added, os.path.basename(source)))
        except (FileNotFoundError, outfit.OutfitError) as error:
            report.append("  CharStartOutfit.dbc  skipped (%s)" % error)

    return payload


# SpellFamilyName 14, which the generators claim for everything this module
# forges. Its percentage costs are lowered along with the flat ones because the
# server sends a correction for every spell in this family; no stock family is,
# so no stock tooltip is touched. Both halves have to stay in step -- see the
# matching note in ClasslessAddon::SendSpellCorrections.
HERO_SPELL_FAMILY = 14


TALENT_REACH_MANIFEST = "talent_reach_manifest.json"


def talent_reach():
    """General talents that reach other classes' abilities, by operation:
    {op: [(targets, is_flat, value), ...]}, from the manifest the server's
    cw_talent_reach.sql was generated with (gen_talent_reach.py). Only the
    cost (14) and cooldown (11) entries are shipped: those are the two the
    client checks itself before it sends a cast. Missing file: nothing."""
    path = os.path.join(HERE, TALENT_REACH_MANIFEST)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for entry in data.get("entries", []):
        out.setdefault(entry["op"], []).append(
            (frozenset(entry["targets"]), bool(entry["flat"]), int(entry["value"])))
    return out


def apply_client_floors(files, payload, report, hero_talents=()):
    """Make the client copy permissive enough never to refuse a legal cast.

    Three passes, all the same idea: the client checks power, cooldown and
    cooldown category itself before it will send a cast, and it cannot apply a
    talent from another class to any of those -- the modifier packet carries a
    class-mask bit and no spell family, so it only matches the chassis own.
    Lower its copy to the least any build could reach and let the server decide;
    the addon writes the true numbers back onto the tooltip.

      1. costs      -- described below
      2. cooldowns  -- lower_talent_reduced_cooldowns
      3. categories -- split_cross_class_categories, so one class reactive
                       ability stops locking out another

    Runs LAST.

    The client checks power itself before it will send a cast and cannot apply a
    cross-class talent to that check, so Improved Thunder Clap left the server
    wanting 16 rage while the client still refused at 16. Lower its copy to the
    lowest cost any combination of talents could produce and the server decides;
    the addon writes the true cost back onto the tooltip so nothing reads low.

    Ordering is the whole point, and getting it wrong is not visible in the
    report. A generated spell is written into the client by cloning a donor row
    and overlaying the columns its manifest names, and that manifest is a DIFF
    against the PRISTINE client row -- so every cost column it leaves out is one
    that MATCHED the pristine row and was therefore never written. Floor the
    table first and those rows inherit the floor instead of their own cost: 808
    of the 1324 generated spells were priced off a row that was not theirs, and
    Holy Overpower quoted 2 rage against a server charging 5, because the client
    copy it cloned had already had Focused Rage taken off it.

    So: append first, floor afterwards, and read the floor's baseline from the
    table as it stands here -- which now holds each generated row at the cost its
    own spell_dbc row carries.

    The skill lines are re-read from the patched table for the same reason. A
    generated spell is filed under its base's class tab by the append pass, and
    the floor only considers spells on a class line; taking that list from the
    archive copy would leave every generated spell unfloored, refused locally the
    moment a talent made the server's price lower than the client's.

    `hero_talents` is the module's own tree, which the client's Talent.dbc does
    not contain and the floor therefore could not read. Without it Thrift took
    30% off a forged spell on the server while the client went on refusing at
    the full price.
    """
    categories = dbc.skill_line_categories(payload.get(SKILLLINE)
                                           or files.find(SKILLLINE)[0])
    class_spells = dbc.class_spell_ids(payload.get(SKILLLINEABILITY)
                                       or files.find(SKILLLINEABILITY)[0], categories)
    talent_raw, talent_source = files.find(TALENT)
    # Glyphs cut costs and cooldowns too, and no talent row names them.
    modifier_spells = tuple(hero_talents) + tuple(
        dbc.glyph_spell_ids(files.find(GLYPHPROPERTIES)[0]))
    reach = talent_reach()
    before = payload[SPELL]
    payload[SPELL], lowered = dbc.lower_talent_reduced_costs(
        before, talent_raw, class_spells, stock_costs=before,
        extra_modifier_spells=modifier_spells, pct_families=(HERO_SPELL_FAMILY,),
        reach=reach.get(14, ()))
    report.append("  Spell.dbc        cost floor lowered on %d spells "
                  "(talent-reduced costs cast at the real price; from %s)"
                  % (lowered, os.path.basename(talent_source)))

    # And the cooldown, which fails the same way and was never handled. The
    # client will not send a cast it believes is still recharging, and the
    # server only tells it a cooldown at login -- so a talent that shortens one
    # left the button grey while the ability was ready.
    before = payload[SPELL]
    payload[SPELL], shortened = dbc.lower_talent_reduced_cooldowns(
        before, talent_raw, class_spells, stock=before,
        extra_modifier_spells=modifier_spells, reach=reach.get(11, ()))
    report.append("  Spell.dbc        cooldown floor lowered on %d spells "
                  "(talent-shortened cooldowns are castable when they are ready)"
                  % shortened)

    # And the last way a cooldown can be wrong on the client: Blizzard files
    # reactive abilities from different classes in one cooldown category, and
    # the client greys the whole category while the server separates it by
    # spell family. Mongoose Bite was locking out Overpower and Revenge.
    category_raw, _src = files.find(SPELLCATEGORY)
    payload[SPELL], payload[SPELLCATEGORY], moved, added = \
        dbc.split_cross_class_categories(payload[SPELL], category_raw, class_spells)
    report.append("  Spell.dbc        %d spell(s) moved into %d new cooldown "
                  "categor(ies) so one class no longer locks out another"
                  % (moved, added))

    # Overpower opens on a dodge through an aura state, not a combo point, so
    # a rogue's combo points no longer light it and it no longer spends them.
    # After the append, so the elemental Overpowers are in class_spells too.
    payload[SPELL], gated = dbc.gate_overpower_on_dodge(payload[SPELL], class_spells)
    report.append("  Spell.dbc        %d Overpower spell(s) open on a dodge, "
                  "not on combo points" % gated)
    return payload


def build_locale_patch(files, name, report, locale, theme=False, icon=False):
    """Assemble the locale patch archive contents for one locale.

    theme -> the Hero creation-screen text + hidden class selector.
    icon  -> the Hero emblem over the class icon (independent; needs no exe
             patch, but replaces UI-Classes-Circles, used all over the UI, so
             it is its own opt-in).
    Returns a possibly-empty payload.
    """
    payload = {}

    if theme:
        raw, source = files.find(GLUESTRINGS)
        text = raw.decode("utf-8", "surrogateescape")
        new_text, replaced = gluestrings.rewrite(text, name)
        if not replaced:
            raise Abort(
                "Found GlueStrings.lua for %s but none of the class description "
                "keys matched, so the creation screen would be unchanged.\n"
                "This locale names its strings differently and needs a look. "
                "Drop --creation-text to install everything else." % locale)
        report.append("  GlueStrings.lua  %d class strings rewritten (from %s)"
                      % (len(replaced), os.path.basename(source)))
        payload[GLUESTRINGS] = new_text.encode("utf-8", "surrogateescape")

        try:
            raw, source = files.find(CHARCREATE_LUA)
        except FileNotFoundError:
            report.append("  CharacterCreate.lua  not found; selector left visible")
        else:
            lua = raw.decode("utf-8", "surrogateescape")
            hooked = charcreate.add_hide_class_hook(lua)
            payload[CHARCREATE_LUA] = hooked.encode("utf-8", "surrogateescape")
            report.append("  CharacterCreate.lua  class selector hidden (from %s)"
                          % os.path.basename(source))

        # class gates in the interface's own code, opened for a Hero
        # (lib/framexml.py); custom interface files load with the exe patch
        for path, edit, what in (
                (framexml.TOTEMFRAME_LUA, framexml.open_totem_frame,
                 "totem timers stay up with a pet out"),
                (framexml.OPTIONS_LUA, lambda t: framexml.open_combo_option(t, 2),
                 "combo point combat text option open"),
                (framexml.OPTIONS_XML, lambda t: framexml.open_combo_option(t, 1),
                 "combo point combat text option open"),
                (framexml.CONSTANTS_LUA, framexml.hero_class_color,
                 "the Hero class color in place of the Paladin's"),
                (framexml.RAIDUI_LUA, framexml.open_raid_pets,
                 "a Hero's pet joins the raid Pets group"),
                (framexml.PAPERDOLL_LUA, framexml.open_pet_bonus,
                 "a Hero's pet bonus lines on the character sheet"),
                (framexml.UIPARENT_LUA, framexml.open_bar_row,
                 "the totem bar joins the stance row; forms past ten are laid out"),
                (framexml.PETBAR_LUA, framexml.open_pet_bar_row,
                 "the pet bar starts after the whole stance row")):
            try:
                raw, source = files.find(path)
            except FileNotFoundError:
                report.append("  %s  not found; left alone" % path.split("\\")[-1])
                continue
            text = raw.decode("utf-8", "surrogateescape")
            new_text, changed = edit(text)
            if changed:
                payload[path] = new_text.encode("utf-8", "surrogateescape")
            report.append("  %s  %s (from %s)" % (path.split("\\")[-1],
                          what if changed else "stock text not found; left alone",
                          os.path.basename(source)))

    if icon:
        # The Hero emblem on the Paladin cell of each class-icon atlas, the cell
        # every Hero is drawn with: UI-Classes-Circles (unit frames, arena),
        # UI-CharacterCreate-Classes (the raid window's class buttons, calendar
        # invites) and Icons-Classes (the battleground scoreboard). All three
        # share one cell layout. The addon's ability-group tabs keep every class
        # icon: it gets its own copy of the stock atlas (install_addon).
        for path, what in ((CLASSICONS_INGAME, "unit frames"),
                           (CLASSICONS_CREATE, "raid window and calendar"),
                           (CLASSICONS_SCORE, "battleground scoreboard")):
            try:
                raw, source = files.find(path)
            except FileNotFoundError:
                raw = None
            atlas = blp.reskin_hero_cell(raw) if raw else None
            if atlas is None and raw is not None:
                raise Abort("The Hero class icon could not be painted: the Python library "
                            "'Pillow' is missing. Run:  python -m pip install --user pillow")
            elif atlas is None:
                report.append("  Hero class icon      %s skipped (atlas not found)" % what)
            else:
                payload[path] = atlas
                report.append("  Hero class icon      emblem on the Hero's cell, %s (from %s)"
                              % (what, os.path.basename(source)))

    return payload


# ----------------------------------------------------------------- actions

def install_addon(wow_dir, dry_run, report, files=None):
    source = os.path.abspath(os.path.join(HERE, os.pardir, "client-addon", ADDON_NAME))
    if not os.path.isdir(source):
        report.append("  addon            SKIPPED, not found at %s" % source)
        return None
    target = resolve_path(wow_dir, "Interface", "AddOns", ADDON_NAME)
    if not dry_run:
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copytree(source, target)
    count = sum(len(names) for _root, _dirs, names in os.walk(source))
    report.append("  addon            %d files -> Interface/AddOns/%s"
                  % (count, ADDON_NAME))

    # give the addon its OWN copy of the class-icon atlas, built from the
    # client, so it does not depend on the shared game texture (the addon falls
    # back to that texture if this is absent)
    if files is not None:
        try:
            raw, _src = files.find(CLASSICONS_CREATE)
        except FileNotFoundError:
            raw = None
        atlas = blp.build_addon_class_atlas(raw) if raw else None
        if atlas is not None and not dry_run:
            with open(os.path.join(target, "classicons.blp"), "wb") as handle:
                handle.write(atlas)
        if atlas is not None:
            report.append("  addon class icons    embedded (classicons.blp)")
        elif raw is not None:
            raise Abort("The addon class icons could not be painted: the Python library "
                        "'Pillow' is missing. Run:  python -m pip install --user pillow")

    return os.path.relpath(target, wow_dir).replace("\\", "/")


def count_cache_files(wow_dir):
    """How many cached records the client is still holding."""
    cache = resolve_child(wow_dir, "Cache")
    if not os.path.isdir(cache):
        return 0
    total = 0
    for _base, _dirs, files in os.walk(cache):
        total += len(files)
    return total


def clear_cache(wow_dir, dry_run, report):
    """Delete the client's cached copy of everything the server ever told it.

    The client keeps every item, spell and creature it has been sent in
    Cache/WDB/<locale>/*.wdb and prefers that copy to anything new. An item
    cached before its stats existed keeps drawing a question mark and refuses to
    equip; a ranged weapon cached without its range keeps answering "Out of
    range". Deleting it is always safe -- nothing of the player's lives there.

    Counted rather than assumed. This used to be `rmtree(ignore_errors=True)`
    followed by an unconditional "cleared", and ignore_errors swallows exactly
    the failure that matters: a RUNNING client holds its .wdb files open, so
    nothing is removed and the installer says it was. Anyone hitting that is
    then looking for a bug in the patch instead of closing the game.

    Returns the number of files still there afterwards.
    """
    before = count_cache_files(wow_dir)
    if not before:
        report.append("  cache            nothing to clear")
        return 0
    if dry_run:
        report.append("  cache            %d cached record(s) would be deleted" % before)
        return 0

    shutil.rmtree(resolve_child(wow_dir, "Cache"), ignore_errors=True)
    left = count_cache_files(wow_dir)
    if not left:
        report.append("  cache            %d cached record(s) deleted "
                      "(the client rebuilds it on next login)" % before)
    else:
        report.append("  cache            COULD NOT CLEAR: %d of %d file(s) are "
                      "still locked. The game is open: CLOSE IT, delete the Cache "
                      "folder yourself, and start the game again. Until you do, "
                      "items show the wrong icon and ranged weapons say \"Out of "
                      "range\"." % (left, before))
    return left


def read_manifest(wow_dir):
    path = os.path.join(wow_dir, MANIFEST_NAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_manifest(wow_dir, data, dry_run):
    if dry_run:
        return
    path = os.path.join(wow_dir, MANIFEST_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


# ----------------------------------------------------------------- install

def uses_app(wow_dir):
    """(uses the Mac app, the app or None). World of Warcraft.app is the
    program on a Mac unless Wow.exe is the only one there (Wine), and
    elsewhere when it is the only one."""
    app = macapp.find_app(wow_dir)
    exe = find_wow_exe(wow_dir)
    if sys.platform == "darwin":
        use = app is not None or not exe
    else:
        use = app is not None and not exe
    return use, app


# A Mac or Switch build the shipped table does not hold: its patch is worked
# out on this PC and checked first (gen_arm64_patch.learn), or not at all.
NEW_BUILD = "new"


def learn_build(program, elf_path=None, name=None):
    """Work out and check the patch for a build the installer has not seen,
    keeping it in this PC's arm64_patch.local.json. Raises Abort, having kept
    nothing, when it cannot be done."""
    print("This %s is a build the installer has not seen. Working out its patch on this"
          % (name or os.path.basename(program)))
    print("PC and checking it by running the patched code (first time only, a minute or two).")
    print()
    ensure_library("capstone", "capstone", "read the new build's code")
    ensure_library("unicorn", "unicorn", "check the patched code by running it")
    import gen_arm64_patch
    try:
        _entry, checks = gen_arm64_patch.learn(program, elf_path)
    except gen_arm64_patch.SiteMissing as error:
        raise Abort("This build moved code the Hero patch relies on (%s), so it cannot be\n"
                    "patched yet. Ask the realm for an installer update. Nothing was written."
                    % error)
    except Exception as error:     # an unreadable file, a Wow.elf from another build, a failed check
        raise Abort("The patch for this build could not be worked out: %s.\n"
                    "Nothing was written." % error)
    print("Checked: all %d checks passed. Kept on this PC for later installs." % checks)
    print()


def plan_app(args, wow_dir, app):
    """What the install does to World of Warcraft.app, decided before
    anything is written: (state, label). Raises Abort when the app cannot be
    given the Hero changes, so a client is never left with the Hero interface
    files and a program that refuses them."""
    if not app:
        raise Abort("World of Warcraft.app was not found beside the Data folder in %s, nor\n"
                    "in Applications. Install the realm's Mac client first." % wow_dir)
    if not macapp.is_wowdecomp(app):
        raise Abort("%s is not the realm's Mac client (wowdecomp's build), so it cannot be\n"
                    "given the Hero changes. Install everything except the program\n"
                    "changes with  --no-creation-text" % app)
    state, _key, label = macapp.inspect(app)
    if state == armpatch.UNKNOWN:
        if args.dry_run:
            return NEW_BUILD, "a new build: its patch is worked out on this PC first"
        learn_build(macapp.executable(app), name=macapp.APP_NAME)
        state, _key, label = macapp.inspect(app)
    if state == armpatch.UNPATCHED and not macapp.can_sign():
        raise Abort("World of Warcraft.app has to be signed again after the patch, which\n"
                    "only a Mac can do. Run this installer on the Mac.")
    return state, label


def find_wow_elf(folder):
    try:
        return next((os.path.join(folder, name) for name in os.listdir(folder)
                     if name.lower() == "wow.elf"), None)
    except OSError:
        return None


def plan_nro(args, nro_file):
    """What the install does to WoW.nro, decided before anything is written:
    (state, label). A build the installer has not seen is worked out here,
    which needs the Wow.elf from the same build next to it."""
    state, _key, label = armpatch.inspect(nro_file)
    if state == armpatch.UNKNOWN:
        elf_path = find_wow_elf(os.path.dirname(nro_file))
        if not elf_path:
            raise Abort("This WoW.nro is a build the installer has not seen. To patch it, put the\n"
                        "Wow.elf from the same build next to it in %s (the realm's Switch\n"
                        "build comes as WoW.nro and Wow.elf) and run this again.\n"
                        "Nothing was written." % os.path.dirname(nro_file))
        if args.dry_run:
            return NEW_BUILD, "a new build: its patch is worked out on this PC first"
        learn_build(nro_file, elf_path)
        state, _key, label = armpatch.inspect(nro_file)
    return state, label


def patch_nro(args, nro_file, plan, report):
    """Patch WoW.nro, before any game file is written. Homebrew is not
    signed, so the bytes are all it needs."""
    state, label = plan
    if state == armpatch.PATCHED:
        report.append("  WoW.nro          already has the Hero changes (%s)" % label)
        return
    if args.dry_run:
        report.append("  WoW.nro          would be patched (%s)" % label)
        return
    try:
        report.append("  WoW.nro          %s" % armpatch.patch_file(nro_file))
    except (OSError, RuntimeError) as error:
        raise Abort("WoW.nro was not patched: %s.\n"
                    "No game files were written. Close the game and run this again." % error)


def patch_app(args, app, plan, report):
    """Patch and sign the app. Runs before any game file is written, so a
    failure leaves the client as it was."""
    state, label = plan
    if state == armpatch.PATCHED:
        report.append("  World of Warcraft.app  already has the Hero changes (%s)" % label)
        return
    if args.dry_run:
        report.append("  World of Warcraft.app  would be patched and signed again (%s)" % label)
        return
    try:
        report.append("  World of Warcraft.app  %s" % macapp.patch(app))
    except macapp.AppError as error:
        raise Abort("World of Warcraft.app was not patched: %s.\n"
                    "No game files were written. Close the game and run this again." % error)
    except OSError as error:
        raise Abort("World of Warcraft.app could not be copied or written (%s). Close the game "
                    "and run this again.\nNo game files were written." % error)


def do_install(args, wow_dir):
    data_dir = resolve_child(wow_dir, "Data")
    exe = find_wow_exe(wow_dir)
    # First thing after the folder is known, so it happens even if a later step
    # aborts. Re-checked at the end, because a client running through the
    # install writes its cache back and undoes this.
    cache_report = []
    cache_left = clear_cache(wow_dir, args.dry_run, cache_report)

    locales = clientfs.detect_locales(data_dir)
    if args.locale:
        if args.locale not in locales:
            raise Abort("locale %s not found in %s (present: %s)"
                        % (args.locale, data_dir, ", ".join(locales) or "none"))
        locales = [args.locale]
    if not locales:
        raise Abort("no locale folder (enUS, deDE, ...) found in %s" % data_dir)

    previous = read_manifest(wow_dir)
    suffix = (previous or {}).get("suffix")
    if not suffix:
        suffix = clientfs.free_patch_suffix(data_dir, locales)
    if not suffix:
        raise Abort("every patch letter from A to Z is already taken in %s"
                    % data_dir)

    # the program the player runs: WoW.nro on a Switch card, World of
    # Warcraft.app on a Mac, else Wow.exe
    nro_file = find_wow_nro(wow_dir)
    use_app, app = (False, None) if nro_file else uses_app(wow_dir)
    mac = plan_app(args, wow_dir, app) if use_app and args.exe else None
    switch = plan_nro(args, nro_file) if nro_file and args.exe else None

    def yn(on):
        return "yes" if on else "no"

    print("World of Warcraft : %s" % wow_dir)
    print("Locales           : %s" % ", ".join(locales))
    print("Class name        : %s" % args.name)
    print("Creation text     : %s" % yn(args.glue))
    print("Armored outfit    : %s" % yn(args.glue))
    print("Hero class icon   : %s" % yn(args.hero_icon))
    print("Elemental variants: %s" % yn(args.elemental))
    if nro_file:
        print("Patch WoW.nro     : %s" % (
            "no" if not switch else "already patched" if switch[0] == armpatch.PATCHED
            else "yes (%s)" % switch[1]))
    elif use_app:
        print("Patch the Mac app : %s" % (
            "no" if not mac else "already patched" if mac[0] == armpatch.PATCHED
            else "yes (%s)" % mac[1]))
    else:
        print("Patch Wow.exe     : %s" % yn(args.exe))
    print("Addon             : %s" % yn(args.addon))
    if previous:
        print("Note              : replacing a previous install (same letter)")
    print()

    if mac and mac[0] == armpatch.UNPATCHED:
        print("  This installs the full Hero client. World of Warcraft.app is patched")
        print("  the way Wow.exe is on Windows and signed again, which macOS needs to")
        print("  start it. The app you have now is kept as")
        print("  %s and comes back with --uninstall." % os.path.basename(macapp.backup_path(app)))
        print("  CLOSE THE GAME before running this.")
        print()
    elif switch and switch[0] == armpatch.UNPATCHED:
        print("  This installs the full Hero client. WoW.nro is patched the way")
        print("  Wow.exe is on Windows, kept first as WoW.nro.classless-bak, which")
        print("  comes back with --uninstall. CLOSE THE GAME before running this.")
        print()
    elif args.exe and not use_app and not nro_file:
        print("  This installs the full Hero client. The creation-screen text edits")
        print("  a signed interface file, so Wow.exe is patched (the well-known")
        print("  \"allow custom interface\" patch) to accept it, backed up first to")
        print("  Wow.exe.classless-bak and reversible with --uninstall. CLOSE THE")
        print("  GAME before running this, or the patch cannot be written.")
        print()

    if not args.yes and not args.dry_run:
        if sys.stdin and sys.stdin.isatty():
            answer = input("Install to this client? [Y/n] ").strip().lower()
            if answer and not answer.startswith("y"):
                raise Abort("cancelled; nothing was changed")
        print()

    report = []
    written = []

    # First, so a failure stops the install: a client must never be left with
    # the Hero interface files and an app that refuses them.
    if mac:
        patch_app(args, app, mac, report)
    if switch:
        patch_nro(args, nro_file, switch, report)

    # read sources as if OUR OWN previous archives were not there, so a
    # reinstall always builds from the pristine client files, never its output
    def own_archives(locale):
        return {"patch-%s.MPQ" % suffix, "patch-%s-%s.MPQ" % (locale, suffix)}

    # base patch: built once, from the highest-priority locale's chain
    with clientfs.ClientFiles(data_dir, locales[0],
                              exclude=own_archives(locales[0])) as files:
        dbc_payload = build_data_patch(files, args.name, report, theme=args.glue, keep_totems=args.exe)
        # Elemental ability variants: the server's generated spell rows have
        # to exist in the client's own Spell.dbc too, or the game has no name,
        # icon or tooltip for them. Appended to the player's tables, with one
        # painted icon per base icon and element.
        if args.elemental:
            manifest_file = elemental.manifest_path()
            if os.path.exists(manifest_file):
                try:
                    manifest = elemental.load_manifest(manifest_file)
                    elemental.apply(files, dbc_payload, manifest, report)
                except (elemental.ElementalError, dbc.DbcError, FileNotFoundError) as error:
                    report.append("  elemental variants  skipped (%s)" % error)
            else:
                report.append("  elemental variants  skipped (no elemental_manifest.json shipped)")

        # Forged spells: abilities that belong to no class, filed under a Hero
        # tab of their own. Runs after the elemental pass so both extend the
        # same patched Spell.dbc and SkillLineAbility.dbc rather than one
        # overwriting the other.
        hero_talents = ()
        if args.forged:
            manifest_file = forged.manifest_path()
            if os.path.exists(manifest_file):
                try:
                    manifest = forged.load_manifest(manifest_file)
                    forged.apply(files, dbc_payload, manifest, report)
                    hero_talents = forged.modifier_spells(manifest)
                except (forged.ForgedError, dbc.DbcError, FileNotFoundError) as error:
                    report.append("  forged spells       skipped (%s)" % error)
            else:
                report.append("  forged spells       skipped (no forged_manifest.json shipped)")

        # Last, and inside this block on purpose: it needs `files` for the
        # client's Talent.dbc, and it must see the appended rows.
        apply_client_floors(files, dbc_payload, report, hero_talents)
    target = os.path.join(data_dir, "patch-%s.MPQ" % suffix)
    if not args.dry_run:
        mpq.write_archive(target, dbc_payload)
    written.append("Data/patch-%s.MPQ" % suffix)
    report.append("  -> Data/patch-%s.MPQ" % suffix)

    # Locale patches -- and the DBCs go in here TOO, which is the part that
    # actually matters. Wow.exe loads every locale patch archive above every
    # base one (see clientfs.archive_chain), so a DBC that also ships in a
    # patch-<loc>-N archive is shadowed if we only put ours in patch-Z.MPQ.
    # That is every DBC we touch: ChrClasses lives in patch-enUS-3,
    # CharStartOutfit and SkillRaceClassInfo in patch-enUS-2, CharBaseInfo in
    # locale-enUS. For a long time the class rename, the relic-slot fix and
    # the skill-line rows were all written correctly and never loaded, while
    # the Lua and strings -- which always went to the locale archive -- worked,
    # which made it look as though the patch was applying.
    #
    # The base archive is still written so a locale folder without a locale
    # patch of its own is covered, but the locale copy is the one that wins.
    for locale in locales:
        with clientfs.ClientFiles(data_dir, locale,
                                  exclude=own_archives(locale)) as files:
            payload = build_locale_patch(files, args.name, report, locale,
                                         theme=args.glue, icon=args.hero_icon)
        # the painted faces stay in the base archive only: nothing outranks
        # them there, and a second copy would only double the download
        payload.update({k: v for k, v in dbc_payload.items()
                        if not dkfaces.is_generated_name(k)})
        name = "patch-%s-%s.MPQ" % (locale, suffix)
        target = os.path.join(data_dir, locale, name)
        if not args.dry_run:
            mpq.write_archive(target, payload)
        written.append("Data/%s/%s" % (locale, name))
        report.append("  -> Data/%s/%s  (DBCs here outrank the client's own locale patches)"
                      % (locale, name))

    # Wow.exe -- only when installing the creation text, and only with the
    # verified pattern set. A running game locks it; that must not throw away
    # the archives already written, so a lock is reported, not fatal.
    exe_patched = False
    exe_locked = False
    if args.exe and not use_app and not nro_file:
        if not exe:
            report.append("  Wow.exe          SKIPPED, not found")
        elif args.dry_run:
            state, _o, digest, label = exepatch.inspect(exe)
            report.append("  Wow.exe          %s (%s)"
                          % (state, label or "sha256 " + digest[:16]))
        else:
            try:
                report.append("  Wow.exe          %s" % exepatch.apply(exe))
                exe_patched = True
            except PermissionError:
                exe_locked = True
                report.append("  Wow.exe          COULD NOT WRITE: close the "
                              "game and re-run")
            except (OSError, RuntimeError) as error:
                exe_locked = True
                report.append("  Wow.exe          NOT PATCHED: %s" % error)

    addon_rel = None
    if args.addon:
        with clientfs.ClientFiles(data_dir, locales[0],
                                  exclude=own_archives(locales[0])) as files:
            addon_rel = install_addon(wow_dir, args.dry_run, report, files)

    report.extend(cache_report)
    # A client that was open during the run writes its cache back on exit, so
    # what matters is whether anything is there NOW, not whether the delete
    # earlier returned.
    if not args.dry_run and not cache_left and count_cache_files(wow_dir):
        cache_left = count_cache_files(wow_dir)
        report.append("  cache            CAME BACK while installing: the game "
                      "is open. Close it, delete the Cache folder, then start the "
                      "game.")

    write_manifest(wow_dir, {
        "version": 1,
        "suffix": suffix,
        "locales": locales,
        "name": args.name,
        "exe_patched": exe_patched or bool((previous or {}).get("exe_patched")),
        "files": written,
        "addon": addon_rel,
        "creation_text": bool(args.glue),
        # the Mac app, for --uninstall
        "app": app if mac else (previous or {}).get("app"),
        "nro": nro_file if switch else (previous or {}).get("nro"),
    }, args.dry_run)

    print("\n".join(report))
    print()
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0
    remember_client(wow_dir)

    if exe_locked:
        print("Almost done. The game was open, so Wow.exe was not patched and")
        print("the creation-screen text will show as corrupt until it is. Close")
        print("World of Warcraft completely and run this installer again to finish.")
        print()

    # Last thing on screen, because it is the one failure whose symptoms look
    # like a broken patch rather than a skipped step: the player sees question
    # marks and "Out of range" and goes looking for a bug.
    if cache_left:
        print("YOUR CACHE WAS NOT CLEARED. The game is open and holding it.")
        print("Close World of Warcraft, delete the Cache folder in:")
        print("    %s" % wow_dir)
        print("and start the game again. Until you do, new items draw the wrong")
        print("icon and ranged weapons say \"Out of range\".")
        print()

    print("Done. Start the game; every character is now a %s." % args.name)
    if args.glue and not exe_locked:
        print("The creation screen now shows the Hero pitch. If it instead says")
        print("the interface is corrupt, re-run with --uninstall to revert.")
    print("To undo everything:  %s --uninstall \"%s\""
          % ("./install.sh" if sys.platform == "darwin" else "python install.py", wow_dir))
    return 0


# --------------------------------------------------------------- uninstall

# Every file the installer ever writes into a patch archive. An archive is ours
# only if EVERY file in it is one of these -- a client pack's own archive always
# has something else in it, so it can never be matched by luck of the letter.
_OUR_FILES = frozenset(x.lower() for x in (
    CHRCLASSES, CHARBASEINFO, CHARSTARTOUTFIT, SKILLRACECLASSINFO, SKILLLINEABILITY,
    SPELLSHAPESHIFTFORM,
    CHARSECTIONS,
    ITEM,
    TALENTTAB,
    GLUESTRINGS, CHARCREATE_LUA,
    CLASSICONS_INGAME, CLASSICONS_CREATE, CLASSICONS_SCORE,
    framexml.TOTEMFRAME_LUA, framexml.OPTIONS_LUA, framexml.OPTIONS_XML,
    framexml.CONSTANTS_LUA, framexml.RAIDUI_LUA, framexml.PAPERDOLL_LUA,
    framexml.UIPARENT_LUA, framexml.PETBAR_LUA,
    elemental.SPELL, elemental.SPELLVISUAL, elemental.SPELLICON,
    SPELLCATEGORY,
    forged.SKILLLINE, forged.CHARTITLES,
))
# the elemental step paints one icon per (base icon, element); the names are
# derived, so ownership of those is decided by prefix rather than by list
_OUR_ICON_PREFIX = (elemental.ICON_DIR + "cw_").lower()


def _is_ours(name: str) -> bool:
    return (name in _OUR_FILES
            or (name.startswith(_OUR_ICON_PREFIX) and name.endswith(".blp"))
            or dkfaces.is_generated_name(name))


def _is_our_archive(path):
    """True only if every file in this MPQ is one the installer writes.

    Used by uninstall when there is no manifest. Reads the listfile and refuses
    to claim anything with an unexpected file in it, so a client pack's own
    patch archive can never be matched by luck of the patch letter.
    """
    try:
        archive = mpq.MPQArchive(path)
    except Exception:
        return False
    try:
        raw = archive.read_file("(listfile)")
    except Exception:
        return False
    finally:
        archive.close()
    names = {n.strip().lower().replace("/", "\\")
             for n in raw.decode("utf-8", "replace").replace("\r", "\n").split("\n")
             if n.strip() and n.strip().lower() != "(listfile)"}
    return bool(names) and all(_is_ours(n) for n in names)


def do_uninstall(args, wow_dir):
    manifest = read_manifest(wow_dir)
    report = []

    locked = []  # things a running game held onto

    if manifest:
        targets = manifest.get("files", [])
        addon_rel = manifest.get("addon")
    else:
        # No manifest: find our archives by CONTENT, never by filename. A patch
        # letter is not proof of ownership -- the client may ship its own
        # patch-enUS-T.MPQ and friends, and deleting those would break it. Ours
        # are the only archives whose listfile is exactly the files we write.
        targets = []
        data_dir = resolve_child(wow_dir, "Data")
        candidates = []
        for suffix in "ZYXWVUTSRQPONMLKJIHGFEDCBA0123456789":
            candidates.append("Data/patch-%s.MPQ" % suffix)
            for locale in clientfs.detect_locales(data_dir):
                candidates.append("Data/%s/patch-%s-%s.MPQ"
                                  % (locale, locale, suffix))
        for rel in candidates:
            path = os.path.join(wow_dir, rel.replace("/", os.sep))
            if os.path.isfile(path) and _is_our_archive(path):
                targets.append(rel)
        addon_rel = "Interface/AddOns/%s" % ADDON_NAME
        report.append("  no install manifest found; removing archives that "
                      "match our contents only")

    for rel in targets:
        path = os.path.join(wow_dir, rel.replace("/", os.sep))
        if os.path.isfile(path):
            if args.dry_run:
                report.append("  would remove %s" % rel)
                continue
            try:
                os.remove(path)
                report.append("  removed %s" % rel)
            except OSError:
                locked.append(rel)
                report.append("  LOCKED, not removed: %s" % rel)

    if addon_rel:
        path = os.path.join(wow_dir, addon_rel.replace("/", os.sep))
        if os.path.isdir(path):
            if args.dry_run:
                report.append("  would remove %s" % addon_rel)
            else:
                try:
                    shutil.rmtree(path)
                    report.append("  removed %s" % addon_rel)
                except OSError:
                    locked.append(addon_rel)
                    report.append("  LOCKED, not removed: %s" % addon_rel)

    # The Mac app: the stock copy goes back (or the bytes are reverted and the
    # app signed again when there is none).
    app = (manifest or {}).get("app") or macapp.find_app(wow_dir)
    if app and os.path.isdir(app) and macapp.is_wowdecomp(app):
        if args.dry_run:
            if macapp.has_changes(app):
                report.append("  World of Warcraft.app  would put back the stock app")
        else:
            try:
                result = macapp.restore(app)
                if "left alone" not in result:
                    report.append("  World of Warcraft.app  %s" % result)
            except (OSError, macapp.AppError) as error:
                locked.append(macapp.APP_NAME)
                report.append("  World of Warcraft.app  NOT restored: %s" % error)

    # The Switch client: the stock WoW.nro goes back the same way.
    nro_file = (manifest or {}).get("nro") or find_wow_nro(wow_dir)
    if nro_file and os.path.isfile(nro_file):
        if args.dry_run:
            if armpatch.has_file_changes(nro_file):
                report.append("  WoW.nro          would restore the original")
        else:
            try:
                result = armpatch.restore_file(nro_file)
                if "left alone" not in result:
                    report.append("  WoW.nro          %s" % result)
            except (OSError, RuntimeError) as error:
                locked.append("WoW.nro")
                report.append("  WoW.nro          NOT restored: %s" % error)

    # The creation text patches Wow.exe, so always offer to restore it.
    # restore() is a no-op ("was not patched; left alone") when an install
    # ran with --no-creation-text and there is nothing to undo.
    exe = find_wow_exe(wow_dir)
    if exe:
        if args.dry_run:
            if exepatch.has_changes(exe):
                report.append("  Wow.exe          would restore the original")
        else:
            try:
                result = exepatch.restore(exe)
                if "left alone" not in result:
                    report.append("  Wow.exe %s" % result)
            except OSError:
                locked.append("Wow.exe")
                report.append("  Wow.exe          LOCKED, not restored")

    clear_cache(wow_dir, args.dry_run, report)

    # keep the manifest if anything was locked or not rebuilt, so a re-run
    # knows what is still left to undo
    manifest_path = os.path.join(wow_dir, MANIFEST_NAME)
    if os.path.isfile(manifest_path) and not args.dry_run and not locked:
        os.remove(manifest_path)

    print("\n".join(report) if report else "  nothing to remove")
    print()
    if args.dry_run:
        print("Dry run: nothing was written.")
    elif locked:
        print("Some files were in use (the game is running). Close World of")
        print("Warcraft fully and run --uninstall again to finish.")
    else:
        print("Client restored to stock.")
    return 0


# -------------------------------------------------------------------- main

def ensure_library(module, package, why):
    """Install a Python library on the spot when it is missing, and stop if
    that fails."""
    try:
        __import__(module)
        return
    except ImportError:
        pass
    cmd = [sys.executable, "-m", "pip", "install", "--user", package]
    print("The Python library '%s' is needed to %s." % (package, why))
    print("Installing it now:  " + " ".join(cmd))
    print()
    try:
        subprocess.run(cmd, check=True)
    except (OSError, subprocess.CalledProcessError):
        if os.name != "nt":
            # Homebrew's Python refuses --user installs; install.sh's own Python takes them
            raise Abort("'%s' could not be installed automatically. Run this, then ./install.sh again:\n"
                        "  %s -m venv .venv && .venv/bin/python -m pip install pillow %s"
                        % (package, os.path.basename(sys.executable), package))
        raise Abort("'%s' could not be installed automatically. Run this, then run the installer "
                    "again:\n  %s" % (package, " ".join(cmd)))
    import importlib
    import site
    importlib.invalidate_caches()
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)
    try:
        __import__(module)
    except ImportError:
        raise Abort("'%s' was installed but this Python cannot import it. Run this, then try again:\n"
                    "  %s" % (package, " ".join(cmd)))
    print()


def ensure_pillow():
    """The install paints the Hero emblem and the elemental icons, so the
    Python 'Pillow' library is required."""
    ensure_library("PIL", "pillow", "paint the Hero and elemental icons")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the mod-classless-wildcard client patch and addon.",
        epilog="With no folder given, common install locations are searched.")
    parser.add_argument("wow_folder", nargs="?",
                        help="the folder containing Wow.exe and Data")
    parser.add_argument("--uninstall", action="store_true",
                        help="remove everything this installer added")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would happen, write nothing")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="do not ask for confirmation")
    parser.add_argument("--locale", help="patch only this locale, e.g. enUS")
    parser.add_argument("--name", default="Hero",
                        help="what every class is called (default: Hero)")
    parser.add_argument("--no-addon", dest="addon", action="store_false",
                        help="do not install the in-game addon")
    # The full Hero client is the default. These turn single pieces OFF for
    # maintainers; a player's install is always the full one.
    parser.add_argument("--no-creation-text", dest="glue", action="store_false",
                        help="skip the Hero creation-screen text and armored "
                             "outfit (and the Wow.exe patch they need)")
    parser.add_argument("--no-forged", dest="forged", action="store_false",
                        help="skip the forged spells and the Hero spellbook tab")
    parser.add_argument("--no-elemental", dest="elemental", action="store_false",
                        help="leave out the elemental ability variants (spell rows and icons)")
    parser.add_argument("--no-hero-icon", dest="hero_icon", action="store_false",
                        help="keep the stock class icon instead of the Hero emblem")
    parser.add_argument("--no-exe", dest="exe_ok", action="store_false",
                        help="install the creation text but do NOT patch Wow.exe "
                             "(only for clients that already accept custom "
                             "interface files)")
    args = parser.parse_args(argv)
    # Wow.exe is patched only when installing the creation text, and only with
    # the verified community pattern set in lib/exepatch.py.
    args.exe = args.glue and args.exe_ok
    if not args.uninstall:
        ensure_pillow()

    print("mod-classless-wildcard client installer")
    print("=" * 39)
    print()

    wow_dir = args.wow_folder or autodetect_client()
    if wow_dir:
        wow_dir = os.path.abspath(os.path.expanduser(wow_dir.strip().strip('"')))
    if not looks_like_client(wow_dir):
        typed = prompt_for_client()
        wow_dir = os.path.abspath(os.path.expanduser(typed)) if typed else None

    if not looks_like_client(wow_dir):
        raise Abort(
            "That is not a World of Warcraft folder.\n"
            "Give me the folder that contains the Data folder (and Wow.exe, "
            "World of Warcraft.app or WoW.nro), for example:\n"
            + ("    ./install.sh \"$HOME/Games/World of Warcraft\"" if sys.platform == "darwin"
               else "    python install.py \"C:\\Games\\World of Warcraft\""))

    if args.uninstall:
        return do_uninstall(args, wow_dir)
    return do_install(args, wow_dir)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as error:
        print("\n%s" % error, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        sys.exit(130)
    except PermissionError as error:
        print("\nPermission denied: %s\n"
              "Close World of Warcraft if it is running. On Windows, if the "
              "client is under C:\\Program Files, run the installer as "
              "Administrator." % error, file=sys.stderr)
        sys.exit(1)
    except OSError as error:
        print("\nFile error: %s" % error, file=sys.stderr)
        sys.exit(1)
