"""RT6 — ops/prod-rt6/rt6_rules.py, the guarded data step that sets Burt's two insulation rules (RT6_DISPATCH
default 2; RT6_RULING_1 / 1a).

The REAL tool runs against the _test database through its two seams (TARGETS: a "test" target naming this database;
PLAN: two marker families, so a shared test database's real CHILLER / FREEZER rows are never touched). It imports the
pure check from backend/app/services (the file mkstage stages beside it). Pinned:
  1. dry-run is read only, "2 to apply"; apply writes both rules (canonical) in one transaction and a journal; a
     second dry-run is "0 to apply, 2 already applied"; --show reads each rule back exactly, names the masters it
     greys, and gives the window's breach count — LIVE breaching costings (quote numbers), soft-deleted separately;
  2. revert puts both back exactly, and refuses once a rule moved since the apply;
  3. a family that already carries ANOTHER rule, a missing family and a duplicated family each refuse, write nothing;
  4. the wrong database for the target refuses.
SYNTHETIC rows only (marker RT6R), removed by primary key.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARK = "RT6R"


@pytest.fixture()
def tool(monkeypatch):
    from app.config import settings
    from app.db_guard import resolve_db_name
    monkeypatch.syspath_prepend(str(ROOT / "backend" / "app" / "services"))   # `import insulation_rules`, as staged
    spec = importlib.util.spec_from_file_location("rt6_rules", ROOT / "ops" / "prod-rt6" / "rt6_rules.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    real = dict(t.PLAN)
    monkeypatch.setattr(t, "TARGETS", {"test": resolve_db_name(settings.DATABASE_URL)})
    monkeypatch.setattr(t, "PLAN", {f"{MARK} CHILLER": real["CHILLER"], f"{MARK} FREEZER": real["FREEZER"]})
    monkeypatch.setenv("DATABASE_URL", settings.DATABASE_URL)
    return t


@pytest.fixture()
def fams():
    """The two marker families; a freezer-shaped body (SIDES EPS / PU masters + lines) in the FREEZER one, with a
    live costing that ticks SIDES EPS and a soft-deleted one that does too, and a clean live one."""
    from app.database import (BillOfMaterial, CalculationRecord, Material, SessionLocal, TrailerGroup, TrailerType)
    with SessionLocal() as db:
        gc = TrailerGroup(name=f"{MARK} CHILLER", sort_order=9401)
        gf = TrailerGroup(name=f"{MARK} FREEZER", sort_order=9402)
        db.add_all([gc, gf])
        db.flush()
        tb = TrailerType(name=f"{MARK} FREEZER BODY", is_active=True, group_id=gf.id)
        db.add(tb)
        db.flush()
        mats, masters = [], {}
        for ins in ("EPS", "PU"):
            mm = Material(name=f"{MARK} SIDES {ins}", unit_of_measure="each", price_per_unit=0, material_code=MARK)
            ml = Material(name=ins, unit_of_measure="m2", price_per_unit=1, material_code=MARK)
            db.add_all([mm, ml])
            db.flush()
            mats += [mm.id, ml.id]
            m = BillOfMaterial(trailer_type_id=tb.id, material_id=mm.id, is_body_option=True, body_option_group="SIDES",
                               body_option_subgroup="INSULATION", formula_expression="1")
            db.add(m)
            db.flush()
            masters[ins] = m.id
            db.add(BillOfMaterial(trailer_type_id=tb.id, material_id=ml.id, bom_section="SIDES", formula_expression="1",
                                  bom_conditions=json.dumps([{"option": f"{MARK} SIDES {ins}", "equals": "Y"}])))
        quotes = {}
        for label, ins, deleted in (("bad", "EPS", False), ("gone", "EPS", True), ("ok", "PU", False)):
            qn = f"{MARK}{label.upper()}{uuid.uuid4().hex[:4]}"
            db.add(CalculationRecord(trailer_type_id=tb.id, status="pending", quote_number=qn,
                                     result_json=json.dumps({"input_state": {"body_option_selections": {
                                         str(masters["EPS"]): ins == "EPS", str(masters["PU"]): ins == "PU"}}}),
                                     deleted_at=datetime.now(timezone.utc) if deleted else None))
            quotes[label] = qn
        db.commit()
        ids = {"c": gc.id, "f": gf.id, "body": tb.id, "mats": mats, "quotes": quotes, "extra": []}
    yield ids
    with SessionLocal() as db:
        db.query(CalculationRecord).filter_by(trailer_type_id=ids["body"]).delete()
        db.query(BillOfMaterial).filter_by(trailer_type_id=ids["body"]).delete()
        db.query(TrailerType).filter_by(id=ids["body"]).delete()
        db.query(Material).filter(Material.id.in_(ids["mats"])).delete(synchronize_session=False)
        db.query(TrailerGroup).filter(TrailerGroup.id.in_([ids["c"], ids["f"], *ids["extra"]])).delete(
            synchronize_session=False)
        db.commit()


def _rules(ids):
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        return db.get(TrailerGroup, ids["c"]).insulation_rule, db.get(TrailerGroup, ids["f"]).insulation_rule


def test_dry_run_apply_idempotent_show_with_the_breach_count_and_revert(tool, fams, tmp_path, capsys):
    plan = list(tool.PLAN.values())
    assert tool.main(["--target", "test"]) == 0
    out = capsys.readouterr().out
    assert "2 to apply, 0 already applied." in out and f"enforced on 1 body: {MARK} FREEZER BODY" in out
    assert _rules(fams) == (None, None)                                         # the dry-run wrote nothing

    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 0
    assert _rules(fams) == tuple(plan)
    (journal,) = tmp_path.glob("rt6_rules_journal_test_*.json")
    j = json.loads(journal.read_text(encoding="utf-8"))
    assert [(r["id"], r["before"], r["after"]) for r in j["rows"]] == [(fams["c"], None, plan[0]), (fams["f"], None, plan[1])]
    capsys.readouterr()
    assert tool.main(["--target", "test"]) == 0
    assert "0 to apply, 2 already applied." in capsys.readouterr().out          # idempotent
    assert tool.main(["--target", "test", "--show"]) == 0
    out = capsys.readouterr().out
    assert repr(plan[1]) in out                                                 # the read-back is exact
    assert f"1 forbidden master(s) greyed ['{MARK} SIDES EPS']" in out
    assert f"live breaching costings: 1 ({fams['quotes']['bad']})" in out       # quote numbers only
    assert "soft-deleted breaching costings: 1" in out and fams["quotes"]["ok"] not in out

    assert tool.main(["--target", "test", "--revert", str(journal), "--out-dir", str(tmp_path)]) == 0
    assert _rules(fams) == (None, None)


def test_revert_refuses_a_rule_that_moved_since(tool, fams, tmp_path):
    from app.database import SessionLocal, TrailerGroup
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 0
    (journal,) = tmp_path.glob("rt6_rules_journal_test_*.json")
    with SessionLocal() as db:
        db.get(TrailerGroup, fams["f"]).insulation_rule = None                  # an admin cleared it since
        db.commit()
    assert tool.main(["--target", "test", "--revert", str(journal), "--out-dir", str(tmp_path)]) == 2
    assert _rules(fams) == (list(tool.PLAN.values())[0], None)                   # nothing reverted


def test_another_rule_is_never_overwritten(tool, fams, tmp_path, capsys):
    from app.database import SessionLocal, TrailerGroup
    other = list(tool.PLAN.values())[1]                                          # the FREEZER rule, on the CHILLER
    with SessionLocal() as db:
        db.get(TrailerGroup, fams["c"]).insulation_rule = other
        db.commit()
    assert tool.main(["--target", "test"]) == 2
    assert "ANOTHER insulation rule" in capsys.readouterr().out
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert _rules(fams) == (other, None) and not list(tmp_path.glob("*.json"))


def test_a_missing_or_duplicated_family_refuses(tool, fams, tmp_path, capsys, monkeypatch):
    from app.database import SessionLocal, TrailerGroup
    monkeypatch.setitem(tool.PLAN, f"{MARK} NOSUCH", list(tool.PLAN.values())[0])
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert "0 trailer group(s)" in capsys.readouterr().out and _rules(fams) == (None, None)
    del tool.PLAN[f"{MARK} NOSUCH"]
    with SessionLocal() as db:
        dup = TrailerGroup(name=f" {MARK} chiller ", sort_order=9403)
        db.add(dup)
        db.commit()
        fams["extra"].append(dup.id)
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert "2 trailer group(s)" in capsys.readouterr().out and _rules(fams) == (None, None)


def test_the_wrong_database_refuses(tool, monkeypatch):
    monkeypatch.setattr(tool, "TARGETS", {"test": "icb_platform"})
    with pytest.raises(SystemExit, match="expects database 'icb_platform'"):
        tool.main(["--target", "test"])


def test_the_planned_rules_are_burts(tool):
    assert sys.modules.get("insulation_rules") is not None
    import insulation_rules as ir
    chiller, freezer = (ir.normalise_rule(r) for r in tool.PLAN.values())
    assert all(chiller[p] == {"EPS"} for p in ir.PANELS)
    assert {p for p in ir.PANELS if "EPS" in freezer[p]} == {"ROOF", "FLOOR"} and all("PU" in v for v in freezer.values())
