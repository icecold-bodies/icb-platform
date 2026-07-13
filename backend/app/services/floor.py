"""§9 floor-doc event integration P1 (v1.41.0) — the server-side floor transition engine.

The /plan Production Flow floor was a client-owned JSON document: browsers mutated a local
copy and PUT the WHOLE document back (last-writer-wins — the two-planners clobber race, the
mock-mode seed-stomp hazard, zero audit). This module makes the SERVER the only writer:

    apply_transition(db, ttype, payload, user)
        SELECT FOR UPDATE plan_floor_state(id=1)  → parse doc (loadState-tolerant)
        → server-side prune of orphaned cut entries (the engine's lazy prune, now persisted)
        → the transition's validator/mutator (line-for-line ports of the engine guards —
          productionFlowEngine.ts is the reference; its copies remain as the MOCK-mode
          implementation, diffable by eye against this file)
        → doc serialized back, version += 1, updated_at = now
        → FloorEvent appended (house audit idiom)
        → ONE commit. Any 404/409/422 rolls the lot back — never half-applied.

The DOC SHAPE IS UNCHANGED byte-for-byte ({v:1, pre, qc, cut, cutAt, consumed, mergedJobs,
mergedChassis} + the v1.40.8 stamps in Z-format) so every existing reader — plan_status
labels, drawer clocks, planning occupancy/pool — works untouched.

Concurrency: clients never send versions. Staleness is caught ENTITY-level — every payload
names its from-location (id/li/vin/job) and the validator checks "is it where you say it
is" under the row lock, so two planners dragging DIFFERENT items both succeed while a
stale drag of a moved item 409s with a human message.

P2 (v1.41.x) — FULL INTEGRATION: the transitions now drive the domain chokepoints inside the
SAME locked transaction via commit=False threading (send_pre_job_card precedent). Lock order
is floor_row → jobs → chassis (the row lock is taken first, always).

    declare_cut / undo_cut        → planning_svc.mark_slots_cut (slots 'completed' ⇄ 'scheduled')
    drop_assembly                 → record_panels_arrived_in_bay (relink-tolerant, see below)
    assembly_back_to_track        → clear_panels_arrived
    body_back_to_panels           → clear_panels_arrived (idempotent 0 when never staged)
    drop_chassis                  → assign_assembly_bay        (UPSERT — re-drops self-heal)
    chassis_back_to_parking       → return_chassis_to_parking  (+ production_jobs_audit row)
    confirm_merge                 → record_body_attached       (THE real merge: links
                                    job.chassis_record_id; VIN-attestation guard for free)
    dispatch                      → record_moved_to_awaiting_qa (status 'awaiting_qa' —
                                    Kenny's QC inbox picks it up natively)

DELIBERATE DEVIATION from the P1 design note: the panels_arrived_in_bay moment is
drop_assembly (the single-slot MERGE BLOCK), not start_body — a floor line's TRACK holds
many bodies, but the DB bay model is one job's panels per bay (busy-bay 409) and
compute_bay_merge_readiness derives 'ready_to_merge' from loose panels + chassis on the
bay, which is exactly the merge block's shape. start_body/move_body stay doc-only
(journaled in floor_events as before).

Bay identity: _bay_for_line() maps floor line index → the nth ACTIVE assembly_bays row by
(sort_order, id) — no link table, no second truth. Cutover tolerance: transitions whose DB
fact is ALREADY true (a pre-P2 panels event on the same bay, body already attached to the
same pair, chassis already awaiting QA) no-op with a details note instead of 409ing, so
in-flight floors converge instead of jamming; anything contradictory stays LOUD.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mes import (
    FloorEvent, PlanFloorState, PlanningSlot, ProductionJob, ProductionStageThreshold,
)
from app.services import chassis as chassis_svc
from app.services import planning as planning_svc

logger = logging.getLogger("icb.floor")

ROW_ID = 1
FLOOR_LINES = 5
CHUTE = 40  # engine constant — track length units (productionFlowEngine.ts:93)


# ── doc helpers (ports of the engine's loadState/emptyBays tolerance) ─────────

def _empty_doc() -> dict:
    return {
        "v": 1,
        "pre": [{"id": f"Bay {n}", "bodies": [],
                 "merge": {"chassis": None, "assembly": None, "attached": None}}
                for n in range(1, FLOOR_LINES + 1)],
        "qc": [], "cut": [], "cutAt": {}, "consumed": [],
        "mergedJobs": [], "mergedChassis": [],
    }


def _load_doc(row: Optional[PlanFloorState]) -> dict:
    """Tolerant parse mirroring engine loadState: pre must be a 5-list else empty bays;
    every collection defaults; unknown keys survive round-trip untouched."""
    try:
        doc = json.loads(row.state) if row is not None and row.state else {}
    except Exception:  # noqa: BLE001 — a corrupt doc degrades to empty, never 500s
        logger.warning("floor: stored document unreadable — treating as empty", exc_info=True)
        doc = {}
    base = _empty_doc()
    out = dict(doc) if isinstance(doc, dict) else {}
    pre = out.get("pre")
    if not (isinstance(pre, list) and len(pre) == FLOOR_LINES):
        out["pre"] = base["pre"]
    for k in ("qc", "cut", "consumed", "mergedJobs", "mergedChassis"):
        if not isinstance(out.get(k), list):
            out[k] = []
    if not isinstance(out.get("cutAt"), dict):
        out["cutAt"] = {}
    out["v"] = 1
    return out


def _iso_z(dt: datetime) -> str:
    """Millisecond 'Z' format — byte-parity with Date.prototype.toISOString(), which the
    v1.40.8 stamps established and _stage_clock's replace('Z','+00:00') parse expects."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _now_iso() -> str:
    return _iso_z(datetime.now(timezone.utc))


def _parse_stamp(iso) -> Optional[datetime]:
    """Tolerant parse of a doc stamp (engine toISOString / _iso_z). None when absent/garbled —
    callers treat an unparseable entry stamp as elapsed 0 (the v1.41.1 honesty rule's cousin:
    never invent time)."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _pre_assembly_threshold_s(db: Session) -> float:
    """A11 chute: the pre_assembly stage threshold in SECONDS (production_stage_thresholds is
    hours). Falls back to the ratified 2h if the row is missing/inactive — reset_timer must
    not 500 because an admin deactivated a threshold row."""
    t = db.execute(select(ProductionStageThreshold).where(
        ProductionStageThreshold.stage_code == "pre_assembly",
        ProductionStageThreshold.is_active.is_(True))).scalars().first()
    return float(t.threshold_hours) * 3600.0 if t is not None else 2.0 * 3600.0


def _jobs_on_floor(doc: dict) -> set[str]:
    s: set[str] = set()
    for bay in doc["pre"]:
        for b in bay.get("bodies") or []:
            if isinstance(b, dict) and b.get("job") is not None:
                s.add(str(b["job"]))
        m = bay.get("merge") or {}
        a = m.get("assembly")
        if isinstance(a, dict) and a.get("job") is not None:
            s.add(str(a["job"]))
        att = m.get("attached")
        if isinstance(att, dict) and isinstance(att.get("body"), dict) \
                and att["body"].get("job") is not None:
            s.add(str(att["body"]["job"]))
    return s


def _qc_jobs(doc: dict) -> set[str]:
    out = set()
    for e in doc["qc"]:
        v = e.get("job") if isinstance(e, dict) else e
        if v is not None:
            out.add(str(v))
    return out


def _find_body_loc(doc: dict, body_id: str):
    for ci, bay in enumerate(doc["pre"]):
        for bi, b in enumerate(bay.get("bodies") or []):
            if isinstance(b, dict) and str(b.get("id")) == str(body_id):
                return {"ci": ci, "bi": bi, "body": b}
    return None


def _find_assembly_in_merge(doc: dict, body_id: str):
    for li, bay in enumerate(doc["pre"]):
        a = (bay.get("merge") or {}).get("assembly")
        if isinstance(a, dict) and str(a.get("id")) == str(body_id):
            return {"li": li, "body": a}
    return None


def _find_free_pos(others: list[dict], length: float, desired: float):
    """Verbatim port of engine findFreePos (:274-280): clamp desired into [0, CHUTE-len],
    collect gaps between occupied intervals, pick the gap-point closest to desired."""
    max_pos = CHUTE - length
    desired = max(0.0, min(max_pos, float(desired)))
    occ = sorted(([float(o["pos"]), float(o["pos"]) + float(o["len"])] for o in others),
                 key=lambda iv: iv[0])
    gaps: list[list[float]] = []
    cur = 0.0
    for iv in occ:
        if iv[0] - cur >= length:
            gaps.append([cur, iv[0] - length])
        cur = max(cur, iv[1])
    if CHUTE - cur >= length:
        gaps.append([cur, CHUTE - length])
    if not gaps:
        return None
    best, bd = None, 1e9
    for g in gaps:
        p = max(g[0], min(g[1], desired))
        d = abs(p - desired)
        if d < bd:
            bd, best = d, p
    return best


def _apply_stage_fill(body: dict) -> None:
    """Port of engine applyStageFill (:281) — green bodies re-derive prog from position."""
    if body.get("status") == "green":
        length = float(body.get("len") or 0)
        denom = CHUTE - length
        pos = float(body.get("pos") or 0)
        body["prog"] = max(0.0, min(1.0, pos / denom)) if denom > 0 else 0.0


def _scheduled_job_numbers(db: Session) -> set[str]:
    rows = db.execute(
        select(ProductionJob.job_number)
        .join(PlanningSlot, PlanningSlot.production_job_id == ProductionJob.id)
        .where(PlanningSlot.status == "scheduled")).scalars().all()
    return {str(j) for j in rows if j}


def _slot_anchor_job_numbers(db: Session) -> set[str]:
    """§9 P2 — jobs still ANCHORED to a V/P slot row: 'scheduled' + 'completed' (declare-cut
    flips a cut job's slot to completed, but the row remains its anchor — the prune and the
    back-to-panels reverse must not treat a cut job as unscheduled)."""
    rows = db.execute(
        select(ProductionJob.job_number)
        .join(PlanningSlot, PlanningSlot.production_job_id == ProductionJob.id)
        .where(PlanningSlot.status.in_(("scheduled", "in_progress", "completed")))).scalars().all()
    return {str(j) for j in rows if j}


def _prune_cut(db: Session, doc: dict, events: list[dict]) -> None:
    """The engine's lazy cut-prune (applyLivePanels :231-237), moved server-side: cut entries
    whose job is no longer scheduled and never started anything are dropped. In the engine
    this never set dirty (lazily persisted); with the PUT gone it MUST live here or orphan
    entries would strand in the doc forever. Each drop journals a cut_pruned event.
    §9 P2: the anchor set includes 'completed' slots — declare-cut flips the slot status,
    and without this the very act of cutting would de-anchor (and prune) the cut entry."""
    sched = _slot_anchor_job_numbers(db)
    on_floor = _jobs_on_floor(doc)
    in_qc = _qc_jobs(doc)
    consumed = {str(j) for j in doc["consumed"]}
    merged = {str(j) for j in doc["mergedJobs"]}
    keep, dropped = [], []
    for j in [str(x) for x in doc["cut"]]:
        if j not in sched and j not in consumed and j not in on_floor \
                and j not in in_qc and j not in merged:
            dropped.append(j)
        else:
            keep.append(j)
    if dropped:
        doc["cut"] = keep
        for j in dropped:
            doc["cutAt"].pop(j, None)
            events.append({"event_type": "cut_pruned", "job_number": j,
                           "from_stage": "panels_ready", "to_stage": "vp", "details": {}})


def _job_by_number(db: Session, job_number: str) -> Optional[ProductionJob]:
    return db.execute(
        select(ProductionJob).where(ProductionJob.job_number == str(job_number))
        .order_by(ProductionJob.id.desc())).scalars().first()


def _bad(code: int, msg: str):
    raise HTTPException(status_code=code, detail=msg)


# ── §9 P2 chokepoint plumbing ─────────────────────────────────────────────────

def _actor(ctx: dict) -> str:
    return (getattr(ctx.get("user"), "username", None) or "floor")[:64]


def _bay_for_line(db: Session, li: int):
    """Floor line index (0-4) → the nth ACTIVE assembly_bays row by (sort_order, id) — the
    exact order every bay list/admin surface uses. No link table, no second truth: reordering
    bays in Master Data re-aims the map (Master Data owns bay identity)."""
    bays = chassis_svc.list_assembly_bays(db)
    if li >= len(bays):
        _bad(422, f"Bay {li + 1} has no matching assembly bay in Master Data "
                  f"(only {len(bays)} active).")
    return bays[li]


def _chassis_by_vin(db: Session, vin: str):
    from app.models.mes import ChassisRecord
    return db.execute(select(ChassisRecord).where(
        ChassisRecord.vin == vin, ChassisRecord.deleted_at.is_(None))
        .order_by(ChassisRecord.id.desc())).scalars().first()


def _require_job(db: Session, job_number: str) -> ProductionJob:
    pj = _job_by_number(db, job_number)
    if pj is None:
        _bad(422, f"No production job found for {job_number} — the floor can't write its "
                  "production events.")
    return pj


def _sync_panels_event(db: Session, pj: ProductionJob, bay, ctx: dict):
    """Ensure the DB says this job's panels are in `bay` (the drop_assembly chokepoint).
    Same-bay pre-existing event (pre-P2 lane, or a body re-staged after assembly_back left
    the event... it doesn't — see clear below) → no-op; an event on a DIFFERENT bay is
    RELINKED (clear + re-record, one transaction) — the floor is the operating surface and
    Master-Data order is bay truth. Consumed panels 409 inside clear_panels_arrived (loud).
    Returns the bay_id the event was relinked from, or None."""
    from app.models.mes import ProductionJobBayEvent
    existing = db.execute(
        select(ProductionJobBayEvent.bay_id).where(
            ProductionJobBayEvent.production_job_id == pj.id,
            ProductionJobBayEvent.event_type == "panels_arrived_in_bay")
        .order_by(ProductionJobBayEvent.id.desc())).scalars().first()
    user_id = getattr(ctx.get("user"), "id", None)
    if existing == bay.id:
        return None
    if existing is not None:
        chassis_svc.clear_panels_arrived(db, pj.id, commit=False)
    chassis_svc.record_panels_arrived_in_bay(db, pj.id, bay.id, user_id=user_id, commit=False)
    return existing


# ── the 11 transitions (each: validate → mutate doc → return the event draft) ─

def _t_declare_cut(db, doc, p, ctx):
    job = str(p.get("job") or "") or _bad(422, "declare_cut needs a job number")
    if job not in _scheduled_job_numbers(db):
        _bad(422, f"Job {job} has no scheduled V/P slot — only scheduled jobs can be declared cut.")
    if job in {str(x) for x in doc["mergedJobs"]}:
        _bad(409, f"Job {job} is merged with its chassis — it can't re-enter Panels Ready.")
    if job in {str(x) for x in doc["cut"]} or job in {str(x) for x in doc["consumed"]} \
            or job in _jobs_on_floor(doc) or job in _qc_jobs(doc):
        _bad(409, f"Job {job}'s panels are already on the floor.")
    doc["cut"].append(job)
    doc["cutAt"][job] = _now_iso()
    # P2: realize the slot vocabulary — the V/P slot is done producing (its clock stops, the
    # cell frees, unschedule 409s until undo). No commit — apply_transition owns the txn.
    flipped = planning_svc.mark_slots_cut(db, job_number=job, cut=True)
    return {"event_type": "declare_cut", "job_number": job,
            "from_stage": "vp", "to_stage": "panels_ready",
            "details": {"slots_completed": flipped}}


def _t_undo_cut(db, doc, p, ctx):
    job = str(p.get("job") or "") or _bad(422, "undo_cut needs a job number")
    if job not in {str(x) for x in doc["cut"]}:
        _bad(409, f"Job {job} is not on the Panels Ready rail — the floor has moved on. Refreshed.")
    if job in {str(x) for x in doc["consumed"]} or job in _jobs_on_floor(doc) \
            or job in _qc_jobs(doc) or job in {str(x) for x in doc["mergedJobs"]}:
        _bad(409, f"Job {job}'s panels have already started — drag the body back first.")
    doc["cut"] = [x for x in doc["cut"] if str(x) != job]
    doc["cutAt"].pop(job, None)
    flipped = planning_svc.mark_slots_cut(db, job_number=job, cut=False)   # completed → scheduled
    return {"event_type": "undo_cut", "job_number": job,
            "from_stage": "panels_ready", "to_stage": "vp",
            "details": {"slots_rescheduled": flipped}}


def _t_start_body(db, doc, p, ctx):
    job = str(p.get("job") or "") or _bad(422, "start_body needs a job number")
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "start_body needs a valid assembly line index (0-4).")
    if job not in {str(x) for x in doc["cut"]}:
        _bad(409, f"Job {job} is not on the Panels Ready rail — the floor has moved on. Refreshed.")
    if job in {str(x) for x in doc["consumed"]} or job in _jobs_on_floor(doc) \
            or job in {str(x) for x in doc["mergedJobs"]}:
        _bad(409, f"Job {job}'s panels have already started in a bay.")
    card = p.get("card") or {}
    length = float(card.get("len") or 5.4)
    pos = _find_free_pos(doc["pre"][li]["bodies"], length, 0)
    if pos is None:
        _bad(409, f"Bay {li + 1}'s track has no free position for a {length:.1f} m body.")
    doc["consumed"].append(job)
    body = {
        "id": job, "job": job,
        "cust": str(card.get("cust") or "—")[:120],
        "len": length, "type": str(card.get("type") or "")[:60],
        "status": "green", "prog": 0, "pos": pos, "days": 0,
        "chassisVin": str(card.get("vin") or "—")[:64],
        "method": str(card.get("method") or "Vacuum")[:16],
        "origin": card.get("origin"),
        "enteredAt": _now_iso(),
    }
    doc["pre"][li]["bodies"].append(body)
    return {"event_type": "start_body", "job_number": job,
            "from_stage": "panels_ready", "to_stage": "pre_assembly",
            "details": {"li": li, "pos": pos, "len": length}}


def _t_body_back_to_panels(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "body_back_to_panels needs a body id")
    loc = _find_body_loc(doc, body_id)
    if loc is None:
        _bad(409, "That body is no longer on a bay track — the floor has moved on. Refreshed.")
    job = str(loc["body"].get("job"))
    if job in {str(x) for x in doc["mergedJobs"]}:
        _bad(409, f"Job {job} is merged with its chassis — it can't move back to Panels Ready.")
    if job not in _slot_anchor_job_numbers(db):        # P2: a cut job's slot is 'completed', still an anchor
        _bad(409, f"Job {job} has no V/P slot row anymore — it can't re-enter the queue.")
    doc["pre"][loc["ci"]]["bodies"].pop(loc["bi"])
    doc["consumed"] = [x for x in doc["consumed"] if str(x) != job]
    if job not in {str(x) for x in doc["cut"]}:
        doc["cut"].append(job)
    doc["cutAt"][job] = _now_iso()                     # re-entered Panels Ready NOW (v1.40.8 rule)
    # P2: if the panels ever staged at a merge block, un-commit them from the DB bay too
    # (idempotent — removed=0 for a track-only body; 409s if consumed by an attached body).
    pj = _job_by_number(db, job)
    removed = chassis_svc.clear_panels_arrived(db, pj.id, commit=False)["removed"] if pj else 0
    return {"event_type": "body_back_to_panels", "job_number": job,
            "from_stage": "pre_assembly", "to_stage": "panels_ready",
            "details": {"from_li": loc["ci"], "panels_events_cleared": removed}}


def _t_move_body(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "move_body needs a body id")
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "move_body needs a valid assembly line index (0-4).")
    loc = _find_body_loc(doc, body_id)
    if loc is None:
        _bad(409, "That body is no longer on a bay track — the floor has moved on. Refreshed.")
    body = loc["body"]
    others = [b for b in doc["pre"][li]["bodies"] if str(b.get("id")) != body_id]
    pos = _find_free_pos(others, float(body.get("len") or 0), float(p.get("desired") or 0))
    if pos is None:
        _bad(409, f"Bay {li + 1}'s track has no free position there.")
    doc["pre"][loc["ci"]]["bodies"].pop(loc["bi"])
    body["pos"] = pos
    _apply_stage_fill(body)
    doc["pre"][li]["bodies"].append(body)
    return {"event_type": "move_body", "job_number": str(body.get("job")),
            "from_stage": "pre_assembly", "to_stage": "pre_assembly",
            "details": {"from_li": loc["ci"], "li": li, "pos": pos}}


# ── A11 Pre-Assembly Chute (v1.42) — per-card work-clock transitions ───────────
# The chute renders each body's position from (now - enteredAt) / pre_assembly threshold.
# Two operator gestures mutate that clock, both journaled like every other transition:
#   reset_timer — a drag BACK re-arms the clock to `fraction` of the threshold ("this
#                 needs more time"). Forward drags are visual-only and never reach here.
#   toggle_hold — pause/resume. Hold freezes the DISPLAY clock by snapshotting elapsed
#                 seconds (held/heldAt/heldElapsedS on the body — additive doc fields);
#                 resume re-bases enteredAt = now - snapshot so work-time continues where
#                 it paused. Health Check's wall-clock breach view (v1.41.1) deliberately
#                 keeps reading the raw stamps — a held body still occupies the bay.

def _t_reset_timer(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "reset_timer needs a body id")
    try:
        frac = float(p.get("fraction"))
    except (TypeError, ValueError):
        frac = -1.0
    if not (0.0 <= frac <= 1.0):
        _bad(422, "reset_timer needs a fraction between 0 and 1.")
    loc = _find_body_loc(doc, body_id)
    if loc is None:
        _bad(409, "That body is no longer on a bay track — the floor has moved on. Refreshed.")
    body = loc["body"]
    thr_s = _pre_assembly_threshold_s(db)
    new_elapsed_s = frac * thr_s
    old_entered = body.get("enteredAt")
    body["enteredAt"] = _iso_z(datetime.now(timezone.utc) - timedelta(seconds=new_elapsed_s))
    if body.get("held"):
        body["heldElapsedS"] = round(new_elapsed_s, 3)   # a held card re-arms its frozen display too
    return {"event_type": "reset_timer", "job_number": str(body.get("job")),
            "from_stage": "pre_assembly", "to_stage": "pre_assembly",
            "details": {"li": loc["ci"], "fraction": round(frac, 4),
                        "threshold_s": round(thr_s, 1),
                        "old_entered_at": old_entered, "new_entered_at": body["enteredAt"]}}


def _t_toggle_hold(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "toggle_hold needs a body id")
    loc = _find_body_loc(doc, body_id)
    if loc is None:
        _bad(409, "That body is no longer on a bay track — the floor has moved on. Refreshed.")
    body = loc["body"]
    now = datetime.now(timezone.utc)
    if body.get("held"):
        held_s = max(0.0, float(body.get("heldElapsedS") or 0.0))
        body["enteredAt"] = _iso_z(now - timedelta(seconds=held_s))
        body["held"] = False
        body.pop("heldAt", None)
        body.pop("heldElapsedS", None)
        details = {"li": loc["ci"], "is_held": False, "resumed_elapsed_s": round(held_s, 3)}
    else:
        entered = _parse_stamp(body.get("enteredAt"))
        elapsed_s = max(0.0, (now - entered).total_seconds()) if entered else 0.0
        body["held"] = True
        body["heldAt"] = _iso_z(now)
        body["heldElapsedS"] = round(elapsed_s, 3)
        details = {"li": loc["ci"], "is_held": True, "held_elapsed_s": round(elapsed_s, 3)}
    return {"event_type": "toggle_hold", "job_number": str(body.get("job")),
            "from_stage": "pre_assembly", "to_stage": "pre_assembly", "details": details}


def _t_drop_assembly(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "drop_assembly needs a body id")
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "drop_assembly needs a valid assembly line index (0-4).")
    m = doc["pre"][li]["merge"]
    if m.get("attached") or m.get("assembly"):
        _bad(409, f"Bay {li + 1}'s merge block is busy.")
    loc = _find_body_loc(doc, body_id)
    if loc is None:
        _bad(409, "That body is no longer on a bay track — the floor has moved on. Refreshed.")
    if loc["ci"] != li:
        _bad(409, "A body can only stage into its own line's merge block.")
    body = loc["body"]
    chassis = m.get("chassis")
    if isinstance(chassis, dict) and chassis.get("job") is not None \
            and str(chassis["job"]) != str(body.get("job")):
        _bad(409, f"The staged chassis belongs to job {chassis['job']} — same-job merges only.")
    # P2 chokepoint — the merge block is the 1:1 "panels on the bay" moment (a line's TRACK
    # holds many bodies; the DB bay model is one job's panels per bay). Same-bay pre-existing
    # event no-ops; a stale different-bay event is relinked; consumed panels 409 loudly.
    pj = _require_job(db, str(body.get("job")))
    bay = _bay_for_line(db, li)
    relinked_from = _sync_panels_event(db, pj, bay, ctx)
    doc["pre"][li]["bodies"].pop(loc["bi"])
    body["mergeEnteredAt"] = _now_iso()
    m["assembly"] = body
    details = {"li": li, "bay_id": bay.id, "bay_code": bay.code}
    if relinked_from is not None:
        details["panels_relinked_from_bay_id"] = relinked_from
    return {"event_type": "drop_assembly", "job_number": str(body.get("job")),
            "from_stage": "pre_assembly", "to_stage": "pre_merge", "details": details}


def _t_assembly_back_to_track(db, doc, p, ctx):
    body_id = str(p.get("id") or "") or _bad(422, "assembly_back_to_track needs a body id")
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "assembly_back_to_track needs a valid assembly line index (0-4).")
    found = _find_assembly_in_merge(doc, body_id)
    if found is None:
        _bad(409, "That body is not staged in a merge block — the floor has moved on. Refreshed.")
    body = found["body"]
    pos = _find_free_pos(doc["pre"][li]["bodies"], float(body.get("len") or 0),
                         float(p.get("desired") or body.get("pos") or 0))
    if pos is None:
        _bad(409, f"Bay {li + 1}'s track has no free position for that body.")
    doc["pre"][found["li"]]["merge"]["assembly"] = None
    body.pop("mergeEnteredAt", None)                   # merge clock cleared; pre-assembly clock resumes
    body["pos"] = pos
    doc["pre"][li]["bodies"].append(body)
    # P2: leaving the merge block un-commits the panels from the DB bay (reverse of
    # drop_assembly; 409s inside if a body was already attached — matches the doc guard).
    pj = _job_by_number(db, str(body.get("job")))
    removed = chassis_svc.clear_panels_arrived(db, pj.id, commit=False)["removed"] if pj else 0
    return {"event_type": "assembly_back_to_track", "job_number": str(body.get("job")),
            "from_stage": "pre_merge", "to_stage": "pre_assembly",
            "details": {"from_li": found["li"], "li": li, "pos": pos,
                        "panels_events_cleared": removed}}


def _t_drop_chassis(db, doc, p, ctx):
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "drop_chassis needs a valid assembly line index (0-4).")
    vin = str(p.get("vin") or "") or _bad(422, "drop_chassis needs a chassis VIN")
    m = doc["pre"][li]["merge"]
    if m.get("attached") or m.get("chassis"):
        _bad(409, f"Bay {li + 1}'s merge block already holds a chassis.")
    if vin in {str(x) for x in doc["mergedChassis"]}:
        _bad(409, f"Chassis {vin} is already merged.")
    for other_li, bay in enumerate(doc["pre"]):
        ch = (bay.get("merge") or {}).get("chassis")
        if isinstance(ch, dict) and str(ch.get("id")) == vin:
            _bad(409, f"Chassis {vin} is already staged in Bay {other_li + 1}.")
    # DB truth for identity + linked job (harden the engine's client-side same-job check):
    from app.models.mes import ChassisRecord
    rec = db.execute(select(ChassisRecord).where(
        ChassisRecord.vin == vin, ChassisRecord.deleted_at.is_(None))).scalars().first()
    if rec is None:
        _bad(404, f"No chassis with VIN {vin}.")
    linked = db.execute(select(ProductionJob.job_number).where(
        ProductionJob.chassis_record_id == rec.id)
        .order_by(ProductionJob.id.desc())).scalars().first()
    linked_job = str(linked) if linked else (str(rec.job_number) if rec.job_number else None)
    assembly = m.get("assembly")
    if isinstance(assembly, dict) and assembly.get("job") is not None and linked_job \
            and str(assembly["job"]) != linked_job:
        _bad(409, f"Chassis {vin} belongs to job {linked_job} — same-job merges only.")
    # P2 chokepoint — the chassis physically arrives at the line's bay. assign_assembly_bay
    # UPSERTs the cycle's assembly_assigned event (re-drops self-heal) and carries the house
    # guards: booked-in (open VCL) 422, VIN/customer 409s, one-chassis-per-bay 409.
    bay = _bay_for_line(db, li)
    chassis_svc.assign_assembly_bay(db, rec.id, bay.id, _actor(ctx), commit=False)
    card = p.get("card") or {}
    m["chassis"] = {
        "id": vin, "job": linked_job,
        "model": str(card.get("model") or rec.make or "—")[:120],
        "cust": str(card.get("cust") or rec.customer_name or "—")[:120],
        "kind": card.get("kind"), "img": card.get("img"),
    }
    return {"event_type": "drop_chassis", "job_number": linked_job,
            "from_stage": "parking", "to_stage": "pre_merge",
            "details": {"li": li, "vin": vin, "bay_id": bay.id, "bay_code": bay.code,
                        "chassis_record_id": rec.id}}


def _t_chassis_back_to_parking(db, doc, p, ctx):
    vin = str(p.get("vin") or "") or _bad(422, "chassis_back_to_parking needs a chassis VIN")
    for li, bay in enumerate(doc["pre"]):
        m = bay.get("merge") or {}
        ch = m.get("chassis")
        if isinstance(ch, dict) and str(ch.get("id")) == vin:
            if m.get("assembly"):
                _bad(409, "Pull the body back to the track before returning the chassis to Parking.")
            # P2 chokepoint — the reverse of assign_assembly_bay: deletes the cycle's
            # assembly_assigned event, status back to 'in_workshop', production_jobs_audit
            # row when a job is linked (the re-prioritisation trail).
            rec = _chassis_by_vin(db, vin)
            if rec is None:
                _bad(404, f"No chassis with VIN {vin}.")
            chassis_svc.return_chassis_to_parking(
                db, rec.id, ctx.get("user"),
                reason="Returned to Parking from the floor merge block", commit=False)
            m["chassis"] = None
            return {"event_type": "chassis_back_to_parking",
                    "job_number": str(ch.get("job")) if ch.get("job") else None,
                    "from_stage": "pre_merge", "to_stage": "parking",
                    "details": {"li": li, "vin": vin, "chassis_record_id": rec.id}}
    _bad(409, f"Chassis {vin} is not staged in any merge block — the floor has moved on. Refreshed.")


def _t_confirm_merge(db, doc, p, ctx):
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "confirm_merge needs a valid assembly line index (0-4).")
    m = doc["pre"][li]["merge"]
    assembly, chassis = m.get("assembly"), m.get("chassis")
    if not (isinstance(assembly, dict) and isinstance(chassis, dict)):
        _bad(409, f"Bay {li + 1} needs both a body and a chassis staged before Confirm merge.")
    job = str(assembly.get("job"))
    matched = chassis.get("job") is not None and str(chassis["job"]) == job
    vin = str(chassis.get("id"))
    # P2 chokepoint — THE REAL MERGE: record_body_attached writes the lifecycle event, links
    # job.chassis_record_id, and enforces the VIN-attestation lock (a planner-attested VIN on
    # the Pre-Job Card refuses a different chassis — the floor gets that protection for free).
    # Cutover tolerance: if the DB already says attached for this SAME pair (pre-P2 lane),
    # no-op with a note instead of the 409 — the floor converges on the existing truth.
    rec = _chassis_by_vin(db, vin)
    if rec is None:
        _bad(409, f"No chassis record for VIN {vin} — the merge can't be written to the DB.")
    pj = _require_job(db, job)
    details = {"li": li, "vin": vin, "matched": matched, "chassis_record_id": rec.id}
    cycle = chassis_svc._latest_cycle(db, rec.id)
    if chassis_svc._has_event(db, rec.id, "body_attached", cycle) \
            and pj.chassis_record_id in (None, rec.id):
        details["already_attached"] = True
    else:
        chassis_svc.record_body_attached(db, rec.id, pj.id, _actor(ctx), commit=False)
    m["attached"] = {"body": assembly, "chassis": chassis, "matched": matched}
    m["assembly"] = None
    m["chassis"] = None
    if job not in {str(x) for x in doc["mergedJobs"]}:
        doc["mergedJobs"].append(job)
    if vin not in {str(x) for x in doc["mergedChassis"]}:
        doc["mergedChassis"].append(vin)
    return {"event_type": "confirm_merge", "job_number": job,
            "from_stage": "pre_merge", "to_stage": "merged", "details": details}


def _t_dispatch(db, doc, p, ctx):
    li = p.get("li")
    if not isinstance(li, int) or not (0 <= li < FLOOR_LINES):
        _bad(422, "dispatch needs a valid assembly line index (0-4).")
    m = doc["pre"][li]["merge"]
    att = m.get("attached")
    if not isinstance(att, dict):
        _bad(409, f"Bay {li + 1} has no merge-complete unit to dispatch.")
    body = att.get("body") or {}
    chassis = att.get("chassis") or {}
    vin = str(chassis.get("id") or "")
    # P2 chokepoint — the Awaiting-QA handoff: status → 'awaiting_qa' clears the bay across
    # every derivation and lands the unit in Kenny's QC inbox natively. Cutover tolerance:
    # already-awaiting chassis (pre-P2 lane) no-op with a note.
    if not vin or vin == "—":
        _bad(409, "The merged unit has no chassis VIN — it can't be dispatched to QC.")
    rec = _chassis_by_vin(db, vin)
    if rec is None:
        _bad(409, f"No chassis record for VIN {vin} — the dispatch can't be written to the DB.")
    details = {"li": li, "vin": vin, "chassis_record_id": rec.id}
    if rec.status == "awaiting_qa":
        details["already_awaiting_qa"] = True
    else:
        chassis_svc.record_moved_to_awaiting_qa(db, rec.id, _actor(ctx), commit=False)
    entry = {
        "id": body.get("id"), "job": body.get("job"), "cust": body.get("cust"),
        "len": body.get("len"), "type": body.get("type"),
        "vin": vin, "matched": bool(att.get("matched")),
        "enteredAt": _now_iso(),
    }
    doc["qc"].insert(0, entry)
    m["attached"] = None
    return {"event_type": "dispatch", "job_number": str(body.get("job")),
            "from_stage": "merged", "to_stage": "qc", "details": details}


_TRANSITIONS: dict[str, Callable] = {
    "declare_cut": _t_declare_cut,
    "undo_cut": _t_undo_cut,
    "start_body": _t_start_body,
    "body_back_to_panels": _t_body_back_to_panels,
    "move_body": _t_move_body,
    "reset_timer": _t_reset_timer,     # A11 chute — drag-back re-arms the work clock
    "toggle_hold": _t_toggle_hold,     # A11 chute — pause/resume the work clock
    "drop_assembly": _t_drop_assembly,
    "assembly_back_to_track": _t_assembly_back_to_track,
    "drop_chassis": _t_drop_chassis,
    "chassis_back_to_parking": _t_chassis_back_to_parking,
    "confirm_merge": _t_confirm_merge,
    "dispatch": _t_dispatch,
}

TRANSITION_TYPES = tuple(_TRANSITIONS)


# ── the pipeline ──────────────────────────────────────────────────────────────

def _locked_row(db: Session) -> PlanFloorState:
    row = db.execute(select(PlanFloorState).where(PlanFloorState.id == ROW_ID)
                     .with_for_update()).scalars().first()
    if row is None:
        row = PlanFloorState(id=ROW_ID, state="{}", version=0)
        db.add(row)
        db.flush()          # visible to this transaction; unique PK races surface here
        row = db.execute(select(PlanFloorState).where(PlanFloorState.id == ROW_ID)
                         .with_for_update()).scalars().one()
    return row


def _append_events(db: Session, drafts: list[dict], version: int, user) -> list[FloorEvent]:
    out = []
    for d in drafts:
        job = _job_by_number(db, d["job_number"]) if d.get("job_number") else None
        ev = FloorEvent(
            event_type=d["event_type"], job_number=d.get("job_number"),
            production_job_id=job.id if job else None,
            from_stage=d.get("from_stage"), to_stage=d.get("to_stage"),
            details=d.get("details") or {},
            doc_version=version,
            user_id=getattr(user, "id", None),
            user_name=(getattr(user, "username", None) or "")[:64] or None,
        )
        db.add(ev)
        out.append(ev)
    return out


def apply_transition(db: Session, *, ttype: str, payload: dict, user) -> dict:
    fn = _TRANSITIONS.get(ttype)
    if fn is None:
        _bad(422, f"Unknown floor transition '{ttype}'.")
    row = _locked_row(db)
    doc = _load_doc(row)
    housekeeping: list[dict] = []
    _prune_cut(db, doc, housekeeping)
    draft = fn(db, doc, payload, {"user": user})   # P2: chokepoints need the actor
    new_version = int(row.version or 0) + 1
    row.state = json.dumps(doc)
    row.version = new_version
    now = datetime.now(timezone.utc)
    row.updated_at = now
    events = _append_events(db, housekeeping + [draft], new_version, user)
    db.commit()
    main_event = events[-1]
    return {
        "ok": True, "version": new_version, "updated_at": now.isoformat(),
        "state": row.state,
        "event": {"id": main_event.id, "event_type": main_event.event_type,
                  "job_number": main_event.job_number,
                  "from_stage": main_event.from_stage, "to_stage": main_event.to_stage},
    }


def reset_floor(db: Session, *, user) -> dict:
    """Admin-only (router enforces admin.floor-reset): reset the doc to the canonical empty
    floor. version stays MONOTONIC (never reset) and the action is journaled. DB/chassis
    state is deliberately untouched — the P2 chokepoint guards make any doc↔DB skew loud."""
    row = _locked_row(db)
    doc = _empty_doc()
    new_version = int(row.version or 0) + 1
    row.state = json.dumps(doc)
    row.version = new_version
    now = datetime.now(timezone.utc)
    row.updated_at = now
    _append_events(db, [{"event_type": "floor_reset", "job_number": None,
                         "from_stage": None, "to_stage": None, "details": {}}],
                   new_version, user)
    db.commit()
    return {"ok": True, "version": new_version, "updated_at": now.isoformat(),
            "state": row.state}
