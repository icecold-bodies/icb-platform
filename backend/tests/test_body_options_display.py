"""v1.42 Body options panel — server-side derivation of door/insulation/floor-type
choices for the costing detail page, read from a saved costing's input_state +
body_variables against the trailer's current BOM body-option rows.

Unit-tests _derive_body_options_display directly (pure function, no DB/request
context — mirrors the _contact_snapshot unit-test pattern in
test_calculation_contact_api.py) against constructed BOM-row stand-ins, plus one
live-endpoint smoke test proving the wiring on GET /api/calculations/{id} degrades
to null (not a 500) for a record with no trailer/body-option data at all.
"""
from types import SimpleNamespace

import pytest

from app.routers.calculator import _derive_body_options_display

_MARK = "V142BOP"


def _row(id, group, subgroup, name, variable_value=None):
    return SimpleNamespace(
        id=id,
        is_body_option=True,
        body_option_group=group,
        body_option_subgroup=subgroup,
        variable_value=variable_value,
        material=SimpleNamespace(name=name),
    )


def _standard_bom_rows():
    """One EPS/PU pair per insulation location + DRD/SRD rear-door pairs + a
    2-way floor-type radio, mirroring the real BOM shape found on trailer 20
    (UP TO 4.8 MT FREEZER 2) during §3.0 discovery."""
    return [
        _row(1, "FRONT", "INSULATION", "FRONT EPS", 0.0),
        _row(2, "FRONT", "INSULATION", "FRONT PU", 0.06),
        _row(3, "SIDES", "INSULATION", "SIDES EPS", 0.0),
        _row(4, "SIDES", "INSULATION", "SIDES PU", 0.06),
        _row(5, "ROOF", "INSULATION", "ROOF EPS", 0.076),
        _row(6, "ROOF", "INSULATION", "ROOF PU", 0.0),
        _row(7, "FLOOR", "INSULATION", "FLOOR EPS", 0.076),
        _row(8, "FLOOR", "INSULATION", "FLOOR PU", 0.0),
        _row(9, "DRD", "INSULATION", "DRD EPS", 0.06),
        _row(10, "DRD", "INSULATION", "DRD PU", 0.0),
        _row(11, "SRD", "INSULATION", "SRD EPS", 0.0),
        _row(12, "SRD", "INSULATION", "SRD PU", 0.0),
        _row(13, "FLOOR", None, "RICE GRAIN ALU FLOOR"),
        _row(14, "FLOOR", None, "ALU EXTRUTION FLOOR"),
        _row(15, "FLOOR", "KICK - 1ST ROW ALU KICK PLATE", "1ST ROW ALU KICK PLATE"),
        _row(16, "FLOOR", "KICK - 2ND ROW ALU KICK PLATE", "2ND ROW ALU KICK PLATE"),
    ]


def _selections(**overrides):
    """All-EPS-front/sides, PU-roof/floor, DRD-door selections by default (mirrors
    a real quote), individually overridable by bom id."""
    sel = {
        "1": True, "2": False,      # FRONT: EPS
        "3": True, "4": False,      # SIDES: EPS
        "5": False, "6": True,      # ROOF: PU
        "7": False, "8": True,      # FLOOR: PU
        "9": True, "10": False,     # DRD: EPS
        "11": False, "12": False,   # SRD: not quoted
        "13": True, "14": False,    # floor type: RICE GRAIN
    }
    sel.update({str(k): v for k, v in overrides.items()})
    return sel


def _input_state(selections, drd_srd=None, body_variables_by_bomid=None):
    return {
        "body_option_selections": selections,
        "ui_snapshot": {
            "drd_srd": drd_srd if drd_srd is not None else {"DRD": True, "SRD": False},
            "body_variables": body_variables_by_bomid or {},
        },
    }


# ── Snapshot record (the common case) ────────────────────────────────────────

def test_snapshot_record_decodes_all_locations_door_and_floor_type():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections())
    saved_body_vars = {
        "FRONT EPS": 0.06, "FRONT PU": 0.0,
        "SIDES EPS": 0.06, "SIDES PU": 0.0,
        "ROOF EPS": 0.0, "ROOF PU": 0.076,
        "FLOOR EPS": 0.0, "FLOOR PU": 0.076,
        "DRD EPS": 0.06, "DRD PU": 0.0,
        "SRD EPS": 0.0, "SRD PU": 0.0,
    }
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert disp["rear_door"] == {"door_type": "DRD", "insulation": "EPS", "thickness_m": 0.06}
    assert disp["floor_type"] == "RICE GRAIN ALU FLOOR"
    by_loc = {p["location"]: p for p in disp["panels"]}
    assert by_loc["FRONT"] == {"location": "FRONT", "insulation": "EPS", "thickness_m": 0.06}
    assert by_loc["SIDES"] == {"location": "SIDES", "insulation": "EPS", "thickness_m": 0.06}
    assert by_loc["ROOF"] == {"location": "ROOF", "insulation": "PU", "thickness_m": 0.076}
    assert by_loc["FLOOR"] == {"location": "FLOOR", "insulation": "PU", "thickness_m": 0.076}
    # Fittings under FLOOR (kick plates) are explicitly out of scope.
    assert "KICK" not in str(disp)


def test_panel_order_is_front_sides_roof_floor():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections())
    saved_body_vars = {
        "FRONT EPS": 0.06, "SIDES EPS": 0.06, "ROOF PU": 0.076, "FLOOR PU": 0.076,
    }
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert [p["location"] for p in disp["panels"]] == ["FRONT", "SIDES", "ROOF", "FLOOR"]


# ── Legacy record: no body_option_selections, fall back to body_variables ────

def test_legacy_record_falls_back_to_nonzero_side_heuristic():
    rows = _standard_bom_rows()
    input_state = {}  # pre-v1.39.9 record: no input_state key at all
    saved_body_vars = {
        "FRONT EPS": 0.0, "FRONT PU": 0.06,
        "DRD EPS": 0.06, "DRD PU": 0.0,
        "SRD EPS": 0.0, "SRD PU": 0.0,
    }
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert disp is not None
    # DRD EPS carries the saved thickness (0.06), DRD PU is the zeroed sibling.
    assert disp["rear_door"] == {"door_type": "DRD", "insulation": "EPS", "thickness_m": 0.06}
    by_loc = {p["location"]: p for p in disp["panels"]}
    assert by_loc["FRONT"] == {"location": "FRONT", "insulation": "PU", "thickness_m": 0.06}
    # No selections snapshot at all → floor type is not derivable (radio choice,
    # not a thickness) — omitted, never invented.
    assert disp["floor_type"] is None


def test_legacy_record_with_nothing_derivable_returns_none():
    """A record with no selections snapshot AND no saved body_variables AND rows
    whose current variable_value is also unset (e.g. never priced) — every
    fallback in the derivation order comes up empty, so the whole block is None."""
    rows = [_row(id, grp, sub, name) for id, grp, sub, name in [
        (1, "FRONT", "INSULATION", "FRONT EPS"), (2, "FRONT", "INSULATION", "FRONT PU"),
        (9, "DRD", "INSULATION", "DRD EPS"), (10, "DRD", "INSULATION", "DRD PU"),
        (13, "FLOOR", None, "RICE GRAIN ALU FLOOR"), (14, "FLOOR", None, "ALU EXTRUTION FLOOR"),
    ]]
    disp = _derive_body_options_display(rows, {}, {})
    assert disp is None


# ── Stale bomIds: ui_snapshot references ids no longer on the trailer's BOM ──

def test_stale_bomids_in_ui_snapshot_are_ignored_not_fatal():
    rows = _standard_bom_rows()
    input_state = _input_state(
        _selections(),
        body_variables_by_bomid={"99999": 0.5, "88888": 0.2},  # rows that no longer exist
    )
    saved_body_vars = {"FRONT EPS": 0.06}
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert disp is not None
    by_loc = {p["location"]: p for p in disp["panels"]}
    assert by_loc["FRONT"]["thickness_m"] == 0.06


def test_renamed_material_falls_through_to_row_variable_value():
    """result.body_variables is keyed by material NAME as-costed at save time; if
    the material has since been renamed, the name lookup misses and the helper
    falls back to ui_snapshot (by bomId) then the row's current variable_value —
    never crashes on the mismatch."""
    rows = _standard_bom_rows()
    input_state = _input_state(_selections(), body_variables_by_bomid={"1": 0.06})
    # saved_body_variables keyed by a name that no longer matches any current row
    disp = _derive_body_options_display(rows, input_state, {"FRONT EPS (OLD NAME)": 0.09})
    assert disp is not None
    by_loc = {p["location"]: p for p in disp["panels"]}
    assert by_loc["FRONT"]["thickness_m"] == 0.06  # from ui_snapshot fallback, not the stale name


# ── Both-zero pair: never invent a value ─────────────────────────────────────

def test_both_zero_pair_is_omitted_not_invented():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections(**{"1": False, "2": False}))  # FRONT: neither selected
    saved_body_vars = {"FRONT EPS": 0.0, "FRONT PU": 0.0}
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    locations = [p["location"] for p in disp["panels"]]
    assert "FRONT" not in locations


def test_srd_stays_omitted_when_unquoted_even_if_both_zero():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections())  # SRD both False, DRD active
    saved_body_vars = {"SRD EPS": 0.0, "SRD PU": 0.0, "DRD EPS": 0.06}
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert disp["rear_door"]["door_type"] == "DRD"


# ── Floor type present + absent ───────────────────────────────────────────────

def test_floor_type_present():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections(**{"13": False, "14": True}))  # ALU EXTRUTION selected
    disp = _derive_body_options_display(rows, input_state, {})
    assert disp["floor_type"] == "ALU EXTRUTION FLOOR"


def test_floor_type_absent_when_neither_selected():
    rows = _standard_bom_rows()
    input_state = _input_state(_selections(**{"13": False, "14": False}))
    saved_body_vars = {"FRONT EPS": 0.06}
    disp = _derive_body_options_display(rows, input_state, saved_body_vars)
    assert disp is not None  # other data still derivable
    assert disp["floor_type"] is None


# ── Live endpoint smoke test: additive key, never 500s on a bare record ──────

def _purge(db) -> None:
    from sqlalchemy import text
    db.execute(text("DELETE FROM icb_costings.calculations WHERE result_json::text LIKE :m"),
               {"m": f"%{_MARK}%"})


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def api(app_mod):
    import uuid
    from app.database import SessionLocal, User, UserSession
    from app.deps import require_admin, require_user
    from starlette.testclient import TestClient
    sid = str(uuid.uuid4())
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        db.add(UserSession(id=sid, user_id=admin.id, role=admin.role, expires_at=None))
        db.commit()
    app_mod.app.dependency_overrides[require_user] = lambda: admin
    app_mod.app.dependency_overrides[require_admin] = lambda: admin
    with TestClient(app_mod.app) as c:
        c.headers["Cookie"] = f"session_id={sid}"
        yield c
    app_mod.app.dependency_overrides.pop(require_user, None)
    app_mod.app.dependency_overrides.pop(require_admin, None)
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()


def test_get_calculation_exposes_body_options_display_key_and_degrades_to_null(api):
    from app.database import CalculationRecord, SessionLocal
    with SessionLocal() as db:
        rec = CalculationRecord(
            trailer_type_id=None, dimensions_json="{}",
            result_json=f'{{"items": [], "marker": "{_MARK}"}}', status="pending",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        rec_id = rec.id

    got = api.get(f"/api/calculations/{rec_id}").json()
    assert "body_options_display" in got
    assert got["body_options_display"] is None

    with SessionLocal() as db:
        db.query(CalculationRecord).filter_by(id=rec_id).delete()
        db.commit()
