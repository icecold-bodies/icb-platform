"""v1.59.2 (BA ruling 7a) — rule display tidy: DB-first chips + plain-English badges.

A. Trailer Designer chips read the DATABASE rule (what the engine prices), never
   the draft's itemRules copy; a copy that disagrees raises a "draft differs"
   marker instead of being shown; a condition the branch does not offer reads
   "kept", with the v1.59.1 rule editor's own words in its tooltip.
B. The calculator's struck-through badge on a line a RULE switched off reads plain
   English ("not used with SRD PU"), built by mechanism from the stored rule and
   the option names the calc was sent with. The engine's excluded_reason stays in
   the API as it is and rides the tooltip. Display only.

This module pins, under node, the calculator's and the Designer's OWN helpers
(the five badge rows of the ruling, the fallbacks, the draft/DB comparison), and
— against the live test DB — that the calculator's evaluation matches the
engine's on every line of a fixture body (the parity test), plus the additive
bom_conditions field on GET /api/trailers/{id}/bom. The rendered chips and
badges are proven in a real browser by
tests/journeys/test_rule_display_tidy_journey.py.

House pattern: live test DB, marker rows 'J1592RD*', purge on both sides.
"""
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
CALC_JS = APP / "static" / "js" / "calculator.js"
DESIGNER = APP / "templates" / "admin_visual_configurator_settings.html"

_MARK = "J1592RD"


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


def _node(script: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH")
    # The script goes through a FILE, not `node -e`: the parity data is large and a
    # Windows command line caps at 32K characters. Encoding pinned both ways: the
    # badge text carries "·" / "—", which a Windows runner would read as cp1252.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(script)
    try:
        res = subprocess.run([node, fh.name], capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
    finally:
        os.unlink(fh.name)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


_CALC_FUNCS = ("escHtml", "parseStoredRule", "calcOnOptionNames", "conditionBadgeText",
               "excludedBadgeHtml")


def _calc_harness(body: str, data) -> object:
    src = CALC_JS.read_text(encoding="utf-8")
    script = "\n".join([_const_line(src, "RULE_OUT_FALLBACK")]
                       + [_js_function(src, f) for f in _CALC_FUNCS]
                       + [f"const DATA = {json.dumps(data)};", body])
    return _node(script)


def _badge_texts(cases: dict) -> dict:
    """{name: [raw bom_conditions, [option names ON]]} -> {name: text | None}."""
    return _calc_harness(
        "const out = {};"
        "for (const [k, [raw, on]] of Object.entries(DATA))"
        "  out[k] = conditionBadgeText(parseStoredRule(raw), new Set(on));"
        "process.stdout.write(JSON.stringify(out));", cases)


# ── B. The badge text, by mechanism (the ruling's five rows + the edges) ─────────

RF_RULE = json.dumps([{"option": "SRD EPS", "equals": "N", "option_id": 2536},
                      {"option": "SRD PU", "equals": "N", "option_id": 2537}])


def test_the_rulings_five_rows():
    out = _badge_texts({
        # include, X = N, X is on
        "include_N_on": [json.dumps([{"option": "SRD PU", "equals": "N"}]), ["SRD PU"]],
        # include, X = Y, X is off
        "include_Y_off": [json.dumps([{"option": "FRONT EPS", "equals": "Y"}]), []],
        # exclude, all matched (one, then several)
        "exclude_one": [json.dumps({"mode": "exclude",
                                    "all": [{"option": "BAKERY", "equals": "Y"}]}), ["BAKERY"]],
        "exclude_two": [json.dumps({"mode": "exclude",
                                    "all": [{"option": "BAKERY", "equals": "Y"},
                                            {"option": "CHILLER", "equals": "Y"}]}),
                        ["BAKERY", "CHILLER"]],
        # always_exclude
        "always": [json.dumps({"mode": "always_exclude"}), []],
    })
    assert out == {
        "include_N_on": "not used with SRD PU",
        "include_Y_off": "needs FRONT EPS",
        "exclude_one": "not used with BAKERY",
        "exclude_two": "not used with BAKERY, CHILLER",
        "always": "always left out",
    }


def test_the_rear_frame_rule_names_the_door_side_that_is_on():
    """The Manifest A shape on every REAR FRAME line: include SRD EPS = N AND SRD PU = N."""
    out = _badge_texts({
        "srd_pu_quote": [RF_RULE, ["SRD PU", "FRONT PU", "SIDES PU"]],
        "srd_eps_quote": [RF_RULE, ["SRD EPS"]],
        "drd_quote": [RF_RULE, ["DRD PU"]],          # the rule holds: nothing to say
    })
    assert out == {"srd_pu_quote": "not used with SRD PU",
                   "srd_eps_quote": "not used with SRD EPS",
                   "drd_quote": None}


def test_edges_follow_the_engine_loop():
    out = _badge_texts({
        # every failing condition of an include rule is a reason, in both words
        "include_mixed": [json.dumps([{"option": "A", "equals": "Y"},
                                      {"option": "B", "equals": "N"}]), ["B"]],
        # an exclude rule's matched "= N" condition means the option is OFF
        "exclude_N_matched": [json.dumps({"mode": "exclude",
                                          "all": [{"option": "FLOOR PU", "equals": "N"}]}), []],
        # equals defaults to Y and is case-insensitive, as in calculator.py
        "equals_default": [json.dumps([{"option": "X"}]), []],
        "equals_lower": [json.dumps([{"option": "X", "equals": "n"}]), ["X"]],
        # the rule, evaluated here, would NOT exclude -> None (the caller falls back)
        "include_holds": [json.dumps([{"option": "X", "equals": "Y"}]), ["X"]],
        "exclude_partial": [json.dumps({"mode": "exclude",
                                        "all": [{"option": "A", "equals": "Y"},
                                                {"option": "B", "equals": "Y"}]}), ["A"]],
        # no rule / no conditions / malformed -> None
        "no_rule": [None, []],
        "empty_list": ["[]", []],
        "empty_exclude": [json.dumps({"mode": "exclude", "all": []}), []],
        "malformed": ["{not json", []],
        # a failing condition with no option name cannot be named -> None
        "nameless": [json.dumps([{"option": "", "equals": "Y"}]), []],
    })
    assert out == {
        "include_mixed": "not used with B · needs A",
        "exclude_N_matched": "needs FLOOR PU",
        "equals_default": "needs X",
        "equals_lower": "not used with X",
        "include_holds": None,
        "exclude_partial": None,
        "no_rule": None,
        "empty_list": None,
        "empty_exclude": None,
        "malformed": None,
        "nameless": None,
    }


def _badges(cases: dict) -> dict:
    """{name: [item, bRef, [names ON]]} -> {name: badge html}."""
    return _calc_harness(
        "const out = {};"
        "for (const [k, [it, ref, on]] of Object.entries(DATA))"
        "  out[k] = excludedBadgeHtml(it, ref, new Set(on));"
        "process.stdout.write(JSON.stringify(out));", cases)


def test_badge_html_plain_text_with_the_engine_words_in_the_tooltip():
    cond = {"excluded": True, "excluded_by": "condition", "excluded_reason": "SRD PU = N"}
    out = _badges({
        "rule": [cond, {"bom_conditions": RF_RULE}, ["SRD PU"]],
        "no_ref": [cond, None, ["SRD PU"]],
        "stale": [cond, {"bom_conditions": RF_RULE}, []],       # the stored rule now holds
        "user": [{"excluded": True, "excluded_by": "user",
                  "excluded_reason": "Excluded by user"}, None, []],
        "optional": [{"excluded": True, "excluded_by": "optional_section",
                      "excluded_reason": "Optional section not enabled"}, None, []],
        # an old payload with no machine reason keeps the old badge
        "legacy": [{"excluded": True, "excluded_reason": "SRD PU = N"},
                   {"bom_conditions": RF_RULE}, ["SRD PU"]],
        "escaped": [{"excluded": True, "excluded_by": "condition", "excluded_reason": "<b> = N"},
                    {"bom_conditions": json.dumps([{"option": "<b>", "equals": "N"}])}, ["<b>"]],
    })
    assert 'class="bom-rule-out" title="Rule: SRD PU = N"' in out["rule"]
    assert out["rule"].endswith(">not used with SRD PU</span>")
    # No stored rule to read, or one that no longer excludes: plain, never engine words.
    for k in ("no_ref", "stale"):
        assert out[k].endswith(">not used with the options chosen</span>"), k
        assert 'title="Rule: SRD PU = N"' in out[k], k
    # User / optional-section exclusions are unchanged.
    assert out["user"].endswith(">excluded · Excluded by user</span>")
    assert out["optional"].endswith(">excluded · Optional section not enabled</span>")
    assert "bom-rule-out" not in out["user"] + out["optional"] + out["legacy"]
    assert out["legacy"].endswith(">excluded · SRD PU = N</span>")
    # Option names are escaped in both the text and the tooltip.
    assert "<b>" not in out["escaped"] and "not used with &lt;b&gt;" in out["escaped"]
    assert 'title="Rule: &lt;b&gt; = N"' in out["escaped"]


def test_on_names_mirror_the_engine_selection_set():
    out = _calc_harness(
        "const res = [...calcOnOptionNames(DATA.payload, DATA.bom)].sort();"
        "const none = [...calcOnOptionNames(null, DATA.bom)];"
        "process.stdout.write(JSON.stringify({res, none}));",
        {"payload": {"body_option_selections": {"1": True, "2": False, "3": True},
                     "flag_overrides": {"FLAG A": True, "FLAG B": False}},
         "bom": [{"id": 1, "is_body_option": True, "material_name": "SRD PU"},
                 {"id": 2, "is_body_option": True, "material_name": "DRD PU"},
                 # selected, but not a master: the engine ignores it too
                 {"id": 3, "is_body_option": False, "material_name": "RAIL"}]})
    assert out == {"res": ["FLAG A", "SRD PU"], "none": []}


def test_render_reads_the_request_the_result_came_from():
    """Source pins: the badge evaluates against the payload that PRODUCED the rendered
    result (a newer lastCalcPayload may already be in flight), and it never keys off
    a section or flag NAME."""
    src = CALC_JS.read_text(encoding="utf-8")
    assert "const _onNames = calcOnOptionNames(lastResultPayload, bomData);" in src
    assert "? excludedBadgeHtml(it, bRef, _onNames)" in src
    assert "lastResultPayload = _sent;" in src                    # /api/calculate
    assert "lastResultPayload = _pendingApproveBase;" in src      # /api/approve
    body = _js_function(src, "conditionBadgeText") + _js_function(src, "excludedBadgeHtml")
    assert "REAR" not in body and "SRD" not in body


# ── B. Parity with the engine, on a live fixture body ───────────────────────────

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
    """A configurator-v2 marker body: three masters (SRD EPS, SRD PU, FRONT EPS), one
    flag-only name (BAKERY, sent through flag_overrides) and one line per rule shape."""
    from app.database import BillOfMaterial, BOMSection, Material, SessionLocal, TrailerType
    n = lambda s: f"{_MARK} {s}"                                   # noqa: E731
    with SessionLocal() as db:
        _purge(db)
        body = TrailerType(name=n("BODY"), is_active=True, configurator_v2=True)
        sec = BOMSection(name=n("SECTION"), sort_order=9601)
        mats = {k: Material(name=n(k), unit_of_measure="each", price_per_unit=p)
                for k, p in (("SRD EPS", 0.0), ("SRD PU", 0.0), ("FRONT EPS", 0.0),
                             ("WIDGET", 10.0))}
        db.add_all([body, sec, *mats.values()])
        db.flush()

        def bom(mat, conditions=None, master=False):
            r = BillOfMaterial(trailer_type_id=body.id, material_id=mat.id, formula_expression="1",
                               is_body_option=master,
                               bom_section=("BODY OPTIONS" if master else sec.name),
                               bom_section_id=(None if master else sec.id),
                               bom_conditions=conditions)
            db.add(r)
            db.flush()
            return r

        masters = {k: bom(mats[k], master=True) for k in ("SRD EPS", "SRD PU", "FRONT EPS")}
        c = lambda opt, eq: {"option": n(opt), "equals": eq}        # noqa: E731
        rules = {
            "rear_frame": json.dumps([{**c("SRD EPS", "N"), "option_id": masters["SRD EPS"].id},
                                      {**c("SRD PU", "N"), "option_id": masters["SRD PU"].id}]),
            "srd_line": json.dumps([c("SRD PU", "Y")]),
            "mixed_include": json.dumps([c("SRD PU", "Y"), c("FRONT EPS", "N")]),
            "exclude_bakery": json.dumps({"mode": "exclude", "all": [c("BAKERY", "Y")]}),
            "exclude_two": json.dumps({"mode": "exclude",
                                       "all": [c("BAKERY", "Y"), c("FRONT EPS", "Y")]}),
            "exclude_not_srd": json.dumps({"mode": "exclude", "all": [c("SRD PU", "N")]}),
            "always": json.dumps({"mode": "always_exclude"}),
            "plain": None,
        }
        lines = {k: bom(mats["WIDGET"], v).id for k, v in rules.items()}
        db.commit()
        ids = {"body": body.id, "masters": {k: m.id for k, m in masters.items()},
               "lines": lines, "rules": rules, "bakery": n("BAKERY")}
    yield ids
    from app.database import SessionLocal as SL
    with SL() as db:
        _purge(db)


def _get_bom(tt_id: int) -> list:
    from app.database import SessionLocal
    from app.routers.trailers import get_bom
    with SessionLocal() as db:
        return asyncio.run(get_bom(tt_id, db))


def test_get_bom_carries_the_stored_rule_verbatim(staged):
    rows = {r["id"]: r for r in _get_bom(staged["body"])}
    for k, lid in staged["lines"].items():
        assert rows[lid]["bom_conditions"] == staged["rules"][k], k   # the exact stored text
    for mid in staged["masters"].values():
        assert rows[mid]["bom_conditions"] is None


SCENARIOS = {
    # name: (masters ON, BAKERY flag ON)
    "nothing_on": ((), False),
    "srd_pu": (("SRD PU",), False),
    "srd_eps_bakery": (("SRD EPS",), True),
    "srd_pu_front_bakery": (("SRD PU", "FRONT EPS"), True),
}


def test_badge_evaluation_matches_the_engine_on_every_line(staged):
    """For every scenario: the engine excludes a line BY A CONDITION exactly when the
    calculator's own evaluation (GET /bom's stored rule + the request's names) finds a
    reason; and for an include rule, the condition the engine reports is among the
    ones the badge names."""
    from app.database import BillOfMaterial, SessionLocal, TrailerType
    from app.routers.calculator import _build_bom_items
    from app.services import _bom_load_options
    bom = _get_bom(staged["body"])
    cases, truth = {}, {}
    with SessionLocal() as db:
        rows = (db.query(BillOfMaterial).filter_by(trailer_type_id=staged["body"])
                .options(*_bom_load_options()).all())
        body = db.get(TrailerType, staged["body"])
        for name, (on, bakery) in SCENARIOS.items():
            sel = {str(mid): (k in on) for k, mid in staged["masters"].items()}
            fo = {staged["bakery"]: bakery}
            payload = {"body_option_selections": sel, "flag_overrides": fo}
            items = _build_bom_items(rows, {"length": 1.0, "width": 1.0, "height": 1.0}, {}, sel,
                                     db, trailer=body, flag_overrides=fo)
            by_id = {it["bom_id"]: it for it in items}
            for k, lid in staged["lines"].items():
                ref = next(r for r in bom if r["id"] == lid)
                cases[f"{name}:{k}"] = [payload, ref["bom_conditions"]]
                truth[f"{name}:{k}"] = by_id[lid]
    out = _calc_harness(
        "const out = {};"
        "for (const [k, [payload, raw]] of Object.entries(DATA.cases))"
        "  out[k] = conditionBadgeText(parseStoredRule(raw), calcOnOptionNames(payload, DATA.bom));"
        "process.stdout.write(JSON.stringify(out));", {"cases": cases, "bom": bom})
    checked = 0
    for key, it in truth.items():
        by_rule = it["excluded_by"] == "condition"
        assert (out[key] is not None) == by_rule, (key, it["excluded_reason"], out[key])
        reason = it["excluded_reason"] or ""
        if by_rule and " = " in reason and not reason.startswith("["):
            assert reason.split(" = ")[0] in out[key], (key, reason, out[key])
        checked += by_rule
    assert checked >= 10, checked          # the scenarios really exercise the rule lines
    # Spot-check the words on the two cases the ruling names.
    assert out["srd_pu:rear_frame"] == f"not used with {_MARK} SRD PU"
    assert out["nothing_on:srd_line"] == f"needs {_MARK} SRD PU"


# ── A. Designer chips: the database rule, a marker when the draft differs ───────

_DESIGNER_FUNCS = ("ruleChipText", "dbItemRule", "ruleKey", "draftRuleDiffers", "ruleText",
                   "draftDiffersTip", "keptChipText", "keptChipTip")


def _designer(body: str, data) -> object:
    src = DESIGNER.read_text(encoding="utf-8")
    script = "\n".join([_js_function(src, f) for f in _DESIGNER_FUNCS]
                       + [f"const DATA = {json.dumps(data)};", body])
    return _node(script)


def _item(conditions, mode="include", item_id=7):
    return {"id": item_id, "conditions": conditions, "conditionMode": mode}


def test_draft_copy_is_flagged_only_when_it_disagrees():
    srd = [{"option": "SRD EPS", "equals": "N", "option_id": 1},
           {"option": "SRD PU", "equals": "N", "option_id": 2}]
    cases = {
        "no_copy": [{"itemRules": {}}, _item(srd)],
        # same conditions, other order, no option_id, lower-case equals: the same rule
        "same_rule": [{"itemRules": {"7": {"mode": "include", "conditions": [
            {"option": "SRD PU", "equals": "n"}, {"option": "SRD EPS", "equals": "N"}]}}},
                      _item(srd)],
        # the substitution signature: the draft holds FRONT EPS = N
        "substituted": [{"itemRules": {"7": {"mode": "include", "conditions": [
            {"option": "FRONT EPS", "equals": "N"}]}}}, _item(srd)],
        "mode_differs": [{"itemRules": {"7": {"mode": "exclude", "conditions": srd}}}, _item(srd)],
        "always_out_copy": [{"itemRules": {"7": {"mode": "always_exclude", "conditions": []}}},
                            _item([])],
        # an empty include copy and no DB rule both mean "always included"
        "empty_copy": [{"itemRules": {"7": {"mode": "include", "conditions": []}}}, _item([])],
    }
    out = _designer(
        "const out = {};"
        "for (const [k, [draft, item]] of Object.entries(DATA)) {"
        "  const d = draftRuleDiffers(draft, item);"
        "  out[k] = d ? draftDiffersTip(d) : null; }"
        "process.stdout.write(JSON.stringify(out));", cases)
    assert out["no_copy"] is None and out["same_rule"] is None and out["empty_copy"] is None
    assert out["substituted"] == ("The configurator draft holds a different copy of this rule "
                                  "(when FRONT EPS = N). The costing uses the rule shown here, "
                                  "from the database.")
    assert "(exclude when SRD EPS = N and SRD PU = N)" in out["mode_differs"]
    assert "(always excluded)" in out["always_out_copy"]


def test_chips_show_the_database_rule_and_word_kept_conditions_as_the_editor_does():
    out = _designer(
        "process.stdout.write(JSON.stringify({"
        "  rule: dbItemRule(DATA.item),"
        "  keptN: keptChipText({mode: 'include'}, {option: 'SRD PU', equals: 'N'}),"
        "  keptY: keptChipText({mode: 'exclude'}, {option: 'BAKERY', equals: 'Y'}),"
        "  tipN: keptChipTip({option: 'SRD PU', equals: 'N'}),"
        "  tipY: keptChipTip({option: 'BAKERY', equals: 'Y'}),"
        "  none: dbItemRule({id: 1}) }));",
        {"item": _item([{"option": "SRD PU", "equals": "N"}], "exclude")})
    assert out["rule"] == {"conditions": [{"option": "SRD PU", "equals": "N"}], "mode": "exclude"}
    assert out["none"] == {"conditions": [], "mode": "include"}
    # The chip: the card's own chip plus the editor's word (the full sentence clipped).
    assert out["keptN"] == "when SRD PU = N · kept"
    assert out["keptY"] == "exclude when BAKERY = Y · kept"
    # The tooltip: the v1.59.1 rule editor's exact row text and note.
    assert out["tipN"] == ("SRD PU is not selected — kept (outside this branch). This condition "
                           "uses a flag from another part of the tree. It still applies; edit it "
                           "with the tool or ask the administrator.")
    assert out["tipY"].startswith("BAKERY is selected — kept (outside this branch). ")
    editor = DESIGNER.read_text(encoding="utf-8")
    assert ("is {condition.equals === 'N' ? 'not selected' : 'selected'} — kept (outside this branch)"
            in editor)                                      # the editor still says the same
    assert ("This condition uses a flag from another part of the tree. It still applies; edit it "
            "with the tool or ask the administrator.") in editor


def test_both_chip_sites_read_the_database_rule():
    """Source pins: the catalog card and the config preview never read the draft's
    copy for display; the draft is consulted only for the "draft differs" marker."""
    src = DESIGNER.read_text(encoding="utf-8")
    assert src.count("const rule = dbItemRule(item);") == 2
    assert src.count("const differs = draftRuleDiffers(draft, item);") == 2
    assert "const rule = itemRuleState(draft, item.id, item);" not in src
