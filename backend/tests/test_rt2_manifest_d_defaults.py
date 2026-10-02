"""RT2 Manifest D — ops/prod-rt2/rt2_defaults.py, the four 4G body defaults (RT2_RULING_1 R6, Part 1c).

SYNTHETIC: four throw-away bodies stand in for prod's 12 / 36 / 24 / 15 (the tool's BODIES is pointed at them), in
the _test database, created and removed by primary key. They pin what the window relies on:
  * the dry-run plan line ("4 to apply, 0 already applied."), read-only, nothing written;
  * P FIRST: an own-priced PU foam line on any of the bodies refuses the dry-run AND the apply (exit 2, nothing
    written) — a 4G default over an own 4G price would charge 4G twice;
  * apply writes exactly the four rows, in one transaction, with a journal; a second apply is a no-op;
  * revert is byte-exact and idempotent; a renamed body refuses;
  * any guard mismatch refuses the WHOLE apply (no partial write).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_REPO = Path(__file__).resolve().parents[2]
_TOOL = _REPO / "ops" / "prod-rt2" / "rt2_defaults.py"


def _load():
    spec = importlib.util.spec_from_file_location("rt2_defaults", _TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rt2_defaults"] = mod
    spec.loader.exec_module(mod)
    return mod


D = _load()
NAMES = ["RT2-D TEST MEAT HANGER L", "RT2-D TEST MEAT HANGER SM", "RT2-D TEST EXPLOSIVE 4.9", "RT2-D TEST RHINORANGE"]


@pytest.fixture
def bodies(monkeypatch):
    """Four bodies + one PU FOAM material + one PU foam line per body (shared price). Removed by PRIMARY KEY in
    child-first order (the _test database is shared): a leftover reference fails the DELETE loudly."""
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType, engine
    with SessionLocal() as db:
        ts = [TrailerType(name=n, is_active=True) for n in NAMES]
        m = Material(name="PU FOAM", price_per_unit=4100.0)
        db.add_all([*ts, m])
        db.flush()
        lines = [BillOfMaterial(trailer_type_id=t.id, material_id=m.id, bom_section="SIDES",
                                formula_expression="2*{SIDES PU}*6.7*2.6/2.98") for t in ts]
        db.add_all(lines)
        db.commit()
        ids = {"tids": [t.id for t in ts], "mid": m.id, "bids": [b.id for b in lines]}
    db_name = engine.url.database
    monkeypatch.setattr(D, "BODIES", dict(zip(ids["tids"], NAMES)))
    monkeypatch.setattr(D, "TARGETS", {"prod": "icb_platform", "mirror": db_name})
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    yield ids
    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM bill_of_materials WHERE id = ANY(:b)"), {"b": ids["bids"]})
        c.execute(sa.text("DELETE FROM materials WHERE id = :m"), {"m": ids["mid"]})
        c.execute(sa.text("DELETE FROM trailer_types WHERE id = ANY(:t)"), {"t": ids["tids"]})


def _foams(ids) -> list:
    from app.database import engine
    with engine.connect() as c:
        rows = dict(c.execute(sa.text("SELECT id, default_insulation_foam FROM trailer_types WHERE id = ANY(:t)"),
                              {"t": ids["tids"]}).all())
    return [rows[t] for t in ids["tids"]]


def _sql(stmt, **kw):
    from app.database import engine
    with engine.begin() as c:
        c.execute(sa.text(stmt), kw)


def _run(capsys, *argv) -> tuple[int, str]:
    rc = D.main(["--target", "mirror", *argv])
    return rc, capsys.readouterr().out


def test_dry_run_plans_the_four_and_writes_nothing(bodies, capsys):
    rc, out = _run(capsys)
    assert rc == 0, out
    assert "4 to apply, 0 already applied." in out
    assert "OTHERS_4G:" in out and "DRY RUN" in out
    assert _foams(bodies) == ["32D"] * 4


def test_p_first_an_own_priced_pu_line_refuses_dry_run_and_apply(bodies, capsys, tmp_path):
    _sql("UPDATE bill_of_materials SET unit_price_override = 234.15 WHERE id = :b", b=bodies["bids"][2])
    rc, out = _run(capsys)
    assert rc == 2 and "P first" in out and "own R234.15" in out, out
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 2 and "P first" in out, out
    assert _foams(bodies) == ["32D"] * 4
    assert not list(tmp_path.glob("*.json*")), "a refused apply left a journal"


def test_apply_then_again_is_a_no_op_then_revert_is_byte_exact(bodies, capsys, tmp_path):
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 0, out
    assert _foams(bodies) == ["4G"] * 4
    [j] = list(tmp_path.glob("rt2_defaults_journal_mirror_*.json"))
    assert not list(tmp_path.glob("*.part"))
    journal = json.loads(j.read_text(encoding="utf-8"))
    assert [r["id"] for r in journal["rows"]] == bodies["tids"]
    assert {(r["before"], r["after"]) for r in journal["rows"]} == {("32D", "4G")}

    rc, out = _run(capsys)
    assert rc == 0 and "0 to apply, 4 already applied." in out, out
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path / "again"))
    assert rc == 0 and "nothing to apply." in out, out
    assert not (tmp_path / "again").exists() or not list((tmp_path / "again").glob("*.json"))

    rc, out = _run(capsys, "--revert", str(j), "--out-dir", str(tmp_path / "rv"))
    assert rc == 0 and "REVERTED 4 row(s)" in out, out
    assert _foams(bodies) == ["32D"] * 4
    rc, out = _run(capsys, "--revert", str(j), "--out-dir", str(tmp_path / "rv2"))
    assert rc == 0 and "nothing to revert." in out, out


def test_a_partly_applied_set_applies_only_the_rest(bodies, capsys, tmp_path):
    _sql("UPDATE trailer_types SET default_insulation_foam = '4G' WHERE id = :t", t=bodies["tids"][0])
    rc, out = _run(capsys)
    assert rc == 0 and "3 to apply, 1 already applied." in out, out
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 0, out
    [j] = list(tmp_path.glob("rt2_defaults_journal_mirror_*.json"))
    assert [r["id"] for r in json.loads(j.read_text(encoding="utf-8"))["rows"]] == bodies["tids"][1:]
    assert _foams(bodies) == ["4G"] * 4


def test_a_guard_mismatch_refuses_the_whole_apply(bodies, capsys, tmp_path):
    """Body 3 renamed: nothing at all is written — not even the three bodies that match."""
    _sql("UPDATE trailer_types SET name = name || ' (OLD)' WHERE id = :t", t=bodies["tids"][2])
    rc, out = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 2 and "is named" in out, out
    assert _foams(bodies) == ["32D"] * 4


def test_revert_refuses_a_body_renamed_since(bodies, capsys, tmp_path):
    rc, _ = _run(capsys, "--apply", "--out-dir", str(tmp_path))
    assert rc == 0
    [j] = list(tmp_path.glob("rt2_defaults_journal_mirror_*.json"))
    _sql("UPDATE trailer_types SET name = name || ' (OLD)' WHERE id = :t", t=bodies["tids"][1])
    rc, out = _run(capsys, "--revert", str(j), "--out-dir", str(tmp_path / "rv"))
    assert rc == 2 and "the journal names" in out, out
    assert _foams(bodies) == ["4G"] * 4


def test_the_tool_refuses_a_database_it_was_not_pointed_at(bodies, capsys):
    with pytest.raises(SystemExit, match="expects database 'icb_platform'"):
        D.main(["--target", "prod"])


def test_the_real_bodies_are_prods_four_4g_bodies():
    """The committed BODIES are exactly RT2_RULING_1 R6's four (ids are shared dev <-> prod)."""
    assert _load().BODIES == {12: "MEAT HANGER LARGE", 36: "MEAT HANGER SMALL-MEDIUM",
                              24: "EXPLOSIVE 4.9 AND UP", 15: "RHINORANGE TRAILER"}
