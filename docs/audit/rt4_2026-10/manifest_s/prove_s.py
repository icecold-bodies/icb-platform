"""RT4 B.4 — the pricing proof of Manifest S. Every Manni is priced before S, after S and after --revert, on
the REAL calculator path (_build_bom_items -> calculate_bom, as the costing audit does), and the totals must be
identical to the cent — line by line, not just the grand total.

    cd backend && python ../docs/audit/rt4_2026-10/manifest_s/prove_s.py --target mirror [--out DIR]

ONE connection, ONE transaction, ROLLED BACK at the end — the database is left exactly as it was found:
  1. load the committed prod exports into it (the five Mannis + deleted id 41: discovery_20261004-080150 and
     export41_20261004-134129), set those bodies' rows to prod's values, and put id 41's draft back as prod holds it;
  2. price each Manni at prod's default size: door DRD / SRD x insulation EPS / PU x foam 32D / 4G (MANNI DF has no
     insulation masters: door x foam);
  3. apply Manifest S with the correction tool's own functions (guards, the A2 draft rule, expect_unused_after);
  4. price again; 5. --revert from the journal; 6. price again; then ROLLBACK.
The calculator's cached lookups (sections, formulas, globals) are re-read through the same connection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tools"))

PROD = HERE.parent / "prod"
SNAPS = [PROD / "discovery_20261004-080150" / "manni_snapshot.json", PROD / "export41_20261004-134129" / "body41_snapshot.json"]
MANNI = [3, 4, 5, 6, 7]
PANELS = ("FRONT", "DRD", "SRD", "SIDES", "ROOF", "FLOOR")
INS_RE = re.compile(r"^(FRONT|DRD|SRD|SIDES|ROOF|FLOOR) (EPS|PU)$")


def _norm(s) -> str:
    return " ".join((s or "").upper().split())


def payload_for(rows, door: str, ins: str | None, foam: str) -> tuple[dict, dict, list]:
    """(body_option_selections, body_variable_overrides, excluded_categories) — the way the calculator opens a
    body and the user picks the door and the insulation: every insulation pair on `ins` at the body's own PU
    thickness for that panel, the OTHER door's pair off, a door-type master (DRD/SRD) on for its door, every
    other master at its body default; the other door's sections excluded (as the costing audit's probe does)."""
    masters = [r for r in rows if r.is_body_option and r.material]
    thick = {}
    for r in masters:
        m = INS_RE.match(_norm(r.material.name))
        if m and m.group(2) == "PU":
            thick[m.group(1)] = float(r.variable_value or 0.0)
    for r in masters:
        m = INS_RE.match(_norm(r.material.name))
        if m and m.group(2) == "EPS" and not thick.get(m.group(1)):
            thick[m.group(1)] = float(r.variable_value or 0.0)
    sel, var_over = {}, {}
    for r in masters:
        name = _norm(r.material.name)
        m = INS_RE.match(name)
        on = bool(r.body_option_default)
        if m:
            panel, kind = m.groups()
            on = (kind == ins) and not (panel in ("DRD", "SRD") and panel != door)
            var_over[r.material.name] = thick.get(panel, 0.0) if on else 0.0
        elif name in ("DRD", "SRD"):
            on = name == door
        sel[str(r.id)] = on
    other = "SRD" if door == "DRD" else "DRD"
    excluded = sorted({r.bom_section for r in rows if not r.is_body_option and r.bom_section
                       and (_norm(r.bom_section).split()[0] == other
                            or (other in _norm(r.bom_section).split() and "DOOR" in _norm(r.bom_section).split()))})
    return sel, var_over, excluded


def price_all(db, bodies: dict) -> dict:
    from app.database import BillOfMaterial, TrailerType
    from app.formula_engine import calculate_bom
    from app.routers.calculator import (_apply_body_variable_overrides, _bom_load_options, _build_body_variables,
                                        _build_bom_items, get_formula_lib, get_global_vars)
    from app.services import insulation_foam as pu_foam
    out = {}
    db.expire_all()
    for tid in MANNI:
        tt = db.query(TrailerType).filter_by(id=tid).one()
        rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
        has_ins = any(INS_RE.match(_norm(r.material.name)) for r in rows if r.is_body_option and r.material)
        b = bodies[tid]
        dims = {"length": b["default_length"], "width": b["default_width"], "height": b["default_height"]}
        for door in ("DRD", "SRD"):
            for ins in (("EPS", "PU") if has_ins else (None,)):
                for foam in ("32D", "4G"):
                    sel, var_over, excl = payload_for(rows, door, ins, foam)
                    sel_b = {k: bool(v) for k, v in sel.items()}
                    flag_over = {r.material.name: sel_b[str(r.id)] for r in rows if r.is_body_option and r.material}
                    items = _build_bom_items(rows, dims, {}, sel_b, db, excl, trailer=tt, flag_overrides=flag_over,
                                             include_all_items=False, user_excluded_bom_ids=[],
                                             optional_sections_enabled=[], formula_overrides=None,
                                             insulation_foam=pu_foam.normalise(foam))
                    bv = _build_body_variables(rows)
                    _apply_body_variable_overrides(bv, var_over)
                    res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
                    key = f"{tid} {b['name']} | {door} | {ins or 'n/a'} | {foam}"
                    out[key] = {"grand_total": round(float(res.get("grand_total") or 0), 2),
                                "lines": {str(it.get("bom_id")): round(float(it.get("line_cost") or 0), 2)
                                          for it in res.get("items", [])},
                                "categories": {k: round(float(v), 2) for k, v in (res.get("category_totals") or {}).items()}}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=("mirror", "test"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    import audit_pricing_corrections as PC
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from app import database as _db
    from app.services import costing_audit_runs
    from tools.costing_audit.mes_snapshot import load_snapshot
    dbname = PC.assert_target(a.target)
    disc = json.loads((PROD / "discovery_20261004-080150" / "discovery.json").read_text(encoding="utf-8"))
    e41 = json.loads((PROD / "export41_20261004-134129" / "export41.json").read_text(encoding="utf-8"))
    bodies = {b["id"]: b for b in disc["bodies"]}
    manifest = HERE / "manifest_s.yaml"
    report = {"database": dbname, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "states": {}}
    real_sessionlocal = _db.SessionLocal
    # load_snapshot bumps id sequences with setval(), which a ROLLBACK does not undo: note each one now and put
    # it back after the rollback, so the database really is left as it was found
    tables = sorted({t for s in SNAPS for t in json.loads(s.read_text(encoding="utf-8"))["tables"]}
                    | {"configurator_drafts"})
    seqs = {}
    with _db.engine.connect() as c0:
        for t in tables:
            seq = c0.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": t}).scalar()
            if seq:
                seqs[seq] = tuple(c0.execute(text(f"SELECT last_value, is_called FROM {seq}")).one())
    conn = _db.engine.connect()
    txn = conn.begin()
    try:
        # 1 — prod's rows for the six bodies, inside this transaction only
        for snap in SNAPS:
            load_snapshot(snap, allow_non_test_db=True, conn=conn, log=lambda *x: None)
        for tid, b in bodies.items():
            conn.execute(text("UPDATE trailer_types SET name=:n, is_active=:a, configurator_v2=:v, default_length=:l, "
                              "default_width=:w, default_height=:h, default_insulation_foam=:f WHERE id=:i"),
                         {"n": b["name"], "a": b["is_active"], "v": b["configurator_v2"], "l": b["default_length"],
                          "w": b["default_width"], "h": b["default_height"], "f": b["default_insulation_foam"], "i": tid})
        conn.execute(text("DELETE FROM configurator_drafts WHERE trailer_type_id = 41"))
        conn.execute(text("INSERT INTO configurator_drafts (trailer_type_id, payload, updated_at) VALUES (41, :p, now())"),
                     {"p": e41["draft41"]["payload"]})
        n41 = conn.execute(text("SELECT count(*) FROM bill_of_materials WHERE trailer_type_id=41 AND bom_section_id IN (83,84,85)")).scalar()
        nman = {t: conn.execute(text("SELECT count(*) FROM bill_of_materials WHERE trailer_type_id=:t"), {"t": t}).scalar() for t in MANNI}
        report["loaded"] = {"body41_lines_in_83_84_85": n41, "manni_lines": nman}
        # the calculator's cached lookups read through THIS connection
        _db.SessionLocal = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")
        costing_audit_runs.fresh_lookups()
        db = _db.SessionLocal()

        report["states"]["before"] = price_all(db, bodies)
        # 3 — Manifest S, with the tool's own functions
        changes, sha = PC.load_manifest(manifest)
        plan = PC.build_plan(conn, changes)
        PC.build_draft_plan(conn, plan, PC.load_drafts(manifest))
        problems = PC.unused_after_problems(conn, PC.load_expect_unused(manifest), plan)
        report["plan"] = {"todo": len(plan.todo), "draft_todo": len(plan.draft_todo), "unused_problems": problems}
        assert not problems, problems
        journal = PC.apply_plan(conn, plan, target=a.target, dbname=dbname, manifest_sha=sha,
                                note=PC.manifest_note(manifest))
        again = PC.build_plan(conn, changes)
        PC.build_draft_plan(conn, again, PC.load_drafts(manifest))
        report["second_dry_run"] = {"todo": len(again.todo) + len(again.draft_todo),
                                    "done": len(again.done) + len(again.draft_done),
                                    "unused_problems": PC.unused_after_problems(conn, PC.load_expect_unused(manifest), again)}
        costing_audit_runs.fresh_lookups()
        report["states"]["after_S"] = price_all(db, bodies)
        report["after_S_83_84_85_lines"] = conn.execute(text(
            "SELECT count(*) FROM bill_of_materials WHERE bom_section_id IN (83,84,85) OR bom_section IN "
            "('DOOR FITTINGS SRD','DOOR FITTINGS DRD','REAR FRAME + FLOOR PLATE')")).scalar()
        # 5 — the revert
        rev = PC.revert_journal(conn, json.loads(json.dumps(journal, default=str)))
        report["revert"] = rev
        costing_audit_runs.fresh_lookups()
        report["states"]["after_revert"] = price_all(db, bodies)
        db.close()
    finally:
        _db.SessionLocal = real_sessionlocal
        costing_audit_runs.fresh_lookups()
        txn.rollback()
        conn.close()
        with _db.engine.begin() as c1:
            for seq, (last, called) in seqs.items():
                c1.execute(text("SELECT setval(:s, :v, :c)"), {"s": seq, "v": last, "c": called})
        report["sequences_restored"] = len(seqs)

    b, s, r = (report["states"][k] for k in ("before", "after_S", "after_revert"))
    diffs = [k for k in b if b[k] != s[k]] + [k for k in b if b[k] != r[k]]
    report["identical_to_the_cent"] = not diffs
    report["differences"] = diffs
    lines = [f"# Manifest S pricing proof — {dbname}, {report['at']} (one transaction, rolled back)", "",
             f"loaded: {report['loaded']}", f"plan: {report['plan']}", f"second dry-run: {report['second_dry_run']}",
             f"lines still in 83/84/85 after S: {report['after_S_83_84_85_lines']}", f"revert: {report['revert']}", "",
             "| body | door | insulation | foam | before | after S | after revert | lines identical |",
             "|---|---|---|---|---:|---:|---:|---|"]
    for k in b:
        tid_name, door, ins, foam = [x.strip() for x in k.split("|")]
        same = "yes" if b[k]["lines"] == s[k]["lines"] == r[k]["lines"] else "**NO**"
        lines.append(f"| {tid_name} | {door} | {ins} | {foam} | {b[k]['grand_total']:,.2f} | {s[k]['grand_total']:,.2f} "
                     f"| {r[k]['grand_total']:,.2f} | {same} |")
    lines += ["", f"**{'IDENTICAL to the cent, line by line, in all ' + str(len(b)) + ' pricings' if not diffs else 'DIFFERENCES: ' + ', '.join(diffs)}**"]
    print("\n".join(lines))
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"proof_s_{a.target}.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
        (out / f"proof_s_{a.target}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if not diffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
