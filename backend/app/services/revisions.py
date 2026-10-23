"""RT10 — revisions visible: every costing shows its REV, and which one is the latest.

Michael's rule (22 Oct 2026): "the first save does not have a REV number ever … Call the 1st quote REV 0, then REV 1
etc." The stored ``result_json["version"]`` is NOT changed (no data is rewritten; RT8's ``repriced.from_version``
keeps its meaning): **REV = version − 1**, a display mapping that lives here, once, on the server (and once in the
client, ``frontend/src/lib/revisions.ts`` / ``static/js/calculator.js`` ``revLabel``).

The chain (RT10_RULING_1 Q1): **the quote number is the chain.** A revision is an edit or re-issue of the same quote
and always keeps its number; a new costing for the same customer is a new number at REV 0. No parent link is stored.

* **Latest** = the highest version among the chain's LIVE rows; a tie goes to the newer ``created_at``, then the higher
  id. Older live rows read "REV n · earlier"; nothing is hidden.
* **Numbering:** Save as Rev. takes ``max(version over the whole chain, soft-deleted rows included) + 1``, decided by
  the server inside the save transaction with the chain's rows locked (``SELECT … FOR UPDATE``): prod runs four
  workers, and the router's ``_approve_lock`` is one per process. A number is never issued twice, and never reused
  after a delete (a customer may hold it). The client's ``next_version`` is ignored.

No migration (ratified): versions are read from ``result_json`` in Python (it is ``Text``; one malformed legacy row
must not fail a whole SQL query), and a chain is a handful of rows on the indexed ``quote_number``.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import CalculationRecord

SEP = " · "


# ── the one mapping ──────────────────────────────────────────────────────────
def version_of(result) -> int:
    """The stored version of a saved costing (its result_json as text or dict); a row without one is version 1."""
    if isinstance(result, (str, bytes)):
        try:
            result = json.loads(result) if result else {}
        except Exception:
            result = {}
    try:
        return max(int((result or {}).get("version", 1) or 1), 1)
    except (TypeError, ValueError, AttributeError):
        return 1


def rev_number(version) -> int:
    """REV = version − 1: the first save (version 1) is REV 0."""
    try:
        return max(int(version or 1) - 1, 0)
    except (TypeError, ValueError):
        return 0


def rev_label(version) -> str:
    return f"REV {rev_number(version)}"


def staff_label(quote_number, version, record_id=None) -> str:
    """Staff screens: ``N10022/10/2026 · REV 1`` — REV 0 included, so a group reads clearly."""
    qn = quote_number or (f"#{record_id}" if record_id is not None else "")
    return f"{qn}{SEP}{rev_label(version)}"


def doc_label(quote_number, version, record_id=None) -> str:
    """Documents (the costing exports, the letterhead quote): the quote number alone at REV 0 ("the first save does
    not have a REV number ever"), ``N10022/10/2026 · REV 1`` from REV 1."""
    qn = quote_number or (f"#{record_id}" if record_id is not None else "")
    n = rev_number(version)
    return qn if n == 0 else f"{qn}{SEP}REV {n}"


# ── the chain ────────────────────────────────────────────────────────────────
def _key(m: dict):
    """The Latest rule's order: the higher version, then the newer created time, then the higher id."""
    c = m.get("created_at")
    return (m["version"], c.replace(tzinfo=None).isoformat() if c is not None else "", m["id"])


def _members(rows) -> list[dict]:
    return [{"id": r.id, "quote_number": r.quote_number, "version": version_of(r.result_json),
             "created_at": r.created_at, "deleted": r.deleted_at is not None} for r in rows]


def _summarise(members: list[dict]) -> dict:
    live = [m for m in members if not m["deleted"]]
    latest = max(live, key=_key) if live else None
    return {"revision_count": len(live),
            "latest_version": latest["version"] if latest else None,
            "latest_rev": rev_number(latest["version"]) if latest else None,
            "latest_id": latest["id"] if latest else None,
            # deleted rows included: the next revision's REV is rev_number(max_version + 1)
            "max_version": max((m["version"] for m in members), default=1)}


def chain_info(db: Session, records) -> dict:
    """{record id: {version, rev, revision_count, latest_version, latest_rev, latest_id, is_latest}} for a page of
    records — the rows already loaded, plus AT MOST ONE query for the members of their chains outside the page
    (never one per row). A record without a quote number is a chain of its own."""
    records = list(records)
    by_id = {r.id: r for r in records}
    members: dict = {}
    for m in _members(records):
        if m["quote_number"]:
            members.setdefault(m["quote_number"], {})[m["id"]] = m
    if members:
        q = (select(CalculationRecord.id, CalculationRecord.quote_number, CalculationRecord.result_json,
                    CalculationRecord.created_at, CalculationRecord.deleted_at)
             .where(CalculationRecord.quote_number.in_(list(members)))
             .where(CalculationRecord.id.notin_(list(by_id))))
        for m in _members(db.execute(q).all()):
            members[m["quote_number"]][m["id"]] = m
    out = {}
    for r in records:
        v = version_of(r.result_json)
        if r.quote_number:
            s = _summarise(list(members[r.quote_number].values()))
        else:
            s = _summarise(_members([r]))
        out[r.id] = {"version": v, "rev": rev_number(v), **s,
                     "is_latest": r.deleted_at is None and s["latest_id"] == r.id}
    return out


def revisions_of(db: Session, rec: CalculationRecord) -> list[dict]:
    """The costing view's Revisions list: every row of the chain, latest first, deleted ones included (marked), so a
    gap in the numbering (a deleted REV) explains itself."""
    if rec.quote_number:
        rows = db.query(CalculationRecord).filter(CalculationRecord.quote_number == rec.quote_number).all()
    else:
        rows = [rec]
    s = _summarise(_members(rows))
    out = []
    for r in sorted(rows, key=lambda x: _key(_members([x])[0]), reverse=True):
        v = version_of(r.result_json)
        try:
            data = json.loads(r.result_json) if r.result_json else {}
        except Exception:
            data = {}
        net = r.net_total if getattr(r, "net_total", None) is not None else data.get("net_total")
        if net is None:
            net = data.get("selling_price") or data.get("grand_total")
        out.append({"id": r.id, "version": v, "rev": rev_number(v),
                    "saved_at": data.get("saved_at") or (r.created_at.isoformat() if r.created_at else None),
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
                    "net_total": float(net) if net is not None else None,
                    "status": r.status or ("accepted" if r.approved_at else "pending"),
                    "deleted": r.deleted_at is not None,
                    "is_latest": r.deleted_at is None and s["latest_id"] == r.id})
    return out


def next_version(db: Session, quote_number: str) -> int:
    """The next revision's stored version: max over the WHOLE chain (soft-deleted rows included) + 1. Locks the
    chain's rows first (FOR UPDATE), then reads them in a new statement — so a second Save as Rev. of the same quote
    in another worker waits for the first to commit and then sees its row. Call inside the save's transaction."""
    db.execute(select(CalculationRecord.id).where(CalculationRecord.quote_number == quote_number)
               .with_for_update()).all()
    versions = [version_of(rj) for (rj,) in db.execute(
        select(CalculationRecord.result_json).where(CalculationRecord.quote_number == quote_number)).all()]
    return (max(versions) if versions else 0) + 1
