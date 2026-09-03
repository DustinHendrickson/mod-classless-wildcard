#!/usr/bin/env python3
"""Render every shipped base icon in every element, from a real client's art,
into one preview sheet, so a hue change can be judged before anyone reinstalls.

    python3 preview_elemental_icons.py [WOW_FOLDER] [--out preview.png]

Reads the base icons through the client's archive chain exactly as the
installer does, paints them with lib/elemental.render_icon, and lays them out
at twice the 36px the game draws icons at. Column one is the untouched base.
Writes nothing to the client. Needs Pillow.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from lib import blp, clientfs, elemental  # noqa: E402
import install  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wow_folder", nargs="?", help="World of Warcraft 3.3.5a folder (autodetected if omitted)")
    ap.add_argument("--out", default=os.path.join(HERE, "elemental_icons_preview.png"))
    ap.add_argument("--manifest", default=elemental.manifest_path())
    args = ap.parse_args(argv)

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        sys.exit("Pillow is required: python3 -m pip install --user pillow")

    wow = args.wow_folder or install.autodetect_client()
    if not wow or not install.looks_like_client(wow):
        sys.exit("no 3.3.5a client at %r; pass the WoW folder" % wow)
    data_dir = os.path.join(wow, "Data")
    locales = clientfs.detect_locales(data_dir)
    if not locales:
        sys.exit("no locale folder in %s" % data_dir)

    manifest = elemental.load_manifest(args.manifest)
    elements = manifest["elements"]
    bases = {}
    for v in manifest["variants"]:
        bases.setdefault(v["icon"]["base_path"], v["icon"])
    if not bases:
        sys.exit("manifest has no variants")

    cell, gap, scale = 36, 6, 2
    cols, rows = 1 + len(elements), len(bases)
    width = gap + cols * (cell * scale + gap)
    height = gap + rows * (cell * scale + gap + 14)
    sheet = Image.new("RGB", (width, height), (28, 28, 32))
    draw = ImageDraw.Draw(sheet)

    with clientfs.ClientFiles(data_dir, locales[0]) as files:
        for r, (path, icon) in enumerate(sorted(bases.items())):
            try:
                raw, _source = files.find(path + ".blp")
            except FileNotFoundError:
                print("missing in client: %s" % path)
                continue
            w, h, rgba = blp.decode_blp(raw)
            cells = [("base", Image.frombytes("RGBA", (w, h), rgba).convert("RGB"))]
            for e in elements:
                painted = elemental.render_icon(raw, dict(icon, element=e["key"], hue=e["hue"], glyph=e["glyph"]))
                pw, ph, prgba = blp.decode_blp(painted)
                cells.append((e["key"], Image.frombytes("RGBA", (pw, ph), prgba).convert("RGB")))
            y = gap + r * (cell * scale + gap + 14)
            draw.text((gap, y + cell * scale + 1), path.split("\\")[-1], fill=(200, 200, 200))
            for c, (name, im) in enumerate(cells):
                x = gap + c * (cell * scale + gap)
                sheet.paste(im.resize((cell * scale, cell * scale), Image.LANCZOS), (x, y))
                if r == 0:
                    draw.text((x, 0), name, fill=(230, 230, 230))

    sheet.save(args.out)
    print("wrote %s (%dx%d): %d base icon(s) x %d element(s)" % (args.out, width, height, rows, len(elements)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
