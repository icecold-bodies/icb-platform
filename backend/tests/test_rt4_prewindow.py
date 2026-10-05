"""RT4_RULING_2 — the pre-window check (ops/prod-rt4/rt4_prewindow.py) and the door report it runs.

Pure: the snapshot diff, the draft node diff, which draft node offers a master, Burt's two rulings read from a draft,
a condition's master by id and name, the 3 Oct door report's saved times, the cell comparison.

On the database (the committed MES snapshot loaded onto ONE connection inside a transaction that is rolled back —
icb_test is left as found), with Settings-page drafts for CHILLER MEDIUM (26) and FREEZER MEDIUM (20):
  1. Michael's removals as DRAFT NODES ONLY (PU flags off the chiller; EPS flags off the freezer's FRONT, SIDES and
     doors) -> (a) "DRAFT NODES ONLY", Burt's rulings as ruled; (b) every Manifest A body OK through the engine;
  2. the same removals as DELETED MASTERS (the BOM rows gone) -> (a) "BOM ROWS AS WELL" with the master ids;
     (b) the conditions on the gone SRD master read as not selected and the rule still holds; (c) the door report
     still runs and reads OK for both bodies (the gone master is a '-' cell);
  3. the negative control: CHILLER MEDIUM's REAR FRAME rules removed -> (b) "#26 !! PROBLEM" (SRD costs REAR FRAME).
"""
import importlib.util
import json
import re
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
RT3 = _REPO / "docs" / "audit" / "rt3_2026-10" / "prod" / "window_20261003"
DOOR_3OCT = RT3 / "icb-rt2-doors" / "out-20261003-061457" / "door_report.txt"
MANIFEST_A = _REPO / "docs" / "audit" / "srd_rear_frame_2026-09" / "manifest_a.yaml"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PW = _load("rt4_prewindow", _REPO / "ops" / "prod-rt4" / "rt4_prewindow.py")
DOORS = _load("rt1_door_report", _REPO / "ops" / "prod-rt1" / "rt1_door_report.py")


# ---------------------------------------------------------------------------------------------------------------
# pure
# ---------------------------------------------------------------------------------------------------------------
def test_the_3_oct_door_report_gives_every_body_its_saved_time():
    saved = PW.parse_door_report(DOOR_3OCT.read_text(encoding="utf-8"))
    assert len(saved) == 14
    assert saved[26] == "2026-10-01 10:12" and saved[20] == "2026-09-29 12:39" and saved[21] == "2026-10-02 17:42"


def _doc(bom, tt=None, groups=None, mats=None):
    return {"trailer_ids": [26], "tables": {
        "trailer_types": tt or [{"id": 26, "name": "CHILLER MEDIUM", "group_id": None}],
        "trailer_groups": groups or [],
        "materials": mats or [{"id": 1, "name": "SRD PU"}, {"id": 2, "name": "SRD EPS"}, {"id": 3, "name": "2.5MM REAR FRAME"}],
        "bill_of_materials": bom}}


def test_the_snapshot_diff_names_a_deleted_master_and_a_changed_rule_and_labels_rt3():
    m_pu = {"id": 10, "trailer_type_id": 26, "material_id": 1, "is_body_option": True, "body_option_group": "SRD",
            "body_option_subgroup": "INSULATION", "variable_value": 0.0, "bom_section": "BODY OPTIONS", "bom_conditions": None}
    m_eps = dict(m_pu, id=11, material_id=2)
    line = {"id": 12, "trailer_type_id": 26, "material_id": 3, "is_body_option": False, "body_option_group": None,
            "body_option_subgroup": None, "variable_value": None, "bom_section": PW.RF,
            "bom_conditions": '[{"option": "SRD EPS", "equals": "N"}, {"option": "SRD PU", "equals": "N"}]'}
    base = _doc([m_pu, m_eps, line])
    now = _doc([m_eps, dict(line, bom_conditions='[{"option": "SRD EPS", "equals": "N"}]')],
               tt=[{"id": 26, "name": "CHILLER MEDIUM", "group_id": 7}], groups=[{"id": 7, "name": "CHILLER"}])
    diff = PW.snapshot_diff(base, now, {"bill_of_materials": ["id"], "trailer_types": ["id"], "trailer_groups": ["id"],
                                        "materials": ["id"]})
    assert [r["id"] for r in diff["bill_of_materials"]["removed"]] == [10]
    assert diff["bill_of_materials"]["changed"][0]["pk"] == [12]
    lines = []
    counts = PW.render_diff(diff, base, now, lines.append)
    assert counts == {"bom_removed_master": 1, "bill_of_materials_changed": 1}      # RT3's group_id is not counted
    text_ = "\n".join(lines)
    assert "REMOVED body 26 CHILLER MEDIUM · MASTER bom 10 'SRD PU' [SRD/INSULATION]" in text_
    assert "trailer_types [26]" in text_ and "(RT3)" in text_
    assert PW.snapshot_diff(base, base, {"bill_of_materials": ["id"]}) == {}


def _flag(i, name, parent="ins", bid=None):
    return {"id": i, "type": "flag", "label": name, "flagBindingId": bid, "flagBindingName": name, "parentId": parent}


def test_draft_nodes_offer_masters_by_id_or_name_and_burt_reads_them():
    nodes = {"ins": {"id": "ins", "type": "folder", "label": "INSULATION"},
             "a": _flag("a", "FRONT EPS", bid=1), "b": _flag("b", "FRONT PU", bid=2),
             "c": {"id": "c", "type": "flag", "label": "ROOF EPS", "parentId": "ins"},              # unbound: by name
             "d": _flag("d", "SIDES EPS", bid=99)}                                                 # stale binding
    assert PW.refs_to_master(nodes, {"id": 1, "name": "FRONT EPS"}) == ["flag 'FRONT EPS' bound=1/FRONT EPS under INSULATION"]
    assert PW.refs_to_master(nodes, {"id": 5, "name": "ROOF EPS"})
    assert PW.refs_to_master(nodes, {"id": 6, "name": "ROOF PU"}) == []
    assert PW.stale_bindings(nodes, {1, 2}) == ["flag 'SIDES EPS' bound=99/SIDES EPS under INSULATION"]
    assert PW.burt_check("CHILLER", {"FRONT": {"EPS"}, "ROOF": {"EPS"}}) == (True, "no PU offered (as ruled)")
    assert PW.burt_check("CHILLER", {"FRONT": {"EPS", "PU"}})[0] is False
    assert PW.burt_check("FREEZER", {"ROOF": {"EPS", "PU"}, "FLOOR": {"EPS"}, "DRD": {"PU"}}) == \
        (True, "EPS offered on FLOOR, ROOF only (as ruled)")
    assert PW.burt_check("FREEZER", {"SIDES": {"EPS"}}) == (False, "!! EPS still offered on SIDES")
    assert PW.burt_check(None, {})[0] is None


def test_the_node_diff_lists_removed_added_and_changed_nodes():
    before = {"nodes": {"ins": {"id": "ins", "type": "folder", "label": "INSULATION"},
                        "a": _flag("a", "FRONT PU", bid=2), "b": _flag("b", "FRONT EPS", bid=1)}}
    after = {"nodes": {"ins": before["nodes"]["ins"], "b": dict(before["nodes"]["b"], label="FRONT EPS 60")}}
    d = PW.node_diff(before, after)
    assert d["removed"] == ["flag 'FRONT PU' bound=2/FRONT PU under INSULATION"] and d["added"] == []
    assert d["changed"][0].endswith("label: FRONT EPS -> FRONT EPS 60")


def test_a_condition_is_checked_by_id_and_by_name():
    by_id = {5: {"id": 5, "trailer_type_id": 26, "name": "SRD EPS"}, 7: {"id": 7, "trailer_type_id": 26, "name": "SRD EPS X"}}
    by_name = {(26, "SRD EPS"): [by_id[5]]}
    assert PW.check_condition({"option": "SRD EPS", "equals": "N", "option_id": 5}, 26, by_id, by_name)[0] is True
    good, txt = PW.check_condition({"option": "SRD PU", "equals": "N", "option_id": 6}, 26, by_id, by_name)
    assert good is False and "GONE" in txt and "reads as not selected (N)" in txt
    # the id points at another master but the NAME exists (the engine matches by name): fine, noted
    good, txt = PW.check_condition({"option": "SRD EPS", "equals": "N", "option_id": 7}, 26, by_id, by_name)
    assert good is True and "is 'SRD EPS X', but 'SRD EPS' exists as [5]" in txt
    assert PW.check_condition({"option": "SRD XX", "equals": "N", "option_id": 7}, 26, by_id, by_name)[0] is False
    assert PW.check_condition({"option": "SRD EPS", "equals": "N", "option_id": 9}, 26, by_id, by_name)[0] is True
    assert PW.check_condition({"option": "LOGO", "equals": "Y"}, 26, by_id, by_name, set())[0] is None
    assert PW.check_condition({"option": "SRD PU", "equals": "N"}, 26, by_id, by_name, {(26, "SRD PU")})[0] is False
    assert PW.cond_list('{"mode": "exclude", "all": [{"option": "X"}]}') == ("exclude", [{"option": "X"}])
    assert PW.cond_list(None) == ("none", []) and PW.cond_list("nope") == ("malformed", [])


def test_cells_compare_on_status_and_totals_to_the_cent():
    c = lambda s, st, m: {"scenario_id": s, "section_excel": "X", "status": st, "base_status": None,   # noqa: E731
                          "excel_total": 1.0, "mes_total": m}
    r = PW.compare_cells([c("a", "PASS", 10.001), c("b", "PASS", 5.0), c("gone", "PASS", 1)],
                         [c("a", "PASS", 10.004), c("b", "FLAG", 6.0), c("new", "PASS", 1)])
    assert r["identical"] == 1 and r["moved"] == [("b", "X", "")]
    assert r["only_page"] == [("gone", "X", "")] and r["only_cli"] == [("new", "X", "")]


# ---------------------------------------------------------------------------------------------------------------
# on the database
# ---------------------------------------------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch, tmp_path):
    from app import cache
    from app import database as _db
    from app.services import costing_audit_runs
    from tools.costing_audit.mes_snapshot import load_snapshot, snapshot_path
    conn = _db.engine.connect()
    outer = conn.begin()
    load_snapshot(snapshot_path("all"), conn=conn, log=lambda *_: None)
    monkeypatch.setattr(_db, "SessionLocal",
                        sessionmaker(bind=conn, join_transaction_mode="create_savepoint", autoflush=False))
    cache.invalidate_all()
    costing_audit_runs.fresh_lookups()
    stage = tmp_path / "stage"
    stage.mkdir()
    shutil.copy(snapshot_path("all"), stage / "all.json")
    shutil.copy(MANIFEST_A, stage / "manifest_a.yaml")
    shutil.copy(DOOR_3OCT, stage / "door_report_20261003.txt")
    out = tmp_path / "out"
    out.mkdir()
    masters = {}
    for r in conn.execute(text("""select b.id, b.trailer_type_id, m.name from bill_of_materials b
                                    join materials m on m.id = b.material_id
                                   where b.is_body_option and b.trailer_type_id in (26, 20)""")):
        masters.setdefault(r.trailer_type_id, {})[PW.norm(r.name)] = r.id
    db = Session(bind=conn, join_transaction_mode="create_savepoint", autoflush=False)
    try:
        yield SimpleNamespace(conn=conn, db=db, stage=stage, out=out, masters=masters,
                              base=json.loads((stage / "all.json").read_text(encoding="utf-8")))
    finally:
        db.close()
        cache.invalidate_all()
        outer.rollback()
        conn.close()
        costing_audit_runs.fresh_lookups()


def _draft(masters: dict, keep) -> str:
    nodes = {"dt": {"id": "dt", "type": "folder", "label": "DOOR TYPE", "folderMode": "container"},
             "fd": {"id": "fd", "type": "folder", "label": "DRD DOORS", "folderMode": "radio", "folderValue": 1, "parentId": "dt"},
             "fs": {"id": "fs", "type": "folder", "label": "SRD DOORS", "folderMode": "radio", "folderValue": 0, "parentId": "dt"},
             "cd": {"id": "cd", "type": "category", "label": "DRD", "sourceCategoryKey": "DRD", "parentId": "fd"},
             "cs": {"id": "cs", "type": "category", "label": "SRD", "sourceCategoryKey": "SRD", "parentId": "fs"},
             "ins": {"id": "ins", "type": "folder", "label": "INSULATION", "folderMode": "container"}}
    for name, mid in sorted(masters.items()):
        if PW.INS_RE.match(name) and keep(name):
            nodes[f"f{mid}"] = _flag(f"f{mid}", name, bid=mid)
    return json.dumps({"rootIds": ["dt", "ins"], "nodes": nodes})


CHILLER_KEEP = lambda n: not n.endswith(" PU")                                         # noqa: E731
FREEZER_KEEP = lambda n: not (n.endswith(" EPS") and n.split()[0] in ("FRONT", "SIDES", "DRD", "SRD"))  # noqa: E731


def _drafts_as_michael_left_them(w):
    for tid, keep, at in ((26, CHILLER_KEEP, "2026-10-04 11:00"), (20, FREEZER_KEEP, "2026-10-04 11:05")):
        w.conn.execute(text("delete from configurator_draft_snapshots where trailer_type_id = :t"), {"t": tid})
        w.conn.execute(text("delete from configurator_drafts where trailer_type_id = :t"), {"t": tid})
        w.conn.execute(text("""insert into configurator_draft_snapshots (trailer_type_id, label, payload, created_at)
                               values (:t, 'before Burt', :p, '2026-10-04 10:00')"""),
                       {"t": tid, "p": _draft(w.masters[tid], lambda n: True)})
        w.conn.execute(text("insert into configurator_drafts (trailer_type_id, payload, updated_at) values (:t, :p, :u)"),
                       {"t": tid, "p": _draft(w.masters[tid], keep), "u": at})


def _facts(w, now_doc):
    lines = []
    v = PW.facts(w.conn, w.db, w.stage, w.out, now_doc, lines.append)
    return v, "\n".join(lines)


def test_draft_only_removals_read_as_draft_nodes_only_and_every_rear_frame_rule_holds(world):
    w = world
    _drafts_as_michael_left_them(w)
    v, out = _facts(w, w.base)                             # the BOM rows are as on 2 Oct: the export equals all.json
    assert v["a"].startswith("DRAFT NODES ONLY") and "[20, 26]" in v["a"]
    assert "as ruled on 2 of 2 bodies with a draft" in v["a"]
    assert "no draft: not read" in out
    assert "0 of them new since 2 Oct" in out                 # nothing was deleted: no rule names a gone master
    assert "no BOM row deleted, added or changed" in v["a"]
    assert "no PU offered (as ruled)" in out and "EPS offered on FLOOR, ROOF only (as ruled)" in out
    assert "the draft now vs backup #" in out and "REMOVED  flag 'DRD PU'" in out and "REMOVED  flag 'SIDES EPS'" in out
    assert v["b_ok"] is True, out
    assert v["b"].startswith("#25 OK; #26 OK; #27 OK; #19 OK; #20 OK; #21 OK") and "8/8 OK" in v["b"]
    assert "SRD EPS REAR FRAME       0.00  excluded 9/9" in out
    assert json.loads((w.out / "facts.json").read_text(encoding="utf-8"))["verdict"]["a"] == v["a"]


def _delete_masters(w):
    gone = {26: [mid for n, mid in w.masters[26].items() if PW.INS_RE.match(n) and n.endswith(" PU")],
            20: [mid for n, mid in w.masters[20].items() if PW.INS_RE.match(n) and not FREEZER_KEEP(n)]}
    ids = gone[26] + gone[20]
    w.conn.execute(text("update bom_sections set body_option_master_id = null where body_option_master_id = any(:i)"), {"i": ids})
    w.conn.execute(text("delete from bill_of_materials where id = any(:i)"), {"i": ids})
    now = json.loads(json.dumps(w.base))
    now["tables"]["bill_of_materials"] = [r for r in now["tables"]["bill_of_materials"] if r["id"] not in ids]
    return gone, now


def test_deleted_masters_read_as_bom_rows_as_well_the_rules_still_hold_and_the_door_report_runs(world, monkeypatch, capsys):
    w = world
    _drafts_as_michael_left_them(w)
    gone, now = _delete_masters(w)
    v, out = _facts(w, now)
    assert v["a"].startswith("BOM ROWS AS WELL")
    assert f"26: {sorted(gone[26])}" in v["a"] and f"20: {sorted(gone[20])}" in v["a"]
    assert f"DELETED since 2 Oct: {sorted(gone[26])}" in out
    # (b): the SRD PU condition names a master that is gone -> not selected; the rule still excludes on SRD EPS
    assert v["b_ok"] is True, out
    assert "#26 OK (names a gone master)" in v["b"] and "#20 OK (names a gone master)" in v["b"]
    assert "reads as not selected (N)" in out
    assert re.search(r"· 2[0-9] condition\(s\) naming a missing master, 2[0-9] of them new since 2 Oct", out), out
    # (c): the door report, unchanged, on the same connection (the gone PU / EPS master is a '-' cell)
    raw = w.conn.connection.driver_connection

    @contextmanager
    def same_conn(*_a, **_k):
        yield raw
    monkeypatch.setattr(DOORS, "psycopg", SimpleNamespace(connect=same_conn))
    assert DOORS.main("postgresql://unused", str(w.stage / "all.json")) == 0
    rep = capsys.readouterr().out
    row26 = next(ln for ln in rep.splitlines() if ln.strip().startswith("26 CHILLER MEDIUM"))
    row20 = next(ln for ln in rep.splitlines() if ln.strip().startswith("20 FREEZER MEDIUM"))
    assert row26.endswith("| OK") and " / - / " in row26, row26
    assert row20.endswith("| OK") and "- / " in row20, row20


def test_negative_control_a_broken_rear_frame_rule_is_a_problem(world):
    w = world
    _drafts_as_michael_left_them(w)
    w.conn.execute(text("update bill_of_materials set bom_conditions = null "
                        "where trailer_type_id = 26 and bom_section = :rf"), {"rf": PW.RF})
    v, out = _facts(w, w.base)
    assert v["b_ok"] is False
    assert "#26 !! PROBLEM" in v["b"] and "#25 OK" in v["b"]
    assert "VERDICT #26: !! PROBLEM" in out and "SRD EPS REAR FRAME" in out and "!! FAIL" in out
