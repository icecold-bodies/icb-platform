"""RT4 B.6 — the five Mannis against Burt's Manni sheets (21 Sep zip). REPORT ONLY: fixes nothing.

The costing audit's own machinery, pointed at five sheets it does not normally map:

    cd backend
    python ../docs/audit/rt4_2026-10/burt_gap/manni_gap.py discover --workbook-dir DIR
    python ../docs/audit/rt4_2026-10/burt_gap/manni_gap.py golden   --workbook-dir DIR [--provenance JSON] [--prove]
    python ../docs/audit/rt4_2026-10/burt_gap/manni_gap.py run      --target mirror

* The five sheets are registered for this run only (mapping.SHEET_TO_TRAILER is extended in memory:
  'Manni RIGIDS CB' -> 3, 'Manni Bakkie Rigids' -> 4, 'Manni RIGIDS FB' -> 5, 'Manni TRAILERS' -> 6,
  'Manni DF' -> 7 — prod's ids). The tool's committed files are not changed.
* golden: the ExcelOracle recalculates every scenario of manni_gap.yaml (each Manni at prod's default size,
  RT4 discovery) with LibreOffice on a COPY of the workbooks -> golden/ next to this file.
* run: ONE connection to the prod mirror, ONE transaction, ROLLED BACK — prod's rows for the five Mannis
  (the read-only export of 4 Oct, discovery_20261004-080150/manni_snapshot.json) are loaded into it with the
  bodies' prod settings, the calculator's lookups read through it, and the audit's MesProbe costs every golden
  scenario; compare/report are the audit's own, with NO accepted list (every difference shows). -> report/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

SHEETS = {"Manni RIGIDS CB": 3, "Manni Bakkie Rigids": 4, "Manni RIGIDS FB": 5, "Manni TRAILERS": 6, "Manni DF": 7}
PROD = HERE.parent / "prod" / "discovery_20261004-080150"
PACK = HERE / "manni_gap.yaml"


def _register() -> None:
    from tools.costing_audit import mapping
    mapping.SHEET_TO_TRAILER.update(SHEETS)          # the same dict object excel_oracle / scenarios imported


def cmd_discover(a) -> int:
    _register()
    from tools.costing_audit.excel_oracle import ExcelOracle
    from tools.costing_audit.sheet_map import render_text
    work = Path(a.work_dir)
    o = ExcelOracle(Path(a.workbook_dir), work_dir=work, log=print)
    chunks = []
    for s in SHEETS:
        try:
            chunks.append(render_text(o.discover(s)))
        except Exception as exc:                                   # noqa: BLE001
            chunks.append(f"=== {s!r}\n  NOT DISCOVERABLE: {exc}")
    text = "\n\n".join(chunks) + "\n"
    (HERE / "discover.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


def cmd_golden(a) -> int:
    _register()
    from tools.costing_audit import cli
    cli._golden(str(PACK), a.workbook_dir, golden_dir=HERE / "golden", work_dir=a.work_dir, soffice=None,
                sheet_maps=None, prove=a.prove, provenance=a.provenance)
    return 0


def cmd_run(a) -> int:
    _register()
    import audit_pricing_corrections as PC                         # noqa: F401 (assert_target)
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from app import database as _db
    from app.services import costing_audit_runs
    from tools.costing_audit.compare import RunReport               # noqa: F401
    from tools.costing_audit.mes_probe import MesProbe
    from tools.costing_audit.mes_snapshot import load_snapshot
    from tools.costing_audit.report import write_all
    from tools.costing_audit.runner import golden_for, cost_and_compare
    from tools.costing_audit.scenarios import load_pack
    dbname = PC.assert_target(a.target)
    disc = json.loads((PROD / "discovery.json").read_text(encoding="utf-8"))
    bodies = {b["id"]: b for b in disc["bodies"] if b["id"] in SHEETS.values()}
    pack = load_pack(PACK)
    manifest, goldens, warnings = golden_for(pack, HERE / "golden")
    seqs = {}
    snap = PROD / "manni_snapshot.json"
    tables = sorted(json.loads(snap.read_text(encoding="utf-8"))["tables"])
    with _db.engine.connect() as c0:
        for t in tables:
            seq = c0.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": t}).scalar()
            if seq:
                seqs[seq] = tuple(c0.execute(text(f"SELECT last_value, is_called FROM {seq}")).one())
    real = _db.SessionLocal
    conn = _db.engine.connect()
    txn = conn.begin()
    try:
        load_snapshot(snap, allow_non_test_db=True, conn=conn, log=lambda *x: None)
        for tid, b in bodies.items():
            conn.execute(text("UPDATE trailer_types SET name=:n, is_active=:a, configurator_v2=:v, default_length=:l, "
                              "default_width=:w, default_height=:h, default_insulation_foam=:f WHERE id=:i"),
                         {"n": b["name"], "a": b["is_active"], "v": b["configurator_v2"], "l": b["default_length"],
                          "w": b["default_width"], "h": b["default_height"], "f": b["default_insulation_foam"], "i": tid})
        # prod since the 4 Oct 08:01 export: material 182 '28781 SMALL HORIZONTALE CAP' 197.20 -> 203.25 (4 Oct 11:45)
        used182 = conn.execute(text("SELECT count(*) FROM bill_of_materials WHERE material_id = 182 "
                                    "AND trailer_type_id = ANY(:t)"), {"t": list(SHEETS.values())}).scalar()
        if used182:
            conn.execute(text("UPDATE materials SET price_per_unit = 203.25 WHERE id = 182"))
        warnings.append(f"MES side: prod's rows exported 4 Oct 08:01 (RT4 discovery), loaded into {dbname} in a "
                        f"rolled-back transaction; material 182 at prod's 4 Oct price (used by {used182} line(s))")
        _db.SessionLocal = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")
        costing_audit_runs.fresh_lookups()
        db = _db.SessionLocal()
        probe = MesProbe(session=db, log=print)
        rep = cost_and_compare(pack.name, manifest, goldens, probe=probe, accepted=[], tolerance_pct=pack.tolerance_pct,
                               mes_source=f"prod rows of 4 Oct on {dbname} (rolled back)", warnings=warnings)
        db.close()
    finally:
        _db.SessionLocal = real
        costing_audit_runs.fresh_lookups()
        txn.rollback()
        conn.close()
        with _db.engine.begin() as c1:
            for seq, (last, called) in seqs.items():
                c1.execute(text("SELECT setval(:s, :v, :c)"), {"s": seq, "v": last, "c": called})
    paths = write_all(rep, HERE / "report", stem="manni_gap")
    print(Path(paths["md"]).read_text(encoding="utf-8"))
    return 0


# ---------------------------------------------------------------------------------------------------------------
# Manni DF — Burt's dry-freight template (inputs B3:B5, Y/N options B8:B29, lines A desc / D qty / E price /
# F total, a TOTAL row per section with F = sum, G = the option gate, H = the gated total; GRAND TOTAL H261).
# ---------------------------------------------------------------------------------------------------------------
DF_SHEET = "Manni DF"
DF_ID = 7


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_df(ws) -> dict:
    """{options, sections: [{name, lines: [{desc, qty, price, total}], f_total, gate, gated}], grand}"""
    opts = {str(ws.cell(r, 1).value).strip(): str(ws.cell(r, 2).value).strip().upper()
            for r in range(8, 30) if ws.cell(r, 1).value}
    sections, cur, prev_name = [], None, ""

    def start(name):
        nonlocal cur, prev_name
        nm = " ".join(str(name).split()).upper()
        if nm == "DOOR FITTINGS" and prev_name:          # Burt's bare DOOR FITTINGS take their door's name
            nm = f"{prev_name} DOOR FITTINGS"
        cur = {"name": nm, "row": r, "lines": [], "f_total": None, "gate": None, "gated": None}
        sections.append(cur)
        if nm in ("DRD", "DRD INTO REAR PANEL"):
            prev_name = nm
    grand = None
    for r in range(30, ws.max_row + 1):
        a, b, d, e, f, g, h = (ws.cell(r, c).value for c in (1, 2, 4, 5, 6, 7, 8))
        es, fs = str(e or "").strip().upper(), str(f or "").strip().upper()
        if es == "TOTAL" and r >= 255 and a is None and _num(h) is not None and (cur is None or cur.get("gated") is not None):
            grand = _num(h)
            continue
        if isinstance(a, str) and a.strip() and fs == "TOTAL":                     # a section header row
            start(a)
            continue
        if es == "TOTAL":                                                          # a section's TOTAL row
            if isinstance(a, str) and a.strip():                                   # ESCAPE HATCH: label + TOTAL
                start(a)
            if cur is not None:
                cur["f_total"], cur["gate"], cur["gated"] = _num(f), _num(g), _num(h)
            continue
        if isinstance(a, str) and a.strip():
            if all(x is None for x in (b, d, e, f, g, h)) and not cur_has_open_lines(cur):
                start(a)                                                           # SPRAY PAINTING / DRAIN HOLES ...
                continue
            if _num(f) is not None or _num(h) is not None:
                if cur is None or cur.get("gated") is not None:                    # a line after a closed section
                    start(a)
                cur["lines"].append({"desc": " ".join(a.split()), "qty": _num(d) if _num(d) is not None else _num(b),
                                     "price": _num(e), "total": _num(f), "gated_row": _num(h), "gate_row": _num(g)})
    for s in sections:                                     # sections without a TOTAL row (SPRAY PAINTING ...)
        if s["gated"] is None:
            hs = [l["gated_row"] for l in s["lines"] if l["gated_row"] is not None]
            s["gated"] = sum(hs) if hs else 0.0
    return {"options": opts, "sections": sections, "grand": grand,
            "sum_gated": round(sum(s["gated"] or 0 for s in sections), 2)}


def cur_has_open_lines(cur) -> bool:
    return bool(cur and cur["lines"] and cur.get("gated") is None)


def _df_excel(workbook_dir: Path, work_dir: Path, sizes: dict) -> dict:
    import shutil
    from openpyxl import load_workbook
    from tools.costing_audit.soffice import convert_batch
    work_dir.mkdir(parents=True, exist_ok=True)
    for n in ("PRICE 2017 MARCH.xlsx", "FORMULAS 2018.xls"):
        shutil.copy(workbook_dir / n, work_dir / n)
    files = {}
    for tag, size in sizes.items():
        wb = load_workbook(workbook_dir / "GRP Costings 2018.xlsx")
        ws = wb[DF_SHEET]
        if size:
            ws["B3"], ws["B4"], ws["B5"] = size
        p = work_dir / f"manni_df_{tag}.xlsx"
        wb.save(p)
        files[tag] = p
    out, secs = convert_batch(list(files.values()), work_dir / "out")
    print(f"[df] soffice recalculated {len(files)} copies in {secs}s")
    return {tag: parse_df(load_workbook(out[p], data_only=True)[DF_SHEET]) for tag, p in files.items()}


def _df_mes(target: str, size: tuple) -> dict:
    """MANNI DF priced DRD and SRD at `size` through the calculator path, on the mirror with prod's rows
    (one transaction, rolled back) — prove_s.py's payload."""
    import importlib.util
    import audit_pricing_corrections as PC
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from app import database as _db
    from app.database import BillOfMaterial, TrailerType
    from app.formula_engine import calculate_bom
    from app.routers.calculator import (_apply_body_variable_overrides, _bom_load_options, _build_body_variables,
                                        _build_bom_items, get_formula_lib, get_global_vars)
    from app.services import costing_audit_runs
    from tools.costing_audit.mes_snapshot import load_snapshot
    spec = importlib.util.spec_from_file_location("prove_s", HERE.parent / "manifest_s" / "prove_s.py")
    ps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ps)
    PC.assert_target(target)
    disc = json.loads((PROD / "discovery.json").read_text(encoding="utf-8"))
    b = next(x for x in disc["bodies"] if x["id"] == DF_ID)
    snap = PROD / "manni_snapshot.json"
    seqs = {}
    with _db.engine.connect() as c0:
        for t in json.loads(snap.read_text(encoding="utf-8"))["tables"]:
            seq = c0.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": t}).scalar()
            if seq:
                seqs[seq] = tuple(c0.execute(text(f"SELECT last_value, is_called FROM {seq}")).one())
    real = _db.SessionLocal
    conn = _db.engine.connect()
    txn = conn.begin()
    out = {}
    try:
        load_snapshot(snap, allow_non_test_db=True, conn=conn, log=lambda *x: None)
        conn.execute(text("UPDATE trailer_types SET name=:n, is_active=:a, configurator_v2=:v, default_length=:l, "
                          "default_width=:w, default_height=:h, default_insulation_foam=:f WHERE id=:i"),
                     {"n": b["name"], "a": b["is_active"], "v": b["configurator_v2"], "l": b["default_length"],
                      "w": b["default_width"], "h": b["default_height"], "f": b["default_insulation_foam"], "i": DF_ID})
        _db.SessionLocal = sessionmaker(bind=conn, join_transaction_mode="create_savepoint")
        costing_audit_runs.fresh_lookups()
        db = _db.SessionLocal()
        tt = db.query(TrailerType).filter_by(id=DF_ID).one()
        rows = db.query(BillOfMaterial).filter_by(trailer_type_id=DF_ID).options(*_bom_load_options()).all()
        dims = {"length": size[0], "width": size[1], "height": size[2]}
        for door in ("DRD", "SRD"):
            sel, var_over, excl = ps.payload_for(rows, door, None, "32D")
            sel_b = {k: bool(v) for k, v in sel.items()}
            flags = {r.material.name: sel_b[str(r.id)] for r in rows if r.is_body_option and r.material}
            items = _build_bom_items(rows, dims, {}, sel_b, db, excl, trailer=tt, flag_overrides=flags,
                                     include_all_items=False, user_excluded_bom_ids=[], optional_sections_enabled=[],
                                     formula_overrides=None, insulation_foam="32D")
            bv = _build_body_variables(rows)
            _apply_body_variable_overrides(bv, var_over)
            res = calculate_bom(items, dims, bv, get_formula_lib(), get_global_vars())
            out[door] = {"grand_total": round(float(res.get("grand_total") or 0), 2), "excluded_categories": excl,
                         "items": [{k: it.get(k) for k in ("category", "bom_id", "material", "formula", "quantity",
                                                           "unit_price", "line_cost", "excluded")}
                                   for it in res["items"]]}
        db.close()
    finally:
        _db.SessionLocal = real
        costing_audit_runs.fresh_lookups()
        txn.rollback()
        conn.close()
        with _db.engine.begin() as c1:
            for seq, (last, called) in seqs.items():
                c1.execute(text("SELECT setval(:s, :v, :c)"), {"s": seq, "v": last, "c": called})
    return out


def cmd_df(a) -> int:
    disc = json.loads((PROD / "discovery.json").read_text(encoding="utf-8"))
    b = next(x for x in disc["bodies"] if x["id"] == DF_ID)
    size = (b["default_length"], b["default_width"], b["default_height"])
    xl = _df_excel(Path(a.workbook_dir), Path(a.work_dir), {"saved": None, "default": size})
    mes = _df_mes(a.target, size)
    doc = {"sheet": DF_SHEET, "trailer_id": DF_ID, "default_size": size, "workbook_dir": a.workbook_dir,
           "excel": xl, "mes": mes}
    (HERE / "report").mkdir(exist_ok=True)
    (HERE / "report" / "manni_df.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    sv = xl["saved"]
    print(f"[df] saved size: sum of gated section totals {sv['sum_gated']} vs the sheet's GRAND TOTAL {sv['grand']}")
    dv = xl["default"]
    print(f"[df] default size {size}: Excel {dv['sum_gated']} (grand {dv['grand']}) · MES DRD {mes['DRD']['grand_total']}"
          f" · MES SRD {mes['SRD']['grand_total']}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover"); d.add_argument("--workbook-dir", required=True); d.add_argument("--work-dir", required=True)
    g = sub.add_parser("golden"); g.add_argument("--workbook-dir", required=True); g.add_argument("--work-dir", required=True)
    g.add_argument("--provenance"); g.add_argument("--prove", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--target", required=True, choices=("mirror",))
    f = sub.add_parser("df"); f.add_argument("--workbook-dir", required=True); f.add_argument("--work-dir", required=True)
    f.add_argument("--target", required=True, choices=("mirror",))
    a = ap.parse_args(argv)
    sys.path.insert(0, str(BACKEND / "tools"))
    return {"discover": cmd_discover, "golden": cmd_golden, "run": cmd_run, "df": cmd_df}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
