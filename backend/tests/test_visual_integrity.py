"""WO v4.36b §3.1 — visual_integrity flag-derivation service unit tests.

Pure-logic tests (no DB) pin the band/severity resolver + the spec registry. DB-backed tests seed
throwaway records (created_source_ref / job_number 'ZZVI' prefix, FK-safe teardown) and drive the
derivation deterministically via the service's `now=` injection — no dependence on wall-clock or a
particular seed state. Execution on CI/icb_test per ADR 0011.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import visual_integrity as vi

UTC = timezone.utc
REF = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)        # the test "now"; seed timestamps precede it
_MARK = "ZZVI"


# ── pure logic (no DB) ─────────────────────────────────────────────────────────
def test_flag_specs_integrity():
    groups = {"Chassis", "Jobs", "Bays", "Sign-offs", "Stale Reviews"}
    domains = {"chassis", "jobs", "bays"}
    sevs = {"sky", "amber", "red"}
    assert len(vi.FLAG_SPECS) == 17                    # §1 catalog (13) + 4 stage-breach flags (v1.41.1)
    for key, s in vi.FLAG_SPECS.items():
        assert key == s.flag
        assert s.domain in domains and s.group in groups
        assert s.bands, f"{key} has no bands"
        gts = [gt for gt, _ in s.bands]
        assert gts == sorted(gts), f"{key} bands not ascending"
        assert all(sev in sevs for _, sev in s.bands)


def test_resolve_picks_highest_exceeded_band():
    spec = vi.FLAG_SPECS["bay_post_attached_stale"]    # bands ((3,'amber'),(5,'red'))
    assert vi._resolve(spec, 2) is None                # below trigger
    assert vi._resolve(spec, 4) == "amber"
    assert vi._resolve(spec, 6) == "red"
    assert vi._resolve(spec, None) is None


def test_resolve_fires_immediately_for_no_age_flag():
    spec = vi.FLAG_SPECS["chassis_no_customer"]        # band ((-1,'red')) → fires at any age >= 0
    assert vi._resolve(spec, 0) == "red"


def test_age_days_handles_date_and_datetime():
    assert vi._age_days(REF, datetime(2026, 1, 5, tzinfo=UTC)) == 5
    assert vi._age_days(REF, REF.date().replace(day=3)) == 7    # a date basis (UTC midnight)
    assert vi._age_days(REF, None) is None


# ── DB-backed ──────────────────────────────────────────────────────────────────
def _purge(db):
    from sqlalchemy import text
    # slots first — planning_slots.production_job_id is SET NULL on job delete (orphan residue)
    db.execute(text("DELETE FROM icb_mes.planning_slots WHERE production_job_id IN "
                    "(SELECT id FROM icb_mes.production_jobs WHERE job_number LIKE 'ZZVI%')"))
    db.execute(text("DELETE FROM icb_mes.production_jobs WHERE job_number LIKE 'ZZVI%'"))
    db.execute(text("DELETE FROM icb_mes.chassis_records WHERE created_source_ref LIKE 'ZZVI%'"))
    db.commit()


@pytest.fixture
def db():
    from app.database import SessionLocal
    with SessionLocal() as s:
        _purge(s)
        try:
            yield s
        finally:
            _purge(s)


def _chassis(db, *, vin=None, customer_name=None, make=None, status="received",
             created_at=datetime(2026, 1, 1, tzinfo=UTC)):
    from app.models.mes import ChassisRecord
    c = ChassisRecord(vin=vin, customer_name=customer_name, make=make, status=status,
                      created_via="manual_chassis_menu", created_source_ref=f"{_MARK}-test",
                      created_at=created_at, created_by="t", updated_by="t")
    db.add(c)
    db.flush()
    return c.id


def _job(db, *, chassis_id=None, status="planning", chassis_eta=None,
         planning_acknowledged_at=None, job_number="ZZVI001"):
    from app.database import Branch
    from app.models.mes import ProductionJob
    branch = db.query(Branch).order_by(Branch.id).first()
    j = ProductionJob(branch_id=branch.id, source="quote", status=status, job_number=job_number,
                      chassis_record_id=chassis_id, chassis_eta=chassis_eta,
                      planning_acknowledged_at=planning_acknowledged_at)
    db.add(j)
    db.flush()
    return j.id


def _flags(hits):
    return {h["flag"] for h in hits}


def _sev(hits, flag):
    return next(h["severity"] for h in hits if h["flag"] == flag)


def test_chassis_no_vin_fires_red(db):
    cid = _chassis(db, vin=None, make="X")
    hits = vi.compute_chassis_flags(db, cid, now=REF)
    assert "chassis_no_vin" in _flags(hits) and _sev(hits, "chassis_no_vin") == "red"


def test_chassis_vin_format_legacy_amber(db):
    cid = _chassis(db, vin="SHORTLEGACYVIN", make="X")     # not 17-char ISO-3779
    hits = vi.compute_chassis_flags(db, cid, now=REF)
    assert _sev(hits, "chassis_vin_format_legacy") == "amber"
    assert "chassis_no_vin" not in _flags(hits)            # has a VIN, just legacy-format


def test_chassis_no_customer_requires_linked_job(db):
    # unlinked chassis with no customer → NOT flagged no-customer (nothing to backfill from)
    lone = _chassis(db, vin="1HGCM82633A004352", make="X", customer_name=None)
    assert "chassis_no_customer" not in _flags(vi.compute_chassis_flags(db, lone, now=REF))
    # linked to a job, customer blank → red
    linked = _chassis(db, vin="1HGCM82633A004353", make="X", customer_name=None)
    _job(db, chassis_id=linked)
    hits = vi.compute_chassis_flags(db, linked, now=REF)
    assert _sev(hits, "chassis_no_customer") == "red"


def test_chassis_no_make_model_amber_on_stub(db):
    cid = _chassis(db, vin="1HGCM82633A004400", make=None, status="expected")
    hits = vi.compute_chassis_flags(db, cid, now=REF)
    assert _sev(hits, "chassis_no_make_model") == "amber"


def test_job_eta_overdue_red(db):
    jid = _job(db, chassis_id=None, status="planning",
               chassis_eta=datetime(2026, 1, 5, tzinfo=UTC))   # before REF, not received
    hits = vi.compute_job_flags(db, jid, now=REF)
    assert _sev(hits, "job_eta_overdue") == "red"


def test_job_eta_missing_amber(db):
    jid = _job(db, chassis_id=None, status="planning", chassis_eta=None,
               planning_acknowledged_at=datetime(2026, 1, 1, tzinfo=UTC))
    hits = vi.compute_job_flags(db, jid, now=REF)
    assert _sev(hits, "job_eta_missing") == "amber"
    assert "job_eta_overdue" not in _flags(hits)


def test_summary_aggregates_seeded_flags(db):
    _chassis(db, vin=None, make="X")                          # chassis_no_vin
    before = vi.compute_planning_board_flags(db, now=REF)
    cid = _chassis(db, vin=None, make=None, status="expected")  # +no_vin +no_make_model
    after = vi.compute_planning_board_flags(db, now=REF)
    assert after["by_flag"].get("chassis_no_vin", 0) >= 2
    assert after["by_flag"].get("chassis_no_make_model", 0) >= 1
    assert after["total"] > before["total"]
    assert after["by_severity"]["red"] >= 2


# ── §3.5 role-based filtering ────────────────────────────────────────────────
def test_visible_groups_matrix():
    assert vi._visible_groups("workshop") == {"Jobs", "Bays"}
    assert vi._visible_groups("sales") == {"Chassis", "Sign-offs", "Stale Reviews"}
    assert vi._visible_groups("admin") == vi._ALL_GROUPS
    assert vi._visible_groups("planner") == vi._ALL_GROUPS
    assert vi._visible_groups("production") == vi._ALL_GROUPS
    assert vi._visible_groups(None) == vi._ALL_GROUPS          # unknown/None → all (advisory)
    assert vi._visible_groups("WORKSHOP") == {"Jobs", "Bays"}  # case-insensitive


def test_role_filter_scopes_summary(db):
    _chassis(db, vin=None, make="X")                           # chassis_no_vin → Chassis group
    _job(db, chassis_id=None, status="planning",
         chassis_eta=datetime(2026, 1, 5, tzinfo=UTC))         # job_eta_overdue → Jobs group
    workshop = vi.compute_planning_board_flags(db, role="workshop", now=REF)
    sales = vi.compute_planning_board_flags(db, role="sales", now=REF)
    admin = vi.compute_planning_board_flags(db, role="admin", now=REF)
    # workshop sees Jobs, never Chassis-group flags
    assert "job_eta_overdue" in workshop["by_flag"] and "chassis_no_vin" not in workshop["by_flag"]
    assert "Chassis" not in workshop["by_group"]
    # sales sees Chassis, never Jobs-group flags
    assert "chassis_no_vin" in sales["by_flag"] and "job_eta_overdue" not in sales["by_flag"]
    # admin sees both
    assert "chassis_no_vin" in admin["by_flag"] and "job_eta_overdue" in admin["by_flag"]


def test_role_filter_scopes_drillthrough(db):
    _chassis(db, vin=None, make="X")                           # chassis_no_vin (Chassis)
    # workshop can't see the Chassis group → its chassis drill-through is empty even though the row is flagged
    assert vi.list_flagged_chassis(db, role="workshop", now=REF) == []
    assert any(r for r in vi.list_flagged_chassis(db, role="admin", now=REF))


# ── stage-threshold breach flags (Michael's 10-Jul WO, v1.41.1) ─────────────────
# Determinism: `now=REF` is injected end-to-end. Floor-stage clocks are UTC-pure (stamp vs REF)
# so amber/red ratios pin exactly. The V/P clock is server-LOCAL (ADR 0035) — REF converts by
# the machine's TZ offset (±14h worst case), so V/P scenarios use a slot ~3 weeks before REF
# with an 8h threshold: elapsed ≈ 500h ± 14h is red (>=1.5x) in EVERY timezone (CI-TZ-proof,
# sign-and-range discipline). Floor doc + threshold rows are saved/restored around each test.

def _iso_z(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


@pytest.fixture
def stage_env(db):
    """Thresholds pinned to known values + floor-doc singleton saved/restored. Teardown runs
    BEFORE the db fixture's purge commit, so restored state is what gets committed."""
    from app.models.mes import PlanFloorState, ProductionStageThreshold
    orig = {t.stage_code: (t.threshold_hours, t.workday_start, t.is_active)
            for t in db.query(ProductionStageThreshold).all()}
    row = db.get(PlanFloorState, 1)
    created = row is None
    if created:
        row = PlanFloorState(id=1, state="{}")
        db.add(row)
    orig_state = None if created else row.state
    for t in db.query(ProductionStageThreshold).all():
        if t.stage_code in ("vacuum", "press", "panels_ready", "pre_assembly"):
            t.is_active = True
    db.flush()
    yield db
    row = db.get(PlanFloorState, 1)
    if created and row is not None:
        db.delete(row)
    elif row is not None:
        row.state = orig_state
    for t in db.query(ProductionStageThreshold).all():
        if t.stage_code in orig:
            t.threshold_hours, t.workday_start, t.is_active = orig[t.stage_code]
    db.flush()


def _set_threshold(db, stage_code, *, hours=None, is_active=None):
    from app.models.mes import ProductionStageThreshold
    t = db.query(ProductionStageThreshold).filter_by(stage_code=stage_code).one()
    if hours is not None:
        t.threshold_hours = hours
    if is_active is not None:
        t.is_active = is_active
    db.flush()
    return t


def _slot(db, job_id, *, bay="V-1", lane="vacuum", week, day=0):
    from app.models.mes import PlanningSlot
    s = PlanningSlot(production_job_id=job_id, week=week, bay=bay, lane=lane,
                     slot_position=1, day_of_week=day, status="scheduled")
    db.add(s)
    db.flush()
    return s.id


def _set_floor_doc(db, doc):
    import json as _json
    from app.models.mes import PlanFloorState
    db.get(PlanFloorState, 1).state = _json.dumps(doc)
    db.flush()


def test_stage_breach_vp_red_and_press_mapping(stage_env):
    db = stage_env
    _set_threshold(db, "vacuum", hours=8)
    _set_threshold(db, "press", hours=4)
    _set_floor_doc(db, {})                                     # floor empty — pure V/P scenario
    week = (REF - timedelta(days=21)).date()
    week = week - timedelta(days=week.weekday())               # a Monday ~3 weeks before REF
    v_jid = _job(db, job_number="ZZVI801")
    _slot(db, v_jid, bay="V-1", lane="vacuum", week=week, day=0)
    p_jid = _job(db, job_number="ZZVI802")
    _slot(db, p_jid, bay="P-2", lane="panelshop", week=week, day=0)

    v_hits = vi.compute_job_flags(db, v_jid, now=REF)
    assert _sev(v_hits, "stage_vacuum_overdue") == "red"       # ~500h vs 8h — red in any TZ
    v = next(h for h in v_hits if h["flag"] == "stage_vacuum_overdue")
    assert "h of 8h" in v["detail"] and v["age_days"] >= 18    # weeks over, minus TZ slack
    p_hits = vi.compute_job_flags(db, p_jid, now=REF)
    assert _sev(p_hits, "stage_press_overdue") == "red"        # panelshop lane → press threshold
    assert "stage_vacuum_overdue" not in _flags(p_hits)

    summary = vi.compute_planning_board_flags(db, now=REF)
    assert summary["by_flag"].get("stage_vacuum_overdue", 0) >= 1
    assert summary["by_flag"].get("stage_press_overdue", 0) >= 1
    listed = vi.list_flagged_jobs(db, "stage_vacuum_overdue", role="workshop", now=REF)
    assert any(r["job_number"] == "ZZVI801" for r in listed)   # Jobs group → workshop-visible


def test_stage_breach_panels_ready_amber_red_and_under(stage_env):
    db = stage_env
    _set_threshold(db, "panels_ready", hours=8)
    amber_jid = _job(db, job_number="ZZVI811")                 # 10h of 8h → ratio 1.25 → amber
    red_jid = _job(db, job_number="ZZVI812")                   # 30h of 8h → ratio 3.75 → red
    under_jid = _job(db, job_number="ZZVI813")                 # 2h of 8h → under, no flag
    _set_floor_doc(db, {
        "cut": [{"job": "ZZVI811"}, {"job": "ZZVI812"}, {"job": "ZZVI813"}],
        "cutAt": {"ZZVI811": _iso_z(REF - timedelta(hours=10)),
                  "ZZVI812": _iso_z(REF - timedelta(hours=30)),
                  "ZZVI813": _iso_z(REF - timedelta(hours=2))},
    })
    hits = vi.compute_job_flags(db, amber_jid, now=REF)
    assert _sev(hits, "stage_panels_ready_overdue") == "amber"
    h = next(x for x in hits if x["flag"] == "stage_panels_ready_overdue")
    assert h["detail"] == "Panels Ready 10.0h of 8h" and h["age_days"] == 0
    assert _sev(vi.compute_job_flags(db, red_jid, now=REF), "stage_panels_ready_overdue") == "red"
    assert "stage_panels_ready_overdue" not in _flags(vi.compute_job_flags(db, under_jid, now=REF))


def test_stage_breach_pre_assembly_and_unstamped_honesty(stage_env):
    db = stage_env
    _set_threshold(db, "pre_assembly", hours=40)
    red_jid = _job(db, job_number="ZZVI821")                   # 100h of 40h → red
    legacy_jid = _job(db, job_number="ZZVI822")                # unstamped legacy body → NEVER flags
    _set_floor_doc(db, {
        "pre": [{"bodies": [{"job": "ZZVI821", "enteredAt": _iso_z(REF - timedelta(hours=100))},
                            {"job": "ZZVI822"}], "merge": {}}],
    })
    assert _sev(vi.compute_job_flags(db, red_jid, now=REF), "stage_pre_assembly_overdue") == "red"
    assert _flags(vi.compute_job_flags(db, legacy_jid, now=REF)) == set()


def test_stage_breach_exclusions(stage_env):
    db = stage_env
    _set_threshold(db, "vacuum", hours=8)
    week = (REF - timedelta(days=21)).date()
    week = week - timedelta(days=week.weekday())
    # (a) job progressed past V/P per the floor doc (cut, unstamped) → V/P clock never fires,
    #     and the unstamped cut entry can't fire Panels Ready either → ZERO breach flags.
    jid = _job(db, job_number="ZZVI831")
    _slot(db, jid, week=week)
    _set_floor_doc(db, {"cut": [{"job": "ZZVI831"}], "cutAt": {}})
    assert not (_flags(vi.compute_job_flags(db, jid, now=REF)) & set(vi._STAGE_FLAG_KEYS.values()))
    # (b) inactive threshold → stage never flags even when massively over.
    _set_floor_doc(db, {})
    _set_threshold(db, "vacuum", is_active=False)
    assert "stage_vacuum_overdue" not in _flags(vi.compute_job_flags(db, jid, now=REF))
