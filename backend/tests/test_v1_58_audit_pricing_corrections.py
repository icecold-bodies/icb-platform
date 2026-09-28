"""v1.58 — the costing-audit pricing-corrections tool (tools/audit_pricing_corrections.py).

Two kinds of test:

  * SYNTHETIC — a throw-away body with two BOM lines in the _test database,
    created and removed by primary key. They pin the three rules the BA ratified
    (default 3): a guard mismatch aborts the WHOLE apply; --revert is byte-exact;
    a second apply is a no-op. Plus: the database-name pin, the equal_at oracle
    and the manifest's own refusals.
  * THE COMMITTED MANIFEST against the committed prod snapshot (no database) —
    every entry names a real line, and the snapshot is either entirely BEFORE the
    corrections (the 28 Sep baseline) or entirely AFTER them (the snapshot
    regenerated from prod once the apply ran). A half-and-half snapshot fails.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parent.parent
_TOOLS = _BACKEND / "tools"
MANIFEST = _BACKEND.parent / "docs" / "audit" / "pricing_corrections_2026-09" / "manifest.yaml"
SNAPSHOT = _BACKEND / "tests" / "costing_audit" / "mes_snapshot" / "all.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PC = _load("audit_pricing_corrections")

BODY = "PC-TEST BODY v1.58"
MAT = "PC-TEST PU v1.58"
STAMP = "2026-09-04T14:32:34.811001+02:00"


# ── synthetic fixture ────────────────────────────────────────────────────────

@pytest.fixture
def body():
    """One body, one material, two lines. Removed by PRIMARY KEY (never by name —
    the _test database is shared) in child-first order; a leftover reference
    makes the DELETE fail loud instead of cascading."""
    from app.database import BillOfMaterial, Material, SessionLocal, TrailerType, engine
    with SessionLocal() as db:
        t = TrailerType(name=BODY)
        m = Material(name=MAT, price_per_unit=4100.0)
        db.add_all([t, m])
        db.flush()
        from datetime import datetime
        srd = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, bom_section="SRD",
                             formula_expression="1.22*2.44*2", unit_price_override=None,
                             price_updated_at=datetime.fromisoformat(STAMP))
        floor = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, bom_section="FLOOR",
                               formula_expression="13*(6.7+{Waste})", body_option_default=True)
        db.add_all([srd, floor])
        db.commit()
        ids = {"tid": t.id, "mid": m.id, "srd": srd.id, "floor": floor.id}
    yield ids
    with engine.begin() as c:
        bids = [ids["srd"], ids["floor"]]
        c.execute(sa.text("DELETE FROM bom_override_history WHERE bom_id = ANY(:b)"), {"b": bids})
        c.execute(sa.text("DELETE FROM bill_of_materials WHERE id = ANY(:b)"), {"b": bids})
        c.execute(sa.text("DELETE FROM materials WHERE id = :m"), {"m": ids["mid"]})
        c.execute(sa.text("DELETE FROM trailer_types WHERE id = :t"), {"t": ids["tid"]})


def _entry(ids, which, field, current, new, **extra):
    e = {"finding": "FX", "body_id": ids["tid"], "body": BODY,
         "section": "SRD" if which == "srd" else "FLOOR", "bom_id": ids[which], "line": MAT,
         "field": field, "current": current, "new": new}
    e.update(extra)
    return e


def _manifest(tmp_path, entries) -> Path:
    import yaml
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump({"changes": entries}, sort_keys=False), encoding="utf-8")
    return p


def _standard(ids):
    return [
        _entry(ids, "srd", "formula_expression", "1.22*2.44*2", "(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2"),
        _entry(ids, "srd", "unit_price_override", None, 4100.0),
        _entry(ids, "floor", "formula_expression", "13*(6.7+{Waste})", "13*(length+{Waste})",
               equal_at={"length": 6.7}, vars={"Waste": 0.05}),
        _entry(ids, "floor", "body_option_default", True, False),
    ]


def _rows(ids) -> dict:
    """Every column of the two lines — the byte-exact comparison target."""
    from app.database import engine
    with engine.connect() as c:
        res = c.execute(sa.text("SELECT * FROM bill_of_materials WHERE id = ANY(:b) ORDER BY id"),
                        {"b": [ids["srd"], ids["floor"]]}).mappings().all()
        hist = c.execute(sa.text("SELECT COUNT(*) FROM bom_override_history WHERE bom_id = ANY(:b)"),
                         {"b": [ids["srd"], ids["floor"]]}).scalar()
    return {"rows": [dict(r) for r in res], "history": hist}


def _run(*argv) -> int:
    return PC.main(["--target", "test", *argv])


def _journals(d: Path) -> list[Path]:
    return sorted(d.glob("pricing_corrections_journal_test_*.json"))


# ── the three ratified rules ─────────────────────────────────────────────────

def test_apply_writes_everything_and_a_second_apply_is_a_noop(body, tmp_path, capsys):
    m = _manifest(tmp_path, _standard(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    after = _rows(body)
    srd, floor = after["rows"]
    assert srd["formula_expression"] == "(1.22*2.44*{SRD PU}/2.98)*(1.22*2.44)*2"
    assert srd["unit_price_override"] == 4100.0
    assert floor["formula_expression"] == "13*(length+{Waste})"
    assert floor["body_option_default"] is False
    assert after["history"] == 1                                  # one price change -> one trail row
    [j] = _journals(tmp_path)
    journal = json.loads(j.read_text(encoding="utf-8"))
    assert len(journal["changes"]) == 4 and len(journal["before_rows"]) == 2
    # the price change stamps price_updated_at with the batch; the formula-only line keeps its own
    from datetime import datetime
    assert srd["price_updated_at"] == datetime.fromisoformat(journal["batch_at"])
    assert floor["price_updated_at"] is None

    capsys.readouterr()
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    assert "0 to apply, 4 already applied" in capsys.readouterr().out
    assert _rows(body) == after                                   # nothing moved
    assert len(_journals(tmp_path)) == 1                          # and no second journal


def test_a_guard_mismatch_aborts_the_whole_apply(body, tmp_path, capsys):
    from app.database import engine
    with engine.begin() as c:                                     # prod drifted on ONE line
        c.execute(sa.text("UPDATE bill_of_materials SET formula_expression='13*(6.8+{Waste})' WHERE id=:i"),
                  {"i": body["floor"]})
    before = _rows(body)
    m = _manifest(tmp_path, _standard(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 2
    out = capsys.readouterr().out
    assert "GUARD" in out and "13*(6.8+{Waste})" in out and "Nothing written" in out
    assert _rows(body) == before                                  # the OTHER line was not written either
    assert _journals(tmp_path) == []


def test_revert_is_byte_exact(body, tmp_path):
    before = _rows(body)
    m = _manifest(tmp_path, _standard(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    assert _rows(body) != before
    [j] = _journals(tmp_path)
    assert _run("--revert", str(j), "--out-dir", str(tmp_path)) == 0
    assert _rows(body) == before                                  # every column, history rows gone
    assert list(tmp_path.glob("pricing_corrections_revert_test_*.json"))
    # and the manifest applies cleanly again after a revert
    assert _run("--manifest", str(m), "--out-dir", str(tmp_path)) == 0


def test_revert_refuses_a_line_that_moved_since_the_apply(body, tmp_path, capsys):
    m = _manifest(tmp_path, _standard(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    from app.database import engine
    with engine.begin() as c:                                     # a hand edit after the apply
        c.execute(sa.text("UPDATE bill_of_materials SET unit_price_override=4200 WHERE id=:i"),
                  {"i": body["srd"]})
    moved = _rows(body)
    [j] = _journals(tmp_path)
    assert _run("--revert", str(j), "--out-dir", str(tmp_path)) == 2
    assert "moved since the apply" in capsys.readouterr().out
    assert _rows(body) == moved


def test_an_identity_mismatch_aborts(body, tmp_path, capsys):
    e = _standard(body)
    e[0]["section"] = "DRD"                                       # right id, wrong line description
    m = _manifest(tmp_path, e)
    before = _rows(body)
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 2
    assert "identity mismatch" in capsys.readouterr().out
    assert _rows(body) == before


def test_equal_at_refuses_a_wrong_substitution(body, tmp_path, capsys):
    e = _standard(body)
    e[2]["new"] = "13*(length+{Waste})+1"                         # typo: not equal at 6.7 m
    m = _manifest(tmp_path, e)
    before = _rows(body)
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 2
    assert "equal_at check failed" in capsys.readouterr().out
    assert _rows(body) == before


def test_the_target_pins_the_database_name():
    assert PC.assert_target("test").endswith("_test")
    for t in ("mirror", "prod", "dev"):
        with pytest.raises(SystemExit):
            PC.assert_target(t)


def test_the_manifest_refuses_noops_duplicates_and_unknown_fields(tmp_path):
    ids = {"tid": 1, "srd": 2, "floor": 3}
    with pytest.raises(SystemExit):
        PC.load_manifest(_manifest(tmp_path, [_entry(ids, "srd", "formula_expression", "1", "1")]))
    dup = _entry(ids, "srd", "formula_expression", "1", "2")
    with pytest.raises(SystemExit):
        PC.load_manifest(_manifest(tmp_path, [dup, dict(dup, new="3")]))
    with pytest.raises(SystemExit):
        PC.load_manifest(_manifest(tmp_path, [_entry(ids, "srd", "material_id", 1, 2)]))


# ── the committed manifest ───────────────────────────────────────────────────

def _committed():
    changes, _sha = PC.load_manifest(MANIFEST)
    return changes


def test_the_committed_manifest_substitutions_hold_at_6_7_m():
    changes = _committed()
    f3 = [c for c in changes if c.finding == "F3"]
    assert len(f3) == 14 and all(c.equal_at for c in f3)
    assert all("6.7" not in c.new for c in f3)
    assert PC.check_equivalences(changes, {"Waste": 0.05}) == []


def test_the_committed_snapshot_is_wholly_before_or_wholly_after_the_corrections():
    """The CI snapshot is prod's pricing. Before the prod apply every entry sits at
    its guard; after the close step (snapshot regenerated from prod) every entry
    sits at its new value. Anything in between means prod drifted or the apply
    was partial — surface it, never commit it."""
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["tables"]
    bom = {r["id"]: r for r in snap["bill_of_materials"]}
    tt = {r["id"]: r["name"] for r in snap["trailer_types"]}
    mat = {r["id"]: r["name"] for r in snap["materials"]}
    at_current, at_new = [], []
    for c in _committed():
        r = bom.get(c.bom_id)
        assert r is not None, f"{c.key}: not in the snapshot"
        assert (r["trailer_type_id"], tt[r["trailer_type_id"]], r["bom_section"], mat[r["material_id"]]) \
            == (c.body_id, c.body, c.section, c.line), c.key
        have = r[c.field]
        assert have in (c.current, c.new), f"{c.key}: snapshot has {have!r}"
        (at_current if have == c.current else at_new).append(c.key)
    assert not (at_current and at_new), f"half-applied: {len(at_new)} at new, {len(at_current)} at guard"
