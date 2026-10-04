"""RT4 — BOM sections are GLOBAL rows (bom_sections.name is UNIQUE); every body's lines point at one shared row.
This module is the one place that answers "who uses this section" and moves one body's lines between sections,
so Body Templates, the Configurator (preview) page and Manifest S all behave the same way:

  * section_usage()          every body with a line in the section — by FK id OR by the legacy string — and every
                             Settings-page draft whose category nodes name it;
  * move_rows_to_section()   THE row move: sets bom_section_id and the legacy bom_section string together (the
                             configurator's move-items and Body Templates' move-body-lines both call it);
  * rewrite_draft_key()      the A2 draft rule (RT4_RULING_1 Q4/Q6): a draft's category nodes keyed `old` are
                             re-keyed `new` ONLY when the draft has no category node keyed `new` yet; otherwise the
                             draft is left exactly as it is and the caller tells the admin to check it;
  * rewrite_drafts_for_rename()  the A2 rule over every draft that names the old key (a global rename).
Draft snapshots are never touched (a restore already tolerates orphan keys).
"""
from __future__ import annotations

import json

DOOR_PREFIXES = ("DRD", "SRD")


def _key(name) -> str:
    return (name or "").strip().upper()


def is_deleted_body(name) -> bool:
    """DELETE /api/trailers/{id} is a soft delete that renames the body '… [deleted-{id}]'."""
    return "[deleted-" in (name or "")


def door_prefix(name):
    """The DRD/SRD name prefix a NON-v2 body gates a section on (calculator.py _DRDSR_GROUPS)."""
    up = (name or "").upper()
    return next((p for p in DOOR_PREFIXES if up.startswith(p)), None)


# ── drafts ─────────────────────────────────────────────────────────────────────

def _draft_nodes(payload) -> dict | None:
    try:
        doc = json.loads(payload or "{}")
    except (ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    nodes = doc.get("nodes")
    return nodes if isinstance(nodes, dict) else None


def draft_category_count(payload, name) -> int:
    """How many category nodes in this draft are keyed `name` (case-insensitive, as calculator.js matches)."""
    nodes = _draft_nodes(payload) or {}
    k = _key(name)
    return sum(1 for n in nodes.values()
               if isinstance(n, dict) and n.get("type") == "category" and _key(n.get("sourceCategoryKey")) == k)


def rewrite_draft_key(payload, old, new) -> tuple[str, str | None, int]:
    """The A2 rule on ONE draft payload. Returns (status, new_payload_or_None, nodes_rewritten):
        "rewritten"    every category node keyed `old` now keyed `new` (its label too, only where the label was
                       exactly the old name — a custom label is kept);
        "node_exists"  the draft already has a category node keyed `new`: left unchanged (check it by hand);
        "no_node"      no category node keyed `old`: nothing to do;
        "unparseable"  the payload is not a draft tree: left unchanged."""
    try:
        doc = json.loads(payload or "{}")
    except (ValueError, TypeError):
        return "unparseable", None, 0
    nodes = doc.get("nodes") if isinstance(doc, dict) else None
    if not isinstance(nodes, dict):
        return "unparseable", None, 0
    ko, kn = _key(old), _key(new)
    cats = [n for n in nodes.values() if isinstance(n, dict) and n.get("type") == "category"]
    hit = [n for n in cats if _key(n.get("sourceCategoryKey")) == ko]
    if not hit:
        return "no_node", None, 0
    if any(_key(n.get("sourceCategoryKey")) == kn for n in cats):
        return "node_exists", None, 0
    for n in hit:
        if _key(n.get("label")) == ko:          # the label IS the old name -> it follows; a custom label stays
            n["label"] = new
        n["sourceCategoryKey"] = new
    return "rewritten", json.dumps(doc), len(hit)


def drafts_naming(db, name) -> list[dict]:
    """Every Settings-page draft with a category node keyed `name`: [{trailer_type_id, trailer_name, node_count}]."""
    from ..database import ConfiguratorDraft, TrailerType
    out = []
    for row in db.query(ConfiguratorDraft).order_by(ConfiguratorDraft.trailer_type_id).all():
        n = draft_category_count(row.payload, name)
        if n:
            tt = db.query(TrailerType).filter_by(id=row.trailer_type_id).first()
            out.append({"trailer_type_id": row.trailer_type_id,
                        "trailer_name": tt.name if tt else f"#{row.trailer_type_id}", "node_count": n})
    return out


def rewrite_drafts_for_rename(db, old, new, *, only_body=None, dry_run=False) -> dict:
    """The A2 rule over every draft that names `old` (or only `only_body`'s). The caller owns the transaction.
    Returns {"rewritten": [...], "left": [...]} — each [{trailer_type_id, trailer_name, nodes}]; `left` are the
    drafts that already have a node keyed `new` (unchanged — the admin checks them)."""
    from ..database import ConfiguratorDraft, TrailerType
    res = {"rewritten": [], "left": []}
    q = db.query(ConfiguratorDraft)
    if only_body is not None:
        q = q.filter(ConfiguratorDraft.trailer_type_id == only_body)
    for row in q.order_by(ConfiguratorDraft.trailer_type_id).all():
        status, payload, n = rewrite_draft_key(row.payload, old, new)
        if status not in ("rewritten", "node_exists"):
            continue
        tt = db.query(TrailerType).filter_by(id=row.trailer_type_id).first()
        item = {"trailer_type_id": row.trailer_type_id, "trailer_name": tt.name if tt else f"#{row.trailer_type_id}",
                "nodes": n if status == "rewritten" else draft_category_count(row.payload, old)}
        if status == "rewritten":
            if not dry_run:
                row.payload = payload
            res["rewritten"].append(item)
        else:
            res["left"].append(item)
    return res


# ── usage ──────────────────────────────────────────────────────────────────────

def section_lines_query(db, section):
    """Every bill_of_materials row in `section`, matched by FK id OR by the legacy string (the same test
    DELETE /api/bom-sections uses before it refuses)."""
    from ..database import BillOfMaterial
    return db.query(BillOfMaterial).filter((BillOfMaterial.bom_section_id == section.id)
                                           | (BillOfMaterial.bom_section == section.name))


def section_usage(db, section, *, rename_to=None) -> dict:
    """Who uses `section`: lines per body (deleted bodies flagged), the drafts naming it, and its own pricing
    properties. With `rename_to`, also which drafts a global rename would rewrite and which it would leave."""
    from sqlalchemy import func
    from ..database import BillOfMaterial, TrailerType
    counts = dict(section_lines_query(db, section)
                  .with_entities(BillOfMaterial.trailer_type_id, func.count(BillOfMaterial.id))
                  .group_by(BillOfMaterial.trailer_type_id).all())
    names = {t.id: t for t in db.query(TrailerType).filter(TrailerType.id.in_(list(counts) or [-1])).all()}
    bodies = []
    for tid, n in counts.items():
        t = names.get(tid)
        bodies.append({"id": tid, "name": t.name if t else None, "lines": n,
                       "is_active": bool(t.is_active) if t else False,
                       "deleted": (t is None) or is_deleted_body(t.name),
                       "configurator_v2": bool(t.configurator_v2) if t else False})
    bodies.sort(key=lambda b: (b["deleted"], (b["name"] or "").upper()))
    out = {"id": section.id, "name": section.name,
           "multiplier": section.multiplier if section.multiplier is not None else 1.0,
           "is_optional": bool(section.is_optional), "archived": section.archived_at is not None,
           "door_prefix": door_prefix(section.name),
           "lines": sum(counts.values()), "bodies": bodies,
           "live_bodies": sum(1 for b in bodies if not b["deleted"]),
           "drafts": drafts_naming(db, section.name)}
    if rename_to:
        out["rename_drafts"] = rewrite_drafts_for_rename(db, section.name, rename_to, dry_run=True)
    return out


# ── the move ───────────────────────────────────────────────────────────────────

def move_rows_to_section(rows, section) -> list[int]:
    """THE row move: each row's FK id and its legacy string together. The caller owns the transaction."""
    moved = []
    for row in rows:
        row.bom_section_id = section.id
        row.bom_section = section.name      # legacy string column, kept in sync
        moved.append(row.id)
    return moved
