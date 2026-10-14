"""RT6 — Burt's insulation rules enforced at the server (RT6_DISPATCH default 4; RT6_RULING_1 Q3/Q8; RULING_1a).

  1. /api/calculate WARNS: the breaches ride the result (any role); a family with no rule is never blocked; on a
     ruled body the insulation choices the check cannot read are reported (rule_unclassified).
  2. /api/approve REFUSES (409, a plain-English reason) for sales, full AND admin — no override — on every save path:
     new, revision, save-as-new, Replace, overwrite, capture-for, a draft-flag alias, Calculator 2 (include_all_items);
     nothing is written: the existing costings Replace / overwrite would touch stay byte-identical. The allowed quote
     saves.
  3. Accept, the costing's pre-job card and a production job from the costing REFUSE a saved costing that breaches the
     CURRENT rule; the costing is never altered. A non-breaching costing and a repair are accepted.
  4. RULING_1a — restore a soft-deleted breaching costing: the restore is not guarded; Accept then refuses (409).
  5. The reads: /api/trailers carries insulation_rule; the BOM rows carry rule_class / rule_forbidden.
  6. The family editor: the grid sets / clears the rule (canonical); a panel with nothing allowed is refused; an
     older form leaves it alone; the JSON endpoint is admin-only (403 otherwise).
  7. Drafts WARN, never block: the draft PUT, a backup's rule-warnings, a restore.
  8. The audit probe is never guarded: _build_bom_items and the audit tool do not call the check.
SYNTHETIC rows only (marker RT6G), in the _test database, removed by primary key.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services import insulation_rules as ir

MARK = "RT6G"
ROOT = Path(__file__).resolve().parents[2]
CHILLER = ir.canonical_rule({"allowed": {p: ["EPS"] for p in ir.PANELS}})
FREEZER = ir.canonical_rule({"allowed": {"FRONT": ["PU"], "SIDES": ["PU"], "ROOF": ["EPS", "PU"],
                                         "FLOOR": ["EPS", "PU"], "DRD": ["PU"], "SRD": ["PU"]}})
DIMS = {"length": 6.0, "width": 2.4, "height": 2.4, "floor_thickness": 0.1, "panel_thickness": 0.06,
        "insulation_thickness": 0.06, "num_axles": 2, "num_doors": 2}


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):            # startup seeds the admin user + permissions
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _session(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"rt6g-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role, expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def users(app_mod):
    from app.database import SessionLocal, User, UserSession
    made = {}
    with SessionLocal() as db:
        for role in ("sales", "full"):
            uname = f"{MARK.lower()}_{role}_{uuid.uuid4().hex[:6]}"
            db.add(User(username=uname, password_hash="x", role=role))
            made[role] = uname
        db.commit()
    heads = {role: _session(u) for role, u in made.items()}
    heads["admin"] = _session("admin")
    yield heads
    with SessionLocal() as db:
        for h in heads.values():
            db.query(UserSession).filter_by(id=h["Cookie"].split("session_id=")[1]).delete()
        for uname in made.values():
            db.query(User).filter_by(username=uname).delete()
        db.commit()


def _purge_marker() -> None:
    """This file's marker rows, found by the marker and deleted child-first BY ID (never TRUNCATE): at setup — what a
    run that died mid-way left, or a negative control that let a refused write through (a job from a costing, whose
    FK then blocked the costing's delete and left the whole set behind) — and again at teardown."""
    from sqlalchemy import or_
    from app.database import (BillOfMaterial, CalculationRecord, ConfiguratorDraft, ConfiguratorDraftSnapshot,
                              Customer, Material, SessionLocal, TrailerGroup, TrailerType)
    from app.models.mes import PrejobCard, ProductionJob
    with SessionLocal() as db:
        bodies = [i for (i,) in db.query(TrailerType.id).filter(TrailerType.name.like(f"{MARK} %"))]
        groups = [i for (i,) in db.query(TrailerGroup.id).filter(TrailerGroup.name.like(f"{MARK} %"))]
        custs = [i for (i,) in db.query(Customer.id).filter(Customer.name == f"{MARK} CUSTOMER")]
        calcs = [i for (i,) in db.query(CalculationRecord.id).filter(or_(
            CalculationRecord.trailer_type_id.in_(bodies), CalculationRecord.customer_id.in_(custs),
            CalculationRecord.quote_number.like(f"{MARK}%")))]
        db.query(PrejobCard).filter(PrejobCard.calculation_id.in_(calcs)).delete(synchronize_session=False)
        db.query(ProductionJob).filter(ProductionJob.calculation_record_id.in_(calcs)).delete(synchronize_session=False)
        db.query(CalculationRecord).filter(CalculationRecord.id.in_(calcs)).delete(synchronize_session=False)
        db.query(ConfiguratorDraftSnapshot).filter(ConfiguratorDraftSnapshot.trailer_type_id.in_(bodies)).delete(synchronize_session=False)
        db.query(ConfiguratorDraft).filter(ConfiguratorDraft.trailer_type_id.in_(bodies)).delete(synchronize_session=False)
        db.query(BillOfMaterial).filter(BillOfMaterial.trailer_type_id.in_(bodies)).delete(synchronize_session=False)
        db.query(TrailerType).filter(TrailerType.id.in_(bodies)).delete(synchronize_session=False)
        db.query(TrailerGroup).filter(TrailerGroup.id.in_(groups)).delete(synchronize_session=False)
        db.query(Material).filter(Material.material_code == MARK).delete(synchronize_session=False)
        db.query(Customer).filter(Customer.id.in_(custs)).delete(synchronize_session=False)
        db.commit()


@pytest.fixture(scope="module")
def staged(app_mod):
    """Three families — CHILLER-ruled, FREEZER-ruled, no rule — one body each, shaped like prod's: per panel an EPS
    and a PU master (INSULATION choice group) and an EPS / PU cost line in the panel's section, gated by a condition
    naming the master. Plus a customer and the marker materials. Purged by marker, child-first by id, before and after."""
    from app.database import (BillOfMaterial, Customer, Material, SessionLocal, TrailerGroup, TrailerType)
    _purge_marker()
    ids: dict = {"groups": [], "bodies": {}, "materials": [], "masters": {}, "lines": {}}
    with SessionLocal() as db:
        fams = {}
        for key, rule, order in (("chill", CHILLER, 9601), ("freeze", FREEZER, 9602), ("plain", None, 9603)):
            g = TrailerGroup(name=f"{MARK} {key.upper()} FAM", sort_order=order, insulation_rule=rule)
            db.add(g)
            db.flush()
            fams[key] = g.id
            ids["groups"].append(g.id)

        def mat(name, price=10.0, uom="each"):
            m = Material(name=name, unit_of_measure=uom, price_per_unit=price, material_code=MARK, is_active=True)
            db.add(m)
            db.flush()
            ids["materials"].append(m.id)
            return m
        line_mat = {"EPS": mat("EPS", 100.0, "m2"), "PU": mat("PU", 300.0, "m2")}
        master_mat = {(p, i): mat(f"{MARK} {p} {i}", 0.0) for p in ir.PANELS for i in ir.INSULATIONS}
        for key in ("chill", "freeze", "plain"):
            t = TrailerType(name=f"{MARK} {key.upper()} BODY", is_active=True, configurator_v2=False,
                            group_id=fams[key], default_length=6.0, default_width=2.4, default_height=2.4)
            db.add(t)
            db.flush()
            ids["bodies"][key] = t.id
            ms, ls = {}, {}
            for p in ir.PANELS:
                for i in ir.INSULATIONS:
                    default = (i == "EPS") if key != "freeze" else (i == "PU")
                    r = BillOfMaterial(trailer_type_id=t.id, material_id=master_mat[(p, i)].id, formula_expression="1",
                                       is_body_option=True, body_option_group=p, body_option_subgroup="INSULATION",
                                       selection_mode="single", selection_group="INSULATION",
                                       body_option_default=default, variable_value=0.06 if default else 0.0,
                                       bom_section="BODY OPTIONS")
                    db.add(r)
                    db.flush()
                    ms[(p, i)] = r.id
                    ln = BillOfMaterial(trailer_type_id=t.id, material_id=line_mat[i].id, formula_expression="2",
                                        waste_percentage=0.0, bom_section=p,
                                        bom_conditions=json.dumps([{"option": f"{MARK} {p} {i}", "equals": "Y",
                                                                    "option_id": r.id}]))
                    db.add(ln)
                    db.flush()
                    ls[(p, i)] = ln.id
            ids["masters"][key], ids["lines"][key] = ms, ls
        cust = Customer(name=f"{MARK} CUSTOMER")
        db.add(cust)
        db.commit()
        ids["customer"] = cust.id
    yield ids
    _purge_marker()


def sel(staged, key, picks):
    """body_option_selections: per panel the picked insulation ticked, the other unticked."""
    out = {}
    for p in ir.PANELS:
        for i in ir.INSULATIONS:
            out[str(staged["masters"][key][(p, i)])] = (picks.get(p, "EPS" if key != "freeze" else "PU") == i)
    return out


def payload(staged, key, picks=None, **extra):
    return {"trailer_type_id": staged["bodies"][key], "dimensions": DIMS, "profit_margin": 0,
            "body_option_selections": sel(staged, key, picks or {}), **extra}


def saved_costing(staged, key, picks, status="pending", deleted=False, legacy=False, customer=False):
    """A costing saved BEFORE the rule existed (inserted as the app stored it then)."""
    from app.database import CalculationRecord, SessionLocal
    st = {"body_option_selections": sel(staged, key, picks)} if not legacy else {}
    items = [{"bom_id": staged["lines"][key][(p, i)], "excluded": False}
             for p in ir.PANELS for i in ir.INSULATIONS if picks.get(p, "EPS" if key != "freeze" else "PU") == i]
    with SessionLocal() as db:
        rec = CalculationRecord(trailer_type_id=staged["bodies"][key], user_id=None,
                                customer_id=staged["customer"] if customer else None,
                                dimensions_json=json.dumps(DIMS), status=status,
                                quote_number=f"{MARK}{uuid.uuid4().hex[:6]}",
                                result_json=json.dumps({"input_state": st, "items": items, "grand_total": 1.0}),
                                approved_at=datetime.now(timezone.utc) if status == "accepted" else None,
                                deleted_at=datetime.now(timezone.utc) if deleted else None)
        db.add(rec)
        db.commit()
        return rec.id


def row_fingerprint(rec_id) -> str:
    from sqlalchemy import text
    from app.database import SessionLocal
    with SessionLocal() as db:
        return db.execute(text("select row_to_json(c)::text from icb_costings.calculations c where id = :i"),
                          {"i": rec_id}).scalar() or ""


def count(staged, key) -> int:
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        return db.query(CalculationRecord).filter_by(trailer_type_id=staged["bodies"][key]).count()


# ── 1. calculate warns ───────────────────────────────────────────────────────
@pytest.mark.parametrize("role", ["sales", "full", "admin"])
def test_calculate_warns_with_the_breach_and_still_prices(client, users, staged, role):
    r = client.post("/api/calculate", json=payload(staged, "chill", {"FRONT": "PU"}), headers=users[role])
    assert r.status_code == 200, r.text
    b = r.json()["rule_breaches"]
    assert [(x["panel"], x["insulation"], x["via"]) for x in b] == [("FRONT", "PU", "selection")]
    assert "not allowed on the FRONT" in b[0]["message"]
    assert r.json()["grand_total"] > 0                    # priced as asked: calculate never refuses
    r = client.post("/api/calculate", json=payload(staged, "freeze", {"SIDES": "EPS", "DRD": "EPS"}),
                    headers=users[role])
    assert {(x["panel"], x["insulation"]) for x in r.json()["rule_breaches"]} == {("SIDES", "EPS"), ("DRD", "EPS")}
    assert "the DRD (double rear doors)" in json.dumps(r.json()["rule_breaches"])


def test_an_allowed_quote_and_a_family_with_no_rule_are_never_blocked(client, users, staged):
    for key, picks in (("chill", {}), ("freeze", {"ROOF": "EPS", "FLOOR": "EPS"}),
                       ("plain", {p: "PU" for p in ir.PANELS})):
        r = client.post("/api/calculate", json=payload(staged, key, picks), headers=users["sales"])
        assert r.status_code == 200 and r.json()["rule_breaches"] == [], (key, r.text)


# ── 2. approve refuses, on every save path, for every role ───────────────────
@pytest.mark.parametrize("role", ["sales", "full", "admin"])
@pytest.mark.parametrize("path", ["new", "new_version", "save_as_new", "flag_alias", "calculator2"])
def test_approve_refuses_a_breach_on_every_save_path_for_every_role(client, users, staged, role, path):
    before = count(staged, "chill")
    body = payload(staged, "chill", {"SIDES": "PU"})
    if path in ("new_version", "save_as_new"):
        body.update(version_action=path, next_version=2)
    if path == "flag_alias":                               # no master ticked: a draft-flag alias names it
        body = payload(staged, "chill", {}, flag_overrides={f"{MARK} SIDES PU": True})
    if path == "calculator2":                              # Calculator 2: every line prices unless excluded
        body = {**payload(staged, "chill", {}), "body_option_selections": None, "include_all_items": True,
                "user_excluded_bom_ids": []}
    r = client.post("/api/approve", json=body, headers=users[role])
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "insulation_rule" and "PU insulation is not allowed" in d["message"]
    assert "Remove it, then save again." in d["message"]
    assert count(staged, "chill") == before                # nothing written


def test_replace_and_overwrite_are_refused_before_they_touch_anything(client, users, staged):
    existing = saved_costing(staged, "chill", {}, customer=True)          # a clean costing Replace would delete
    stale = saved_costing(staged, "chill", {"ROOF": "PU"})               # saved before the rule: the one overwritten
    fp = {i: row_fingerprint(i) for i in (existing, stale)}
    r = client.post("/api/approve", headers=users["admin"],
                    json=payload(staged, "chill", {"ROOF": "PU"}, customer_id=staged["customer"], version_action="replace"))
    assert r.status_code == 409, r.text
    r = client.post("/api/approve", headers=users["admin"],
                    json=payload(staged, "chill", {"ROOF": "PU"}, edit_record_id=stale, version_action="overwrite"))
    assert r.status_code == 409, r.text
    r = client.post("/api/approve", headers=users["admin"],      # capture-for (who the costing is FOR): same refusal
                    json=payload(staged, "chill", {"ROOF": "PU"}, sales_rep_user_id=None))
    assert r.status_code == 409, r.text
    assert {i: row_fingerprint(i) for i in (existing, stale)} == fp      # byte-identical: nothing deleted, nothing changed


def test_the_allowed_quote_saves_and_the_removed_choice_lets_the_overwrite_through(client, users, staged):
    stale = saved_costing(staged, "freeze", {"SIDES": "EPS"})
    r = client.post("/api/approve", headers=users["sales"],
                    json=payload(staged, "freeze", {}, edit_record_id=stale, version_action="overwrite"))
    assert r.status_code == 200, r.text
    st = json.loads(json.loads(row_fingerprint(stale))["result_json"])["input_state"]["body_option_selections"]
    assert st[str(staged["masters"]["freeze"][("SIDES", "PU")])] is True
    assert client.post("/api/approve", json=payload(staged, "plain", {p: "PU" for p in ir.PANELS}),
                       headers=users["sales"]).status_code == 200


# ── 3. Accept / pre-job / job from a costing ─────────────────────────────────
@pytest.mark.parametrize("role", ["sales", "full", "admin"])
def test_accept_refuses_a_saved_costing_that_breaches_the_current_rule(client, users, staged, role):
    rec = saved_costing(staged, "freeze", {"FRONT": "EPS"})
    fp = row_fingerprint(rec)
    r = client.post(f"/api/calculations/{rec}/accept", headers=users[role])
    assert r.status_code == 409, r.text
    msg = r.json()["detail"]["message"]
    assert "cannot be accepted" in msg and "EPS insulation is not allowed on the FRONT" in msg
    assert msg.endswith("Re-open it, Remove, save, then accept.")
    assert row_fingerprint(rec) == fp                     # still pending, never altered


def test_accept_takes_a_clean_costing_a_legacy_one_by_what_it_priced_and_a_repair(client, users, staged):
    from app.database import CalculationRecord, SessionLocal
    ok = saved_costing(staged, "chill", {})
    assert client.post(f"/api/calculations/{ok}/accept", headers=users["sales"]).status_code == 200
    legacy_bad = saved_costing(staged, "chill", {"FLOOR": "PU"}, legacy=True)   # no snapshot: judged by priced lines
    assert client.post(f"/api/calculations/{legacy_bad}/accept", headers=users["sales"]).status_code == 409
    with SessionLocal() as db:
        rep = CalculationRecord(trailer_type_id=None, is_repair=True, status="pending", customer_id=staged["customer"],
                                quote_number=f"{MARK}R{uuid.uuid4().hex[:5]}", result_json=json.dumps({"is_repair": True}))
        db.add(rep)
        db.commit()
        rid = rep.id
    assert client.post(f"/api/calculations/{rid}/accept", headers=users["sales"]).status_code == 200


def test_the_pre_job_card_and_a_job_from_the_costing_are_refused(client, users, staged):
    rec = saved_costing(staged, "chill", {"DRD": "PU"}, status="accepted")   # accepted before the rule existed
    fp = row_fingerprint(rec)
    r = client.post(f"/api/calculations/{rec}/pre-job-card", headers=users["admin"])
    assert r.status_code == 409 and "cannot be sent to the floor" in r.json()["detail"]["message"], r.text
    r = client.post(f"/api/production-jobs/from-calculation/{rec}", headers=users["admin"])
    assert r.status_code == 409 and "cannot be sent to production" in r.json()["detail"]["message"], r.text
    assert row_fingerprint(rec) == fp


def test_a_jobs_pre_job_card_is_refused_once_the_current_rule_forbids_its_costing(client, users, staged):
    """A job made while the costing was clean; then the family's rule changes (the CURRENT rule applies): the job's
    pre-job card is refused. The job and the costing are left as they were."""
    from app.database import SessionLocal, TrailerGroup
    from app.models.mes import ProductionJob
    rec = saved_costing(staged, "chill", {}, status="accepted")            # EPS everywhere: clean under CHILLER
    r = client.post(f"/api/production-jobs/from-calculation/{rec}", headers=users["admin"])
    assert r.status_code in (200, 201), r.text
    job_id = r.json()["id"]
    gid = staged["groups"][0]
    with SessionLocal() as db:                                             # the admin now forbids EPS on the ROOF
        db.query(TrailerGroup).filter_by(id=gid).update({"insulation_rule": ir.canonical_rule(
            {"allowed": {**{p: ["EPS"] for p in ir.PANELS}, "ROOF": ["PU"]}})})
        db.commit()
    try:
        fp = row_fingerprint(rec)
        r = client.post(f"/api/production-jobs/{job_id}/pre-job-card", headers=users["admin"])
        assert r.status_code == 409 and "cannot be sent to the floor" in r.json()["detail"]["message"], r.text
        assert row_fingerprint(rec) == fp
        with SessionLocal() as db:
            assert db.get(ProductionJob, job_id).status == "accepted"
    finally:
        with SessionLocal() as db:
            db.query(TrailerGroup).filter_by(id=gid).update({"insulation_rule": CHILLER})
            db.query(ProductionJob).filter_by(id=job_id).delete()
            db.commit()


# ── 4. RULING_1a: restore a soft-deleted breaching costing ────────────────────
def test_a_restored_breaching_costing_is_restored_but_not_accepted(client, users, staged):
    rec = saved_costing(staged, "freeze", {"SIDES": "EPS"}, deleted=True)
    r = client.post(f"/api/calculations/{rec}/restore", headers=users["admin"])
    assert r.status_code == 200, r.text                    # restore stays unguarded (RULING_1 Q3)
    assert client.post(f"/api/calculations/{rec}/accept", headers=users["admin"]).status_code == 409
    got = client.get(f"/api/calculations/{rec}", headers=users["admin"])
    assert got.status_code == 200                          # re-open works; the page shows the warning (journey)
    again = client.post("/api/calculate", headers=users["admin"],
                        json=payload(staged, "freeze", {"SIDES": "EPS"}))
    assert [(b["panel"], b["insulation"]) for b in again.json()["rule_breaches"]] == [("SIDES", "EPS")]


# ── 5. the reads ─────────────────────────────────────────────────────────────
def test_the_body_row_carries_the_rule_and_the_bom_rows_carry_their_class(client, users, staged):
    rows = {t["id"]: t for t in client.get("/api/trailers", headers=users["sales"]).json()}
    assert rows[staged["bodies"]["chill"]]["insulation_rule"] == json.loads(CHILLER)
    assert rows[staged["bodies"]["plain"]]["insulation_rule"] is None
    bom = client.get(f"/api/trailers/{staged['bodies']['freeze']}/bom", headers=users["sales"]).json()
    by_id = {r["id"]: r for r in bom}
    m = by_id[staged["masters"]["freeze"][("SIDES", "EPS")]]
    assert m["rule_class"] == {"kind": "master", "panel": "SIDES", "insulation": "EPS"} and "not allowed" in m["rule_forbidden"]
    assert by_id[staged["masters"]["freeze"][("ROOF", "EPS")]]["rule_forbidden"] is None
    ln = by_id[staged["lines"]["freeze"][("FRONT", "EPS")]]
    assert ln["rule_class"]["kind"] == "line" and ln["rule_forbidden"]


def test_a_choice_the_check_cannot_read_is_reported_on_a_ruled_body(client, users, staged):
    from app.database import BillOfMaterial, Material, SessionLocal
    with SessionLocal() as db:
        m = Material(name=f"{MARK} SIDES EPS PU", unit_of_measure="each", price_per_unit=0, material_code=MARK)
        db.add(m)
        db.flush()
        r = BillOfMaterial(trailer_type_id=staged["bodies"]["chill"], material_id=m.id, is_body_option=True,
                           body_option_group="SIDES", body_option_subgroup="INSULATION", formula_expression="1")
        db.add(r)
        db.commit()
        mid, rid = m.id, r.id
    try:
        res = client.post("/api/calculate", json=payload(staged, "chill", {}), headers=users["admin"]).json()
        assert [u["name"] for u in res["rule_unclassified"]] == [f"{MARK} SIDES EPS PU"]
        chk = client.get(f"/api/trailers/{staged['bodies']['chill']}/insulation-rule-check", headers=users["admin"]).json()
        assert chk["unclassified"] and "both EPS and PU" in chk["unclassified"][0]["reason"]
    finally:
        with SessionLocal() as db:
            db.query(BillOfMaterial).filter_by(id=rid).delete()
            db.query(Material).filter_by(id=mid).delete()
            db.commit()


# ── 6. the family editor ─────────────────────────────────────────────────────
def _edit_form(gid, **extra):
    return {"name": f"{MARK} FREEZE FAM", "description": "", "report_template_id": "", "colour": "",
            "sort_order": "9602", **extra}


def _grid(rule_json):
    allowed = json.loads(rule_json)["allowed"]
    return [f"{p}:{i}" for p, v in allowed.items() for i in v]


def test_the_family_editor_grid_sets_clears_and_refuses_and_an_older_form_leaves_it(client, users, staged):
    from app.database import SessionLocal, TrailerGroup
    gid = staged["groups"][1]
    url = f"/admin/quote-templates/groups/{gid}/edit"
    h = {**users["admin"], "Content-Type": "application/x-www-form-urlencoded"}

    def stored():
        with SessionLocal() as db:
            return db.query(TrailerGroup).filter_by(id=gid).first().insulation_rule
    r = client.post(url, data={**_edit_form(gid), "ins_rule_present": "1"}, headers=h, follow_redirects=False)
    assert r.status_code == 303 and stored() is None                         # Enforce unticked = no rule
    r = client.post(url, data={**_edit_form(gid), "ins_rule_present": "1", "ins_rule_on": "1",
                               "ins_allow": list(reversed(_grid(FREEZER)))}, headers=h, follow_redirects=False)
    assert r.status_code == 303 and stored() == FREEZER                      # canonical, whatever the tick order
    r = client.post(url, data={**_edit_form(gid), "ins_rule_present": "1", "ins_rule_on": "1",
                               "ins_allow": [c for c in _grid(FREEZER) if not c.startswith("SIDES")]},
                    headers=h, follow_redirects=False)
    assert r.status_code == 400 and "SIDES has none" in r.text and stored() == FREEZER
    r = client.post(url, data=_edit_form(gid), headers=h, follow_redirects=False)   # an older page: no grid
    assert r.status_code == 303 and stored() == FREEZER


@pytest.mark.parametrize("role", ["sales", "full"])
def test_only_an_admin_changes_the_rule_through_the_api(client, users, staged, role):
    gid = staged["groups"][0]
    r = client.put(f"/api/admin/body-families/{gid}/insulation-rule", json={"rule": None}, headers=users[role])
    assert r.status_code == 403
    r = client.put(f"/api/admin/body-families/{gid}/insulation-rule", headers=users["admin"],
                   json={"rule": json.loads(CHILLER)})
    assert r.status_code == 200 and r.json()["insulation_rule"]["SIDES"] == ["EPS"]


# ── 7. drafts warn, never block ──────────────────────────────────────────────
def test_a_draft_that_offers_a_forbidden_choice_is_saved_with_a_warning_and_so_is_its_restore(client, users, staged):
    tid = staged["bodies"]["chill"]
    draft = {"nextId": 3, "rootIds": ["1"], "itemRules": {}, "nodes": {
        "1": {"id": "1", "type": "category", "label": "FRONT", "parentId": None, "childIds": ["2"]},
        "2": {"id": "2", "type": "flag", "label": "FRONT PU", "parentId": "1", "childIds": [], "flagMode": "radio",
              "flagBindingId": staged["masters"]["chill"][("FRONT", "PU")]}}}
    r = client.put(f"/api/configurator/trailers/{tid}/draft", json={"draft": draft}, headers=users["admin"])
    assert r.status_code == 200 and r.json()["ok"]
    w = r.json()["rule_warnings"]
    assert [(x["panel"], x["insulation"], x["label"]) for x in w] == [("FRONT", "PU", "FRONT PU")]
    snap = client.post(f"/api/configurator/trailers/{tid}/draft-snapshots", json={"label": f"{MARK} backup"},
                       headers=users["admin"]).json()
    pre = client.get(f"/api/configurator/draft-snapshots/{snap['id']}/rule-warnings", headers=users["admin"]).json()
    assert [x["panel"] for x in pre["rule_warnings"]] == ["FRONT"]
    res = client.post(f"/api/configurator/draft-snapshots/{snap['id']}/restore", headers=users["admin"])
    assert res.status_code == 200 and [x["panel"] for x in res.json()["rule_warnings"]] == ["FRONT"]


def test_the_new_routes_are_closed_without_a_session(client, staged):
    """RT4's deny-by-default covers RT6's routes too (the release's probe_paths.txt expects these 401s)."""
    for path in (f"/api/trailers/{staged['bodies']['chill']}/insulation-rule-check",
                 "/api/configurator/draft-snapshots/1/rule-warnings"):
        assert client.get(path, headers={"Accept": "application/json"}).status_code == 401, path
    r = client.put(f"/api/admin/body-families/{staged['groups'][0]}/insulation-rule", json={"rule": None},
                   headers={"Accept": "application/json"})
    assert r.status_code in (401, 403)


# ── 8. the audit probe is never guarded ──────────────────────────────────────
def test_the_check_is_in_the_routers_never_in_the_pricing_engine_or_the_audit():
    src = (ROOT / "backend/app/routers/calculator.py").read_text(encoding="utf-8")
    engine = re.search(r"def _build_bom_items\(.*?(?=\ndef )", src, re.S).group(0)
    assert "rule_guard" not in engine and "insulation_rules" not in engine
    for f in (ROOT / "backend/tools/costing_audit").rglob("*.py"):
        assert "rule_guard" not in f.read_text(encoding="utf-8"), f
