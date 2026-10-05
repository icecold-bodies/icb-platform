"""RT5 — Burt's two body rules as the CHILLER and FREEZER families' rule notes (RT5_RULING_1: the wording approved
exactly). Data only; over v1.60.2 (alembic 0052, trailer_groups.rule_note). psycopg only, independent of app code.

    DATABASE_URL=...  python rt5_notes.py --target prod|mirror                               dry-run (read only)
    DATABASE_URL=...  python rt5_notes.py --target prod|mirror --apply --out-dir DIR         apply (journaled)
    DATABASE_URL=...  python rt5_notes.py --target prod|mirror --revert J --out-dir DIR      revert a journal
    DATABASE_URL=...  python rt5_notes.py --target prod|mirror --show                        read back (read only)

THE PLAN: each family (trailer group) found BY NAME, exactly one row, case-insensitive:
    CHILLER  "No PU insulation for Chillers"
    FREEZER  "Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors"

Guards (every one refuses with exit 2 and writes nothing): the database is the target's; the column exists; each
family exists exactly once; its note is EMPTY (to apply) or EXACTLY the planned text (already applied: a no-op) —
anything else (someone typed a different note) refuses; apply re-reads every row FOR UPDATE inside its one
transaction and re-checks before the commit. Revert needs every journaled row to hold exactly what the journal wrote,
and puts each back as it was. --show prints every family's note exactly (repr) and which bodies show it: the
window's read-back after the admin edit and after its set-back (RT5_RULING_0). Reads no person column.
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

TARGETS = {"prod": "icb_platform", "mirror": "icb_prodmirror"}
S = "icb_costings"
PLAN = {
    "CHILLER": "No PU insulation for Chillers",
    "FREEZER": "Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors",
}


class Refused(Exception):
    """A guard refused: nothing is written."""


def tool_sha() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def plan_sha() -> str:
    return hashlib.sha256(json.dumps(PLAN, sort_keys=True).encode()).hexdigest()


def connect(target: str, read_only: bool):
    url = os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://")
    if not url:
        raise SystemExit("REFUSED: DATABASE_URL is not set")
    # autocommit: each read stands alone, and `with cx.transaction()` is a real BEGIN ... COMMIT (never a savepoint
    # inside an implicit transaction that close() would roll back)
    kw = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    cx = psycopg.connect(url, autocommit=True, **kw)
    db = cx.execute("select current_database()").fetchone()[0]
    if db != TARGETS[target]:
        cx.close()
        raise SystemExit(f"REFUSED: --target {target} expects database {TARGETS[target]!r}; this is {db!r}")
    return cx, db


def _norm(s) -> str:
    return (s or "").strip()


def read_state(cx, lock: bool = False) -> list[dict]:
    """One row per planned family, guarded: the column exists, each family exactly once."""
    col = cx.execute("select count(*) from information_schema.columns where table_schema = %s and "
                     "table_name = 'trailer_groups' and column_name = 'rule_note'", (S,)).fetchone()[0]
    if col != 1:
        raise Refused("trailer_groups.rule_note does not exist: deploy v1.60.2 (alembic 0052) first")
    out = []
    for fam, text in PLAN.items():
        rows = cx.execute(f"select id, name, rule_note from {S}.trailer_groups where upper(btrim(name)) = %s order by id"
                          + (" for update" if lock else ""), (fam,)).fetchall()
        if len(rows) != 1:
            raise Refused(f"family {fam!r}: {len(rows)} trailer group(s) carry that name, expected exactly 1")
        gid, name, note = rows[0]
        if _norm(note) == text:
            state = "already"
        elif not _norm(note):
            state = "todo"
        else:
            raise Refused(f"family {name!r} (#{gid}) already carries ANOTHER note {note!r}: not overwritten")
        bodies = cx.execute(f"select name, is_active from {S}.trailer_types where group_id = %s order by name",
                            (gid,)).fetchall()
        out.append({"family": fam, "id": gid, "name": name, "before": note, "after": text, "state": state,
                    "bodies": [f"{n}{'' if a else ' (inactive)'}" for n, a in bodies]})
    return out


def show(cx) -> None:
    for gid, name, note in cx.execute(f"select id, name, rule_note from {S}.trailer_groups order by sort_order, name"):
        n = cx.execute(f"select count(*) from {S}.trailer_types where group_id = %s and is_active", (gid,)).fetchone()[0]
        print(f"   #{gid:<3} {name:<12} {n:>2} active bod{'y' if n == 1 else 'ies'} · rule_note = {note!r}")


def dry_run(cx, db: str, target: str) -> int:
    print(f"database {db} (--target {target}); RT5 rule notes; plan sha256 {plan_sha()[:16]}…; tool sha256 {tool_sha()[:16]}…")
    try:
        rows = read_state(cx)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 2
    for r in rows:
        print(f"   {r['state'].upper():<7} #{r['id']} {r['name']}: {r['before']!r} -> {r['after']!r}")
        print(f"           shown on {len(r['bodies'])} bod{'y' if len(r['bodies']) == 1 else 'ies'}: {', '.join(r['bodies']) or '-'}")
    todo = sum(r["state"] == "todo" for r in rows)
    print(f"{todo} to apply, {len(rows) - todo} already applied.")
    return 0


def write_file(out_dir: Path, stem: str, doc: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = out_dir / f"{stem}_{ts}.json"
    part = final.with_suffix(".json.part")
    part.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    return part, final


def apply(cx, db: str, target: str, out_dir: Path) -> int:
    print(f"database {db} (--target {target}); RT5 rule notes; plan sha256 {plan_sha()[:16]}…; tool sha256 {tool_sha()[:16]}…")
    try:
        with cx.transaction():
            rows = read_state(cx, lock=True)
            todo = [r for r in rows if r["state"] == "todo"]
            for r in todo:
                cx.execute(f"update {S}.trailer_groups set rule_note = %s where id = %s", (r["after"], r["id"]))
            again = read_state(cx, lock=True)                 # re-checked from the database before the commit
            if any(a["state"] != "already" for a in again):
                raise Refused("a note does not read back as planned inside the transaction")
            journal = {"tool": "rt5_notes", "plan_sha256": plan_sha(), "tool_sha256": tool_sha(), "target": target,
                       "database": db, "applied_at": datetime.now(timezone.utc).isoformat(),
                       "rows": [{k: r[k] for k in ("id", "name", "before", "after")} for r in todo]}
            part, final = write_file(out_dir, f"rt5_notes_journal_{target}", journal)
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    part.rename(final)
    print(f"APPLIED {len(todo)} note(s): " + "; ".join(f"#{r['id']} {r['name']}" for r in todo))
    print(f"journal {final}  sha256 {hashlib.sha256(final.read_bytes()).hexdigest()}")
    print(f"Undo: python rt5_notes.py --target {target} --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, target: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "rt5_notes":
        raise SystemExit(f"REFUSED: {jpath.name} is not an rt5_notes journal")
    if j.get("database") != db or j.get("target") != target:
        raise SystemExit(f"REFUSED: the journal was written on {j.get('database')!r} (--target {j.get('target')}); this is {db!r}")
    print(f"database {db} (--target {target}); revert RT5 rule notes from {jpath.name}; tool sha256 {tool_sha()[:16]}…")
    try:
        with cx.transaction():
            for r in j["rows"]:
                row = cx.execute(f"select rule_note from {S}.trailer_groups where id = %s for update", (r["id"],)).fetchone()
                if row is None:
                    raise Refused(f"#{r['id']} {r['name']} no longer exists")
                if row[0] != r["after"]:
                    raise Refused(f"#{r['id']} {r['name']} reads {row[0]!r}, not the journal's {r['after']!r}: moved since")
                cx.execute(f"update {S}.trailer_groups set rule_note = %s where id = %s", (r["before"], r["id"]))
            part, final = write_file(out_dir, f"rt5_notes_revert_{target}",
                                     {"tool": "rt5_notes", "reverted": jpath.name, "database": db, "target": target,
                                      "at": datetime.now(timezone.utc).isoformat(), "rows": j["rows"]})
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    part.rename(final)
    print(f"REVERTED {len(j['rows'])} note(s); record {final}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    gx = ap.add_mutually_exclusive_group()
    gx.add_argument("--apply", action="store_true")
    gx.add_argument("--revert", metavar="JOURNAL")
    gx.add_argument("--show", action="store_true")
    ap.add_argument("--out-dir", default=None)
    a = ap.parse_args(argv)
    if (a.apply or a.revert) and not a.out_dir:
        ap.error("--apply / --revert need --out-dir")
    cx, db = connect(a.target, read_only=not (a.apply or a.revert))
    try:
        if a.show:
            print(f"database {db} (--target {a.target}); every family's rule note (read only)")
            show(cx)
            return 0
        if a.apply:
            return apply(cx, db, a.target, Path(a.out_dir))
        if a.revert:
            return revert(cx, db, a.target, Path(a.revert), Path(a.out_dir))
        return dry_run(cx, db, a.target)
    finally:
        cx.close()


if __name__ == "__main__":
    sys.exit(main())
