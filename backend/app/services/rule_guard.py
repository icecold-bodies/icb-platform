"""RT6 — the router side of Burt's insulation rules: where a body's rule comes from, and the one place every guard
asks. The rule is DATA on the body's family (trailer_groups.insulation_rule, migration 0053); the classification and
the check are services/insulation_rules (pure). Called from the routers only — never from `_build_bom_items`, so the
audit probe (which prices Burt's sheets, whatever they hold) is never guarded.

    family_rule(tt)                      the body's rule ({panel: allowed}) or None
    body_breaches(tt, bom_rows, payload) a calculate / approve payload's breaches          -> [breach dict]
    bom_annotations(tt, bom_rows)        each insulation master's class + the reason it is forbidden (the panels)
    saved_breaches(db, rec)              a SAVED costing against the CURRENT rule (Accept, pre-job)
    refuse_saved(db, rec, action)        409 when a saved costing breaches (Accept, pre-job, job from a costing)
    draft_warnings(db, tt_id, payload)   the forbidden choices a draft tree would offer (save / restore warn)
    unclassified(tt, bom_rows)           insulation choices the check cannot read on a ruled body (admin warning)
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import object_session

from . import insulation_rules as ir

log = logging.getLogger("burtcost")

ACCEPT_HINT = "Re-open it, Remove, save, then accept."


def _group_of(tt):
    if tt is None:
        return None
    if tt.group is not None:
        return tt.group
    from .body_family import _other_group           # the same family body_family() resolves for a group-less body
    return _other_group(object_session(tt))


def family_rule(tt):
    """The body's insulation rule ({panel: frozenset(allowed)}) — its family's; None when the family has none. A
    malformed stored rule (the editor and the data step never write one) is logged and enforced as none."""
    g = _group_of(tt)
    raw = getattr(g, "insulation_rule", None) if g is not None else None
    if not raw:
        return None
    try:
        return ir.normalise_rule(raw)
    except (ValueError, TypeError) as e:
        log.error("trailer group %s carries a malformed insulation_rule (%s) — not enforced", getattr(g, "id", "?"), e)
        return None


def rule_json(tt) -> dict | None:
    """The rule as the page reads it: {"allowed": {panel: [insulation, ...]}} in canonical order, or None."""
    rule = family_rule(tt)
    return json.loads(ir.canonical_rule(rule)) if rule else None


def _views(bom_rows):
    return [ir.row_view(r) for r in bom_rows if getattr(r, "material", True) is not None]


def body_breaches(tt, bom_rows, payload: dict) -> list[dict]:
    rule = family_rule(tt)
    if not rule:
        return []
    return [b.as_dict() for b in ir.breaches(rule, ir.classify_body(_views(bom_rows)), payload or {})]


def bom_annotations(tt, bom_rows) -> dict[int, dict]:
    """{row id: {kind, panel, insulation, forbidden}} for every classified insulation MASTER (kind 'master': the
    panels grey by it) and insulation COST LINE (kind 'line': Remove on a snapshot-less re-open excludes it);
    `forbidden` is the plain-English reason when the family's rule forbids it, else None."""
    cls = ir.classify_body(_views(bom_rows))
    rule = family_rule(tt)
    out = {}
    for kind, items in (("line", ((lid, (p, i)) for lid, (p, i, _s) in cls.lines.items())),
                        ("master", cls.by_master_id.items())):
        for rid, (panel, ins) in items:
            bad = bool(rule) and ins not in rule[panel]
            out[rid] = {"kind": kind, "panel": panel, "insulation": ins,
                        "forbidden": ir.message(panel, ins) if bad else None}
    return out


def unclassified(tt, bom_rows) -> list[dict]:
    """On a body whose family HAS a rule: the insulation choices the check cannot read (reported, never passed)."""
    if not family_rule(tt):
        return []
    return ir.classify_body(_views(bom_rows)).unclassified


def saved_payload(result: dict) -> dict:
    """A saved costing's choices as the payload the check reads. A costing that kept no selection snapshot (saved
    before input_state, or by Calculator 2) is judged by what it PRICED: its included lines, as include_all_items."""
    st = (result or {}).get("input_state") or {}
    snap = st.get("ui_snapshot") if isinstance(st.get("ui_snapshot"), dict) else {}
    sel = st.get("body_option_selections") or (snap or {}).get("body_option_selections") or {}
    flags = st.get("flag_overrides") or {}
    if sel or flags:
        return {"body_option_selections": sel, "flag_overrides": flags}
    included = set()
    for it in (result or {}).get("items") or []:
        if isinstance(it, dict) and not it.get("excluded"):
            bid = it.get("bom_id", it.get("id"))
            if bid is not None:
                included.add(str(bid))
    return {"include_all_items": True, "_included": included}


def saved_breaches(db, rec) -> list[dict]:
    """A SAVED body costing against its family's CURRENT rule. Repairs (no body) and unruled families: []."""
    if rec is None or rec.trailer_type_id is None:
        return []
    from ..database import BillOfMaterial, TrailerType
    tt = db.query(TrailerType).filter_by(id=rec.trailer_type_id).first()
    if not family_rule(tt):
        return []
    try:
        result = json.loads(rec.result_json) if rec.result_json else {}
    except (TypeError, ValueError):
        result = {}
    rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tt.id).all()
    payload = saved_payload(result)
    if payload.get("include_all_items"):
        cls = ir.classify_body(_views(rows))
        payload = {"include_all_items": True,
                   "user_excluded_bom_ids": [lid for lid in cls.lines if str(lid) not in payload["_included"]]}
    return body_breaches(tt, rows, payload)


def refusal(breaches: list[dict], what: str, hint: str) -> dict:
    """The 409 body: a machine code, the breaches, and one plain-English sentence."""
    return {"code": "insulation_rule", "breaches": breaches,
            "message": f"{what} breaks the body family's insulation rule: "
                       + " ".join(b["message"] for b in breaches) + f" {hint}"}


def refuse_saved(db, rec, action: str) -> None:
    """Accept / pre-job / a job from a costing: 409 when the saved costing breaches the CURRENT rule. The saved
    costing is never altered (RT6_RULING_1 Q3)."""
    from fastapi import HTTPException
    found = saved_breaches(db, rec)
    if found:
        label = rec.quote_number or f"Costing #{rec.id}"
        raise HTTPException(status_code=409, detail=refusal(found, f"{label} cannot be {action}: it", ACCEPT_HINT))


def draft_warnings(db, tt_id: int, draft: dict) -> list[dict]:
    """The forbidden choices a draft tree would offer on this body (the save / restore WARNING — drafts are
    Michael's data, so this never blocks). [] when the family has no rule."""
    from ..database import BillOfMaterial, TrailerType
    tt = db.query(TrailerType).filter_by(id=tt_id).first()
    rule = family_rule(tt)
    if not rule:
        return []
    nodes = (draft or {}).get("nodes") if isinstance(draft, dict) else None
    rows = db.query(BillOfMaterial).filter_by(trailer_type_id=tt_id).all()
    found = ir.draft_offers(rule, ir.classify_body(_views(rows)), nodes or {})
    for f in found:
        f["message"] = (f"The draft offers {f['insulation']} on {ir.panel_label(f['panel'])} ('{f['label']}'), which "
                        "the family's rule forbids. Quotes will show it greyed out.")
    return found
