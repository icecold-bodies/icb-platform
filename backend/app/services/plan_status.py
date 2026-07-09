"""Floor-derived job statuses (v1.40.3 — "the status stops at Planning" fix, Michael 6 Jul).

The official floor lifecycle (docs/releases/v1.40.0.md, ratified 2 Jul) continues past
the DB's `planning` status: Vacuum/Press → Panels Ready → Pre-Assembly → Pre-Merge →
Merged → QC. Those positions are ALREADY persisted — planning_slots holds the V/P grid,
and the /plan floor document (PlanFloorState, single JSON row) holds every drag beyond
it — so the extended statuses are DERIVED at read time from those sources of truth.

Deliberately display-only: ProductionJob.status stays 'planning' throughout the floor
(ADR 0008 §0.4 — scheduling never mutates job.status; the 16-Jun ruling — body-attach
doesn't either). Only `mes_status` (the label the SPA pills/filters read, a plain str
in the API schema) becomes floor-aware, which keeps the ProductionJobStatus Literal,
every status-precondition guard, and the reversibility story intact: drag a card back
and the derived status falls back with it, no ratchets, no new writers.

Zone → label mapping (floor doc shape per productionFlowEngine.serializeState):
  planning_slots status='scheduled'   → "Vacuum" or "Press" (slot.bay 'P…' = Press —
                                        mirrors PlanningCockpit.laneForBay)
  cut[]                               → "Panels Ready" (panel declared cut, off the grid)
  pre[].bodies[]                      → "Pre-Assembly" (on an assembly-bay track)
  pre[].merge.assembly                → "Pre-Merge"   (body staged in the merge block)
  pre[].merge.attached / mergedJobs[] → "Merged"      (chassis attached — permanent)
  qc[]                                → "QC"          (dispatched, awaiting sign-off)
Later stages overwrite earlier ones, so a job's label is its furthest position.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.mes import PlanFloorState, PlanningSlot, ProductionJob

logger = logging.getLogger("icb.plan_status")

#: Labels this module may emit (the SPA palette carries a pill style for each).
FLOOR_STAGE_LABELS = ("Vacuum", "Press", "Panels Ready", "Pre-Assembly",
                      "Pre-Merge", "Merged", "QC")


def stage_key_for(lane, bay) -> str:
    """The production_stage_thresholds.stage_code for a V/P planning slot. lane is the
    authoritative machine kind ('panelshop' = Press); the bay-prefix check is only the
    fallback for lane-less legacy slots. Single source of stage truth — shared by the
    floor-status derivation below and the board's stage-clock (thresholds WO)."""
    is_press = (lane == "panelshop") if lane else str(bay or "").upper().startswith("P")
    return "press" if is_press else "vacuum"


def _jobs_from(entries, key: str = "job") -> list[str]:
    """Job numbers out of a floor-doc list that may hold dicts or bare values."""
    out = []
    for e in entries or []:
        v = e.get(key) if isinstance(e, dict) else e
        if v is not None and str(v).strip():
            out.append(str(v))
    return out


def floor_status_by_job_number(db: Session) -> dict[str, str]:
    """job_number → furthest floor-stage label. Best-effort and read-only: any
    malformed floor document degrades to {} (the pills simply keep 'Planning')."""
    out: dict[str, str] = {}

    # 1) Scheduled on the V/P planner grid (earliest floor stage). lane is the
    #    authoritative machine kind ('panelshop' renders as Press in the cockpit);
    #    the bay-prefix check is only the fallback for lane-less legacy slots.
    try:
        rows = db.execute(
            select(PlanningSlot.lane, PlanningSlot.bay, ProductionJob.job_number)
            .join(ProductionJob, ProductionJob.id == PlanningSlot.production_job_id)
            .where(PlanningSlot.status == "scheduled")
        ).all()
        for lane, bay, job_number in rows:
            if not job_number:
                continue
            out[str(job_number)] = "Press" if stage_key_for(lane, bay) == "press" else "Vacuum"
    except Exception:  # noqa: BLE001 — never let status derivation break a list API
        logger.warning("floor-status: planning-slot scan failed", exc_info=True)

    # 2) The persisted floor document — later assignments win (furthest stage).
    try:
        row = db.get(PlanFloorState, 1)
        doc = json.loads(row.state) if row is not None and row.state else {}
    except Exception:  # noqa: BLE001
        logger.warning("floor-status: floor-state document unreadable", exc_info=True)
        return out

    for j in _jobs_from(doc.get("cut")):
        out[j] = "Panels Ready"
    for bay in doc.get("pre") or []:
        if not isinstance(bay, dict):
            continue
        for j in _jobs_from(bay.get("bodies")):
            out[j] = "Pre-Assembly"
        merge = bay.get("merge") or {}
        assembly = merge.get("assembly")
        if isinstance(assembly, dict) and assembly.get("job") is not None:
            out[str(assembly["job"])] = "Pre-Merge"
        attached = merge.get("attached")
        if isinstance(attached, dict):
            body = attached.get("body")
            if isinstance(body, dict) and body.get("job") is not None:
                out[str(body["job"])] = "Merged"
    for j in _jobs_from(doc.get("mergedJobs")):
        out[j] = "Merged"
    for j in _jobs_from(doc.get("qc")):
        out[j] = "QC"
    return out


def apply_floor_status(items, floor: dict[str, str]) -> None:
    """Overlay floor-derived labels onto API items (list or detail models, mutated
    in place). Only 'planning' jobs are eligible — the floor can't out-rank an
    earlier pipeline state — and the computed 'Repair' label keeps precedence."""
    for it in items:
        if (it.status == "planning" and it.mes_status != "Repair"
                and it.job_number and str(it.job_number) in floor):
            it.mes_status = floor[str(it.job_number)]
