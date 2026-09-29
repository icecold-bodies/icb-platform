"""v1.59.1 — a section whose rules switch every line off reads NOT SELECTED.

Michael (28 Sep): a section that is zeroed because every one of its lines failed a
rule condition (the SRD rear-frame rule is the first one) must not read R0.00 on
the costing: sales users would wonder why a section is free. The header says
NOT SELECTED.

Ratified rule (by mechanism, never by section name): a NON-optional section with
at least one line, where EVERY line is excluded by a CONDITION — not by the user,
not because an optional section is off. Mixed sections keep their subtotal.
Display only: every number stays a number.

This module pins:
  * the backend's additive ``excluded_by`` field ("condition" | "user" |
    "optional_section") — the machine-readable WHY next to the display text, so
    the front end never parses ``excluded_reason``;
  * that ``excluded_by`` changes no money (totals identical with and without it)
    and is absent on included lines (a saved snapshot of them stays byte-identical);
  * the calculator's OWN ``sectionNotSelected`` predicate and label, run under
    node against the four section shapes.
The rendered header is proven in a real browser by
tests/journeys/test_section_not_selected_journey.py.

House pattern: live test DB, marker rows 'J1591NS*', purge on both sides.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
CALC_JS = APP / "static" / "js" / "calculator.js"

_MARK = "J1591NS"


# ── The front-end predicate, under node ──────────────────────────────────────

def _js_function(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth = 0
    for j in range(src.index("{", start), len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _const_line(src: str, name: str) -> str:
    return next(l for l in src.splitlines() if l.startswith(f"const {name} ="))


def _run_node(cases: dict) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    src = CALC_JS.read_text(encoding="utf-8")
    script = "\n".join([
        _const_line(src, "NOT_SELECTED_TIP"),
        _const_line(src, "NOT_SELECTED_LABEL_HTML"),
        _js_function(src, "sectionNotSelected"),
        f"const CASES = {json.dumps(cases)};",
        "const out = {};",
        "for (const [k, its] of Object.entries(CASES)) out[k] = sectionNotSelected(its);",
        "out.__label = NOT_SELECTED_LABEL_HTML;",
        "out.__tip = NOT_SELECTED_TIP;",
        "process.stdout.write(JSON.stringify(out));",
    ])
    res = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


def _line(excluded_by=None, optional=False, line_cost=0.0):
    it = {"excluded": excluded_by is not None, "section_is_optional": optional,
          "line_cost": line_cost}
    if excluded_by:
        it["excluded_by"] = excluded_by
        it["excluded_reason"] = {"condition": "SRD PU = N", "user": "Excluded by user",
                                 "optional_section": "Optional section not enabled"}[excluded_by]
    return it


def test_predicate_all_condition_excluded_reads_not_selected():
    out = _run_node({
        "all_condition": [_line("condition"), _line("condition")],
        "single_condition": [_line("condition")],
    })
    assert out["all_condition"] is True
    assert out["single_condition"] is True


def test_predicate_leaves_every_other_section_shape_alone():
    out = _run_node({
        # mixed: some lines in, some out -> keeps its subtotal
        "mixed": [_line("condition"), _line(None, line_cost=120.0)],
        # the user switched every line off -> unchanged (R0.00 stays)
        "all_user": [_line("user"), _line("user")],
        # an optional section that is off -> the v1.47 header tick owns it
        "optional_off": [_line("optional_section", optional=True)],
        # a condition-failed line inside an OPTIONAL section -> still optional's
        "optional_condition": [_line("condition", optional=True)],
        # all excluded, but not all by a condition
        "condition_plus_user": [_line("condition"), _line("user")],
        # a section with no lines never renders; the predicate still says no
        "empty": [],
        # excluded flag with no machine reason (an old payload) -> unchanged
        "legacy_no_reason": [{"excluded": True, "excluded_reason": "SRD PU = N",
                              "section_is_optional": False}],
    })
    for k in ("mixed", "all_user", "optional_off", "optional_condition",
              "condition_plus_user", "empty", "legacy_no_reason"):
        assert out[k] is False, k


def test_label_is_exact_uppercase_dim_with_plain_english_tooltip():
    out = _run_node({})
    assert ">NOT SELECTED</span>" in out["__label"]
    assert "var(--text-dim)" in out["__label"]          # muted, not red
    assert "red" not in out["__label"].lower()
    assert out["__tip"] == ("Nothing in this section is costed with the options chosen. "
                            "Click the eye to see the lines.")
    assert f'title="{out["__tip"]}"' in out["__label"]


def test_header_renders_label_in_place_of_subtotal_and_keeps_the_number():
    """Source pin: the header swaps only the RENDERED text; the section total
    it computed stays the number every other consumer reads."""
    src = CALC_JS.read_text(encoding="utf-8")
    assert "const _notSelected = sectionNotSelected(its);" in src
    assert ("const subtotalTxt = _notSelected ? '' : "
            "(hasFullCostAccess ? fmt(catTotal) : '••••');") in src
    assert "${_notSelected ? NOT_SELECTED_LABEL_HTML : ''}" in src
    # Nothing keys off a section NAME.
    body = src[src.index("const _notSelected"):src.index("const _notSelected") + 400]
    assert "REAR" not in body and "SRD" not in body


# ── Backend: the additive excluded_by field ──────────────────────────────────

def _purge(db) -> None:
    from sqlalchemy import text
    tt = "(SELECT id FROM icb_costings.trailer_types WHERE name LIKE :m)"
    db.execute(text(f"DELETE FROM icb_costings.bill_of_materials WHERE trailer_type_id IN {tt}"),
               {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.materials WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.trailer_types WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.execute(text("DELETE FROM icb_costings.bom_sections WHERE name LIKE :m"), {"m": f"{_MARK}%"})
    db.commit()


@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app):
        yield m


@pytest.fixture
def staged(app_mod):
    """A configurator-v2 marker body with one flag master (OFF) and four sections:
    RULED (every line needs the flag), MIXED (one ruled + one plain line),
    USEROUT (a plain line the user switched off) and OPTIONAL (is_optional, off)."""
    from app.database import (BillOfMaterial, BOMSection, Material, SessionLocal,
                              TrailerType)
    with SessionLocal() as db:
        _purge(db)
        body = TrailerType(name=f"{_MARK} BODY", is_active=True, configurator_v2=True)
        secs = {k: BOMSection(name=f"{_MARK} {k}", sort_order=9100 + i,
                              is_optional=(k == "OPTIONAL"))
                for i, k in enumerate(("RULED", "MIXED", "USEROUT", "OPTIONAL"))}
        flag = Material(name=f"{_MARK} FLAG", unit_of_measure="each", price_per_unit=0.0)
        widget = Material(name=f"{_MARK} WIDGET", unit_of_measure="each", price_per_unit=10.0)
        db.add_all([body, flag, widget, *secs.values()])
        db.flush()
        rule = json.dumps([{"option": flag.name, "equals": "Y"}])

        def bom(sec, conditions=None, master=False):
            r = BillOfMaterial(trailer_type_id=body.id, material_id=(flag if master else widget).id,
                               formula_expression="1", is_body_option=master,
                               bom_section=(sec.name if sec else "BODY OPTIONS"),
                               bom_section_id=(sec.id if sec else None),
                               bom_conditions=conditions)
            db.add(r)
            return r

        master = bom(None, master=True)
        ruled_a = bom(secs["RULED"], rule)
        ruled_b = bom(secs["RULED"], rule)
        mixed_ruled = bom(secs["MIXED"], rule)
        mixed_plain = bom(secs["MIXED"])
        user_out = bom(secs["USEROUT"])
        opt_line = bom(secs["OPTIONAL"])
        db.commit()
        ids = {"body": body.id, "master": master.id, "ruled_a": ruled_a.id, "ruled_b": ruled_b.id,
               "mixed_ruled": mixed_ruled.id, "mixed_plain": mixed_plain.id,
               "user_out": user_out.id, "opt_line": opt_line.id}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _items(db, ids, flag_on=False):
    from app.database import BillOfMaterial, TrailerType
    from app.routers.calculator import _build_bom_items
    from app.services import _bom_load_options
    rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=ids["body"])
            .options(*_bom_load_options()).all())
    body = db.get(TrailerType, ids["body"])
    dims = {"length": 1.0, "width": 1.0, "height": 1.0}
    sel = {str(ids["master"]): flag_on}
    return _build_bom_items(rows, dims, {}, sel, db, trailer=body,
                            user_excluded_bom_ids=[ids["user_out"]],
                            optional_sections_enabled=[])


def test_excluded_by_names_the_mechanism(staged):
    from app.database import SessionLocal
    ids = staged
    with SessionLocal() as db:
        by = {it["bom_id"]: it for it in _items(db, ids)}
    assert by[ids["ruled_a"]]["excluded_by"] == "condition"
    assert by[ids["ruled_b"]]["excluded_by"] == "condition"
    assert by[ids["mixed_ruled"]]["excluded_by"] == "condition"
    assert by[ids["mixed_plain"]]["excluded"] is False
    assert by[ids["mixed_plain"]]["excluded_by"] is None
    assert by[ids["user_out"]]["excluded_by"] == "user"
    assert by[ids["opt_line"]]["excluded_by"] == "optional_section"
    # The display text is untouched.
    assert by[ids["user_out"]]["excluded_reason"] == "Excluded by user"
    assert by[ids["opt_line"]]["excluded_reason"] == "Optional section not enabled"


def test_flag_on_brings_the_section_back(staged):
    from app.database import SessionLocal
    ids = staged
    with SessionLocal() as db:
        by = {it["bom_id"]: it for it in _items(db, ids, flag_on=True)}
    assert by[ids["ruled_a"]]["excluded"] is False and by[ids["ruled_a"]]["excluded_by"] is None


def test_excluded_by_changes_no_money_and_rides_only_on_excluded_lines(staged):
    from app.database import SessionLocal
    from app.formula_engine import calculate_bom
    ids = staged
    dims = {"length": 1.0, "width": 1.0, "height": 1.0}
    with SessionLocal() as db:
        items = _items(db, ids)
    with_field = calculate_bom(items, dims, {}, {}, {})
    without = calculate_bom([{k: v for k, v in it.items() if k != "excluded_by"} for it in items],
                            dims, {}, {}, {})
    # Every number identical.
    assert with_field["grand_total"] == without["grand_total"]
    assert with_field["category_totals"] == without["category_totals"]
    assert [i["line_cost"] for i in with_field["items"]] == [i["line_cost"] for i in without["items"]]
    # The all-condition section contributes nothing and has no totals key (it
    # never did); the mixed section keeps its real subtotal.
    assert f"{_MARK} RULED" not in with_field["category_totals"]
    assert with_field["category_totals"][f"{_MARK} MIXED"] == pytest.approx(10.0)
    # Included lines carry no excluded_by key at all: their payload is unchanged.
    for it in with_field["items"]:
        if it["excluded"]:
            assert it["excluded_by"] in ("condition", "user", "optional_section")
        else:
            assert "excluded_by" not in it
