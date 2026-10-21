"""RT8 — the prod frozen-quote check reads only what it needs (G4), pinned.

ops/prod-rt8/rt8_frozen_check.py runs on prod by Michael's paste and reports quote numbers, months, bodies and the
stored lines' figures. These tests pin its allow-lists: no column or key that could carry a person is on them, its
SQL selects only those columns, a record carrying personal keys yields none of them to the check, and the import-
time guard refuses a list that names one (the negative control, run against a tampered copy of the lists).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[2] / "ops" / "prod-rt8" / "rt8_frozen_check.py"
PERSONAL_COLUMNS = {"customer_id", "user_id", "sales_rep_user_id", "contact_id", "contact_name", "contact_email",
                    "contact_telephone", "contact_role", "end_user_id", "end_user_company", "end_user_contact_name",
                    "end_user_contact_email", "end_user_contact_telephone", "approved_by_user_id", "deleted_by",
                    "decline_reason", "pre_job_signoff_sales_by", "planning_acknowledged_by"}


@pytest.fixture(scope="module")
def kit():
    spec = importlib.util.spec_from_file_location("rt8_frozen_check", KIT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_allow_lists_name_nothing_personal(kit):
    for lst in (kit.COLUMNS, kit.JOIN_COLUMNS, kit.MATERIAL_COLUMNS, kit.TOP_KEYS, kit.ITEM_KEYS, kit.CHASSIS_KEYS,
                kit.INPUT_STATE_KEYS, kit.REPAIR_LINE_KEYS):
        assert not (set(lst) & PERSONAL_COLUMNS), lst
    kit.assert_allowlist_clean(kit.COLUMNS, kit.TOP_KEYS, kit.ITEM_KEYS, kit.REPAIR_LINE_KEYS)   # the import-time guard, again


def test_the_sql_selects_only_the_allow_listed_columns(kit):
    select_list = kit.SQL.split(" from ")[0]
    cols = re.findall(r"\bc\.([a-z_]+)", kit.SQL)
    assert set(cols) <= set(kit.COLUMNS), set(cols) - set(kit.COLUMNS)
    joined = re.findall(r"\bt\.([a-z_]+)", select_list)        # the join key (t.id) is not a selected column
    assert set(joined) <= set(kit.JOIN_COLUMNS)
    assert "customers" not in kit.SQL and "users" not in kit.SQL and "contact" not in kit.SQL
    assert re.search(r"\bfrom materials\b", kit.SQL_MATERIALS) and "name" not in kit.SQL_MATERIALS
    assert "deleted_at is null" in kit.SQL and "'pending'" in kit.SQL


def test_a_record_carrying_personal_keys_yields_none_of_them(kit):
    raw = {"items": [{"bom_id": 1, "material": "PLY", "category": "ROOF", "formula": "1", "quantity": 1,
                      "unit_price": 2, "waste_pct": 0, "section_multiplier": 1, "line_cost": 2, "excluded": False,
                      "customer_name": "LEAK A"}],
           "category_totals": {"ROOF": 2}, "grand_total": 2, "body_variables": {}, "global_variables": {},
           "customer_name": "LEAK B", "contact_email": "leak@example.com", "trailer_name": "X",
           "input_state": {"repair_lines": [{"kind": "stock", "key": "s1", "material_id": 5, "unit_price": 1, "qty": 1,
                                             "description": "LEAK C", "notes": "LEAK D"}],
                           "ui_snapshot": {"body_option_selections": {"1": True}},
                           "icb_contact_name": "LEAK E", "vehicle_registration": "LEAK F"}}
    import json
    dims, data = kit.read_record(json.dumps({"length": 6, "customer": "LEAK G"}), json.dumps(raw))
    blob = json.dumps({"dims": dims, "data": data})
    assert "LEAK" not in blob and "example.com" not in blob
    assert data["input_state"]["ui_snapshot"] is True          # presence only
    assert data["input_state"]["repair_lines"] == [{"kind": "stock", "key": "s1", "material_id": 5, "unit_price": 1, "qty": 1}]
    assert dims == {"length": 6, "width": None, "height": None, "floor_thickness": None, "panel_thickness": None,
                    "insulation_thickness": None, "num_doors": None, "num_axles": None}


def test_the_import_guard_refuses_a_tampered_allow_list(kit):
    """Negative control: add one personal-looking key to a list and the guard the module runs at import refuses."""
    for bad in ("customer_name", "contact_email", "sales_rep_user_id", "description", "notes", "vehicle_registration"):
        with pytest.raises(RuntimeError, match="personal-looking"):
            kit.assert_allowlist_clean(tuple(kit.TOP_KEYS) + (bad,))
    kit.assert_allowlist_clean(("material", "name", "quantity"))     # a product's or body type's name is not a person


def test_the_replay_check_matches_the_frozen_engine_on_a_saved_shape(kit):
    """The kit's replay is the service's core without a DB: a stored result replays to itself, and a moved price or
    size is caught (the check that was proven on dev in RT8_RETURN_1 §2)."""
    from app.formula_engine import calculate_bom
    items = [{"bom_id": 1, "category": "ROOF", "material": "PLY", "formula": "length*width", "quantity": 20.28,
              "unit_price": 86.58, "waste_pct": 0, "section_multiplier": 1.0, "line_cost": 1755.84, "excluded": False},
             {"bom_id": 2, "category": "ROOF", "material": "PU", "formula": "length*width*{roof_factor}", "quantity": 2.028,
              "unit_price": 5581.0, "waste_pct": 0, "section_multiplier": 1.0, "line_cost": 11318.27, "excluded": False}]
    data = {"items": items, "category_totals": {"ROOF": 13074.11}, "grand_total": 13074.11,
            "body_variables": {}, "global_variables": {"ROOF_FACTOR": 0.1}}
    dims = {"length": 7.8, "width": 2.6, "height": 2.56}
    ok = kit.replay(data, dims, calculate_bom)
    assert ok["pass"] and ok["bad_lines"] == 0 and ok["library"] == "none", ok
    worse = {**data, "items": [dict(items[0], unit_price=86.59), items[1]]}
    assert not kit.replay(worse, dims, calculate_bom)["pass"]
    assert not kit.replay(data, {**dims, "length": 7.801}, calculate_bom)["pass"]
    lib = {**data, "global_variables": {}, "formula_library_resolved": {"roof_factor": 0.1}}
    r = kit.replay(lib, dims, calculate_bom)
    assert r["pass"] and r["library"] == "values" and r["library_tokens"] == ["roof_factor"]


def test_the_totals_are_compared_the_engines_way(kit):
    """The engine sums the UNROUNDED line costs into category_totals and rounds once; each stored line carries its
    cost rounded to the cent. On 21 Oct every one of prod's 69 pending bodies replayed line for line yet read FAIL,
    because the kit re-summed the rounded lines (seven lines of 0.8667 already differ by two cents). The kit now
    takes the engine's own totals, free-hand lines replayed through the engine too, and adds the chassis subtotal
    the way the router does. Negative controls: a stored category total or grand total one cent off still fails,
    and a moved price still fails on its line."""
    from app.formula_engine import calculate_bom
    dims = {"length": 2.6, "width": 2.6, "height": 2.56}
    bom = [{"bom_id": i, "material_name": f"M{i}", "category_name": "ROOF", "formula_expression": "length/3",
            "waste_percentage": 0, "price_per_unit": 1.0, "unit_of_measure": "m", "material_code": "",
            "section_multiplier": 1.0, "excluded": False} for i in range(1, 8)]
    bom.append({"bom_id": None, "free_hand": True, "free_hand_key": "fh1", "free_hand_kind": "free_hand",
                "material_name": "typed", "category_name": "EXTRAS", "quantity": 3.0, "price_per_unit": 1.2345,
                "total_only": False, "unit_of_measure": "", "material_code": "", "waste_percentage": 0,
                "section_multiplier": 1.0, "excluded": False})
    saved = calculate_bom(bom, dims, {}, {}, {})                 # what /api/approve stores
    roof_rounded = round(sum(it["line_cost"] for it in saved["items"] if it["category"] == "ROOF"), 2)
    assert roof_rounded != saved["category_totals"]["ROOF"], "the fixture must carry a real rounding gap"
    data = {"items": saved["items"], "category_totals": saved["category_totals"],
            "materials_total": saved["grand_total"], "chassis": {"subtotal": 1500.0},
            "grand_total": round(saved["grand_total"] + 1500.0, 2), "body_variables": {}, "global_variables": {}}
    r = kit.replay(data, dims, calculate_bom)
    assert r["pass"] and r["bad_lines"] == 0 and r["cat_ok"] and r["gt_ok"], r
    off_cat = {**data, "category_totals": {**data["category_totals"],
                                           "ROOF": round(data["category_totals"]["ROOF"] + 0.01, 2)}}
    assert not kit.replay(off_cat, dims, calculate_bom)["pass"]
    off_gt = {**data, "grand_total": round(data["grand_total"] + 0.01, 2)}
    assert not kit.replay(off_gt, dims, calculate_bom)["pass"]
    moved = {**data, "items": [dict(data["items"][0], unit_price=1.01)] + data["items"][1:]}
    assert kit.replay(moved, dims, calculate_bom)["bad_lines"] == 1
