"""Check that no module SQL file deletes rows another module SQL file writes.

The updater applies every file in data/sql/db-world (and db-characters) in name
order, and re-applies any one whose text changed. So a file that clears a whole
id band with `DELETE ... BETWEEN` wipes whatever an earlier file put inside it,
and a later re-run of either file breaks the other again. That is how
cw_world_vendor_lists.sql deleted the forged summons (990110..990119) and
cw_world_skillraceclass.sql deleted the Hero skill line's row (990500).

For every single-column DELETE (`= N`, `IN (...)`, `BETWEEN a AND b`) this
finds the rows other files insert into that table whose value in the same
column falls inside it. Deletes with a compound or joined condition are
narrower than any one column, so they are not counted.

Run:  python3 validate_id_ranges.py      (exits non-zero on a collision)
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_DIRS = [os.path.join(HERE, os.pardir, d) for d in ("db-world", "db-characters")]

DELETE = re.compile(r"DELETE\s+FROM\s+`?(\w+)`?\s+WHERE\s+`?(\w+)`?\s*"
                    r"(?:BETWEEN\s+(\d+)\s+AND\s+(\d+)|IN\s*\(([^)]*)\)|=\s*(\d+))\s*;", re.I)
INSERT = re.compile(r"(?:INSERT|REPLACE)\s+(?:IGNORE\s+)?INTO\s+`?(\w+)`?\s*\(([^)]*)\)\s*VALUES", re.I)
# cw_world_vendor_lists.sql clones a row through a temporary table:
#   CREATE TEMPORARY TABLE `cw_vlist` AS SELECT * FROM `creature_template` ...
#   UPDATE `cw_vlist` SET `entry` = N, ...
#   INSERT INTO `creature_template` SELECT * FROM `cw_vlist`;
CLONE = re.compile(r"CREATE\s+TEMPORARY\s+TABLE\s+`?(\w+)`?\s+AS\s+SELECT\s+\*\s+FROM\s+`?(\w+)`?.*?"
                   r"UPDATE\s+`?\1`?\s+SET\s+`?(\w+)`?\s*=\s*(\d+)", re.I | re.S)


def strip_comments(text):
    """Drop -- comments outside string literals."""
    out, i, quoted = [], 0, False
    while i < len(text):
        c = text[i]
        if quoted:
            out.append(c)
            if c == "\\":
                out.append(text[i + 1:i + 2])
                i += 2
                continue
            if c == "'":
                quoted = False
            i += 1
            continue
        if c == "'":
            quoted = True
        elif text.startswith("--", i):
            j = text.find("\n", i)
            i = len(text) if j < 0 else j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def tuples(text, start):
    """The top-level (...) groups of a VALUES list, as lists of raw values,
    up to the statement's closing semicolon."""
    rows, depth, quoted, buf, row = [], 0, False, [], []
    i = start
    while i < len(text):
        c = text[i]
        if quoted:
            buf.append(c)
            if c == "\\":
                buf.append(text[i + 1:i + 2])
                i += 2
                continue
            if c == "'":
                quoted = False
        elif c == "'":
            quoted = True
            buf.append(c)
        elif c == "(":
            depth += 1
            if depth > 1:
                buf.append(c)
        elif c == ")":
            depth -= 1
            if depth == 0:
                row.append("".join(buf).strip())
                rows.append(row)
                buf, row = [], []
            else:
                buf.append(c)
        elif c == "," and depth == 1:
            row.append("".join(buf).strip())
            buf = []
        elif c == ";" and depth == 0:
            break
        elif depth >= 1:
            buf.append(c)
        i += 1
    return rows


def load():
    deletes = []    # (file, table, column, lo, hi)
    written = []    # (file, table, {column: int value})
    for d in SQL_DIRS:
        for name in sorted(os.listdir(d)):
            if not name.endswith(".sql"):
                continue
            text = strip_comments(io.open(os.path.join(d, name), encoding="utf-8").read())
            for m in DELETE.finditer(text):
                table, col = m.group(1).lower(), m.group(2).lower()
                if m.group(3):
                    deletes.append((name, table, col, int(m.group(3)), int(m.group(4))))
                else:
                    for v in re.findall(r"-?\d+", m.group(5) or m.group(6)):
                        deletes.append((name, table, col, int(v), int(v)))
            for m in INSERT.finditer(text):
                cols = [c.strip().strip("`").lower() for c in m.group(2).split(",")]
                for row in tuples(text, m.end()):
                    values = {c: int(v) for c, v in zip(cols, row) if re.fullmatch(r"-?\d+", v)}
                    written.append((name, m.group(1).lower(), values))
            for m in CLONE.finditer(text):
                written.append((name, m.group(2).lower(), {m.group(3).lower(): int(m.group(4))}))
    return deletes, written


def main():
    deletes, written = load()
    hits = []
    for name, table, col, lo, hi in deletes:
        victims = sorted({(src, v[col]) for src, t, v in written
                          if t == table and src != name and col in v and lo <= v[col] <= hi})
        if victims:
            hits.append("%s deletes %s.%s %d..%d, wiping %s"
                        % (name, table, col, lo, hi,
                           ", ".join("%s %d" % (src, val) for src, val in victims[:6])
                           + (" and %d more" % (len(victims) - 6) if len(victims) > 6 else "")))
    print("%d deletes checked against %d written rows" % (len(deletes), len(written)))
    for h in hits:
        print("  COLLISION " + h)
    if hits:
        sys.exit(1)
    print("no file deletes another file's rows")


if __name__ == "__main__":
    main()
