"""RT5 — ops/prod-rt5/rt5_notes.py, the guarded data step that sets the two rule notes (RT5_RULING_1).

The REAL tool runs against the _test database through two test seams it already has as constants: TARGETS (a
"test" target naming this database) and PLAN (two marker families, so the real CHILLER / FREEZER rows a shared test
database may hold are never touched). Pinned:
  1. dry-run is read only and reports "2 to apply"; apply writes both notes in one transaction and a journal;
     a second dry-run finds "0 to apply, 2 already applied" (idempotent); --show reads every note back exactly;
  2. revert puts both back exactly, and refuses once a note moved since the apply;
  3. a family that already carries ANOTHER note, a missing family, and a duplicated family each refuse (exit 2)
     and write nothing;
  4. the wrong database for the target refuses.
SYNTHETIC rows only (marker RT5N), removed by primary key.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MARK = "RT5N"
PLAN = {f"{MARK} CHILLER": "No PU insulation for Chillers",
        f"{MARK} FREEZER": "Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors"}


@pytest.fixture()
def tool(monkeypatch):
    from app.config import settings
    from app.db_guard import resolve_db_name
    spec = importlib.util.spec_from_file_location("rt5_notes", ROOT / "ops" / "prod-rt5" / "rt5_notes.py")
    t = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(t)
    monkeypatch.setattr(t, "TARGETS", {"test": resolve_db_name(settings.DATABASE_URL)})
    monkeypatch.setattr(t, "PLAN", dict(PLAN))
    monkeypatch.setenv("DATABASE_URL", settings.DATABASE_URL)
    return t


@pytest.fixture()
def fams():
    from app.database import SessionLocal, TrailerGroup, TrailerType
    with SessionLocal() as db:
        gc = TrailerGroup(name=f"{MARK} CHILLER", sort_order=9301)
        gf = TrailerGroup(name=f"{MARK} FREEZER", sort_order=9302)
        db.add_all([gc, gf])
        db.flush()
        tb = TrailerType(name=f"{MARK} CHILLER BODY", is_active=True, group_id=gc.id)
        db.add(tb)
        db.commit()
        ids = {"c": gc.id, "f": gf.id, "body": tb.id, "extra": []}
    yield ids
    with SessionLocal() as db:
        db.query(TrailerType).filter_by(id=ids["body"]).delete()
        db.query(TrailerGroup).filter(TrailerGroup.id.in_([ids["c"], ids["f"], *ids["extra"]])).delete(
            synchronize_session=False)
        db.commit()


def _notes(ids):
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        return db.get(TrailerGroup, ids["c"]).rule_note, db.get(TrailerGroup, ids["f"]).rule_note


def test_dry_run_apply_idempotent_show_and_revert(tool, fams, tmp_path, capsys):
    assert tool.main(["--target", "test"]) == 0
    out = capsys.readouterr().out
    assert "2 to apply, 0 already applied." in out and f"shown on 1 body: {MARK} CHILLER BODY" in out
    assert _notes(fams) == (None, None)                                         # the dry-run wrote nothing

    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 0
    assert _notes(fams) == tuple(PLAN.values())
    (journal,) = tmp_path.glob("rt5_notes_journal_test_*.json")
    j = json.loads(journal.read_text(encoding="utf-8"))
    assert [(r["id"], r["before"], r["after"]) for r in j["rows"]] == [(fams["c"], None, PLAN[f"{MARK} CHILLER"]),
                                                                        (fams["f"], None, PLAN[f"{MARK} FREEZER"])]
    capsys.readouterr()
    assert tool.main(["--target", "test"]) == 0
    assert "0 to apply, 2 already applied." in capsys.readouterr().out          # idempotent
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path / "again")]) == 0
    assert "APPLIED 0 note(s)" in capsys.readouterr().out
    assert tool.main(["--target", "test", "--show"]) == 0
    assert repr(PLAN[f"{MARK} FREEZER"]) in capsys.readouterr().out             # the read-back is exact

    assert tool.main(["--target", "test", "--revert", str(journal), "--out-dir", str(tmp_path)]) == 0
    assert _notes(fams) == (None, None)


def test_revert_refuses_a_note_that_moved_since(tool, fams, tmp_path):
    from app.database import SessionLocal, TrailerGroup
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 0
    (journal,) = tmp_path.glob("rt5_notes_journal_test_*.json")
    with SessionLocal() as db:
        db.get(TrailerGroup, fams["f"]).rule_note = "an admin edit since"
        db.commit()
    assert tool.main(["--target", "test", "--revert", str(journal), "--out-dir", str(tmp_path)]) == 2
    assert _notes(fams) == (PLAN[f"{MARK} CHILLER"], "an admin edit since")      # nothing reverted


def test_another_note_is_never_overwritten(tool, fams, tmp_path, capsys):
    from app.database import SessionLocal, TrailerGroup
    with SessionLocal() as db:
        db.get(TrailerGroup, fams["c"]).rule_note = "typed by someone"
        db.commit()
    assert tool.main(["--target", "test"]) == 2
    assert "ANOTHER note" in capsys.readouterr().out
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert _notes(fams) == ("typed by someone", None)                           # the FREEZER one was not written
    assert not list(tmp_path.glob("*.json"))


def test_a_missing_or_duplicated_family_refuses(tool, fams, tmp_path, capsys, monkeypatch):
    from app.database import SessionLocal, TrailerGroup
    monkeypatch.setitem(tool.PLAN, f"{MARK} NOSUCH", "x")
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert "0 trailer group(s)" in capsys.readouterr().out and _notes(fams) == (None, None)
    del tool.PLAN[f"{MARK} NOSUCH"]
    with SessionLocal() as db:                                                   # names are unique in the table, so
        dup = TrailerGroup(name=f" {MARK} chiller ", sort_order=9303)           # a twin differs only in case / spaces
        db.add(dup)
        db.commit()
        fams["extra"].append(dup.id)
    assert tool.main(["--target", "test", "--apply", "--out-dir", str(tmp_path)]) == 2
    assert "2 trailer group(s)" in capsys.readouterr().out and _notes(fams) == (None, None)


def test_the_wrong_database_refuses(tool, monkeypatch):
    monkeypatch.setattr(tool, "TARGETS", {"test": "icb_platform"})
    with pytest.raises(SystemExit, match="expects database 'icb_platform'"):
        tool.main(["--target", "test"])
