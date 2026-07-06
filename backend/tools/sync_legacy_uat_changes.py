"""Sync Nadie's UAT-tested edits from the legacy (HostAfrica MySQL) CSV export into this DB.

Scope + rules are the BA-approved set signed off 2026-07-04 (see reconciliation report):
  * 15 body types (trailer_type ids below).
  * A) materials.price_per_unit — apply diffs >= R0.10 (sub-cent = float noise, skipped).
  * B) bill_of_materials.formula_expression — apply, EXCEPT bom 2466 (kept ICB's newer dynamic
       formula; held for Nadie).
  * C) bill_of_materials.unit_price_override — MIRROR the legacy on the 15 body types
       (bring legacy-only, change where both differ, CLEAR ICB-only), EXCEPT bom 3392
       (legacy R24,356.20 = typo, excluded).

Matching is by STABLE id (verified 794/794 materials, 39/39 trailers, BOM ids stable). Every
material touched is name-cross-checked (id AND name must agree) or it is skipped + reported —
so a price can never land on the wrong material if ids ever drift on the target.

DRY-RUN by default (reads only, prints the report). --apply writes in ONE transaction with
price_history + last_bulk_update stamp (admin 'Undo Last Bulk Update' reverts the prices) and
bom_override_history (batch_at groups this run). Formula changes have no audit table — the
pre-apply pg_dump is their rollback anchor (see the runbook).

Usage:
    python tools/sync_legacy_uat_changes.py --csv-dir "<dir with the 3 CSVs>"            # DRY RUN
    python tools/sync_legacy_uat_changes.py --csv-dir "<dir>" --apply                    # WRITE
"""
import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # put backend/ on sys.path
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.database import (SessionLocal, Material, TrailerType, BillOfMaterial,   # noqa: E402
                          PriceHistory, BomOverrideHistory)

FIFTEEN = [1, 2, 7, 8, 9, 11, 12, 13, 19, 20, 22, 24, 25, 26, 27]
NOISE = 0.10           # |Δprice| below this (Rand) = float noise -> skip
TYPO_LINE = 3392       # legacy R24,356.20 override -> excluded as a typo
HOLD_FORMULA = {2466}  # keep ICB's dynamic formula; flagged for Nadie
CHANGED_BY = "legacy_uat_sync 2026-07-04"


def _num(x):
    try:
        return round(float(x), 2)
    except Exception:
        return None


def _load(csv_dir, name):
    with open(Path(csv_dir) / name, newline="", encoding="utf-8-sig") as f:
        return {str(r["id"]): r for r in csv.DictReader(f)}


def compute(db, csv_dir):
    leg_mat = _load(csv_dir, "materials.csv")
    leg_bom = _load(csv_dir, "bill_of_materials.csv")
    icb_mat = {m.id: m for m in db.query(Material).all()}
    mat_name = {m.id: m.name for m in icb_mat.values()}
    tt_name = {t.id: t.name for t in db.query(TrailerType).all()}
    icb_bom = db.query(BillOfMaterial).filter(BillOfMaterial.trailer_type_id.in_(FIFTEEN)).all()

    problems, prices = [], []
    for mid, m in icb_mat.items():
        lr = leg_mat.get(str(mid))
        if not lr:
            continue
        lp, ip = _num(lr["price_per_unit"]), round(float(m.price_per_unit or 0), 2)
        if lp is None or lp == ip or abs(lp - ip) < NOISE:
            continue
        if (lr["name"] or "").strip().upper() != (m.name or "").strip().upper():
            problems.append(f"MATERIAL id {mid}: name mismatch legacy={lr['name']!r} target={m.name!r} -> SKIPPED")
            continue
        prices.append((m, ip, lp))

    formulas, overrides = [], []
    for b in icb_bom:
        lr = leg_bom.get(str(b.id))
        if not lr:
            continue
        lf, icf = (lr.get("formula_expression") or "").strip(), (b.formula_expression or "").strip()
        if lf != icf and b.id not in HOLD_FORMULA:
            formulas.append((b, icf, lf))
        lo, io = _num(lr.get("unit_price_override")), _num(b.unit_price_override)
        if (lo or 0) != (io or 0) and b.id != TYPO_LINE:
            overrides.append((b, io, lo))
    return prices, formulas, overrides, problems, tt_name, mat_name


def report(prices, formulas, overrides, problems, tt_name, mat_name):
    print(f"A) MASTER PRICES: {len(prices)}")
    for m, old, new in sorted(prices, key=lambda x: -abs(x[2] - x[1])):
        pct = (new - old) / old * 100 if old else 0
        flag = "  <-- LARGE, Nadie-confirmed" if abs(pct) >= 100 else ""
        print(f"   mat{m.id:<5} {m.name[:30]:<31} {old:>10,.2f} -> {new:>10,.2f}  {pct:+5.0f}%{flag}")
    print(f"\nB) FORMULAS: {len(formulas)} (bom 2466 held for Nadie)")
    for b, old, new in formulas:
        print(f"   bom{b.id} tt{b.trailer_type_id}/{b.bom_section}:\n     OLD {old}\n     NEW {new}")
    br = [o for o in overrides if o[1] is None and o[2] is not None]
    ch = [o for o in overrides if o[1] is not None and o[2] is not None]
    cl = [o for o in overrides if o[2] is None]
    print(f"\nC) OVERRIDES: bring {len(br)}, change {len(ch)}, clear {len(cl)}  (R24,356 typo excluded)")
    for b, old, new in br + ch:
        print(f"   set  tt{b.trailer_type_id} {b.bom_section} {mat_name.get(b.material_id,'')[:22]}: {old} -> {new}")
    for b, old, new in cl:
        print(f"   CLR  tt{b.trailer_type_id} {b.bom_section} {mat_name.get(b.material_id,'')[:22]}: {old} -> (master)")
    if problems:
        print("\n!! PROBLEMS (skipped) !!")
        for p in problems:
            print("  " + p)
    print(f"\nTOTAL WRITES: {len(prices)} prices, {len(formulas)} formulas, {len(overrides)} overrides")


def apply(db, prices, formulas, overrides, tt_name, mat_name):
    batch = datetime.now(timezone.utc)
    for m, old, new in prices:
        db.add(PriceHistory(material_id=m.id, old_price=old, new_price=new, changed_by=CHANGED_BY))
        m.price_per_unit = new
        m.last_bulk_update_at = batch
        m.last_bulk_update_note = CHANGED_BY
    for b, old, new in formulas:
        b.formula_expression = new
    for b, old, new in overrides:
        db.add(BomOverrideHistory(
            bom_id=b.id, material_id=b.material_id, trailer_type_id=b.trailer_type_id,
            trailer_type_name=tt_name.get(b.trailer_type_id), material_name=mat_name.get(b.material_id),
            old_price=old, new_price=new, batch_at=batch))
        b.unit_price_override = new
    db.commit()
    return batch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", required=True, help="folder holding materials.csv / trailer_types.csv / bill_of_materials.csv")
    ap.add_argument("--apply", action="store_true", help="write the changes (default is a read-only dry run)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        prices, formulas, overrides, problems, tt_name, mat_name = compute(db, args.csv_dir)
        from app.db_guard import resolve_host, resolve_db_name
        from app.config import settings
        url = settings.DATABASE_URL
        print(f"=== LEGACY-UAT -> ICB SYNC  |  target host={resolve_host(url)} db={resolve_db_name(url)}  |  "
              f"mode: {'APPLY' if args.apply else 'DRY-RUN'} ===\n")
        report(prices, formulas, overrides, problems, tt_name, mat_name)

        if not args.apply:
            print("\n[dry-run] nothing written. Re-run with --apply to write.")
            return
        if problems:
            raise SystemExit("\n[ABORT] name-mismatch problems above — resolve before --apply.")

        from scripts._environment_guard import confirm_if_shared_db
        confirm_if_shared_db(
            "sync_legacy_uat_changes --apply",
            destroys=(f"UPDATE {len(prices)} material prices, {len(formulas)} BOM formulas, "
                      f"{len(overrides)} BOM overrides (with price_history + bom_override_history audit)."))
        batch = apply(db, prices, formulas, overrides, tt_name, mat_name)
        print(f"\n[COMMITTED] batch_at={batch.isoformat()}")
        print("  Undo prices : Admin > Materials > 'Undo Last Bulk Update'  (or restore from the pre-apply pg_dump).")
        print(f"  Undo overrides/formulas : restore materials + bill_of_materials from the pre-apply pg_dump.")
    except SystemExit:
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
