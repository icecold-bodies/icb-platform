"""Zero the INACTIVE rear-door group's EPS/PU insulation thickness on every
active body type (v1.44.1 — Michael 4 Aug).

The rule: only one rear door (DRD or SRD) is quoted per body. The inactive
door's insulation thicknesses must be 0 — non-zero values leak into the
``{SRD EPS}``-style formula tokens (the engine resolves EVERY body variable
from the template regardless of selection) and silently under-quote the
active door's panels. calculator.js enforces this on toggle and (since
v1.44.1) heals on load; this script fixes the whole fleet in one pass.

The "active" door mirrors calculator.js `_seedDrdSrdFromDefaults`: a group is
default-ON when ANY of its body-option rows carries ``body_option_default``;
if both default ON, DRD wins. Bodies where NEITHER group defaults on are
reported and SKIPPED (ambiguous — needs a human choice), as are bodies with
no DRD/SRD groups at all (nothing to do).

Dry-run by default — prints exactly what would change and exits without
touching the DB. Pass --apply to write. The summary always distinguishes
CHANGED / CLEAN / SKIPPED so an all-skip run can never read as success.

Run (dev):     backend/.venv Python, repo root on sys.path via this file.
Run (prod):    sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; \
                 /opt/icb-platform/.venv/bin/python \
                 /opt/icb-platform/backend/scripts/zero_inactive_door_insulation.py [--apply]'
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DOOR_GROUPS = ("DRD", "SRD")   # DRD first — mirrors _DRDSR_TOGGLE_GROUPS


def collect(db):
    """Return (actions, ambiguous, clean) where actions =
    [{tt, active, rows: [(bom_row, material_name, current_value), …]}, …]."""
    from app.database import BillOfMaterial, TrailerType

    actions, ambiguous, clean = [], [], []
    tts = (db.query(TrailerType)
           .filter_by(is_active=True).order_by(TrailerType.name).all())
    for tt in tts:
        rows = (db.query(BillOfMaterial)
                .filter_by(trailer_type_id=tt.id, is_body_option=True).all())
        by_group = {g: [r for r in rows if (r.body_option_group or "") == g]
                    for g in DOOR_GROUPS}
        if not by_group["DRD"] and not by_group["SRD"]:
            continue   # no rear-door groups — nothing to enforce
        default_on = [g for g in DOOR_GROUPS
                      if any(r.body_option_default for r in by_group[g])]
        if not default_on:
            ambiguous.append(tt.name)
            continue
        active = default_on[0]
        dirty = []
        for g in DOOR_GROUPS:
            if g == active:
                continue
            for r in by_group[g]:
                if (r.body_option_subgroup or "").upper() != "INSULATION":
                    continue
                if r.material is None or not re.search(r"EPS|PU", r.material.name, re.I):
                    continue
                if float(r.variable_value or 0) != 0:
                    dirty.append((r, r.material.name, float(r.variable_value)))
        if dirty:
            actions.append({"tt": tt, "active": active, "rows": dirty})
        else:
            clean.append(tt.name)
    return actions, ambiguous, clean


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the zeros (default: dry-run, no DB writes)")
    args = ap.parse_args()

    from app.database import SessionLocal

    with SessionLocal() as db:
        actions, ambiguous, clean = collect(db)

        for a in actions:
            print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] {a['tt'].name} "
                  f"(active door: {a['active']}):")
            for _row, mat, val in a["rows"]:
                print(f"    {mat}: {val:g} -> 0")
        for name in ambiguous:
            print(f"[SKIP-AMBIGUOUS] {name}: neither DRD nor SRD defaults on — "
                  f"needs a human choice, untouched")

        if args.apply and actions:
            for a in actions:
                for row, _mat, _val in a["rows"]:
                    row.variable_value = 0
            db.commit()

        n_rows = sum(len(a["rows"]) for a in actions)
        verb = "CHANGED" if args.apply else "WOULD CHANGE"
        print(f"\nSummary: {verb} {n_rows} row(s) on {len(actions)} body/ies · "
              f"CLEAN {len(clean)} · SKIPPED-AMBIGUOUS {len(ambiguous)}")
        if not args.apply:
            print("Dry-run only — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
