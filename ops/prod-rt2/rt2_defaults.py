"""RT2 Manifest D — the four 4G body defaults (RT2_RULING_1 R6, Part 1c). FOUR rows of trailer_types:

    trailer_types.default_insulation_foam   '32D' -> '4G'   on
        12 MEAT HANGER LARGE · 36 MEAT HANGER SMALL-MEDIUM · 24 EXPLOSIVE 4.9 AND UP · 15 RHINORANGE TRAILER

A NEW costing on these bodies then opens on 4G FOAM (calculator.js _bodyDefaultFoam, labelled "4G (body default)");
a saved costing keeps its own grade; every other body stays 32D. The column is migration 0050 (v1.59.3), so D runs
only over v1.59.3. It takes effect on the next costing opened: no restart.

ORDER — D goes AFTER Manifest P. Before P, some of these bodies' PU foam lines carry their OWN price, set at a 4G
price (EXPLOSIVE 4.9 AND UP's, RHINORANGE's at the September 4G); the engine prices a 4G quote's PU foam line at its
price x the stored 4G factor (app/routers/calculator.py, insulation_foam.price_multiplier), so a 4G default over an
own 4G price would charge 4G twice. The guard: none of the four bodies has an active PU foam line (material PU /
PU FOAM, not a body option) with its own price. That is exactly what P leaves (G1: only the 18 chiller lines keep
one, and no chiller is here).

    DATABASE_URL=...  python rt2_defaults.py --target prod|mirror                                  dry-run
    DATABASE_URL=...  python rt2_defaults.py --target prod|mirror --apply --out-dir DIR            apply
    DATABASE_URL=...  python rt2_defaults.py --target prod|mirror --revert J --out-dir DIR         revert

Guards: apply needs every row to hold exactly (id, name, active, '32D'), or '4G' (already applied: a no-op);
revert needs every journaled row to hold exactly what the journal wrote. Anything else refuses with exit 2 and
writes nothing (one transaction, rows locked). trailer_types has no updated_at: the journal records the one column,
before and after, per row. psycopg only, independent of the app code. Reads no customer, contact, user or person
column (the saved-costing count is a count).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

BODIES = {12: "MEAT HANGER LARGE", 36: "MEAT HANGER SMALL-MEDIUM", 24: "EXPLOSIVE 4.9 AND UP", 15: "RHINORANGE TRAILER"}
BEFORE, AFTER = "32D", "4G"
TARGETS = {"prod": "icb_platform", "mirror": "icb_prodmirror"}
PU_FOAM = ["PU", "PU FOAM"]          # app/services/insulation_foam.PU_FOAM_MATERIAL_NAMES
TABLE = "icb_costings.trailer_types"


class Refused(Exception):
    """A guard refused: the rows are not where D says. Raised inside the transaction, so nothing is written."""


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


def has_column(cx) -> bool:
    return cx.execute("""select count(*) from information_schema.columns where table_schema = 'icb_costings'
                         and table_name = 'trailer_types' and column_name = 'default_insulation_foam'""").fetchone()[0] == 1


def read_rows(cx, lock: bool = False) -> dict[int, tuple]:
    rows = cx.execute(f"select id, name, is_active, default_insulation_foam from {TABLE} where id = any(%s) order by id"
                      + (" for update" if lock else ""), (list(BODIES),)).fetchall()
    return {r[0]: r[1:] for r in rows}


def own_priced_pu(cx) -> list[tuple]:
    """Active PU foam lines with their OWN price on the four bodies — P removes every one of them."""
    return cx.execute("""select b.trailer_type_id, b.id, b.bom_section, b.unit_price_override
                         from icb_costings.bill_of_materials b join icb_costings.materials m on m.id = b.material_id
                         where b.trailer_type_id = any(%s) and upper(trim(m.name)) = any(%s)
                           and not coalesce(b.is_body_option, false) and b.unit_price_override is not null
                         order by b.trailer_type_id, b.id""", (list(BODIES), PU_FOAM)).fetchall()


def others_4g(cx) -> list[tuple]:
    return cx.execute(f"select id, name from {TABLE} where default_insulation_foam = %s and not (id = any(%s)) order by id",
                      (AFTER, list(BODIES))).fetchall()


def check(cx) -> tuple[list[int], list[int]]:
    """(to apply, already applied) — or Refused. Every guard, before any write."""
    if not has_column(cx):
        raise Refused("trailer_types has no default_insulation_foam column: D goes over v1.59.3 (alembic 0050) only")
    rows = read_rows(cx)
    todo, done = [], []
    for tid, name in BODIES.items():
        if tid not in rows:
            raise Refused(f"no body id {tid} ({name})")
        rname, active, foam = rows[tid]
        if rname != name:
            raise Refused(f"body id {tid} is named {rname!r}; D expects {name!r}")
        if not active:
            raise Refused(f"body id {tid} {name} is not active")
        if foam == AFTER:
            done.append(tid)
        elif foam == BEFORE:
            todo.append(tid)
        else:
            raise Refused(f"body id {tid} {name} holds {foam!r}; D expects exactly {BEFORE!r} (or {AFTER!r} once applied)")
    own = own_priced_pu(cx)
    if todo and own:
        lines = "; ".join(f"body {t} bom {b} {s} own R{p}" for t, b, s, p in own)
        raise Refused(f"P first: {len(own)} PU foam line(s) on these bodies still carry their own price ({lines}). "
                      "A 4G default over them would charge 4G twice — apply Manifest P, then D")
    return todo, done


def report(cx, rows_before: dict | None = None) -> None:
    rows = read_rows(cx)
    for tid, name in BODIES.items():
        r = rows.get(tid)
        print(f"   body {tid:>3} {name:<26} default {r[2] if r else '(missing)'}")
    o = others_4g(cx)
    print(f"OTHERS_4G: {len(o)}" + (" — " + ", ".join(f"{i} {n}" for i, n in o) if o else " (every other body opens on 32D)"))
    n = cx.execute("""select count(*) from icb_costings.calculations where deleted_at is null and trailer_type_id = any(%s)""",
                   (list(BODIES),)).fetchone()[0]
    print(f"   saved costings on these four bodies (not deleted): {n} — each keeps the grade it was saved with; "
          "D changes only what a NEW costing opens on")


def dry_run(cx, db: str, target: str) -> int:
    print(f"database {db} (--target {target}); Manifest D: {TABLE}.default_insulation_foam; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        cx.execute("set transaction read only")
        todo, done = check(cx)
        for tid in done:
            print(f"  done  body {tid} {BODIES[tid]}: {AFTER!r}")
        for tid in todo:
            print(f"  APPLY body {tid} {BODIES[tid]}: {BEFORE!r} -> {AFTER!r}")
        print(f"   P first: 0 own-priced PU foam lines on these bodies")
        report(cx)
        print(f"{len(todo)} to apply, {len(done)} already applied.")
        print("nothing to apply." if not todo else "(DRY RUN — nothing written. Re-run with --apply.)")
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
    print(f"database {db} (--target {target}); Manifest D: {TABLE}.default_insulation_foam; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        read_rows(cx, lock=True)                  # lock the four rows, then every guard under the lock
        todo, done = check(cx)
        if not todo:
            print(f"0 to apply, {len(done)} already applied.")
            print("nothing to apply.")
            return 0
        wrote = []
        for tid in todo:
            got = cx.execute(f"update {TABLE} set default_insulation_foam = %s where id = %s and name = %s "
                             f"and default_insulation_foam = %s returning id, default_insulation_foam",
                             (AFTER, tid, BODIES[tid], BEFORE)).fetchall()
            if got != [(tid, AFTER)]:
                raise RuntimeError(f"body {tid}: the update returned {got!r}")
            wrote.append({"id": tid, "name": BODIES[tid], "before": BEFORE, "after": AFTER})
            print(f"  APPLY body {tid} {BODIES[tid]}: {BEFORE!r} -> {AFTER!r}")
        journal = {"tool": "rt2_defaults", "manifest": "D", "tool_sha256": tool_sha(), "target": target, "database": db,
                   "column": f"{TABLE}.default_insulation_foam", "rows": wrote, "already_applied": done,
                   "applied_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        part, final = write_file(out_dir, f"rt2_defaults_journal_{target}", journal)
    part.replace(final)        # the journal gets its final name only once the transaction has committed
    with cx.transaction():
        cx.execute("set transaction read only")
        now = read_rows(cx)
        bad = [t for t in BODIES if (now.get(t) or (None, None, None))[2] != AFTER]
        report(cx)
    if bad:
        print(f"!! after commit bodies {bad} do not read {AFTER!r} — tell the CA")
        return 1
    print(f"APPLIED {len(wrote)} change(s) (trailer_types ids {[w['id'] for w in wrote]}). Journal: {final}")
    print(f"Undo: python rt2_defaults.py --target {target} --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, target: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "rt2_defaults" or j.get("manifest") != "D":
        raise SystemExit(f"REFUSED: {jpath} is not a Manifest D journal")
    if j.get("database") != db or j.get("target") != target:
        raise SystemExit(f"REFUSED: the journal was written on {j.get('database')!r} (--target {j.get('target')}); this is {db!r}")
    print(f"database {db} (--target {target}); revert Manifest D from {jpath.name}; tool sha256 {tool_sha()[:16]}…")
    with cx.transaction():
        if not has_column(cx):
            raise Refused("trailer_types has no default_insulation_foam column")
        rows = read_rows(cx, lock=True)
        todo, done = [], []
        for w in j["rows"]:
            r = rows.get(w["id"])
            if r is None or r[0] != w["name"]:
                raise Refused(f"body id {w['id']} is {r!r}; the journal names {w['name']!r}")
            if r[2] == w["before"]:
                done.append(w)
            elif r[2] == w["after"]:
                todo.append(w)
            else:
                raise Refused(f"body {w['id']} {w['name']} holds {r[2]!r}; D wrote {w['after']!r}")
        if not todo:
            print(f"  done  every journaled body already holds its before-state ({BEFORE!r})")
            print("nothing to revert.")
            return 0
        for w in todo:
            got = cx.execute(f"update {TABLE} set default_insulation_foam = %s where id = %s and name = %s "
                             f"and default_insulation_foam = %s returning id, default_insulation_foam",
                             (w["before"], w["id"], w["name"], w["after"])).fetchall()
            if got != [(w["id"], w["before"])]:
                raise RuntimeError(f"body {w['id']}: the revert returned {got!r}")
            print(f"  REVERT body {w['id']} {w['name']}: {w['after']!r} -> {w['before']!r}")
        part, final = write_file(out_dir, f"rt2_defaults_revert_{target}",
                                 {"tool": "rt2_defaults", "manifest": "D", "reverted_journal": jpath.name,
                                  "rows": todo, "already_reverted": done,
                                  "reverted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    part.replace(final)
    with cx.transaction():
        cx.execute("set transaction read only")
        now = read_rows(cx)
    bad = [w["id"] for w in j["rows"] if (now.get(w["id"]) or (None, None, None))[2] != w["before"]]
    if bad:
        print(f"!! after commit bodies {bad} do not read their before-state — tell the CA")
        return 1
    print(f"REVERTED {len(todo)} row(s) byte-exact to {BEFORE!r}. Record: {final}")
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
