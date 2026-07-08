"""v1.40.3 — floor-derived mes_status (services/plan_status.py).

The job's DISPLAY status must keep tracking the /plan floor after 'planning'
(Michael 6 Jul: "the status stops at Planning but the process continues"):
Vacuum/Press → Panels Ready → Pre-Assembly → Pre-Merge → Merged → QC — derived
read-only from planning_slots + the PlanFloorState JSON doc. Raw status stays
'planning' (ADR 0008 §0.4); only mes_status changes; non-planning jobs and
Repair keep their labels; a malformed floor doc degrades to plain 'Planning'.
"""
import json
import uuid
from datetime import date

import pytest


@pytest.fixture
def floor_job(app_mod):
    """Factory -> (id, job_number) for a bare 'planning' job (workbook-style row)."""
    from app.database import SessionLocal, Branch
    from app.models.mes import ProductionJob
    created = []

    def _make(**kw):
        with SessionLocal() as db:
            jhb = db.query(Branch).filter_by(code="JHB").first()
            j = ProductionJob(
                calculation_record_id=None, source="workbook",
                branch_id=(jhb.id if jhb else None),
                job_number=kw.get("job_number", f"FS{uuid.uuid4().hex[:6]}"),
                status=kw.get("status", "planning"),
                customer_name="Floor Status Test Ltd",
                description="5.5m Chiller",
                selling_zar=100000.0,
            )
            db.add(j)
            db.commit()
            created.append(j.id)
            return j.id, j.job_number

    yield _make
    from app.models.mes import PlanningSlot
    with SessionLocal() as db:
        for jid in created:
            for s in db.query(PlanningSlot).filter_by(production_job_id=jid).all():
                db.delete(s)
            j = db.get(ProductionJob, jid)
            if j:
                db.delete(j)
        db.commit()


@pytest.fixture
def floor_doc(app_mod):
    """Set the PlanFloorState doc for the test; restores the prior doc afterwards."""
    from app.database import SessionLocal
    from app.models.mes import PlanFloorState
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        prior = row.state if row else None

    def _set(doc: dict | str):
        from datetime import datetime, timezone
        with SessionLocal() as db:
            row = db.get(PlanFloorState, 1)
            state = doc if isinstance(doc, str) else json.dumps(doc)
            if row is None:
                db.add(PlanFloorState(id=1, state=state, updated_at=datetime.now(timezone.utc)))
            else:
                row.state = state
            db.commit()

    yield _set
    with SessionLocal() as db:
        row = db.get(PlanFloorState, 1)
        if row is not None:
            if prior is None:
                db.delete(row)
            else:
                row.state = prior
            db.commit()


def _row(api, jid):
    return next(r for r in api.get("/api/production-jobs?limit=300").json() if r["id"] == jid)


def _doc(**over):
    base = {"v": 1, "pre": [], "qc": [], "cut": [], "consumed": [], "mergedJobs": [], "mergedChassis": []}
    base.update(over)
    return base


def test_vacuum_and_press_from_scheduled_slots(api, floor_job, floor_doc, app_mod):
    from app.database import SessionLocal
    from app.models.mes import PlanningSlot
    floor_doc(_doc())
    (vid, vnum), (pid, pnum) = floor_job(), floor_job()
    with SessionLocal() as db:
        db.add(PlanningSlot(production_job_id=vid, week=date(2026, 7, 6), bay="V1",
                            lane="vacuum", slot_position=1, status="scheduled"))
        db.add(PlanningSlot(production_job_id=pid, week=date(2026, 7, 6), bay="P1",
                            lane="panelshop", slot_position=1, status="scheduled"))
        db.commit()
    v, p = _row(api, vid), _row(api, pid)
    assert (v["status"], v["mes_status"]) == ("planning", "Vacuum")   # raw status untouched
    assert (p["status"], p["mes_status"]) == ("planning", "Press")


def test_floor_doc_stages_furthest_wins(api, floor_job, floor_doc):
    (jid, num) = floor_job()
    # cut → Panels Ready
    floor_doc(_doc(cut=[num]))
    assert _row(api, jid)["mes_status"] == "Panels Ready"
    # on a bay track → Pre-Assembly (also still in cut — later stage must win)
    floor_doc(_doc(cut=[num], pre=[{"id": "Bay 1", "bodies": [{"job": num}], "merge": {}}]))
    assert _row(api, jid)["mes_status"] == "Pre-Assembly"
    # staged in the merge block → Pre-Merge
    floor_doc(_doc(pre=[{"id": "Bay 1", "bodies": [], "merge": {"assembly": {"job": num}}}]))
    assert _row(api, jid)["mes_status"] == "Pre-Merge"
    # chassis attached / merged set → Merged
    floor_doc(_doc(mergedJobs=[num]))
    assert _row(api, jid)["mes_status"] == "Merged"
    # dispatched to QC → QC (mergedJobs membership is permanent — QC still wins)
    floor_doc(_doc(mergedJobs=[num], qc=[{"job": num}]))
    row = _row(api, jid)
    assert (row["status"], row["mes_status"]) == ("planning", "QC")


def test_non_planning_jobs_are_not_overridden(api, floor_job, floor_doc):
    jid, num = floor_job(status="accepted")
    floor_doc(_doc(cut=[num]))
    row = _row(api, jid)
    assert (row["status"], row["mes_status"]) == ("accepted", "Accepted")


def test_malformed_floor_doc_degrades_to_planning(api, floor_job, floor_doc):
    jid, num = floor_job()
    floor_doc("{not json")
    row = _row(api, jid)
    assert (row["status"], row["mes_status"]) == ("planning", "Planning")
