"""RT9 close (RT9_RULING_2 Q1) - the checked backup against the live costings, row by row. READ ONLY: two streams in,
allow-listed text out. Standard library only (prod's venv python runs it with -I).

    python -I rt9_quotes_filter.py --dump <stream> --now <stream> --columns a,b,c --deploy-count 92 --today 2026-10-22

  --dump     pg_restore --data-only -n icb_costings -t calculations -f - <the deploy's .dump>: a SQL script holding
             ONE COPY block (never restored; rt9_quotes.sh hands it over as a pipe, nothing lands on disk)
  --now      psql -c "copy (select * from icb_costings.calculations order by id) to stdout": the live rows, the same
             COPY text format from the same server, so a row that did not change is byte-identical
  --columns  the live table's columns in order (information_schema), for the --now stream

Prints ONLY the fields in ALLOW: id; the quote number's FIRST WORD (a repair's number carries the customer's name);
created_at as stored; version and the total from result_json (nothing else out of it); status; soft-deleted Y/N;
net_total; and, for a changed row, the NAMES of the changed columns. emit() refuses any other field name before it is
printed (RefusedOutput): the negative control in backend/tests/test_ops_rt9.py. No value of any other column is read
into the output.

Exit 0 = compared (the last line is SUMMARY: ...); 2 = refused or cannot parse; 3 = the backup holds a different
number of rows than the deploy recorded (it is not the deploy's state).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta

TABLE = "icb_costings.calculations"
NEEDED = ("id", "quote_number", "created_at", "status", "deleted_at", "net_total", "result_json")
ALLOW = ("id", "quote", "created", "version", "status", "deleted", "selling", "net_total", "changed_columns")
ROW = ("id", "quote", "created", "version", "status", "deleted", "selling", "net_total")
CHANGED = ("id", "quote", "changed_columns")
HEADER = "id | quote | created (as stored) | version | status | deleted | selling (result_json) | net total"
_ESC = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}


class RefusedOutput(Exception):
    """A field outside the allow-list was about to be printed."""


class ParseError(Exception):
    """The stream is not one COPY block of the costings table."""


def emit(fields: dict, order=ROW) -> str:
    bad = sorted(set(fields) - set(ALLOW))
    if bad:
        raise RefusedOutput(f"refusing to print {', '.join(bad)}: not in the allow-list ({', '.join(ALLOW)})")
    return " | ".join("-" if fields.get(k) is None else str(fields[k]) for k in order if k in fields)


def unescape(field: str):
    """COPY text format -> the value (None for \\N). COPY TO emits only \\b \\f \\n \\r \\t \\v \\\\ (no octal/hex)."""
    if field == "\\N":
        return None
    out, i = [], 0
    while i < len(field):
        c = field[i]
        if c == "\\" and i + 1 < len(field):
            out.append(_ESC.get(field[i + 1], field[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_dump(path: str):
    """The columns and rows of the table's one COPY block in a pg_restore --data-only script."""
    columns, rows, state = None, [], 0
    with open(path, encoding="utf-8", newline="\n") as fh:
        for line in fh:
            # a bare CR at the end is a Windows-side pipe's line ending (prod's pipes have none): COPY writes a CR
            # inside a value as the two characters backslash-r, so stripping it never touches data
            line = line.rstrip("\n").rstrip("\r")
            if state == 0:
                if line.startswith("COPY "):
                    m = re.match(r'COPY (\S+) \((.*)\) FROM stdin;$', line)
                    if not m:
                        raise ParseError(f"unreadable COPY line: {line[:60]}")
                    if m.group(1) != TABLE:
                        raise ParseError(f"the stream holds {m.group(1)}, not {TABLE}")
                    columns = [c.strip().strip('"') for c in m.group(2).split(",")]
                    state = 1
            elif state == 1:
                if line == "\\.":
                    state = 2
                else:
                    rows.append(line.split("\t"))
            elif line.startswith("COPY "):
                raise ParseError("a second COPY block in the stream")
    if columns is None or state != 2:
        raise ParseError(f"no complete COPY block for {TABLE} in the stream")
    return columns, rows


def parse_now(path: str):
    with open(path, encoding="utf-8", newline="\n") as fh:
        return [line.rstrip("\n").rstrip("\r").split("\t") for line in fh if line.rstrip("\n").rstrip("\r") != ""]


def as_dicts(columns, rows):
    out = {}
    for r in rows:
        if len(r) != len(columns):
            raise ParseError(f"a row has {len(r)} fields, the table {len(columns)} columns")
        d = dict(zip(columns, r))
        out[int(d["id"])] = d
    return out


def _money(v):
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "-"


def view(row: dict) -> dict:
    """The allow-listed view of one row: nothing from result_json but version and the total."""
    data = {}
    rj = unescape(row["result_json"])
    if rj:
        try:
            data = json.loads(rj)
        except ValueError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    total = data.get("grand_total", data.get("selling_price"))
    created = unescape(row["created_at"]) or ""
    quote = unescape(row["quote_number"]) or "(none)"
    return {"id": int(row["id"]), "quote": quote.split(" ")[0], "created": created[:19],
            "version": data.get("version", "?"), "status": unescape(row["status"]) or "-",
            "deleted": "N" if unescape(row["deleted_at"]) is None else "Y",
            "selling": _money(total), "net_total": _money(unescape(row["net_total"]))}


def _created(row: dict):
    try:
        return datetime.strptime((unescape(row["created_at"]) or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--now", required=True)
    ap.add_argument("--columns", required=True)
    ap.add_argument("--deploy-count", type=int, required=True)
    ap.add_argument("--today", required=True, help="YYYY-MM-DD: rows created from 2 h before this day's start are listed")
    a = ap.parse_args(argv)
    try:
        dcols, drows = parse_dump(a.dump)
        ncols = [c.strip() for c in a.columns.split(",") if c.strip()]
        nrows = parse_now(a.now)
        missing = [c for c in NEEDED if c not in dcols or c not in ncols]
        if missing:
            raise ParseError(f"column(s) missing: {', '.join(missing)}")
        if set(dcols) != set(ncols):
            raise ParseError(f"the backup's columns differ from the live table's: {sorted(set(dcols) ^ set(ncols))}")
        dump, now = as_dicts(dcols, drows), as_dicts(ncols, nrows)
    except (ParseError, ValueError, OSError) as e:
        print(f"REFUSED: {e}")
        return 2
    if len(dump) != a.deploy_count:
        print(f"REFUSED: the backup holds {len(dump)} rows; the deploy recorded {a.deploy_count} saved costings")
        return 3
    try:
        added = sorted(i for i in now if i not in dump)
        removed = sorted(i for i in dump if i not in now)
        changed = []
        for i in sorted(set(dump) & set(now)):
            cols = [c for c in dcols if dump[i][c] != now[i][c]]
            if cols:
                changed.append((i, cols))
        day0 = datetime.strptime(a.today, "%Y-%m-%d") - timedelta(hours=2)
        today = sorted((i for i in now if (_created(now[i]) or datetime.min) >= day0), reverse=True)
        print(f"== the backup: {len(dump)} rows (max id {max(dump) if dump else '-'}); now: {len(now)} rows (max id {max(now) if now else '-'})")
        print(f"== added since the backup: {len(added)}")
        if added:
            print("   " + HEADER)
        for i in added:
            print("   " + emit(view(now[i])))
        print(f"== changed since the backup: {len(changed)}  (id | quote | the changed columns' names; never their values)")
        for i, cols in changed:
            v = view(now[i])
            print("   " + emit({"id": v["id"], "quote": v["quote"], "changed_columns": ", ".join(cols)}, CHANGED))
        print(f"== removed since the backup: {len(removed)}")
        for i in removed:
            print("   " + emit(view(dump[i])))
        print(f"== rows created on {a.today} (as stored, 2 h of leeway for the zone), newest first: {len(today)}")
        if today:
            print("   " + HEADER)
        for i in today:
            flag = "   <- added since the backup" if i in added else ""
            print("   " + emit(view(now[i])) + flag)
        print(f"SUMMARY: backup {len(dump)} rows; now {len(now)} rows; added {len(added)}, changed {len(changed)}, "
              f"removed {len(removed)}; created today {len(today)}")
    except RefusedOutput as e:
        print(f"REFUSED: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
