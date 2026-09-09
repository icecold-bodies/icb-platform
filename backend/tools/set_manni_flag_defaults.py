"""Seed server-side default thicknesses on Manni RIGIDS CB's draft flags.

Writes `flagVarDefault` (metres) onto the named flag nodes of the trailer's
ConfiguratorDraft payload — the base layer every browser inherits on the
costing page (per-browser values and explicit-zero tombstones override).
SRD PU is deliberately not seeded: that door is unquoted by design.

Dry-run by default; --apply writes. Safe to re-run (reports already-set).
Runs against whichever database DATABASE_URL points at (dev icb / prod
icb_platform) — the flag names are the same on both bodies; any name the
draft does not carry is reported loudly, never skipped silently.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TRAILER_NAME = "Manni RIGIDS CB"
DEFAULTS = {
    "FRONT PU": 0.062,
    "DRD PU": 0.038,
    "SIDES PU": 0.038,
    "ROOF PU": 0.038,
    "FLOOR PU": 0.076,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry-run)")
    args = ap.parse_args()

    from app.database import ConfiguratorDraft, SessionLocal, TrailerType

    with SessionLocal() as db:
        trailer = db.query(TrailerType).filter_by(name=TRAILER_NAME).first()
        if not trailer:
            print(f"ABORT: no trailer named {TRAILER_NAME!r} in this database")
            return 2
        draft_row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=trailer.id).first()
        if not draft_row or not draft_row.payload:
            print(f"ABORT: trailer {trailer.id} has no ConfiguratorDraft payload")
            return 2
        try:
            draft = json.loads(draft_row.payload)
        except (ValueError, TypeError) as exc:
            print(f"ABORT: draft payload is not valid JSON ({exc})")
            return 2
        nodes = draft.get("nodes")
        if not isinstance(nodes, dict):
            print("ABORT: draft payload has no nodes object")
            return 2

        found: dict[str, tuple] = {}
        for node in nodes.values():
            if not isinstance(node, dict) or node.get("type") != "flag":
                continue
            name = (node.get("flagBindingName") or node.get("label") or "").strip()
            if name in DEFAULTS and name not in found:
                found[name] = (node, node.get("flagVarDefault"))

        missing = sorted(set(DEFAULTS) - set(found))
        plan, already = [], []
        for name, (node, current) in sorted(found.items()):
            target = DEFAULTS[name]
            if current is not None and float(current) == target:
                already.append(name)
            else:
                plan.append((name, node, current, target))

        print(f"trailer {trailer.id} {TRAILER_NAME!r}: "
              f"{len(plan)} to set, {len(already)} already set, {len(missing)} missing")
        for name in already:
            print(f"  = {name}: already {DEFAULTS[name]}")
        for name, _node, current, target in plan:
            print(f"  + {name}: {current!r} -> {target}")
        for name in missing:
            print(f"  ! MISSING flag {name!r} in this draft — not seeded")

        if missing:
            print("ABORT — every default must land; fix the draft (or DEFAULTS) first.")
            return 2
        if not plan:
            print("Nothing to do.")
            return 0
        if not args.apply:
            print("\nDRY-RUN — re-run with --apply to write.")
            return 0

        for _name, node, _current, target in plan:
            node["flagVarDefault"] = target
        draft_row.payload = json.dumps(draft)
        db.commit()
        print(f"\nAPPLIED {len(plan)} default(s) to the draft payload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
