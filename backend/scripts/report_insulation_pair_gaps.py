"""READ-ONLY report: insulation EPS/PU pairs the render-time invariant cannot
fix by itself (v1.44.2 — Michael 4 Aug).

Context: _enforceInsulationInvariant (calculator.js, v1.39.10) aligns every
SEEDED pair's thickness onto its selected side at the render chokepoint, and
the v1.44.1 load guard zeroes the non-quoted rear door. What neither can do is
invent a value — so the remaining gaps are DATA gaps a human must fill:

  NEEDS-VALUE       both sides of a pair are 0/NULL — nothing is quoted for
                    that location (EXPLOSIVE-class); enter the thickness on
                    Admin / Body Templates (red "no thickness set" chip) or
                    the calculator's (0.000 m) span.
  NULL-SIDE         one side NULL (renders 0.000 since v1.44.2, previously
                    invisible) — informational; the invariant treats it as 0.
  DOOR-DIRTY        a NON-default rear-door group still carries thickness —
                    run scripts/zero_inactive_door_insulation.py.
  FLAG-VS-VALUE     the body_option_default flag disagrees with which side
                    holds the value. On FLAT bodies the flag seeds the radio,
                    so this self-heals on first open (value carries across).
                    On v2 bodies the CONFIGURATOR DRAFT seeds the radio — the
                    flag is not authoritative there, so this is informational
                    only; verify in the calculator, never by script.

This script never writes — pair mutation by script is deliberately NOT offered:
the selected side on v2 bodies lives in the configurator draft, not in
bill_of_materials, so a DB-only script cannot know the owner side safely.

Run (prod):    sudo bash -c 'set -a; . /etc/icb/backend.env; set +a; \
                 /opt/icb-platform/.venv/bin/python \
                 /opt/icb-platform/backend/scripts/report_insulation_pair_gaps.py'
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DOOR_GROUPS = ("DRD", "SRD")   # DRD first — mirrors _DRDSR_TOGGLE_GROUPS

_EPS = re.compile(r"EPS", re.I)
_PU = re.compile(r"PU", re.I)


def _pairs_for(rows):
    """Yield (eps_row, pu_row) structural pairs (mirrors _insulationPairFor)."""
    by_key: dict[tuple, list] = {}
    for r in rows:
        key = ((r.body_option_group or ""), (r.body_option_subgroup or ""))
        by_key.setdefault(key, []).append(r)
    for _key, sibs in sorted(by_key.items()):
        if len(sibs) != 2:
            continue
        named = [r for r in sibs if r.material is not None]
        if len(named) != 2:
            continue
        eps = next((r for r in named if _EPS.search(r.material.name)), None)
        pu = next((r for r in named
                   if _PU.search(r.material.name) and not _EPS.search(r.material.name)), None)
        if eps is None or pu is None or eps.id == pu.id:
            continue
        yield eps, pu


def collect(db):
    """Return dict of report buckets: needs_value / null_side / door_dirty /
    flag_vs_value, each a list of (trailer, eps_row, pu_row) tuples."""
    from app.database import BillOfMaterial, TrailerType

    out = {"needs_value": [], "null_side": [], "door_dirty": [], "flag_vs_value": []}
    tts = (db.query(TrailerType)
           .filter_by(is_active=True).order_by(TrailerType.name).all())
    for tt in tts:
        rows = (db.query(BillOfMaterial)
                .filter_by(trailer_type_id=tt.id, is_body_option=True).all())
        default_doors = [g for g in DOOR_GROUPS
                         if any(r.body_option_default for r in rows
                                if (r.body_option_group or "") == g)]
        active_door = default_doors[0] if default_doors else None
        for eps, pu in _pairs_for(rows):
            grp = eps.body_option_group or ""
            eps_v = float(eps.variable_value or 0)
            pu_v = float(pu.variable_value or 0)
            if grp in DOOR_GROUPS and grp != active_door:
                if eps_v or pu_v:
                    out["door_dirty"].append((tt, eps, pu))
                continue
            if eps_v == 0 and pu_v == 0:
                out["needs_value"].append((tt, eps, pu))
                continue
            if eps.variable_value is None or pu.variable_value is None:
                out["null_side"].append((tt, eps, pu))
            eps_def = bool(eps.body_option_default)
            pu_def = bool(pu.body_option_default)
            if eps_def != pu_def:
                flagged = eps if eps_def else pu
                if float(flagged.variable_value or 0) == 0:
                    out["flag_vs_value"].append((tt, eps, pu))
    return out


def main() -> int:
    from app.database import SessionLocal

    with SessionLocal() as db:
        acts = collect(db)
        for tt, eps, pu in acts["needs_value"]:
            print(f"[NEEDS-VALUE] {tt.name}: {eps.material.name} + {pu.material.name} "
                  f"both 0/empty — nothing quoted for this location, enter the thickness")
        for tt, eps, pu in acts["null_side"]:
            print(f"[NULL-SIDE] {tt.name}: {eps.material.name}={eps.variable_value!r} / "
                  f"{pu.material.name}={pu.variable_value!r}")
        for tt, eps, pu in acts["door_dirty"]:
            print(f"[DOOR-DIRTY] {tt.name}: {eps.material.name}={eps.variable_value!r} / "
                  f"{pu.material.name}={pu.variable_value!r} — "
                  f"run zero_inactive_door_insulation.py")
        for tt, eps, pu in acts["flag_vs_value"]:
            print(f"[FLAG-VS-VALUE] {tt.name}: default flag on the zero side "
                  f"({eps.material.name}={eps.variable_value!r} def={bool(eps.body_option_default)}, "
                  f"{pu.material.name}={pu.variable_value!r} def={bool(pu.body_option_default)}) — "
                  f"flat bodies self-heal on open; v2 bodies follow the configurator draft")
        print(f"\nSummary: NEEDS-VALUE {len(acts['needs_value'])} · "
              f"NULL-SIDE {len(acts['null_side'])} · DOOR-DIRTY {len(acts['door_dirty'])} · "
              f"FLAG-VS-VALUE {len(acts['flag_vs_value'])}  (read-only report — no writes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
