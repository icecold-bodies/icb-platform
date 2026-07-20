"""v1.43 — add the "NO REAR DOORS (SIDE DOORS ONLY)" option to explosive bodies.

Michael's requirement (20 Jul): explosive-body clients can take side doors from
OPTIONAL EXPLOSIVE EXTRAS; the user must then be able to remove the rear doors
(DRD/SRD sections + their DOOR FITTINGS) from the calculation — as a choice,
never automatically (side + rear together stays valid).

Mechanism: the DOOR TYPE group in each explosive body's configurator draft is a
folder containing two RADIO-mode folders (DRD DOORS / SRD DOORS). This script
adds a third, CHILDLESS radio folder — selecting it turns both door folders
off, the existing draft machinery zeroes their branches, and the server then
excludes the DRD/SRD sections and fittings. Pure data: the calculator renders
childless radio folders as-is and `_syncDrdSrdFromDraft` derives both gates off.

Idempotent + additive: a body whose door group already carries a NO REAR DOORS
folder is skipped; drafts without a recognisable door group are reported and
left untouched. Dry-run by default; write with --apply.

Run (dev):   backend> .venv\\Scripts\\python.exe -m scripts.add_no_rear_doors_option --apply
Run (prod):  /opt/icb-platform/backend> sudo -iu icb .venv/bin/python -m scripts.add_no_rear_doors_option --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys

NRD_LABEL = "NO REAR DOORS (SIDE DOORS ONLY)"


def add_no_rear_doors(draft: dict, node_id: str) -> tuple[bool, str]:
    """Mutate `draft` in place: append a childless NO REAR DOORS radio folder to
    the door-type radio group. Returns (changed, reason). Pure — no DB access.

    The door group is located structurally, not by container label: the common
    parent of two RADIO-mode folders whose labels word-match DRD and SRD."""
    nodes = (draft or {}).get("nodes") or {}
    radio_folders = [
        (nid, n) for nid, n in nodes.items()
        if isinstance(n, dict) and n.get("type") == "folder"
        and (n.get("folderMode") or "container") == "radio"
    ]

    def _is(label_re: str, n: dict) -> bool:
        return bool(re.search(label_re, (n.get("label") or "").upper()))

    drd = [(nid, n) for nid, n in radio_folders if _is(r"\bDRD\b", n)]
    srd = [(nid, n) for nid, n in radio_folders if _is(r"\bSRD\b", n)]
    parents = {n.get("parentId") for _nid, n in drd} & {n.get("parentId") for _nid, n in srd}
    parents.discard(None)
    if not parents:
        return False, "no DRD+SRD radio door group found — skipped"
    if len(parents) > 1:
        return False, f"ambiguous door groups ({len(parents)} candidate parents) — skipped"
    parent_id = parents.pop()

    siblings = [n for n in nodes.values()
                if isinstance(n, dict) and n.get("parentId") == parent_id]
    if any(_is(r"^NO REAR DOORS", n) for n in siblings):
        return False, "NO REAR DOORS option already present — skipped"

    if node_id in nodes:
        return False, f"node id {node_id!r} already taken — skipped"
    nodes[node_id] = {
        "type": "folder",
        "label": NRD_LABEL,
        "folderMode": "radio",
        "parentId": parent_id,
        "childIds": [],
    }
    parent = nodes.get(parent_id)
    if isinstance(parent, dict):
        kids = parent.setdefault("childIds", [])
        if node_id not in kids:
            kids.append(node_id)
    draft["nodes"] = nodes
    return True, f"added under door group {parent_id!r}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default is a dry run)")
    ap.add_argument("--trailer-like", default="EXPLOSIVE%",
                    help="SQL LIKE pattern for trailer names (default: EXPLOSIVE%%)")
    args = ap.parse_args()

    sys.path.insert(0, ".")
    from app.database import SessionLocal, TrailerType, ConfiguratorDraft

    db = SessionLocal()
    try:
        trailers = (db.query(TrailerType)
                    .filter(TrailerType.name.ilike(args.trailer_like),
                            TrailerType.is_active.is_(True))
                    .order_by(TrailerType.name).all())
        if not trailers:
            print(f"No active trailers match {args.trailer_like!r} — nothing to do.")
            return 0
        changed_any = False
        for t in trailers:
            row = db.query(ConfiguratorDraft).filter_by(trailer_type_id=t.id).first()
            if not row or not row.payload:
                print(f"  [skip] {t.name} (id {t.id}): no configurator draft")
                continue
            try:
                draft = json.loads(row.payload)
            except (ValueError, TypeError):
                print(f"  [skip] {t.name} (id {t.id}): draft payload unreadable")
                continue
            changed, reason = add_no_rear_doors(draft, node_id=f"node-nrd-{t.id}")
            tag = "CHANGED" if changed else "skip"
            print(f"  [{tag}] {t.name} (id {t.id}): {reason}")
            if changed:
                changed_any = True
                if args.apply:
                    row.payload = json.dumps(draft)
        if args.apply and changed_any:
            db.commit()
            print("Applied.")
        elif changed_any:
            print("Dry run — re-run with --apply to write.")
        else:
            print("Nothing to change.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
