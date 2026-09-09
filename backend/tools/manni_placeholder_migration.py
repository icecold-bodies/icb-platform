"""Manni RIGIDS CB — insulation/waste placeholder migration (8 Sep 2026).

Replaces hardcoded insulation-thickness and waste constants in the body's BOM
formulas with {SECTION EPS}/{SECTION PU} pairs and the built-in {Waste}
global. Two PROFILES, because dev and prod carry sibling datasets of this
body with different rows and formula shapes:

  --profile dev     dev trailer 'Manni RIGIDS CB' (RHINOTEX/R250820/1A rows;
                    applied 8 Sep with a 104/104-item API equivalence proof)
  --profile prod41  prod trailer 41 'Manni RIGIDS CB' (WOVEX/PU INJECTION
                    rows; mapping built from the 8 Sep prod inspect dump)

Safety, both profiles:
  - rows are located by trailer NAME + section + material + EXACT current
    formula (ids differ between databases); duplicate rows that share the
    same formula (e.g. the doubled WOVEX SKIN lines) are all migrated
  - GlobalVariable 'Waste' must exist at 0.05
  - built-in equivalence check: every before/after pair is evaluated with
    the seed thicknesses (FRONT PU .062, DRD/SIDES/ROOF PU .038, FLOOR PU
    .076, EPS + SRD unset = 0, Waste .05) across sample dimensions and must
    agree to 1e-9 — a wrong mapping aborts before anything is written
  - dry-run by default; --apply is all-or-nothing; already-migrated rows
    are skipped so the tool is safe to re-run

The pair convention is deliberately FULL pairs (-{X EPS}-{X PU}) even where
hand edits wrote a single side: identical value today (the unselected side
is 0), still correct the day the selection flips.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TRAILER_NAME = "Manni RIGIDS CB"

SEEDS = {
    "FRONT PU": 0.062, "DRD PU": 0.038, "SIDES PU": 0.038,
    "ROOF PU": 0.038, "FLOOR PU": 0.076, "Waste": 0.05,
    # EPS sides and SRD PU deliberately absent → resolve to 0, like an
    # unset flag variable does at calc time.
}
SAMPLE_DIMS = [
    {"length": 7.5, "width": 2.5, "height": 2.6},
    {"length": 13.6, "width": 2.6, "height": 2.6},
    {"length": 4.0, "width": 2.0, "height": 2.2},
]

# ── shared pattern fragments ────────────────────────────────────────────────
ROOFP = "{ROOF EPS}-{ROOF PU}"
FLOORP = "{FLOOR EPS}-{FLOOR PU}"
SIDESP = "{SIDES EPS}-{SIDES PU}"
SRDP = "{SRD EPS}-{SRD PU}"


def F(sect: str) -> tuple[str, str]:
    return "{" + sect + " PU}", "({" + sect + " EPS}+{" + sect + " PU})"


def build_edits_dev() -> list[tuple[str, str, str, str]]:
    """(section, material_name, expected current formula, new formula) — the
    dev dataset (RHINOTEX / R250820/1A rows). Applied 8 Sep; kept so re-runs
    report 'already migrated' and the mapping stays on record."""
    P1o, P1n = "(2.6-0.038-0.076)", f"(2.6-{ROOFP}-{FLOORP})"
    P2o, P2n = "(height-0.038)", f"(height-{ROOFP})"
    P3o, P3n = "(height-0.038-0-0.038+0.05)", f"(height-{ROOFP}-{SIDESP}+{{Waste}})"
    P4o, P4n = "(2.6-0-0.038-0.05)", f"(2.6-{SIDESP}-{{Waste}})"
    P5o, P5n = "(2.6-0-0-0.038+0.05)", f"(2.6-{SRDP}-{SIDESP}+{{Waste}})"
    e: list[tuple[str, str, str, str]] = []
    add = lambda *a: e.append(a)  # noqa: E731

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


def build_edits_prod41() -> list[tuple[str, str, str, str]]:
    """The prod trailer-41 dataset (WOVEX / PU INJECTION rows), mapped from
    the 8 Sep inspect dump. Geometry conventions read off the literals:
    height-terms deduct ROOF (0.038) and, where present, FLOOR (0.076);
    width-terms deduct SIDES per wall (single or doubled as written);
    +0.05 in dimension terms = {Waste}; ×1.1 waste factors stay literal;
    the SRD PU-injection's ×0 quantity gate stays literal."""
    # Dimension-term patterns as they appear on trailer 41.
    A_o = "(width-0.038-0.038+0.05)"
    A_n = f"(width-{SIDESP}-{SIDESP}+{{Waste}})"
    B_o = "(height-0.038+0.05)"
    B_n = f"(height-{ROOFP}+{{Waste}})"
    C_o = "(width-0.038)"
    C_n = f"(width-{SIDESP})"
    D_o = "(height-0.038-0.076)"
    D_n = f"(height-{ROOFP}-{FLOORP})"
    e: list[tuple[str, str, str, str]] = []
    add = lambda *a: e.append(a)  # noqa: E731

    # NB: unlike the dev profile (whose PU factors had already been wired to
    # {X PU} tokens in the first migration step), prod 41's pre-migration
    # formulas hold the LITERAL thickness constants — the old-sides below must
    # be token-free (enforced in verify_equivalence). This exact mistake
    # caused the 8 Sep prod abort: token old-sides matched nothing.
    _, fpu_n = F("FRONT")
    add("FRONT", "RHINO PANEL", f"{A_o}*{B_o}", f"{A_n}*{B_n}")
    add("FRONT", "Rhinotex Bioshield", f"{A_o}*{B_o}", f"{A_n}*{B_n}")
    add("FRONT", "PU INJECTION", f"width*{D_o}*0.062*50*1.1", f"width*{D_n}*{fpu_n}*50*1.1")

    _, spu_n = F("SRD")
    add("SRD", "WOVEX SKIN", f"{A_o}*{B_o}", f"{A_n}*{B_n}")
    add("SRD", "PU INJECTION", f"{A_o}*{B_o}*0*40*1.1", f"{A_n}*{B_n}*{spu_n}*40*1.1")
    add("DOOR FITTINGS SRD", "28779 DOOR CAPPING", f"({B_o}*2+0.85+0.85)", f"({B_n}*2+0.85+0.85)")
    add("DOOR FITTINGS SRD", "28777 DOOR CAPPING", f"({B_o}*2+0.85)", f"({B_n}*2+0.85)")
    add("DOOR FITTINGS SRD", "2316 DOOR RUBBER", f"({B_o}*2+0.85+0.85)", f"({B_n}*2+0.85+0.85)")
    add("DOOR FITTINGS SRD", "2317 DOOR RUBBER", f"({B_o}*2+0.85+0.85)", f"({B_n}*2+0.85+0.85)")

    _, dpu_n = F("DRD")
    add("DRD", "RHINO PANEL", f"{C_o}*{D_o}", f"{C_n}*{D_n}")
    add("DRD", "Rhinotex Bioshield", f"{C_o}*{D_o}", f"{C_n}*{D_n}")
    add("DRD", "PU INJECTION", f"{C_o}*{D_o}*0.038*50*1.1", f"{C_n}*{D_n}*{dpu_n}*50*1.1")
    add("DOOR FITTINGS DRD", "28779 DOOR CAPPING", f"({D_o}*3+{C_o}*2)", f"({D_n}*3+{C_n}*2)")
    add("DOOR FITTINGS DRD", "28777 DOOR CAPPING", f"{D_o}", f"{D_n}")
    add("DOOR FITTINGS DRD", "2316 DOOR RUBBER", f"({D_o}*3+{C_o}*2)", f"({D_n}*3+{C_n}*2)")
    add("DOOR FITTINGS DRD", "2317 DOOR RUBBER", f"({D_o}*3+{C_o}*2)", f"({D_n}*3+{C_n}*2)")

    _, sipu_n = F("SIDES")
    add("SIDES", "WOVEX SKIN", f"length*{D_o}", f"length*{D_n}")
    add("SIDES", "PU INJECTION", f"length*{D_o}*0.038*50*1.1", f"length*{D_n}*{sipu_n}*50*1.1")

    _, rpu_n = F("ROOF")
    add("ROOF", "PU INJECTION", "length*width*0.038*50*1.1", f"length*width*{rpu_n}*50*1.1")
    _, flpu_n = F("FLOOR")
    add("FLOOR", "PU INJECTION", "length*width*0.076*75", f"length*width*{flpu_n}*75")
    return e


PROFILES = {"dev": build_edits_dev, "prod41": build_edits_prod41}


def verify_equivalence(edits) -> list[str]:
    """Evaluate every before/after pair with the seed values across sample
    dims — the mapping oracle. Returns a list of mismatch descriptions."""
    from app.formula_engine import build_geometry, evaluate_formula
    bad: list[str] = []
    for sect, mat, old, new in edits:
        for dims in SAMPLE_DIMS:
            ctx = build_geometry(dims)
            a = evaluate_formula(old, ctx, SEEDS)
            b = evaluate_formula(new, ctx, SEEDS)
            if abs(a - b) > 1e-9:
                bad.append(f"{sect} / {mat} @ {dims}: before={a!r} after={b!r}")
                break
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="dev",
                    help="which dataset's mapping to use (default: dev)")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry-run)")
    args = ap.parse_args()

    edits = PROFILES[args.profile]()

    if args.profile == "prod41":
        # prod 41 has never been migrated: every old-side must be the literal
        # pre-migration text. A token in an old-side means the mapping was
        # copied from the dev profile (whose PU factors were already wired) —
        # the value-equivalence oracle cannot catch that (a seeded token
        # evaluates identically to its literal), so enforce it textually.
        tokened = [f"{s} / {m}" for s, m, old, _new in edits if "{" in old]
        if tokened:
            print("ABORT — prod41 old-sides must be literal (pre-migration state); "
                  "tokens found in:", ", ".join(tokened))
            return 2

    mismatches = verify_equivalence(edits)
    if mismatches:
        print("ABORT — mapping fails the built-in equivalence check:")
        for m in mismatches:
            print("  -", m)
        return 2
    print(f"profile {args.profile}: {len(edits)} mappings, equivalence check ok "
          f"(seeds {SEEDS} over {len(SAMPLE_DIMS)} dim samples)")

    from app.database import BillOfMaterial, GlobalVariable, SessionLocal, TrailerType

    problems: list[str] = []
    with SessionLocal() as db:
        trailer = db.query(TrailerType).filter_by(name=TRAILER_NAME).first()
        if not trailer:
            print(f"ABORT: no trailer named {TRAILER_NAME!r} in this database")
            return 2
        waste = db.query(GlobalVariable).filter_by(name="Waste").first()
        if not waste or float(waste.value) != 0.05:
            print(f"ABORT: GlobalVariable 'Waste' missing or not 0.05 "
                  f"(found {getattr(waste, 'value', None)!r})")
            return 2

        rows = db.query(BillOfMaterial).filter_by(trailer_type_id=trailer.id).all()

        def find(sect, mat, formula):
            return [r for r in rows
                    if (r.bom_section or "") == sect
                    and getattr(r.material, "name", None) == mat
                    and (r.formula_expression or "") == formula]

        plan = []
        migrated = 0
        for sect, mat, old, new in edits:
            hits = find(sect, mat, old)
            done = find(sect, mat, new)
            if not hits and done:
                migrated += len(done)
                print(f"skip (already migrated ×{len(done)}): {sect} / {mat}")
                continue
            if not hits:
                problems.append(f"{sect} / {mat}: no row matches the expected formula {old!r}")
                continue
            # Duplicate rows sharing the same formula all take the same rewrite.
            for row in hits:
                plan.append((row, old, new, sect, mat))

        if problems:
            print("ABORT — the database does not match the expected state:")
            for p in problems:
                print("  -", p)
            print("Nothing was written.")
            return 2

        print(f"trailer {trailer.id} {TRAILER_NAME!r}: {len(plan)} rows to migrate "
              f"({migrated} already done)")
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
              "wired rows compute 0 with the orange 'set thickness' suffix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
