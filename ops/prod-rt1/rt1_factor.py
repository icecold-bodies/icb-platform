"""RT1 Manifest F — the stored PU 4G factor (RT1 ruling 2 §2a). ONE admin setting:

    admin_settings['costings.pu_foam_4g_factor']   '1.3170731707317074'  ->  '1.362881562881563'
                                                    Burt's September        Burt's 21 Sep list
                                                    5 400 / 4 100           5 581 / 4 095

The MES stores one price per PU foam line (the 32D one) and prices a 4G quote's PU foam lines at that price x this
factor (app/services/insulation_foam.py). Prod's PU material has held Burt's 21 Sep 32D price (R4 095) since 29 Sep;
with the September factor a 4G line prices at R5 393.41 against Burt's R5 581. The factor is read on every
calculation (no cache), so the change takes effect on the next calculation: no restart, no deploy. The code fallback
FACTOR_4G_DEFAULT (5 875 / 4 310) is left alone; it is only used when the row is missing or unparseable.

    DATABASE_URL=...  python rt1_factor.py --target prod|mirror                           dry-run, READ ONLY
    DATABASE_URL=...  python rt1_factor.py --target prod|mirror --apply --out-dir DIR     one transaction + journal
    DATABASE_URL=...  python rt1_factor.py --target prod|mirror --revert J --out-dir DIR  value AND updated_at back

Guards: apply needs the row to hold exactly BEFORE; revert needs it to hold exactly what the journal wrote (value
and updated_at). Anything else refuses with exit 2 and writes nothing. Idempotent: apply over F, or revert over a
reverted row, is a no-op. psycopg only, independent of the app code, so it runs over v1.59.0 or v1.59.2. The dry-run
also lists the saved costings graded 4G (quote numbers only); no customer, contact, user or person column is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg

KEY = "costings.pu_foam_4g_factor"
BEFORE = "1.3170731707317074"    # repr(5400 / 4100), written by tools/september_price_import.py (v1.52)
AFTER = "1.362881562881563"      # repr(5581 / 4095)
assert BEFORE == repr(5400 / 4100) and AFTER == repr(5581 / 4095) and float(AFTER) == 5581 / 4095
P32 = 4095.0                     # the shared PU material on prod since 29 Sep = Burt's 21 Sep 32D
TARGETS = {"prod": "icb_platform", "mirror": "icb_prodmirror"}
TABLE = "icb_costings.admin_settings"
PLAN_TODO = "1 to apply, 0 already applied."
PLAN_DONE = "0 to apply, 1 already applied."
FOAM_4G = re.compile(r"^\s*4G(\s*FOAM)?\s*$", re.I)   # insulation_foam.normalise: 4G / 4G FOAM / 4GFOAM


class Refused(Exception):
    """A guard refused: the row is not where F says. Raised inside the transaction, so nothing is written."""


def tool_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def connect(target: str, read_only: bool):
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    if not url:
        raise SystemExit("REFUSED: DATABASE_URL is not set")
    kw = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    cx = psycopg.connect(url, autocommit=True, **kw)
    db = cx.execute("select current_database()").fetchone()[0]
    if db != TARGETS[target]:
        cx.close()
        raise SystemExit(f"REFUSED: --target {target} expects database {TARGETS[target]!r}; this is {db!r}")
    return cx, db


def read_row(cx, lock: bool = False):
    rows = cx.execute(f"select id, value, updated_at::text from {TABLE} where key = %s" + (" for update" if lock else ""),
                      (KEY,)).fetchall()
    return rows[0] if rows else None


def show_price(value: str) -> str:
    try:
        return f"R{P32 * float(value):,.2f}"
    except ValueError:
        return "(not a number)"


def impact(cx) -> None:
    """Saved costings graded 4G (input_state.insulation_foam), not deleted — quote numbers only."""
    rows = cx.execute(r"""select c.quote_number, c.status, c.created_at::date::text, t.name, c.result_json
                          from icb_costings.calculations c
                          left join icb_costings.trailer_types t on t.id = c.trailer_type_id
                          where c.deleted_at is null and c.result_json ~* '"insulation_foam"\s*:\s*"4G'
                          order by c.created_at""").fetchall()
    hits = []
    for qn, status, day, body, rj in rows:
        try:
            ist = (json.loads(rj) or {}).get("input_state") or {}
        except (ValueError, TypeError, AttributeError):
            continue
        if FOAM_4G.match(str(ist.get("insulation_foam") or "")):
            hits.append((qn, status, day, body))
    by = Counter(h[1] for h in hits)
    print(f"saved costings graded 4G (not deleted): {len(hits)}" + (f" — by status {dict(sorted(by.items()))}" if hits else ""))
    print("   a saved costing keeps its saved totals; one re-opened and re-calculated after F prices its PU foam at the new factor")
    for qn, status, day, body in hits[:80]:
        print(f"   {qn or '(no quote number)'} | {status} | saved {day} | {body}")
    if len(hits) > 80:
        print(f"   … and {len(hits) - 80} more")


def dry_run(cx, db: str, target: str) -> int:
    print(f"database {db} (--target {target}); Manifest F: admin_settings[{KEY!r}]; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        cx.execute("set transaction read only")
        row = read_row(cx)
        if row is None:
            print(f"  REFUSED: no admin_settings row {KEY!r} (the calculator is on the code fallback); F updates an existing row only")
            return 2
        rid, value, upd = row
        print(f"  row id {rid}  value {value!r}  updated_at {upd}")
        if value == AFTER:
            print(f"  done  {BEFORE!r} -> {AFTER!r}")
            print(PLAN_DONE)
            print("nothing to apply.")
            impact(cx)
            return 0
        if value != BEFORE:
            print(f"  REFUSED: the value is {value!r}; F expects exactly {BEFORE!r} (or {AFTER!r} once applied). Nothing written.")
            return 2
        print(f"  APPLY {BEFORE!r} -> {AFTER!r}  (x {float(AFTER) / float(BEFORE)!r})")
        print(f"        a 4G PU foam line on the R{P32:,.0f} material: {show_price(BEFORE)} -> {show_price(AFTER)} per m³ (Burt's 4G: R5,581.00)")
        print("        32D quotes, EPS quotes and every non-foam line: unchanged")
        print(PLAN_TODO)
        print("(DRY RUN — nothing written. Re-run with --apply.)")
        impact(cx)
    return 0


def write_file(out_dir: Path, stem: str, data: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{stem}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    part = final.with_name(final.name + ".part")
    with open(part, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return part, final


def apply(cx, db: str, target: str, out_dir: Path) -> int:
    print(f"database {db} (--target {target}); Manifest F: admin_settings[{KEY!r}]; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        row = read_row(cx, lock=True)
        if row is None:
            raise Refused(f"no admin_settings row {KEY!r}")
        rid, value, upd = row
        if value == AFTER:
            print(f"  done  row id {rid} already holds {AFTER!r} (updated_at {upd})")
            print(PLAN_DONE)
            print("nothing to apply.")
            return 0
        if value != BEFORE:
            raise Refused(f"row id {rid} holds {value!r}; F expects exactly {BEFORE!r}")
        got = cx.execute(f"update {TABLE} set value = %s, updated_at = now() where id = %s and key = %s and value = %s "
                         f"returning value, updated_at::text", (AFTER, rid, KEY, BEFORE)).fetchall()
        if len(got) != 1 or got[0][0] != AFTER:
            raise RuntimeError(f"the update touched {len(got)} row(s): {got!r}")
        journal = {"tool": "rt1_factor", "manifest": "F", "tool_sha256": tool_sha(), "target": target, "database": db,
                   "key": KEY, "row_id": rid,
                   "before": {"value": value, "updated_at": upd},
                   "after": {"value": got[0][0], "updated_at": got[0][1]},
                   "applied_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        part, final = write_file(out_dir, f"rt1_factor_journal_{target}", journal)
        print(f"  APPLY row id {rid}: {value!r} -> {AFTER!r}  updated_at {upd} -> {got[0][1]}")
    part.replace(final)        # the journal gets its final name only once the transaction has committed
    with cx.transaction():
        cx.execute("set transaction read only")
        now = read_row(cx)
    if now is None or now[1] != AFTER:
        print(f"!! after commit the row reads {now!r} — tell the CA")
        return 1
    print(f"APPLIED 1 change (admin_settings id {rid}). Journal: {final}")
    print(f"Undo: python rt1_factor.py --target {target} --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, target: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "rt1_factor" or j.get("manifest") != "F" or j.get("key") != KEY:
        raise SystemExit(f"REFUSED: {jpath} is not a Manifest F journal")
    if j.get("database") != db or j.get("target") != target:
        raise SystemExit(f"REFUSED: the journal was written on {j.get('database')!r} (--target {j.get('target')}); this is {db!r}")
    b, a, rid = j["before"], j["after"], j["row_id"]
    print(f"database {db} (--target {target}); revert Manifest F from {jpath.name}; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        row = read_row(cx, lock=True)
        if row is None or row[0] != rid:
            raise Refused(f"admin_settings row {KEY!r} is {row!r}; the journal names id {rid}")
        _, value, upd = row
        if value == b["value"] and upd == b["updated_at"]:
            print(f"  done  row id {rid} already holds the journal's before-state ({value!r}, updated_at {upd})")
            print("nothing to revert.")
            return 0
        if value != a["value"] or upd != a["updated_at"]:
            raise Refused(f"row id {rid} moved since F: it holds ({value!r}, {upd}), F wrote ({a['value']!r}, {a['updated_at']})")
        got = cx.execute(f"update {TABLE} set value = %s, updated_at = %s::timestamp where id = %s and value = %s "
                         f"returning value, updated_at::text", (b["value"], b["updated_at"], rid, a["value"])).fetchall()
        if got != [(b["value"], b["updated_at"])]:
            raise RuntimeError(f"the revert wrote {got!r}, expected {[(b['value'], b['updated_at'])]!r}")
        part, final = write_file(out_dir, f"rt1_factor_revert_{target}",
                                 {"tool": "rt1_factor", "manifest": "F", "reverted_journal": jpath.name, "row_id": rid,
                                  "from": a, "to": b, "reverted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"  REVERT row id {rid}: ({value!r}, {upd}) -> ({b['value']!r}, {b['updated_at']})")
    part.replace(final)
    with cx.transaction():
        cx.execute("set transaction read only")
        now = read_row(cx)
    if now != (rid, b["value"], b["updated_at"]):
        print(f"!! after commit the row reads {now!r}, not the journal's before-state — tell the CA")
        return 1
    print(f"REVERTED byte-exact: value {b['value']!r}, updated_at {b['updated_at']}. Record: {final}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true")
    g.add_argument("--revert", metavar="JOURNAL")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if (a.apply or a.revert) and not a.out_dir:
        ap.error("--apply / --revert need --out-dir")
    cx, db = connect(a.target, read_only=not (a.apply or a.revert))
    try:
        if a.apply:
            return apply(cx, db, a.target, Path(a.out_dir))
        if a.revert:
            return revert(cx, db, a.target, Path(a.revert), Path(a.out_dir))
        return dry_run(cx, db, a.target)
    except Refused as e:
        print(f"  REFUSED: {e}. The transaction rolled back; nothing written.")
        return 2
    finally:
        cx.close()


if __name__ == "__main__":
    sys.exit(main())
