"""RT6 — the one pure check (backend/app/services/insulation_rules.py, RT6_DISPATCH default 3): classification by
mechanism, the three ways a quote selects an insulation, Burt's two rules, and what is reported instead of passed.

  1. The listing: every insulation master on every CHILLER and FREEZER body of the committed prod snapshot (the CI
     audit's mes_snapshot/all.json — prod's master data) is classified panel x insulation, exactly as prod's
     read-only discovery found it (RT6_RETURN_1: 72 of 72), with the masters Burt's rules forbid.
  2. Every panel x insulation for both families: selected -> a breach exactly when the rule forbids it; a family
     with no rule is never blocked.
  3. The mechanisms: a ticked master, a draft-flag alias, an included line (include_all_items); a saved thickness
     with nothing selected (N9937) is not a breach; a tick keyed to a master that is not on the body selects nothing.
  4. Reported, never passed: a master naming both insulations, one whose group is not a panel, one gating the other
     insulation's line, and a name two panels share.
  5. The stored rule: all six panels, canonical, a malformed one refused; the draft offers; a saved costing's
     payload (snapshot, or what it priced).
Pure: no database.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import insulation_rules as ir

ROOT = Path(__file__).resolve().parents[2]
CHILLER = {"allowed": {p: ["EPS"] for p in ir.PANELS}}
FREEZER = {"allowed": {"FRONT": ["PU"], "SIDES": ["PU"], "ROOF": ["EPS", "PU"], "FLOOR": ["EPS", "PU"],
                       "DRD": ["PU"], "SRD": ["PU"]}}
FORBIDDEN = {"CHILLER": {(p, "PU") for p in ir.PANELS},
             "FREEZER": {("FRONT", "EPS"), ("SIDES", "EPS"), ("DRD", "EPS"), ("SRD", "EPS")}}

# prod's six chiller / freezer bodies (RT6_RETURN_1 §1): the same 12 masters each, ids as on prod
PROD_BODIES = {25: "CHILLER", 26: "CHILLER", 27: "CHILLER", 19: "FREEZER", 20: "FREEZER", 21: "FREEZER"}


# ── synthetic bodies ─────────────────────────────────────────────────────────
def body(extra=(), lines=True):
    """A body shaped like prod's: per panel an EPS and a PU master (group = the panel, INSULATION choice group) and
    one EPS / PU cost line each in the panel's section, gated by an include condition naming the master."""
    rows, nid = [], 1000
    for p in ir.PANELS:
        for ins in ir.INSULATIONS:
            mid = nid
            rows.append({"id": mid, "is_body_option": True, "body_option_group": p, "body_option_subgroup": "INSULATION",
                         "selection_group": "INSULATION", "material_name": f"{p} {ins}", "bom_section": "BODY OPTIONS",
                         "bom_conditions": None, "body_option_linked": None})
            if lines:
                rows.append({"id": mid + 500, "is_body_option": False, "body_option_group": None,
                             "body_option_subgroup": None, "selection_group": None, "material_name": ins,
                             "bom_section": p, "body_option_linked": f"{p} {ins}",
                             "bom_conditions": json.dumps([{"option": f"{p} {ins}", "equals": "Y", "option_id": mid}])})
            nid += 1
    rows.extend(extra)
    return rows


def mid_of(cls, panel, ins):
    return next(m.id for m in cls.masters if m.panel == panel and m.insulation == ins)


# ── 1. the listing over prod's master data ───────────────────────────────────
def test_every_insulation_master_on_every_chiller_and_freezer_body_is_classified_as_prod_found():
    snap = json.loads((ROOT / "backend/tests/costing_audit/mes_snapshot/all.json").read_text(encoding="utf-8"))["tables"]
    mats = {m["id"]: m["name"] for m in snap["materials"]}
    prod = json.loads((ROOT / "docs/audit/rt6_2026-10/prod/discovery_20261006-161235/discovery.json")
                      .read_text(encoding="utf-8"))["classification"]
    listing = []
    for tid, fam in PROD_BODIES.items():
        rows = [dict(r, material_name=mats.get(r["material_id"])) for r in snap["bill_of_materials"]
                if r["trailer_type_id"] == tid]
        cls = ir.classify_body(rows)
        assert cls.unclassified == [], (tid, cls.unclassified)
        got = sorted((m.id, m.name, m.panel, m.insulation) for m in cls.masters)
        assert len(got) == 12 and {(p, i) for _, _, p, i in got} == {(p, i) for p in ir.PANELS for i in ir.INSULATIONS}
        want = sorted((m["id"], m["name"], m["panel"], m["insulation"]) for m in prod[str(tid)]["masters"])
        assert got == want, f"body {tid}: the snapshot's classification is not prod's"
        rule = CHILLER if fam == "CHILLER" else FREEZER
        forb = set(ir.forbidden_choices(rule, cls)["master_ids"])
        assert {(p, i) for mid, _, p, i in got if mid in forb} == FORBIDDEN[fam]
        listing += [f"{fam} #{tid} {n:<10} -> {p} x {i}{'  FORBIDDEN' if mid in forb else ''}" for mid, n, p, i in got]
    assert len(listing) == 72
    print("\n".join(listing))       # the listing the dispatch asks for (pytest -s shows it)


# ── 2. every panel x insulation, both families ───────────────────────────────
@pytest.mark.parametrize("fam,rule", [("CHILLER", CHILLER), ("FREEZER", FREEZER)])
@pytest.mark.parametrize("panel", ir.PANELS)
@pytest.mark.parametrize("ins", ir.INSULATIONS)
def test_a_selected_insulation_breaches_exactly_when_the_family_forbids_it(fam, rule, panel, ins):
    cls = ir.classify_body(body())
    got = ir.breaches(rule, cls, {"body_option_selections": {str(mid_of(cls, panel, ins)): True}})
    if (panel, ins) in FORBIDDEN[fam]:
        assert [(b.panel, b.insulation, b.via) for b in got] == [(panel, ins, "selection")]
        assert panel in got[0].as_dict()["message"] or panel in ("DRD", "SRD")
    else:
        assert got == []


@pytest.mark.parametrize("rule", [None, "", {}])
def test_a_family_with_no_rule_is_never_blocked(rule):
    cls = ir.classify_body(body())
    every = {str(m.id): True for m in cls.masters}
    assert ir.breaches(rule, cls, {"body_option_selections": every, "flag_overrides": {n: True for n in cls.by_name}}) == []
    assert ir.breaches(rule, cls, {"include_all_items": True}) == []
    assert ir.forbidden_choices(rule, cls) == {"master_ids": [], "names": []}


# ── 3. the mechanisms ────────────────────────────────────────────────────────
def test_a_draft_flag_alias_selects_the_insulation_it_names():
    cls = ir.classify_body(body())
    got = ir.breaches(FREEZER, cls, {"flag_overrides": {"SIDES EPS": True, "ROOF EPS": True, "FRONT EPS": False}})
    assert [(b.panel, b.insulation, b.via, b.ref) for b in got] == [("SIDES", "EPS", "flag", "SIDES EPS")]


def test_include_all_items_selects_every_included_insulation_line():
    cls = ir.classify_body(body())
    got = ir.breaches(CHILLER, cls, {"include_all_items": True})
    assert {(b.panel, b.insulation, b.via) for b in got} == {(p, "PU", "line") for p in ir.PANELS}
    pu_lines = [lid for lid, (p, i, _s) in cls.lines.items() if i == "PU"]
    assert ir.breaches(CHILLER, cls, {"include_all_items": True, "user_excluded_bom_ids": pu_lines}) == []
    assert ir.breaches(CHILLER, cls, {"include_all_items": True, "excluded_categories": list(ir.PANELS)}) == []


def test_a_saved_thickness_with_nothing_selected_is_not_a_breach_n9937():
    cls = ir.classify_body(body())
    eps_only = {str(mid_of(cls, p, "EPS")): True for p in ir.PANELS}
    payload = {"body_option_selections": {**eps_only, **{str(mid_of(cls, p, "PU")): False for p in ir.PANELS}},
               "body_variable_overrides": {"FRONT PU": 0.06, "SIDES PU": 0.06, "DRD PU": 0.06}}
    assert ir.breaches(CHILLER, cls, payload) == []


def test_a_tick_keyed_to_a_master_that_is_not_on_this_body_selects_nothing():
    # N9937's snapshot carries FREEZER MEDIUM's master ids (2533 ...): the engine ignores them, so does the check
    cls = ir.classify_body(body())
    assert ir.breaches(CHILLER, cls, {"body_option_selections": {"2533": True, "2539": True}}) == []


def test_an_always_excluded_line_still_leaves_the_selection_a_breach():
    rows = body()
    for r in rows:      # prod's freezer FRONT / SIDES / DRD / SRD EPS lines: always_exclude, tied by the legacy link
        if not r["is_body_option"] and r["material_name"] == "EPS" and r["bom_section"] in ("FRONT", "SIDES", "DRD", "SRD"):
            r["bom_conditions"] = json.dumps({"mode": "always_exclude"})
    cls = ir.classify_body(rows)
    m = next(x for x in cls.masters if x.name == "SIDES EPS")
    assert (m.panel, m.insulation) == ("SIDES", "EPS") and "legacy link only" in m.how
    got = ir.breaches(FREEZER, cls, {"body_option_selections": {str(m.id): True}})
    assert [(b.panel, b.insulation) for b in got] == [("SIDES", "EPS")]      # selected, not priced: still a breach


# ── 4. reported, never passed ────────────────────────────────────────────────
def _master(mid, name, group, sub="INSULATION"):
    return {"id": mid, "is_body_option": True, "body_option_group": group, "body_option_subgroup": sub,
            "selection_group": sub, "material_name": name, "bom_section": "BODY OPTIONS", "bom_conditions": None,
            "body_option_linked": None}


@pytest.mark.parametrize("row,why", [
    (_master(1, "SIDES EPS PU", "SIDES"), "both EPS and PU"),
    (_master(2, "SIDE DOOR EPS", "SIDE DOOR"), "not a panel"),
    (_master(3, "FRONT EPS", "SIDES"), "another panel"),
    (_master(4, "SIDES INSULATION", "SIDES"), "names no insulation"),
])
def test_an_insulation_master_the_check_cannot_read_is_reported(row, why):
    cls = ir.classify_body([row])
    assert cls.unclassified and why in cls.unclassified[0]["reason"]
    assert row["id"] not in cls.by_master_id            # never classified, so never silently allowed or greyed


def test_a_master_gating_the_other_insulations_line_is_reported():
    rows = [_master(10, "ROOF EPS", "ROOF"),
            {"id": 11, "is_body_option": False, "material_name": "PU", "bom_section": "ROOF", "body_option_linked": None,
             "bom_conditions": json.dumps([{"option": "ROOF EPS", "equals": "Y", "option_id": 10}])}]
    cls = ir.classify_body(rows)
    assert cls.unclassified and "gates a PU cost line" in cls.unclassified[0]["reason"]


def test_a_name_that_selects_two_panels_is_reported_meat_36():
    # prod's MEAT HANGER SMALL-MEDIUM #36: a FRONT EPS cost line (legacy-linked to FRONT EPS) whose condition names
    # FLOOR EPS — so the name FLOOR EPS prices EPS on the FRONT too
    rows = body(extra=[{"id": 9999, "is_body_option": False, "material_name": "EPS", "bom_section": "FRONT",
                        "body_option_linked": "FRONT EPS",
                        "bom_conditions": json.dumps([{"option": "FLOOR EPS", "equals": "Y"}])}])
    cls = ir.classify_body(rows)
    assert any(u["name"] == "FLOOR EPS" and "both" in u["reason"] for u in cls.unclassified)
    assert "FLOOR EPS" not in cls.by_name


# ── 5. the stored rule, the draft offers, a saved costing ────────────────────
def test_the_stored_rule_lists_all_six_panels_and_is_canonical():
    assert ir.canonical_rule(CHILLER) == json.dumps({"allowed": {p: ["EPS"] for p in ir.PANELS}}, separators=(",", ":"))
    shuffled = {"allowed": {p: list(reversed(v)) for p, v in reversed(list(FREEZER["allowed"].items()))}}
    assert ir.canonical_rule(shuffled) == ir.canonical_rule(FREEZER)
    assert ir.canonical_rule(None) is None
    for bad in ({"allowed": {"FRONT": ["EPS"]}}, {"allowed": {**CHILLER["allowed"], "ROOF": ["XPS"]}},
                {"allowed": {**CHILLER["allowed"], "SIDE DOOR": ["EPS"]}}, {"nope": 1}, "[1,2]"):
        with pytest.raises((ValueError, TypeError)):
            ir.canonical_rule(bad)


def test_the_draft_offers_a_forbidden_choice_by_binding_by_name_or_by_category():
    cls = ir.classify_body(body())
    nodes = {"1": {"id": "1", "type": "flag", "label": "FRONT PU", "flagBindingId": mid_of(cls, "FRONT", "PU")},
             "2": {"id": "2", "type": "flag", "label": "SIDES PU", "flagBindingName": "SIDES PU"},
             "3": {"id": "3", "type": "category", "label": "roof", "sourceCategoryKey": "ROOF PU"},
             "4": {"id": "4", "type": "flag", "label": "FRONT EPS", "flagBindingId": mid_of(cls, "FRONT", "EPS")}}
    got = ir.draft_offers(CHILLER, cls, nodes)
    assert [(o["panel"], o["insulation"], o["node"]) for o in got] == [("FRONT", "PU", "1"), ("SIDES", "PU", "2"),
                                                                       ("ROOF", "PU", "3")]
    assert ir.draft_offers(None, cls, nodes) == []


def test_a_saved_costing_is_read_by_its_snapshot_or_by_what_it_priced():
    cls = ir.classify_body(body())
    sides_eps = mid_of(cls, "SIDES", "EPS")
    snap = {"input_state": {"ui_snapshot": {"body_option_selections": {str(sides_eps): True}}}}
    assert [(b.panel, b.insulation) for b in ir.breaches(FREEZER, cls, ir.saved_costing_payload(snap, cls))] == [("SIDES", "EPS")]
    eps_line = next(lid for lid, (p, i, _s) in cls.lines.items() if (p, i) == ("FRONT", "EPS"))
    legacy = {"items": [{"bom_id": eps_line, "excluded": False}, {"bom_id": 1, "excluded": False}]}
    got = ir.breaches(FREEZER, cls, ir.saved_costing_payload(legacy, cls))
    assert [(b.panel, b.insulation, b.via) for b in got] == [("FRONT", "EPS", "line")]


def test_the_pu_foam_names_match_the_engines():
    from app.services import insulation_foam
    assert {k for k, v in ir._LINE_MATERIAL.items() if v == "PU"} == set(insulation_foam.PU_FOAM_MATERIAL_NAMES)
