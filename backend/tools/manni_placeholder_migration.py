"""Manni RIGIDS CB — insulation/waste placeholder migration (8 Sep 2026).

Replaces hardcoded insulation-thickness and waste constants in the body's BOM
formulas with {SECTION EPS}/{SECTION PU} pairs and the built-in {Waste}
global. Already applied on dev via the admin API with a 104/104-item
equivalence proof (docs/handoffs/MANNI_PLACEHOLDER_MAP_2026-09-08.md); this
tool is the PROD-safe equivalent: rows are located by trailer NAME + section
+ material + EXACT current formula (ids differ between databases), nothing is
written unless every expected row matches, and the default mode is a dry-run.

Usage (on the VM, venv python, DATABASE_URL from the service env):
    python tools/manni_placeholder_migration.py            # dry-run: plan only
    python tools/manni_placeholder_migration.py --apply    # guarded apply

Prerequisites checked by the tool:
  - trailer named exactly 'Manni RIGIDS CB' exists
  - GlobalVariable 'Waste' exists with value 0.05
  - every one of the 26 target rows matches its expected current formula
Aborts loudly (exit 2) if any check fails; --apply is all-or-nothing.

After applying: thickness values are per-browser user state — each browser
sets them once (one Excel paste, or clicking the orange suffixes); until
then the wired rows compute 0 with a visible warning.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TRAILER_NAME = "Manni RIGIDS CB"

P1o, P1n = "(2.6-0.038-0.076)", "(2.6-{ROOF EPS}-{ROOF PU}-{FLOOR EPS}-{FLOOR PU})"
P2o, P2n = "(height-0.038)", "(height-{ROOF EPS}-{ROOF PU})"
P3o, P3n = "(height-0.038-0-0.038+0.05)", "(height-{ROOF EPS}-{ROOF PU}-{SIDES EPS}-{SIDES PU}+{Waste})"
P4o, P4n = "(2.6-0-0.038-0.05)", "(2.6-{SIDES EPS}-{SIDES PU}-{Waste})"
P5o, P5n = "(2.6-0-0-0.038+0.05)", "(2.6-{SRD EPS}-{SRD PU}-{SIDES EPS}-{SIDES PU}+{Waste})"


def F(sect: str) -> tuple[str, str]:
    return "{" + sect + " PU}", "({" + sect + " EPS}+{" + sect + " PU})"


def build_edits() -> list[tuple[str, str, str, str]]:
    """(section, material_name, expected current formula, new formula)."""
    e: list[tuple[str, str, str, str]] = []

    def add(sect, mat, old, new):
        e.append((sect, mat, old, new))

    fpu_o, fpu_n = F("FRONT")
    add("FRONT", "RHINOTEX SKINS 1375 BIOSHIELD", f"{P3o}*{P4o}", f"{P3n}*{P4n}")
    add("FRONT", "R250820/1A", f"height*{P1o}*{fpu_o}*50*1.1", f"height*{P1n}*{fpu_n}*50*1.1")
    add("FRONT", "RHINO PANEL Gloss Crystex V2", f"{P3o}*{P4o}", f"{P3n}*{P4n}")

    dpu_o, dpu_n = F("DRD")
    add("DRD", "RHINOTEX SKINS 1375 BIOSHIELD", f"{P2o}*{P1o}", f"{P2n}*{P1n}")
    add("DRD", "R250820/1A", f"{P2o}*{P1o}*{dpu_o}*50*1.1", f"{P2n}*{P1n}*{dpu_n}*50*1.1")
    add("DRD", "RHINO PANEL Gloss Crystex V2", f"{P2o}*{P1o}", f"{P2n}*{P1n}")

    add("DOOR FITTINGS DRD", "28779 DOOR CAPPING", f"0*({P1o}*3+{P2o}*2)", f"0*({P1n}*3+{P2n}*2)")
    add("DOOR FITTINGS DRD", "28777 DOOR CAPPING", f"0*{P1o}", f"0*{P1n}")
    add("DOOR FITTINGS DRD", "2316 DOOR RUBBER", f"2.6*({P1o}*3+{P2o}*2)", f"2.6*({P1n}*3+{P2n}*2)")
    add("DOOR FITTINGS DRD", "2317 DOOR RUBBER", f"0*({P1o}*3+{P2o}*2)", f"0*({P1n}*3+{P2n}*2)")
    add("DOOR FITTINGS DRD", "D-RUBBER", f"{P3o}*{P4o}*2", f"{P3n}*{P4n}*2")

    spu_o, spu_n = F("SRD")
    add("SRD", "RHINOTEX SKINS 1375 BIOSHIELD", f"{P3o}*{P5o}", f"{P3n}*{P5n}")
    add("SRD", "R250820/1A", f"{P3o}*{P5o}*{spu_o}*40*1.1", f"{P3n}*{P5n}*{spu_n}*40*1.1")
    add("SRD", "RHINO PANEL Gloss Crystex V2", f"{P3o}*{P5o}", f"{P3n}*{P5n}")

    add("DOOR FITTINGS SRD", "SB 51111 DOOR SET", "(height+0.05)*1", "(height+{Waste})*1")
    add("DOOR FITTINGS SRD", "28779 DOOR CAPPING", f"0*({P5o}*2+0.85+0.85)", f"0*({P5n}*2+0.85+0.85)")
    add("DOOR FITTINGS SRD", "28777 DOOR CAPPING", f"0*({P5o}*2+0.85)", f"0*({P5n}*2+0.85)")
    add("DOOR FITTINGS SRD", "2316 DOOR RUBBER", f"2.6*({P5o}*2+0.85+0.85)", f"2.6*({P5n}*2+0.85+0.85)")
    add("DOOR FITTINGS SRD", "2317 DOOR RUBBER", f"0*({P5o}*2+0.85+0.85)", f"0*({P5n}*2+0.85+0.85)")
    add("DOOR FITTINGS SRD", "D-RUBBER", f"{P3o}*{P4o}*1", f"{P3n}*{P4n}*1")

    sipu_o, sipu_n = F("SIDES")
    add("SIDES", "RHINOTEX SKINS 1375 BIOSHIELD", f"width*{P1o}", f"width*{P1n}")
    add("SIDES", "R250820/1A", f"width*{P1o}*{sipu_o}*50*1.1", f"width*{P1n}*{sipu_n}*50*1.1")
    add("SIDES", "RHINO PANEL Gloss Crystex V2", f"width*{P1o}", f"width*{P1n}")
    add("SIDES", "3MM MILD STEEL PLATE", f"{P1o}*2*0.1", f"{P1n}*2*0.1")

    rpu_o, rpu_n = F("ROOF")
    add("ROOF", "R250820/1A", f"width*height*{rpu_o}*50*1.1", f"width*height*{rpu_n}*50*1.1")
    flpu_o, flpu_n = F("FLOOR")
    add("FLOOR", "R250820/1A", f"width*height*{flpu_o}*75", f"width*height*{flpu_n}*75")
    return e


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry-run)")
    args = ap.parse_args()

    from app.database import BillOfMaterial, GlobalVariable, SessionLocal, TrailerType

    edits = build_edits()
    problems: list[str] = []
    with SessionLocal() as db:
        trailer = db.query(TrailerType).filter_by(name=TRAILER_NAME).first()
        if not trailer:
            print(f"ABORT: no trailer named {TRAILER_NAME!r} in this database")
            return 2
        waste = db.query(GlobalVariable).filter_by(name="Waste").first()
        if not waste or float(waste.value) != 0.05:
            print(f"ABORT: GlobalVariable 'Waste' missing or not 0.05 "
                  f"(found {getattr(waste, 'value', None)!r}) — create it via "
                  f"POST /api/global-variables first")
            return 2

        rows = db.query(BillOfMaterial).filter_by(trailer_type_id=trailer.id).all()

        def find(sect, mat, formula):
            hits = [r for r in rows
                    if (r.bom_section or "") == sect
                    and getattr(r.material, "name", None) == mat
                    and (r.formula_expression or "") == formula]
            return hits

        plan = []
        for sect, mat, old, new in edits:
            hits = find(sect, mat, old)
            if len(hits) != 1:
                already = find(sect, mat, new)
                if len(already) == 1 and not hits:
                    print(f"skip (already migrated): {sect} / {mat}")
                    continue
                problems.append(f"{sect} / {mat}: expected exactly 1 row with the "
                                f"expected formula, found {len(hits)} "
                                f"(already-migrated matches: {len(already)})")
                continue
            plan.append((hits[0], old, new, sect, mat))

        if problems:
            print("ABORT — the database does not match the expected state:")
            for p in problems:
                print("  -", p)
            print("Nothing was written.")
            return 2

        print(f"trailer {trailer.id} {TRAILER_NAME!r}: {len(plan)} rows to migrate "
              f"({len(edits) - len(plan)} already done)")
        for row, old, new, sect, mat in plan:
            print(f"  [{row.id}] {sect} / {mat}\n    - {old}\n    + {new}")

        if not args.apply:
            print("\nDRY-RUN — re-run with --apply to write.")
            return 0
        for row, _old, new, _sect, _mat in plan:
            row.formula_expression = new
        db.commit()
        print(f"\nAPPLIED {len(plan)} formula updates.")
        print("Reminder: thickness values are per-browser — each browser pastes "
              "the Excel block once (or clicks the orange suffixes); until then "
              "wired rows compute 0 with a visible warning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
