"""Capture-for-user — WHO a costing belongs to, decided in one place.

WO v1.52 (Michael, 15 Sep). Michael does costings on behalf of the sales staff, and
until now every costing was credited to whoever was logged in, so his work landed
under "admin" instead of under Nadie or Lezette.

Two people hang off every costing, and they answer different questions:

  * the CREATOR — calculations.user_id. Who pressed Save. It is the audit trail and
    nothing in this module (or anywhere else) rewrites it.
  * the REP — calculations.sales_rep_user_id (migration 0017, "the sales rep this
    quote is being done FOR"). NULL means nobody else, and resolves to the creator.

READS. Anything that names the person a costing BELONGS to goes through
`rep_user` / `rep_user_id` / `rep_username`: the board's Rep column, the legacy
dashboard's person column, the Pre-Job Card's Sales Rep default and the export
filename. One helper, so the rep -> creator fallback exists exactly once and cannot
drift between sites. Reads that name who DID something — the "Created … by" line,
the delete-your-own-draft gate — keep reading user_id, deliberately.

WRITES. Every change of attribution goes through `plan_rep_change`, which states the
whole enforcement rule (G1): a request that would credit a costing to anyone other
than the person it is credited to already needs `costings.capture_for_user`. The
calculator hides its dropdown from everyone else, but that is display only — this
function is the control, and /api/approve (create AND overwrite) and the re-assign
route all call it BEFORE they write anything.

JOURNAL. Every capture and every re-assign appends one CalculationSalesRepAudit row
(migration 0048) with ids and USERNAME snapshots, in the same transaction as the
change itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, object_session
from sqlalchemy.orm.exc import UnmappedInstanceError

from ..database import CalculationSalesRepAudit, User
from ..deps import user_can

CAPTURE_PERMISSION = "costings.capture_for_user"


class _Absent:
    """The payload did not mention sales_rep_user_id at all."""
    def __repr__(self) -> str:   # pragma: no cover — debugging aid only
        return "ABSENT"


ABSENT = _Absent()

# The "Capture for" picker's projection — the ONE place its per-user fields are chosen.
# The follow-on business-partner lane widens the picker by adding a field here (and to
# the calculator's label formatter, _captureForLabel); the query, the ordering, the gate
# and the route stay as they are.
CAPTURE_FOR_USER_FIELDS: tuple[str, ...] = ("id", "username", "role")


# ── reads ────────────────────────────────────────────────────────────────────

def rep_user_id(rec) -> Optional[int]:
    """The id of the user this costing is FOR: the captured-for rep, else the creator."""
    rep = getattr(rec, "sales_rep_user_id", None)
    return rep if rep is not None else getattr(rec, "user_id", None)


def rep_user(rec) -> Optional[User]:
    """The User this costing is FOR: the captured-for rep, else the creator.

    The relationship is trusted only while it agrees with the column — an id assigned
    in this session before a refresh leaves `rec.sales_rep` pointing at the old user,
    and naming the wrong person is exactly the bug this lane exists to fix.
    """
    rep_id = getattr(rec, "sales_rep_user_id", None)
    if rep_id is None:
        return getattr(rec, "user", None)
    rep = getattr(rec, "sales_rep", None)
    if rep is None or rep.id != rep_id:
        try:
            sess = object_session(rec)
        except UnmappedInstanceError:   # a plain object standing in for a record
            sess = None
        rep = sess.get(User, rep_id) if sess is not None else None
    # A dangling id cannot survive the FK (ON DELETE SET NULL), but if one ever did the
    # costing still belongs to somebody: its creator.
    return rep if rep is not None else getattr(rec, "user", None)


def rep_username(rec, default: Any = "—"):
    u = rep_user(rec)
    return u.username if u is not None else default


def is_captured_for_someone_else(rec) -> bool:
    return getattr(rec, "sales_rep_user_id", None) is not None


# ── the picker ───────────────────────────────────────────────────────────────

def capture_for_candidates(db: Session) -> list[dict]:
    """Every user on the Manage Users page, in its order (Michael's ruling: the list is
    NOT narrowed by role — username + role let the admin tell people apart)."""
    users = db.query(User).order_by(User.username).all()
    return [{f: getattr(u, f) for f in CAPTURE_FOR_USER_FIELDS} for u in users]


# ── writes: the G1 gate ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class RepChange:
    """What the attribution must become, decided before anything is written."""
    stored: Optional[int]               # the value calculations.sales_rep_user_id must hold
    action: Optional[str] = None        # 'capture' | 'reassign' | None (nothing changes)
    from_user: Optional[User] = None    # effective rep before
    to_user: Optional[User] = None      # effective rep after

    @property
    def changed(self) -> bool:
        return self.action is not None


def _parse_requested(requested) -> Optional[int]:
    """None for "nobody else"; an int id otherwise. 422 for anything that is neither."""
    if requested is None or requested == "":
        return None
    if isinstance(requested, bool):          # bool is an int subclass — True is not user 1
        raise HTTPException(status_code=422, detail="sales_rep_user_id must be a user id.")
    if isinstance(requested, int):
        return requested
    if isinstance(requested, str) and requested.strip().isdigit():
        return int(requested.strip())
    raise HTTPException(status_code=422, detail="sales_rep_user_id must be a user id.")


def plan_rep_change(db: Session, caller, requested, *, creator_id: Optional[int],
                    current_stored: Optional[int] = None, is_new: bool) -> RepChange:
    """Validate a requested attribution and say what to store. Writes nothing.

    `requested` is the payload's sales_rep_user_id:
      ABSENT    not mentioned -> nothing changes. A new costing is its creator's own; an
                edited costing keeps whoever it is for now. This is what every calculator
                without the dropdown sends (non-admins, Calculator 2), so an edit by one
                of them can never strip an attribution an admin made.
      None/""   "nobody else" -> the creator.
      an id     that user.

    The comparison is on the EFFECTIVE rep (rep -> creator), so choosing yourself on
    your own new costing, or re-choosing the person a costing is already for, is not a
    change: it stores exactly what was there (NULL for "the creator") and journals
    nothing. That is what keeps an untouched dropdown byte-identical to a save that
    never had one.

    Any real change needs costings.capture_for_user -> 403 without it (checked before
    the target's existence, so a refused caller learns nothing about user ids), then
    422 if the target user does not exist.
    """
    before_id = creator_id if is_new or current_stored is None else current_stored
    unchanged = RepChange(stored=None if is_new else current_stored)
    if requested is ABSENT:
        return unchanged

    target = _parse_requested(requested)
    target_id = creator_id if target is None else target
    if target_id == before_id:
        return unchanged

    if not user_can(caller, CAPTURE_PERMISSION, db):
        raise HTTPException(
            status_code=403,
            detail=("Only an administrator can capture a costing for someone else. "
                    "Save it under your own name, or ask an administrator to change "
                    "who it is for."))

    to_user = db.get(User, target_id) if target_id is not None else None
    if target_id is not None and to_user is None:
        raise HTTPException(
            status_code=422,
            detail="The user this costing is being captured for no longer exists — "
                   "choose them again.")
    from_user = db.get(User, before_id) if before_id is not None else None
    return RepChange(
        stored=None if target_id == creator_id else target_id,
        action="capture" if is_new else "reassign",
        from_user=from_user,
        to_user=to_user,
    )


def record_rep_change(db: Session, rec, change: RepChange, actor) -> None:
    """Journal a planned change against `rec` (which must have an id). The caller owns
    the commit, so the journal row lands in the same transaction as the change."""
    if not change.changed:
        return
    db.add(CalculationSalesRepAudit(
        calculation_id=rec.id,
        action=change.action,
        from_user_id=getattr(change.from_user, "id", None),
        from_username=getattr(change.from_user, "username", None),
        to_user_id=getattr(change.to_user, "id", None),
        to_username=getattr(change.to_user, "username", None),
        actor_user_id=getattr(actor, "id", None),
        actor_username=getattr(actor, "username", None),
    ))


def rep_journal(db: Session, calculation_id: int) -> list[dict]:
    rows = (db.query(CalculationSalesRepAudit)
              .filter(CalculationSalesRepAudit.calculation_id == calculation_id)
              .order_by(CalculationSalesRepAudit.created_at, CalculationSalesRepAudit.id)
              .all())
    return [{
        "action": r.action,
        "from_user_id": r.from_user_id,
        "from_username": r.from_username,
        "to_user_id": r.to_user_id,
        "to_username": r.to_username,
        "actor_username": r.actor_username,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]
