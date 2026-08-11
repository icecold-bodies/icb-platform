"""v1.45 Validated references — fingerprint, tolerance, permissions, retirement.

Nadie marks a costing that balanced with her Excel as a VALIDATED REFERENCE.
The four things that must hold, and that this file pins:

  1. FINGERPRINT STABILITY — the same configuration always hashes the same, no
     matter what order the options were ticked in or how the floats were typed;
     and a genuinely different configuration hashes differently. The write path
     and the match path share ONE function, so a reference can never be stored
     under a hash the matcher would not produce.
  2. TOLERANCE BOUNDARY — 1.9% is quiet (green tick), 2.1% warns (red banner),
     against the admin-tunable default of 2%.
  3. PERMISSION GATES — create/retire need costings.validated_refs_manage
     ({admin, full}); reading, matching and recalling need nothing more than a
     costings login.
  4. RETIRED REFERENCES NEVER MATCH and leave the dropdown.

Sessions are real UserSession rows sent via a raw Cookie header — the banked
pattern; dependency_overrides do not reach the inline auth chokepoints.
"""
import json
import uuid

import pytest

from app.services.validated_references import (
    compare_to_reference,
    config_fingerprint,
    fingerprint_from_result,
)

# A representative v2-configurator body: body options ticked, two sections
# excluded, DRD/FRONT insulation flags set, optional extras enabled.
BASE_INPUT_STATE = {
    "body_option_selections": {"3292": True, "3293": False, "3294": True},
    "excluded_categories": ["SRD", "SRD DOOR FITTINGS"],
    "flag_overrides": {"DRD EPS": True, "DRD PU": False, "FRONT EPS": True},
    "user_excluded_bom_ids": [41, 17],
    "optional_sections_enabled": [13, 14, 15],
    "body_variables": {"DRD EPS THICKNESS": 0.08, "FRONT EPS THICKNESS": 0.08},
}
BASE_DIMS = {"length": 7.5, "width": 2.5, "height": 2.6}


# ══ 1. Fingerprint ════════════════════════════════════════════════════════════

def test_fingerprint_is_deterministic():
    a = config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE)
    b = config_fingerprint(7, dict(BASE_DIMS), json.loads(json.dumps(BASE_INPUT_STATE)))
    assert a == b
    assert len(a) == 64  # sha256 hex — the column is varchar(64)


def test_fingerprint_is_option_order_invariant():
    """Nadie ticking the same options in a different order is the SAME body."""
    shuffled = {
        "body_option_selections": {"3294": True, "3293": False, "3292": True},
        "excluded_categories": ["SRD DOOR FITTINGS", "SRD"],
        "flag_overrides": {"FRONT EPS": True, "DRD PU": False, "DRD EPS": True},
        "user_excluded_bom_ids": [17, 41],
        "optional_sections_enabled": [15, 13, 14],
        "body_variables": {"FRONT EPS THICKNESS": 0.08, "DRD EPS THICKNESS": 0.08},
    }
    assert (config_fingerprint(7, BASE_DIMS, shuffled)
            == config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))


def test_fingerprint_ignores_id_types_and_dimension_formatting():
    """13.6 vs 13.600 is the same body, and the identity fields that carry ids
    (body options, excluded categories) are compared as strings either way."""
    variant = dict(BASE_INPUT_STATE,
                   body_option_selections={3292: True, 3293: False, 3294: True})
    dims = {"length": 7.500, "width": 2.5, "height": 2.60}
    assert (config_fingerprint(7, dims, variant)
            == config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))


def test_fingerprint_ignores_price_overrides_margin_and_ratio():
    """Ratified: overrides and margin/ratio are NOT part of identity — they are
    exactly what the drift warning has to be able to move."""
    noisy = dict(BASE_INPUT_STATE,
                 overrides={"41": 999.0}, override_reasons={"41": "spot buy"},
                 profit_margin=25, ratio_value=0.35, ratio_label="35%",
                 chassis={"enabled": True}, is_repair=True)
    assert (config_fingerprint(7, BASE_DIMS, noisy)
            == config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))


@pytest.mark.parametrize("field,mutation", [
    ("body option",        {"body_option_selections": {"3292": True, "3294": False}}),
    ("excluded category",  {"excluded_categories": ["SRD"]}),
    # The two additions beyond the ratified base list, both proven necessary:
    ("insulation type",    {"flag_overrides": {"DRD PU": True, "FRONT EPS": True}}),
    ("insulation depth",   {"body_variables": {"DRD EPS THICKNESS": 0.10,
                                               "FRONT EPS THICKNESS": 0.08}}),
])
def test_fingerprint_separates_different_configurations(field, mutation):
    assert (config_fingerprint(7, BASE_DIMS, dict(BASE_INPUT_STATE, **mutation))
            != config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE)), field


@pytest.mark.parametrize("field,mutation", [
    ("optional sections", {"optional_sections_enabled": [13, 14]}),
    ("no extras at all",  {"optional_sections_enabled": []}),
    ("excluded bom id",   {"user_excluded_bom_ids": [41]}),
    ("no row exclusions", {"user_excluded_bom_ids": []}),
])
def test_extras_are_not_part_of_identity(field, mutation):
    """Michael, 11 Aug 2026 — the optional-EXTRAS selection lives in the
    BROWSER's localStorage, not on the costing, so including it meant a
    reference never matched a fresh browser. Identity now depends only on
    server-side, costing-borne facts."""
    assert (config_fingerprint(7, BASE_DIMS, dict(BASE_INPUT_STATE, **mutation))
            == config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE)), field


def test_a_fresh_browser_matches_a_reference_marked_with_extras():
    """The regression this change exists for: the reference was marked from a
    costing carrying extras 13–23; the fresh browser sends none. Same body,
    same dims, same options → must still match."""
    marked_with_extras = dict(BASE_INPUT_STATE,
                              optional_sections_enabled=list(range(13, 24)),
                              user_excluded_bom_ids=[41, 17])
    fresh_browser = dict(BASE_INPUT_STATE,
                         optional_sections_enabled=[],
                         user_excluded_bom_ids=[])
    assert (config_fingerprint(7, BASE_DIMS, marked_with_extras)
            == config_fingerprint(7, BASE_DIMS, fresh_browser))


def test_fingerprint_separates_dims_and_body_type():
    assert (config_fingerprint(7, dict(BASE_DIMS, length=7.6), BASE_INPUT_STATE)
            != config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))
    assert (config_fingerprint(8, BASE_DIMS, BASE_INPUT_STATE)
            != config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))


def test_fingerprint_from_result_folds_in_root_body_variables():
    """Saved records keep body_variables at the result root, beside input_state.
    fingerprint_from_result must reach it — else every saved reference would
    hash as if it had no insulation pins and mis-match the live path."""
    state = {k: v for k, v in BASE_INPUT_STATE.items() if k != "body_variables"}
    result = {"input_state": state,
              "body_variables": BASE_INPUT_STATE["body_variables"]}
    assert (fingerprint_from_result(7, BASE_DIMS, result)
            == config_fingerprint(7, BASE_DIMS, BASE_INPUT_STATE))


# ══ 2. Tolerance boundary ═════════════════════════════════════════════════════

def _result(total, cats=None):
    return {"grand_total": total, "category_totals": cats or {}}


@pytest.mark.parametrize("live_total,expect_quiet", [
    (101_900.0, True),    # +1.9% — inside 2%: quiet green tick
    (102_000.0, True),    # exactly 2.0% — the boundary is inclusive (<=)
    (102_100.0, False),   # +2.1% — outside: red warning
    (98_100.0,  True),    # −1.9%
    (97_900.0,  False),   # −2.1% — the rule is on the ABSOLUTE move
])
def test_tolerance_boundary(live_total, expect_quiet):
    verdict = compare_to_reference(_result(100_000.0), _result(live_total), 2.0)
    assert verdict["within_tolerance"] is expect_quiet


def test_comparison_reports_signed_percentage_and_category_deltas():
    ref = _result(100_000.0, {"FLOOR": 40_000.0, "SIDES": 60_000.0})
    live = _result(103_000.0, {"FLOOR": 40_500.0, "SIDES": 62_500.0})
    v = compare_to_reference(ref, live, 2.0)
    assert v["within_tolerance"] is False
    assert v["delta"] == 3000.0
    assert round(v["delta_pct"], 2) == 3.0
    # Largest mover first — that is the "where did it move" line on the banner.
    assert [d["category"] for d in v["category_deltas"]] == ["SIDES", "FLOOR"]
    assert v["category_deltas"][0]["delta"] == 2500.0


def test_comparison_survives_a_zero_reference_total():
    """A zero-total reference cannot produce a percentage; report it quiet
    rather than dividing by zero inside the calculator's hot path."""
    v = compare_to_reference(_result(0.0), _result(1234.0), 2.0)
    assert v["within_tolerance"] is True
    assert v["delta_pct"] == 0.0


# ══ API-level fixtures ════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:   # startup seeds admin + the permission catalogue
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _make_session(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"vref-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role,
                             expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    return _make_session("admin")


def _throwaway_user(role: str):
    from app.database import SessionLocal, User, UserSession
    uname = f"t_vref_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        db.add(User(username=uname, password_hash="x", role=role))
        db.commit()
    headers = _make_session(uname)
    yield headers
    with SessionLocal() as db:
        db.query(UserSession).filter_by(
            id=headers["Cookie"].split("session_id=")[1]).delete()
        db.query(User).filter_by(username=uname).delete()
        db.commit()


@pytest.fixture(scope="module")
def full_headers(app_mod):
    """Nadie's role — HAS costings.validated_refs_manage (seeded {admin, full})."""
    yield from _throwaway_user("full")


@pytest.fixture(scope="module")
def planner_headers(app_mod):
    """A costings-logged-in user WITHOUT the manage key — must still read/match."""
    yield from _throwaway_user("planner")


@pytest.fixture()
def costings(app_mod):
    """Two saved costings on one throwaway body: the reference (100k) and a
    live-ish twin. Plus one LEGACY record with no input_state snapshot."""
    from app.database import CalculationRecord, SessionLocal, TrailerType, ValidatedReference
    mark = f"VREF-{uuid.uuid4().hex[:6]}"
    ids = {}
    with SessionLocal() as db:
        tt = TrailerType(name=f"{mark} CHILLER", is_active=True,
                         default_length=7.5, default_width=2.5, default_height=2.6)
        db.add(tt)
        db.flush()

        def rec(total, state, cats, quote):
            r = CalculationRecord(
                trailer_type_id=tt.id,
                dimensions_json=json.dumps(BASE_DIMS),
                result_json=json.dumps({
                    "grand_total": total, "category_totals": cats,
                    "input_state": state,
                    "body_variables": BASE_INPUT_STATE["body_variables"],
                }),
                status="accepted", quote_number=quote)
            db.add(r)
            db.flush()
            return r.id

        state = {k: v for k, v in BASE_INPUT_STATE.items() if k != "body_variables"}
        ids["reference"] = rec(100_000.0, state,
                               {"FLOOR": 40_000.0, "SIDES": 60_000.0}, f"{mark}-1")
        # Pre-v1.39.9 record: result_json without the input_state snapshot.
        legacy = CalculationRecord(
            trailer_type_id=tt.id, dimensions_json=json.dumps(BASE_DIMS),
            result_json=json.dumps({"grand_total": 100_000.0}),
            status="accepted", quote_number=f"{mark}-legacy")
        db.add(legacy)
        db.flush()
        ids["legacy"] = legacy.id
        ids["trailer_type_id"] = tt.id
        db.commit()

    yield ids

    with SessionLocal() as db:
        db.query(ValidatedReference).filter(
            ValidatedReference.trailer_type_id == ids["trailer_type_id"]).delete()
        db.query(CalculationRecord).filter(
            CalculationRecord.trailer_type_id == ids["trailer_type_id"]).delete()
        db.query(TrailerType).filter_by(id=ids["trailer_type_id"]).delete()
        db.commit()


def _live_payload(trailer_type_id, grand_total, cats=None):
    """Exactly the fields the calculator re-sends after a recompute."""
    return {
        "trailer_type_id": trailer_type_id,
        "dimensions": BASE_DIMS,
        "grand_total": grand_total,
        "category_totals": cats or {"FLOOR": 40_000.0, "SIDES": 60_000.0},
        **{k: v for k, v in BASE_INPUT_STATE.items()},
    }


# ══ 3. Permission gates ═══════════════════════════════════════════════════════

def test_create_requires_the_manage_permission(client, costings, planner_headers):
    r = client.post("/api/validated-references", headers=planner_headers,
                    json={"calculation_id": costings["reference"], "label": "nope"})
    assert r.status_code == 403
    assert "costings.validated_refs_manage" in r.json()["detail"]


def test_create_requires_a_login(client, costings):
    r = client.post("/api/validated-references",
                    json={"calculation_id": costings["reference"], "label": "nope"})
    assert r.status_code in (401, 403)


def test_full_role_can_create_and_retire(client, costings, full_headers):
    """Nadie's role owns her own reference library (seeded {admin, full})."""
    r = client.post("/api/validated-references", headers=full_headers,
                    json={"calculation_id": costings["reference"],
                          "label": "Chiller 7.5 — balanced 10 Aug"})
    assert r.status_code == 201, r.text
    ref = r.json()
    assert ref["label"] == "Chiller 7.5 — balanced 10 Aug"
    assert ref["active"] is True
    assert ref["reference_total"] == 100_000.0
    assert len(ref["config_fingerprint"]) == 64

    assert client.post(f"/api/validated-references/{ref['id']}/retire",
                       headers=full_headers).status_code == 200


def test_retire_requires_the_manage_permission(client, costings, admin_headers,
                                               planner_headers):
    ref = client.post("/api/validated-references", headers=admin_headers,
                      json={"calculation_id": costings["reference"],
                            "label": "gate probe"}).json()
    r = client.post(f"/api/validated-references/{ref['id']}/retire",
                    headers=planner_headers)
    assert r.status_code == 403


def test_reading_and_matching_need_no_manage_permission(client, costings,
                                                        admin_headers,
                                                        planner_headers):
    client.post("/api/validated-references", headers=admin_headers,
                json={"calculation_id": costings["reference"], "label": "readable"})
    listed = client.get("/api/validated-references", headers=planner_headers,
                        params={"trailer_type_id": costings["trailer_type_id"]})
    assert listed.status_code == 200
    assert [x["label"] for x in listed.json()] == ["readable"]

    matched = client.post("/api/validated-references/match", headers=planner_headers,
                          json=_live_payload(costings["trailer_type_id"], 100_000.0))
    assert matched.status_code == 200
    assert matched.json()["matched"] is True


def test_tolerance_tuning_is_admin_only(client, full_headers, admin_headers):
    assert client.get("/api/validated-references/settings",
                      headers=full_headers).json()["tolerance_pct"] == 2.0
    assert client.put("/api/validated-references/settings", headers=full_headers,
                      json={"tolerance_pct": 5}).status_code == 403
    r = client.put("/api/validated-references/settings", headers=admin_headers,
                   json={"tolerance_pct": 5})
    assert r.status_code == 200 and r.json()["tolerance_pct"] == 5.0
    # restore the ratified default so later tests / the dev DB are unaffected
    client.put("/api/validated-references/settings", headers=admin_headers,
               json={"tolerance_pct": 2})


# ══ 4. Match, drift and retirement ════════════════════════════════════════════

def test_match_is_quiet_inside_tolerance_and_warns_outside(client, costings,
                                                           admin_headers):
    client.post("/api/validated-references", headers=admin_headers,
                json={"calculation_id": costings["reference"],
                      "label": "Chiller baseline"})

    quiet = client.post("/api/validated-references/match", headers=admin_headers,
                        json=_live_payload(costings["trailer_type_id"], 101_900.0)).json()
    assert quiet["matched"] is True
    assert quiet["reference"]["label"] == "Chiller baseline"
    assert quiet["comparison"]["within_tolerance"] is True

    warn = client.post(
        "/api/validated-references/match", headers=admin_headers,
        json=_live_payload(costings["trailer_type_id"], 102_100.0,
                           {"FLOOR": 40_000.0, "SIDES": 62_100.0})).json()
    assert warn["comparison"]["within_tolerance"] is False
    assert round(warn["comparison"]["delta_pct"], 1) == 2.1
    assert warn["comparison"]["category_deltas"][0]["category"] == "SIDES"


def test_a_different_configuration_does_not_match(client, costings, admin_headers):
    client.post("/api/validated-references", headers=admin_headers,
                json={"calculation_id": costings["reference"], "label": "baseline"})
    payload = _live_payload(costings["trailer_type_id"], 100_000.0)
    payload["dimensions"] = dict(BASE_DIMS, length=9.0)
    assert client.post("/api/validated-references/match", headers=admin_headers,
                       json=payload).json()["matched"] is False


def test_retired_references_never_match_and_leave_the_dropdown(client, costings,
                                                               admin_headers):
    ref = client.post("/api/validated-references", headers=admin_headers,
                      json={"calculation_id": costings["reference"],
                            "label": "to be retired"}).json()
    payload = _live_payload(costings["trailer_type_id"], 100_000.0)
    assert client.post("/api/validated-references/match", headers=admin_headers,
                       json=payload).json()["matched"] is True

    retired = client.post(f"/api/validated-references/{ref['id']}/retire",
                          headers=admin_headers)
    assert retired.status_code == 200 and retired.json()["active"] is False

    assert client.post("/api/validated-references/match", headers=admin_headers,
                       json=payload).json()["matched"] is False
    dropdown = client.get("/api/validated-references", headers=admin_headers,
                          params={"trailer_type_id": costings["trailer_type_id"]}).json()
    assert dropdown == []
    # …but the row survives for audit — soft retire, never a delete.
    audited = client.get("/api/validated-references", headers=admin_headers,
                         params={"trailer_type_id": costings["trailer_type_id"],
                                 "include_retired": True}).json()
    assert [x["label"] for x in audited] == ["to be retired"]


def test_retire_is_idempotent(client, costings, admin_headers):
    ref = client.post("/api/validated-references", headers=admin_headers,
                      json={"calculation_id": costings["reference"], "label": "x"}).json()
    for _ in range(2):
        r = client.post(f"/api/validated-references/{ref['id']}/retire",
                        headers=admin_headers)
        assert r.status_code == 200 and r.json()["active"] is False


def test_remarking_a_costing_relabels_instead_of_duplicating(client, costings,
                                                             admin_headers):
    first = client.post("/api/validated-references", headers=admin_headers,
                        json={"calculation_id": costings["reference"],
                              "label": "first name"}).json()
    again = client.post("/api/validated-references", headers=admin_headers,
                        json={"calculation_id": costings["reference"],
                              "label": "better name"}).json()
    assert again["id"] == first["id"]
    assert again["label"] == "better name"
    listed = client.get("/api/validated-references", headers=admin_headers,
                        params={"trailer_type_id": costings["trailer_type_id"]}).json()
    assert len(listed) == 1


def test_a_legacy_costing_without_input_state_is_refused(client, costings,
                                                         admin_headers):
    """Pre-v1.39.9 records carry no configuration snapshot. Fingerprinting one
    would store a near-empty hash that then matches every other legacy record —
    so the write is refused loudly instead."""
    r = client.post("/api/validated-references", headers=admin_headers,
                    json={"calculation_id": costings["legacy"], "label": "legacy"})
    assert r.status_code == 409
    assert "configuration snapshot" in r.json()["detail"]


def test_create_validates_its_inputs(client, costings, admin_headers):
    assert client.post("/api/validated-references", headers=admin_headers,
                       json={"calculation_id": costings["reference"],
                             "label": "   "}).status_code == 400
    assert client.post("/api/validated-references", headers=admin_headers,
                       json={"label": "no id"}).status_code == 400
    assert client.post("/api/validated-references", headers=admin_headers,
                       json={"calculation_id": 99_999_999,
                             "label": "ghost"}).status_code == 404


def test_the_permission_key_is_seeded_like_its_sibling(app_mod):
    """The catalogue-driven startup bootstrap must have granted the new key to
    exactly the same roles as costings.price_master_edit, the key it was modelled
    on. Reads the ACTUAL (role, permission) grant rows, not the catalogue —
    the two are independent layers."""
    from app.database import Permission, RolePermission, SessionLocal

    def grants(name):
        perm = db.query(Permission).filter_by(name=name).first()
        assert perm, f"{name} was not bootstrapped"
        return {g.role for g in db.query(RolePermission)
                                  .filter_by(permission_id=perm.id).all()}

    with SessionLocal() as db:
        new = grants("costings.validated_refs_manage")
        sibling = grants("costings.price_master_edit")
    assert new == {"admin", "full"}
    assert new == sibling
