"""RT3 — ops/prod-rt3/rt3_families.py, the six body families on prod (RT3_RULING_1 Q3, Q4, Q5, Q7).

Two halves:

  A. THE PROD PLAN against prod's own rows (the committed 2 Oct discovery,
     docs/audit/rt3_2026-10/prod/discovery_20261002-184220/discovery.json — names, ids and bindings only):
       * the plan names exactly prod's 41 bodies, each with its name, active flag and group;
       * THE TEMPLATE GUARD: under the plan every ACTIVE body keeps its resolved quote template, and the ONLY
         bodies that change are the 10 soft-deleted copies of Q5;
       * negative control: without RHINORANGE's own override the guard catches it.

  B. THE TOOL on a database: a synthetic plan (marker RT3T, the tool's tests-only NAME_PREFIX), in the _test
     database — dry-run writes nothing; apply is one transaction with a journal and checks the guard from the
     database before the commit; a second apply is a no-op; revert puts every row back (the deleted group with
     its own id); a stranger or a moved row refuses the WHOLE apply; a plan that would change a template refuses.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[2]
_TOOL = _REPO / "ops" / "prod-rt3" / "rt3_families.py"
_DISC = _REPO / "docs" / "audit" / "rt3_2026-10" / "prod" / "discovery_20261002-184220" / "discovery.json"


def _load():
    spec = importlib.util.spec_from_file_location("rt3_families", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rt3_families"] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load()


# ── A. the prod plan against prod's rows ─────────────────────────────────────

def _prod_state(tool):
    d = json.loads(_DISC.read_text(encoding="utf-8"))
    tm = {t["slug"]: (t["id"], t["is_active"]) for t in d["templates"]}
    g = {x["id"]: {"id": x["id"], "name": x["name"], "report_template_id": x["report_template_id"], "colour": None,
                   "sort_order": 100} for x in d["groups"]}
    b = {x["id"]: {"id": x["id"], "name": x["name"], "is_active": x["is_active"], "group_id": x["group_id"],
                   "override_id": x["override_id"]} for x in d["bodies"]}
    active = {i for i, a in tm.values() if a}
    tid = {slug: i for slug, (i, _a) in tm.items()}
    st = {"groups": g, "bodies": b, "tid": tid, "active_tmpl": active, "templates": tm,
          "fam_gid": {f[0]: f[1] for f in tool.FAMILIES}}
    return d, st


def test_the_plan_names_exactly_prods_41_bodies():
    d, st = _prod_state(F)
    assert len(d["bodies"]) == 41 and set(F.BODIES) == {x["id"] for x in d["bodies"]}
    for x in d["bodies"]:
        name, active, group_before, family = F.BODIES[x["id"]]
        assert (name, active, group_before) == (x["name"], x["is_active"], x["group_id"]), x["id"]
        assert family == x["family"], f"body {x['id']}: the plan's family differs from the confirmed list"
    assert {g["id"]: g["name"] for g in d["groups"]} == {1: "EXPLOSIVE", 2: "RHINORANGE", 3: "MEATHANGER", 4: "FREEZER"}


def test_the_families_are_michaels_in_his_order_with_the_approved_colours():
    assert [(f[0], f[3], f[4]) for f in F.FAMILIES] == [
        ("EXPLOSIVE", "#E03131", 1), ("CHILLER", "#168ED9", 2), ("FREEZER", "#4263EB", 3),
        ("MEAT", "#D66A0B", 4), ("ICE CREAM", "#D63384", 5), ("OTHER", "#7D858C", 6)]
    assert F.BODIES[41][3] == "OTHER" and F.BODIES[15][3] == "OTHER"   # Manni RIGIDS CB, RHINORANGE (Michael)


def test_the_template_guard_every_active_body_keeps_its_template_on_prods_rows():
    d, st = _prod_state(F)
    ag, ab = F.simulate(st)
    assert F.guard(st["groups"], st["bodies"], ag, ab, st["active_tmpl"]) == []
    changed = {i for i in st["bodies"]
               if F.resolved(st["bodies"][i], st["groups"], st["active_tmpl"]) != F.resolved(ab[i], ag, st["active_tmpl"])}
    assert changed == F.ALLOWED_TEMPLATE_CHANGES == {23, 22, 28, 29, 30, 31, 32, 33, 11, 35}
    active = [x for x in d["bodies"] if x["is_active"]]
    assert len(active) == 16
    for x in active:
        assert (F.resolved(st["bodies"][x["id"]], st["groups"], st["active_tmpl"])
                == F.resolved(ab[x["id"]], ag, st["active_tmpl"])), x["name"]
    # RHINORANGE prints rhinorange_quote through its OWN override once its group is gone
    assert ab[15]["override_id"] == st["tid"]["rhinorange_quote"] and 2 not in ag
    # every allowed change is a soft-deleted copy with no saved costing
    for x in d["bodies"]:
        if x["id"] in F.ALLOWED_TEMPLATE_CHANGES:
            assert "[deleted-" in x["name"] and not x["is_active"] and x["saved_costings"] == 0


def test_negative_control_without_rhinoranges_override_the_guard_catches_it(monkeypatch):
    monkeypatch.setattr(F, "OVERRIDES", {})
    d, st = _prod_state(F)
    ag, ab = F.simulate(st)
    bad = F.guard(st["groups"], st["bodies"], ag, ab, st["active_tmpl"])
    assert len(bad) == 1 and bad[0].startswith("body 15 RHINORANGE TRAILER (active)"), bad


# ── B. the tool on a database (synthetic plan) ───────────────────────────────

P = "RT3T "


@pytest.fixture
def plan(monkeypatch):
    """Four synthetic templates; groups EXPLOSIVE / MEATHANGER / FREEZER / RHINORANGE (prefixed); bodies: two
    explosive, a meat hanger, a freezer, a chiller, a rhinorange (moves to OTHER with its own override), a
    soft-deleted explosive copy (the Q5 kind: default document -> its family's template), an inactive other.
    Removed by primary key, child-first."""
    from app.database import ReportTemplate, SessionLocal, TrailerGroup, TrailerType, engine
    with SessionLocal() as db:
        t = {k: ReportTemplate(name=f"{P}{k}", slug=f"rt3t_{k}_quote", is_active=True)
             for k in ("explosive", "rhinorange", "meathanger", "freezer")}
        db.add_all(t.values())
        db.flush()
        g = {"EXP": TrailerGroup(name=f"{P}EXPLOSIVE", report_template_id=t["explosive"].id),
             "RHI": TrailerGroup(name=f"{P}RHINORANGE", report_template_id=t["rhinorange"].id),
             "MEA": TrailerGroup(name=f"{P}MEATHANGER", report_template_id=t["meathanger"].id),
             "FRZ": TrailerGroup(name=f"{P}FREEZER", report_template_id=t["freezer"].id)}
        db.add_all(g.values())
        db.flush()
        spec = [("EXPLOSIVE A", True, "EXP", "EXPLOSIVE"), ("EXPLOSIVE B", True, "EXP", "EXPLOSIVE"),
                ("MEAT HANGER", True, "MEA", "MEAT"), ("FREEZER", True, "FRZ", "FREEZER"),
                ("CHILLER", True, None, "CHILLER"), ("RHINORANGE", True, "RHI", "OTHER"),
                ("EXPLOSIVE [deleted-1]", False, None, "EXPLOSIVE"), ("DRY FREIGHT", False, None, "OTHER")]
        bodies = []
        for name, active, gk, fam in spec:
            tt = TrailerType(name=f"{P}{name}", is_active=active, group_id=g[gk].id if gk else None)
            db.add(tt)
            bodies.append((tt, fam))
        db.commit()
        ids = {"t": {k: v.id for k, v in t.items()}, "g": {k: v.id for k, v in g.items()},
               "b": {tt.name: tt.id for tt, _ in bodies}}
        plan_bodies = {tt.id: (tt.name, tt.is_active, tt.group_id, fam) for tt, fam in bodies}
    monkeypatch.setattr(F, "NAME_PREFIX", P)
    monkeypatch.setattr(F, "TARGETS", {"prod": "icb_platform", "mirror": engine.url.database})
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(F, "FAMILIES", [
        (f"{P}EXPLOSIVE", ids["g"]["EXP"], f"{P}EXPLOSIVE", "#E03131", 1, "rt3t_explosive_quote"),
        (f"{P}CHILLER", None, None, "#168ED9", 2, None),
        (f"{P}FREEZER", ids["g"]["FRZ"], f"{P}FREEZER", "#4263EB", 3, "rt3t_freezer_quote"),
        (f"{P}MEAT", ids["g"]["MEA"], f"{P}MEATHANGER", "#D66A0B", 4, "rt3t_meathanger_quote"),
        (f"{P}OTHER", None, None, "#7D858C", 6, None)])
    monkeypatch.setattr(F, "DELETE_GROUPS", {ids["g"]["RHI"]: (f"{P}RHINORANGE", "rt3t_rhinorange_quote")})
    monkeypatch.setattr(F, "OVERRIDES", {ids["b"][f"{P}RHINORANGE"]: "rt3t_rhinorange_quote"})
    monkeypatch.setattr(F, "BODIES", {i: (n, a, gb, f"{P}{fam}") for i, (n, a, gb, fam) in plan_bodies.items()})
    monkeypatch.setattr(F, "ALLOWED_TEMPLATE_CHANGES", {ids["b"][f"{P}EXPLOSIVE [deleted-1]"]})
    yield ids
    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM trailer_types WHERE name LIKE :p"), {"p": f"{P}%"})
        c.execute(sa.text("DELETE FROM trailer_groups WHERE name LIKE :p"), {"p": f"{P}%"})
        c.execute(sa.text("DELETE FROM report_templates WHERE slug LIKE 'rt3t_%'"))


def _snap():
    from app.database import engine
    with engine.connect() as c:
        g = c.execute(sa.text("SELECT id, name, report_template_id, colour, sort_order FROM trailer_groups "
                              "WHERE name LIKE :p ORDER BY id"), {"p": f"{P}%"}).all()
        b = c.execute(sa.text("SELECT id, name, group_id, override_report_template_id FROM trailer_types "
                              "WHERE name LIKE :p ORDER BY id"), {"p": f"{P}%"}).all()
    return [tuple(r) for r in g], [tuple(r) for r in b]


def _run(capsys, *argv) -> tuple[int, str]:
    rc = F.main(["--target", "mirror", *argv])
    return rc, capsys.readouterr().out


def test_dry_run_plans_every_change_and_writes_nothing(plan, capsys):
    before = _snap()
    rc, out = _run(capsys)
    assert rc == 0, out
    # 3 group updates + 2 creates + 1 delete + 4 body moves (chiller, rhinorange, the copy, dry freight) + 1 override
    assert "TEMPLATE GUARD: 6 of 6 active bodies keep their resolved template" in out, out
    assert "11 to apply, 0 already applied." in out, out
    assert "DRY RUN" in out and _snap() == before


def test_apply_then_again_is_a_no_op_then_revert_puts_every_row_back(plan, capsys, tmp_path):
    before = _snap()
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 0 and "APPLIED 11 change(s)" in out, out
    groups, bodies = _snap()
    by = {n: (gid, ov) for _i, n, gid, ov in bodies}
    gname = {i: n for i, n, *_ in groups}
    assert gname[by[f"{P}CHILLER"][0]] == f"{P}CHILLER" and gname[by[f"{P}DRY FREIGHT"][0]] == f"{P}OTHER"
    assert gname[by[f"{P}MEAT HANGER"][0]] == f"{P}MEAT"                         # the MEATHANGER group, renamed
    assert by[f"{P}RHINORANGE"] == (by[f"{P}DRY FREIGHT"][0], plan["t"]["rhinorange"])   # OTHER + its own override
    assert plan["g"]["RHI"] not in gname                                         # the empty group is gone
    assert {(n, c, o) for _i, n, _t, c, o in groups} >= {(f"{P}EXPLOSIVE", "#E03131", 1), (f"{P}MEAT", "#D66A0B", 4)}
    [j] = list(tmp_path.glob("rt3_families_journal_mirror_*.json"))
    assert not list(tmp_path.glob("*.part"))

    rc, out = _run(capsys)
    assert rc == 0 and "0 to apply, 11 already applied." in out, out
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path / "again"))
    assert rc == 0 and "nothing to apply." in out, out

    rc, out = _run(capsys, "--revert", str(j), "--out-dir", str(tmp_path / "rv"))
    assert rc == 0 and "REVERTED" in out, out
    assert _snap() == before, "the revert must put every row back exactly (the deleted group with its own id)"
    rc, out = _run(capsys, "--revert", str(j), "--out-dir", str(tmp_path / "rv2"))
    assert rc == 0 and "nothing to revert." in out, out


def test_a_body_in_the_group_to_delete_that_the_plan_does_not_move_refuses_everything(plan, capsys, tmp_path):
    from app.database import SessionLocal, TrailerType
    with SessionLocal() as db:
        db.add(TrailerType(name=f"{P}STRANGER", is_active=True, group_id=plan["g"]["RHI"]))
        db.commit()
    before = _snap()
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 2 and "REFUSED" in out and "STRANGER" in out, out
    assert _snap() == before and not list(tmp_path.glob("*.json*"))


def test_a_body_an_admin_moved_since_the_discovery_refuses_everything(plan, capsys, tmp_path):
    from app.database import engine
    with engine.begin() as c:
        c.execute(sa.text("UPDATE trailer_types SET group_id = :g WHERE id = :b"),
                  {"g": plan["g"]["FRZ"], "b": plan["b"][f"{P}CHILLER"]})
    before = _snap()
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 2 and "REFUSED" in out and "CHILLER" in out, out
    assert _snap() == before


def test_negative_control_a_plan_that_would_change_an_active_bodys_template_refuses(plan, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(F, "OVERRIDES", {})            # RHINORANGE would fall to the default document
    before = _snap()
    rc, out = _run(capsys)
    assert rc == 2 and "THE TEMPLATE GUARD" in out and "RHINORANGE" in out, out
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 2 and "THE TEMPLATE GUARD" in out, out
    assert _snap() == before and not list(tmp_path.glob("*.json*"))


def test_an_unknown_body_refuses(plan, capsys):
    from app.database import SessionLocal, TrailerType
    with SessionLocal() as db:
        db.add(TrailerType(name=f"{P}NEW SINCE DISCOVERY", is_active=True))
        db.commit()
    rc, out = _run(capsys)
    assert rc == 2 and "bodies the plan does not know" in out, out
