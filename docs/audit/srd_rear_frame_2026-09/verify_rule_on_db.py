"""v1.58.1 — READ ONLY: price every Manifest A body twice through the engine against the database AS IT IS
(after the apply), with the payload shape the live calculator sends:

  DRD  the DRD insulation master on, excluded_categories = the SRD sections (folder bodies);
       CHILLER LARGE: DOOR TYPE DRD on AND its SRD EPS radio still ticked (the real UI state)
  SRD  the SRD PU master on (thickness 0.06), excluded_categories = the DRD sections;
       CHILLER LARGE: DOOR TYPE SRD on

Expected after Manifest A: DRD -> REAR FRAME priced, 0 excluded; SRD -> REAR FRAME R0, every line
excluded, the section still present in the result (header shows), reason names the SRD master.

    (DATABASE_URL + SESSION_SECRET set; PYTHONPATH = backend/)  python verify_rule_on_db.py
"""
import json
import sys
from pathlib import Path

import yaml
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import app.database as _db
from app.database import BillOfMaterial, TrailerType
from app.formula_engine import calculate_bom
from app.routers.calculator import (_apply_body_variable_overrides, _bom_load_options, _build_body_variables,
                                    _build_bom_items)
from app.services import get_formula_lib, get_global_vars, get_section_snapshot

RF = "REAR FRAME & FLOOR PLATE"
MANIFEST = Path(__file__).resolve().parent / "manifest_a.yaml"


def main():
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    bodies = {}
    for e in doc["changes"]:
        bodies.setdefault(e["body_id"], e["body"][0])
    eng = create_engine(_db.engine.url, poolclass=NullPool,
                        connect_args={"options": "-c default_transaction_read_only=on"})
    if hasattr(_db, "_set_search_path"):
        event.listen(eng, "connect", _db._set_search_path)
    conn = eng.connect()
    db = Session(bind=conn, autoflush=False)
    ok_all = True
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        order = get_section_snapshot().order
        print(f"{'body':<26} {'door':<4} {'RF total':>9} {'excl':>6}  in result  reason")
        for tid, name in sorted(bodies.items(), key=lambda kv: kv[1]):
            tt = db.query(TrailerType).filter_by(id=tid).first()
            rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tid).options(*_bom_load_options()).all()
            rows.sort(key=lambda r: (order.get(r.bom_section or "", 99998), (r.bom_section or "").lower(),
                                     r.material.name.lower() if r.material else ""))
            m = {r.material.name: r.id for r in rows if r.is_body_option and r.material}
            n_rf = sum(1 for r in rows if r.bom_section == RF)
            dims = {"length": tt.default_length or 4.0, "width": tt.default_width or 2.4,
                    "height": tt.default_height or 2.2}
            if "DRD" in m and "SRD" in m and tid == 27:       # DOOR TYPE body (CHILLER LARGE)
                drd = ({str(m["DRD"]): True, str(m["SRD"]): False, str(m["DRD EPS"]): True, str(m["SRD EPS"]): True},
                       {"DRD EPS": True, "SRD EPS": True}, ["SRD"], {"DRD EPS": 0.06})
                srd = ({str(m["DRD"]): False, str(m["SRD"]): True, str(m["SRD EPS"]): True},
                       {"SRD EPS": True}, ["DRD"], {"SRD EPS": 0.06})
            else:
                drd = ({str(m["DRD EPS"]): True, str(m["DRD PU"]): False, str(m["SRD EPS"]): False, str(m["SRD PU"]): False},
                       {"DRD EPS": True, "DRD PU": False, "SRD EPS": False, "SRD PU": False},
                       ["SRD", "SRD DOOR FITTINGS"], {"DRD EPS": 0.06})
                srd = ({str(m["DRD EPS"]): False, str(m["DRD PU"]): False, str(m["SRD EPS"]): False, str(m["SRD PU"]): True},
                       {"DRD EPS": False, "DRD PU": False, "SRD EPS": False, "SRD PU": True},
                       ["DRD", "DRD DOOR FITTINGS"], {"SRD PU": 0.06})
            for door, (sel, flags, excl, var) in (("DRD", drd), ("SRD", srd)):
                items = _build_bom_items(rows, dims, {}, sel, db, excl, trailer=tt, flag_overrides=flags,
                                         include_all_items=False, user_excluded_bom_ids=[],
                                         optional_sections_enabled=[], formula_overrides=None,
                                         insulation_foam="32D")
                bv = _build_body_variables(rows)
                _apply_body_variable_overrides(bv, var)
                res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
                rf = [it for it in res["items"] if it.get("category") == RF]
                total = round(sum(float(it.get("line_cost") or 0) for it in rf), 2)
                nx = sum(1 for it in rf if it.get("excluded"))
                reason = next((it.get("excluded_reason") for it in rf if it.get("excluded")), "")
                good = (total > 0 and nx == 0) if door == "DRD" else (total == 0 and nx == n_rf == len(rf))
                ok_all &= good
                print(f"{name:<26} {door:<4} {total:>9.2f} {nx:>3}/{len(rf):<2}  {'yes' if rf else 'NO '}        "
                      f"{reason or '-'}  {'OK' if good else '!! FAIL'}")
    finally:
        db.rollback()
        db.close()
        conn.close()
    print("ALL OK" if ok_all else "!! SOMETHING FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
