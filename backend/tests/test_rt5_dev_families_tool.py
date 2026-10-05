"""RT5 (RT5_RULING_1 Q6) — ops/dev-rt5/dev_families.py, RT3's six families on dev BY NAME.

The REAL tool runs against the _test database through its two test seams (TARGET_DB = this database, NAME_PREFIX =
the marker, so only marker rows are read and named). Pinned:
  1. the plan: an existing family keeps its group (colour + order set), MEATHANGER is renamed MEAT, a missing family
     is created, bodies map by name (prod's plan), the ice-cream aliases map to ICE CREAM, an unknown body goes to
     OTHER, RHINORANGE TRAILER moves to OTHER with its own override and the empty RHINORANGE group is deleted; no
     active body's quote template changes;
  2. apply writes exactly the reviewed plan (--expect-plan) and a journal; a plan that moved since refuses;
  3. revert puts every row back exactly (the deleted group with its own id);
  4. the tool refuses any database but the one it targets (dev's `icb` in real use).
SYNTHETIC rows only (marker RT5D), removed by primary key / marker.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
P = "RT5D "


@pytest.fixture()
def tool(monkeypatch):
    from app.config import settings
    from app.db_guard import resolve_db_name
    spec = importlib.util.spec_from_file_location("dev_families", ROOT / "ops" / "dev-rt5" / "dev_families.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    monkeypatch.setattr(t, "TARGET_DB", resolve_db_name(settings.DATABASE_URL))
    monkeypatch.setattr(t, "NAME_PREFIX", P)
    monkeypatch.setenv("DATABASE_URL", settings.DATABASE_URL)
    return t


def _state():
    from app.database import SessionLocal, TrailerGroup, TrailerType
    with SessionLocal() as db:
        g = {x.id: (x.name, x.colour, x.sort_order, x.report_template_id)
             for x in db.query(TrailerGroup).filter(TrailerGroup.name.like(P + "%")).all()}
        b = {x.name: (x.group_id, x.override_report_template_id)
             for x in db.query(TrailerType).filter(TrailerType.name.like(P + "%")).all()}
    return g, b


@pytest.fixture()
def dev():
    from app.database import ReportTemplate, SessionLocal, TrailerGroup, TrailerType

    def purge(db):
        db.query(TrailerType).filter(TrailerType.name.like(P + "%")).delete(synchronize_session=False)
        db.query(TrailerGroup).filter(TrailerGroup.name.like(P + "%")).delete(synchronize_session=False)
        db.commit()
    with SessionLocal() as db:
        purge(db)
        tmpl = db.query(ReportTemplate).filter_by(is_active=True).order_by(ReportTemplate.id).first()
        assert tmpl, "the test database has no active quote template"
        ge = TrailerGroup(name=P + "EXPLOSIVE", colour="#F60404", sort_order=100, report_template_id=tmpl.id)
        gm = TrailerGroup(name=P + "MEATHANGER", colour="#D345CF", sort_order=100, report_template_id=tmpl.id)
        gr = TrailerGroup(name=P + "RHINORANGE", sort_order=100, report_template_id=tmpl.id, description="rhino")
        db.add_all([ge, gm, gr])
        db.flush()
        db.add_all([TrailerType(name=P + "EXPLOSIVE UP TO 2.7", is_active=True, group_id=ge.id),
                    TrailerType(name=P + "MEAT HANGER LARGE", is_active=True, group_id=gm.id),
                    TrailerType(name=P + "RHINORANGE TRAILER", is_active=True, group_id=gr.id),
                    TrailerType(name=P + "ICECREAM 4.9 UP", is_active=True),
                    TrailerType(name=P + "CHILLER MEDIUM", is_active=True),
                    TrailerType(name=P + "Manni RIGIDS CB [deleted-103]", is_active=False)])
        db.commit()
        ids = {"ge": ge.id, "gm": gm.id, "gr": gr.id, "tmpl": tmpl.id}
    yield ids
    with SessionLocal() as db:
        purge(db)


def test_the_plan_by_name(tool, dev, capsys):
    cx, _ = tool.connect(read_only=True)
    try:
        groups, bodies, templates = tool.read(cx)
        plan = tool.make_plan(groups, bodies)
        _, lines = tool.describe(cx)
    finally:
        cx.close()
    ops = {o["family"]: o for o in plan["groups"]}
    assert ops["EXPLOSIVE"]["op"] == "update" and ops["EXPLOSIVE"]["after"] == {"name": P + "EXPLOSIVE", "colour": "#E03131", "sort_order": 1}
    assert ops["MEAT"] == {"op": "update", "family": "MEAT", "id": dev["gm"],
                           "before": {"name": P + "MEATHANGER", "colour": "#D345CF", "sort_order": 100},
                           "after": {"name": P + "MEAT", "colour": "#D66A0B", "sort_order": 4}}
    assert {f for f, o in ops.items() if o["op"] == "create"} == {"CHILLER", "FREEZER", "ICE CREAM", "OTHER"}
    fam = {o["name"]: o["family"] for o in plan["bodies"]}
    assert fam == {P + "RHINORANGE TRAILER": "OTHER", P + "ICECREAM 4.9 UP": "ICE CREAM", P + "CHILLER MEDIUM": "CHILLER",
                   P + "Manni RIGIDS CB [deleted-103]": "OTHER"}          # the other two keep their group
    assert plan["overrides"] == [{"id": plan["overrides"][0]["id"], "name": P + "RHINORANGE TRAILER", "before": None,
                                  "after": dev["tmpl"]}]
    assert [d["id"] for d in plan["deletes"]] == [dev["gr"]]
    text = "\n".join(lines)
    assert "0 active body template(s) change" in text
    assert "(alias of prod's 'ICECREAM BODY LARGE')" in text and "(not in prod's plan -> OTHER)" in text


def test_apply_exactly_the_reviewed_plan_then_revert_exactly(tool, dev, tmp_path, capsys):
    before = _state()
    cx, _ = tool.connect(read_only=True)
    try:
        sha = tool.plan_sha(tool.make_plan(*tool.read(cx)[:2]))
    finally:
        cx.close()
    assert tool.main(["--apply", "--expect-plan", "0" * 64, "--out-dir", str(tmp_path)]) == 2   # not the reviewed plan
    assert _state() == before
    assert tool.main(["--apply", "--expect-plan", sha, "--out-dir", str(tmp_path)]) == 0
    g, b = _state()
    names = {v[0]: k for k, v in g.items()}
    assert set(names) == {P + f for f in ("EXPLOSIVE", "MEAT", "CHILLER", "FREEZER", "ICE CREAM", "OTHER")}
    assert dev["gr"] not in g                                                  # RHINORANGE deleted once empty
    assert b[P + "RHINORANGE TRAILER"] == (names[P + "OTHER"], dev["tmpl"])     # keeps its quote by its own override
    assert b[P + "ICECREAM 4.9 UP"][0] == names[P + "ICE CREAM"]
    assert b[P + "Manni RIGIDS CB [deleted-103]"][0] == names[P + "OTHER"]
    assert g[dev["gm"]][:3] == (P + "MEAT", "#D66A0B", 4)
    cx, _ = tool.connect(read_only=True)
    try:
        assert tool.make_plan(*tool.read(cx)[:2])["bodies"] == []                # nothing left to move
    finally:
        cx.close()
    (journal,) = tmp_path.glob("dev_families_journal_*.json")
    assert json.loads(journal.read_text(encoding="utf-8"))["plan_sha256"] == sha
    assert tool.main(["--revert", str(journal), "--out-dir", str(tmp_path)]) == 0
    assert _state() == before                                                   # every row back, RHINORANGE with its id


def test_any_other_database_refuses(tool, monkeypatch):
    monkeypatch.setattr(tool, "TARGET_DB", "icb")
    with pytest.raises(SystemExit, match="runs only on dev's 'icb'"):
        tool.connect(read_only=True)
    monkeypatch.setattr(tool, "TARGET_DB", "icb_platform")
    with pytest.raises(SystemExit, match="REFUSED"):
        tool.connect(read_only=True)
