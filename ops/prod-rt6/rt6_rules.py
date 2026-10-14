"""RT6 — Burt's two insulation rules as the CHILLER and FREEZER families' machine-readable rule (RT6_DISPATCH
default 2). Data only; over v1.61.0 (alembic 0053, trailer_groups.insulation_rule). psycopg only, independent of app
code; the classification and the breach check are the staged copy of backend/app/services/insulation_rules.py (the
guards' own file).

    DATABASE_URL=...  python rt6_rules.py --target prod|mirror|dev                           dry-run (read only)
    DATABASE_URL=...  python rt6_rules.py --target prod|mirror|dev --apply --out-dir DIR     apply (journaled)
    DATABASE_URL=...  python rt6_rules.py --target prod|mirror|dev --revert J --out-dir DIR  revert a journal
    DATABASE_URL=...  python rt6_rules.py --target prod|mirror|dev --show                    read back (read only)

--target names the database the run must be on (prod = icb_platform, mirror = icb_prodmirror, dev = Michael's icb, for
his :8000 after the merge); any other database refuses. The VM wrapper rt6_rules.sh only ever passes prod.

THE PLAN: each family (trailer group) found BY NAME, exactly one row, case-insensitive:
    CHILLER  PU allowed nowhere           {"allowed": {every panel: ["EPS"]}}
    FREEZER  EPS on the ROOF and FLOOR only {"allowed": {FRONT/SIDES/DRD/SRD: ["PU"], ROOF/FLOOR: ["EPS","PU"]}}
Every other family: no rule (nothing is enforced; the tool never touches them).

Guards (every one refuses with exit 2 and writes nothing): the database is the target's; the column exists; each
family exists exactly once; its rule is EMPTY (to apply) or EXACTLY the planned rule (already applied: a no-op) —
anything else (an admin set a different rule) refuses; apply re-reads every row FOR UPDATE inside its one transaction
and re-checks before the commit. Revert needs every journaled row to hold exactly what the journal wrote, and puts
each back as it was.

--show prints every family's stored rule exactly, and — for each ruled family — the forbidden insulation masters on
its bodies (master names), any insulation choice the check cannot read, and the LIVE costings that breach the rule as
stored (quote numbers only), soft-deleted ones counted separately: the window's read-only breach count
(RT6_RULING_1a). Reads no person column; of a costing it reads id, quote number, status, body, deleted and the
insulation keys of result_json only.
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

_HERE = Path(__file__).resolve().parent
# staged (the VM): the copy beside this file; in the repo (the mirror rehearsal, Michael's dev): backend/app/services
if (_HERE / "insulation_rules.py").exists():
    sys.path.insert(0, str(_HERE))
else:                                                   # appended: nothing in services/ may shadow a library module
    sys.path.append(str(_HERE.parents[1] / "backend" / "app" / "services"))
import insulation_rules as ir  # noqa: E402  (the staged copy of backend/app/services/insulation_rules.py)

TARGETS = {"prod": "icb_platform", "mirror": "icb_prodmirror", "dev": "icb"}
S = "icb_costings"
PLAN = {
    "CHILLER": ir.canonical_rule({"allowed": {p: ["EPS"] for p in ir.PANELS}}),
    "FREEZER": ir.canonical_rule({"allowed": {"FRONT": ["PU"], "SIDES": ["PU"], "ROOF": ["EPS", "PU"],
                                              "FLOOR": ["EPS", "PU"], "DRD": ["PU"], "SRD": ["PU"]}}),
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
    kw = {"options": "-c default_transaction_read_only=on"} if read_only else {}
    cx = psycopg.connect(url, autocommit=True, **kw)
    db = cx.execute("select current_database()").fetchone()[0]
    if db != TARGETS[target]:
        cx.close()
        raise SystemExit(f"REFUSED: --target {target} expects database {TARGETS[target]!r}; this is {db!r}")
    return cx, db


def _same(stored, planned: str) -> bool:
    try:
        return ir.canonical_rule(stored) == planned
    except (ValueError, TypeError):
        return False


def read_state(cx, lock: bool = False) -> list[dict]:
    """One row per planned family, guarded: the column exists, each family exactly once, its rule empty or planned."""
    col = cx.execute("select count(*) from information_schema.columns where table_schema = %s and "
                     "table_name = 'trailer_groups' and column_name = 'insulation_rule'", (S,)).fetchone()[0]
    if col != 1:
        raise Refused("trailer_groups.insulation_rule does not exist: deploy v1.61.0 (alembic 0053) first")
    out = []
    for fam, rule in PLAN.items():
        rows = cx.execute(f"select id, name, insulation_rule from {S}.trailer_groups where upper(btrim(name)) = %s "
                          "order by id" + (" for update" if lock else ""), (fam,)).fetchall()
        if len(rows) != 1:
            raise Refused(f"family {fam!r}: {len(rows)} trailer group(s) carry that name, expected exactly 1")
        gid, name, stored = rows[0]
        if stored and _same(stored, rule):
            state = "already"
        elif not (stored or "").strip():
            state = "todo"
        else:
            raise Refused(f"family {name!r} (#{gid}) already carries ANOTHER insulation rule {stored!r}: not overwritten")
        bodies = cx.execute(f"select name, is_active from {S}.trailer_types where group_id = %s order by name",
                            (gid,)).fetchall()
        out.append({"family": fam, "id": gid, "name": name, "before": stored, "after": rule, "state": state,
                    "bodies": [f"{n}{'' if a else ' (inactive)'}" for n, a in bodies]})
    return out


def _bom(cx, tid: int) -> list[dict]:
    cols = ("id", "is_body_option", "body_option_group", "body_option_subgroup", "selection_group", "material_name",
            "bom_section", "bom_conditions", "body_option_linked")
    rows = cx.execute(f"""select b.id, b.is_body_option, b.body_option_group, b.body_option_subgroup, b.selection_group,
                                 m.name, b.bom_section, b.bom_conditions, b.body_option_linked
                          from {S}.bill_of_materials b join {S}.materials m on m.id = b.material_id
                          where b.trailer_type_id = %s""", (tid,)).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def show(cx) -> None:
    """Every family's stored rule; per ruled family the forbidden masters, the unreadable choices and the breaches."""
    live_total = deleted_total = 0
    live_quotes: list[str] = []
    for gid, name, stored in cx.execute(f"select id, name, insulation_rule from {S}.trailer_groups "
                                        "order by sort_order, name").fetchall():
        print(f"   #{gid:<3} {name:<12} insulation_rule = {stored!r}")
        if not stored:
            continue
        try:
            rule = ir.normalise_rule(stored)
        except (ValueError, TypeError) as e:
            print(f"        !! the stored rule is not readable ({e}) — the app enforces it as NONE")
            continue
        for tid, tname, active in cx.execute(f"select id, name, is_active from {S}.trailer_types where group_id = %s "
                                             "order by name", (gid,)).fetchall():
            cls = ir.classify_body(_bom(cx, tid))
            forb = ir.forbidden_choices(rule, cls)
            bad_ids = set(forb["master_ids"])
            names = sorted({mm.name for mm in cls.masters if mm.id in bad_ids})
            print(f"        body #{tid} {tname}{'' if active else ' (inactive)'}: {len(forb['master_ids'])} forbidden "
                  f"master(s) greyed {names}" + (f"; UNREADABLE: {cls.unclassified}" if cls.unclassified else ""))
            for cid, qn, status, deleted, res in cx.execute(
                    f"select id, quote_number, status, deleted_at is not null, result_json from {S}.calculations "
                    "where trailer_type_id = %s order by id", (tid,)).fetchall():
                try:                                    # text on prod; a json column would arrive decoded
                    result = res if isinstance(res, dict) else (json.loads(res) if res else {})
                except (TypeError, ValueError):
                    result = {}
                found = ir.breaches(rule, cls, ir.saved_costing_payload(result, cls))
                if not found:
                    continue
                what = ", ".join(f"{b.insulation} on {b.panel}" for b in found)
                label = qn or f"(no number) id {cid}"
                if deleted:
                    deleted_total += 1
                    print(f"          soft-deleted breaching: {label} ({status}): {what}")
                else:
                    live_total += 1
                    live_quotes.append(label)
                    print(f"          LIVE breaching: {label} ({status}): {what}")
    print(f"live breaching costings: {live_total}" + (f" ({', '.join(live_quotes)})" if live_quotes else ""))
    print(f"soft-deleted breaching costings: {deleted_total}")


def dry_run(cx, db: str, target: str) -> int:
    print(f"database {db} (--target {target}); RT6 insulation rules; plan sha256 {plan_sha()[:16]}…; "
          f"tool sha256 {tool_sha()[:16]}…")
    try:
        rows = read_state(cx)
    except Refused as e:
        print(f"REFUSED: {e}")
        return 2
    for r in rows:
        print(f"   {r['state'].upper():<7} #{r['id']} {r['name']}: {r['before']!r} -> {r['after']}")
        print(f"           enforced on {len(r['bodies'])} bod{'y' if len(r['bodies']) == 1 else 'ies'}: "
              f"{', '.join(r['bodies']) or '-'}")
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
    print(f"database {db} (--target {target}); RT6 insulation rules; plan sha256 {plan_sha()[:16]}…; "
          f"tool sha256 {tool_sha()[:16]}…")
    try:
        with cx.transaction():
            rows = read_state(cx, lock=True)
            todo = [r for r in rows if r["state"] == "todo"]
            for r in todo:
                cx.execute(f"update {S}.trailer_groups set insulation_rule = %s where id = %s", (r["after"], r["id"]))
            again = read_state(cx, lock=True)                 # re-checked from the database before the commit
            if any(a["state"] != "already" for a in again):
                raise Refused("a rule does not read back as planned inside the transaction")
            journal = {"tool": "rt6_rules", "plan_sha256": plan_sha(), "tool_sha256": tool_sha(), "target": target,
                       "database": db, "applied_at": datetime.now(timezone.utc).isoformat(),
                       "rows": [{k: r[k] for k in ("id", "name", "before", "after")} for r in todo]}
            part, final = write_file(out_dir, f"rt6_rules_journal_{target}", journal)
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    part.rename(final)
    print(f"APPLIED {len(todo)} rule(s): " + "; ".join(f"#{r['id']} {r['name']}" for r in todo))
    print(f"journal {final}  sha256 {hashlib.sha256(final.read_bytes()).hexdigest()}")
    print(f"Undo: python rt6_rules.py --target {target} --revert {final} --out-dir <dir>")
    return 0


def revert(cx, db: str, target: str, jpath: Path, out_dir: Path) -> int:
    j = json.loads(jpath.read_text(encoding="utf-8"))
    if j.get("tool") != "rt6_rules":
        raise SystemExit(f"REFUSED: {jpath.name} is not an rt6_rules journal")
    if j.get("database") != db or j.get("target") != target:
        raise SystemExit(f"REFUSED: the journal was written on {j.get('database')!r} (--target {j.get('target')}); "
                         f"this is {db!r}")
    print(f"database {db} (--target {target}); revert RT6 insulation rules from {jpath.name}; "
          f"tool sha256 {tool_sha()[:16]}…")
    try:
        with cx.transaction():
            for r in j["rows"]:
                row = cx.execute(f"select insulation_rule from {S}.trailer_groups where id = %s for update",
                                 (r["id"],)).fetchone()
                if row is None:
                    raise Refused(f"#{r['id']} {r['name']} no longer exists")
                if row[0] != r["after"]:
                    raise Refused(f"#{r['id']} {r['name']} reads {row[0]!r}, not the journal's {r['after']!r}: moved since")
                cx.execute(f"update {S}.trailer_groups set insulation_rule = %s where id = %s", (r["before"], r["id"]))
            part, final = write_file(out_dir, f"rt6_rules_revert_{target}",
                                     {"tool": "rt6_rules", "reverted": jpath.name, "database": db, "target": target,
                                      "at": datetime.now(timezone.utc).isoformat(), "rows": j["rows"]})
    except Refused as e:
        print(f"REFUSED: {e} — the transaction rolled back; nothing changed")
        return 2
    part.rename(final)
    print(f"REVERTED {len(j['rows'])} rule(s); record {final}")
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
            print(f"database {db} (--target {a.target}); every family's insulation rule (read only)")
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
