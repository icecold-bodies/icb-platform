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


# ── v1.58.1: bom_conditions (the SRD rear-frame rule) ────────────────────────

RULE = [{"option": "SRD EPS", "equals": "N", "option_id": 9001},
        {"option": "SRD PU", "equals": "N", "option_id": 9002}]
RULE_TEXT = '[{"option": "SRD EPS", "equals": "N", "option_id": 9001}, ' \
            '{"option": "SRD PU", "equals": "N", "option_id": 9002}]'


def _rule_entries(ids):
    return [_entry(ids, "srd", "bom_conditions", None, RULE),
            _entry(ids, "floor", "bom_conditions", None, RULE)]


def _set_conditions(ids, which, text):
    from app.database import engine
    with engine.begin() as c:
        c.execute(sa.text("UPDATE bill_of_materials SET bom_conditions=:v WHERE id=:i"),
                  {"v": text, "i": ids[which]})


def test_conditions_apply_stores_the_endpoint_text_and_a_second_apply_is_a_noop(body, tmp_path, capsys):
    m = _manifest(tmp_path, _rule_entries(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    after = _rows(body)
    # byte-for-byte what PATCH /api/configurator/items/{id}/conditions writes (json.dumps)
    assert [r["bom_conditions"] for r in after["rows"]] == [RULE_TEXT, RULE_TEXT]
    assert after["history"] == 0                                  # not a price: no trail row
    assert [r["price_updated_at"] for r in after["rows"]][1] is None
    capsys.readouterr()
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    assert "0 to apply, 2 already applied" in capsys.readouterr().out
    assert _rows(body) == after
    assert len(_journals(tmp_path)) == 1


def test_conditions_revert_is_byte_exact(body, tmp_path):
    before = _rows(body)
    m = _manifest(tmp_path, _rule_entries(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 0
    assert _rows(body) != before
    [j] = _journals(tmp_path)
    assert _run("--revert", str(j), "--out-dir", str(tmp_path)) == 0
    assert _rows(body) == before                                  # NULL again, every other column untouched


def test_conditions_guard_compares_canonical_json(body, tmp_path, capsys):
    # the same rule stored with other key order + spacing counts as ALREADY APPLIED, not a mismatch
    _set_conditions(body, "srd", '[{"equals":"N","option_id":9001,"option":"SRD EPS"},'
                                 '{"option_id":9002,"option":"SRD PU","equals":"N"}]')
    m = _manifest(tmp_path, _rule_entries(body))
    assert _run("--manifest", str(m), "--out-dir", str(tmp_path)) == 0
    assert "1 to apply, 1 already applied" in capsys.readouterr().out


def test_a_conditions_guard_mismatch_aborts_the_whole_apply(body, tmp_path, capsys):
    # someone saved a DIFFERENT rule on one line (the editor's replace-on-save: FRONT EPS = N)
    _set_conditions(body, "floor", '[{"option": "FRONT EPS", "equals": "N"}]')
    before = _rows(body)
    m = _manifest(tmp_path, _rule_entries(body))
    assert _run("--manifest", str(m), "--apply", "--out-dir", str(tmp_path)) == 2
    out = capsys.readouterr().out
    assert "GUARD" in out and "FRONT EPS" in out and "Nothing written" in out
    assert _rows(body) == before                                  # the srd line was NOT written either
    assert _journals(tmp_path) == []


def test_body_may_list_the_dev_and_prod_names(body, tmp_path, capsys):
    e = _rule_entries(body)
    for x in e:
        x["body"] = ["ICECREAM BODY LARGE", BODY]                 # prod name, dev name
    assert _run("--manifest", str(_manifest(tmp_path, e)), "--out-dir", str(tmp_path)) == 0
    for x in e:
        x["body"] = ["ICECREAM BODY LARGE", "ICECREAM 4.9 UP"]    # neither is this body
    before = _rows(body)
    assert _run("--manifest", str(_manifest(tmp_path, e)), "--apply", "--out-dir", str(tmp_path)) == 2
    assert "identity mismatch" in capsys.readouterr().out
    assert _rows(body) == before


def test_the_manifest_refuses_a_malformed_rule(tmp_path):
    ids = {"tid": 1, "srd": 2, "floor": 3}
    for bad in ([{"option": "SRD PU", "equals": "X"}], [{"equals": "N"}], {"mode": "include"}, "not json"):
        with pytest.raises(SystemExit):
            PC.load_manifest(_manifest(tmp_path, [_entry(ids, "srd", "bom_conditions", None, bad)]))
    # a rule that equals its guard canonically is a no-op entry
    with pytest.raises(SystemExit):
        PC.load_manifest(_manifest(tmp_path, [_entry(ids, "srd", "bom_conditions",
                                                     json.dumps(RULE, indent=1), RULE)]))


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


# Prod moved on after the v1.58 apply, deliberately, and the CI snapshot is prod's pricing (RT1 Stage 3, 1 Oct 2026):
# on 29 Sep Michael put these two single-rear-door PU lines onto the shared PU material (ratified: RT1 ruling 1, Q-A),
# dropping the own R4 100 that F1 gave them; the material is R4 100 again since 1 Oct (Burt's corrected 32D), so they
# price as F1 intended. Each must sit exactly at its later value; every other entry stays wholly at guard or new.
LATER_PROD = {
    ("F1", 3576, "unit_price_override"): None,   # FREEZER 2.3 METER / SRD / PU
    ("F1", 2415, "unit_price_override"): None,   # FREEZER MEDIUM / SRD / PU
}


def test_the_committed_snapshot_is_wholly_before_or_wholly_after_the_corrections():
    """The CI snapshot is prod's pricing. Before the prod apply every entry sits at
    its guard; after the close step (snapshot regenerated from prod) every entry
    sits at its new value. Anything in between means prod drifted or the apply
    was partial — surface it, never commit it. A later, ratified prod change is
    named in LATER_PROD and must sit exactly at its later value."""
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
        later = (c.finding, c.bom_id, c.field)
        if later in LATER_PROD:
            assert have == LATER_PROD[later], f"{c.key}: the ratified later value is {LATER_PROD[later]!r}, the snapshot has {have!r}"
            continue
        assert have in (c.current, c.new), f"{c.key}: snapshot has {have!r}"
        (at_current if have == c.current else at_new).append(c.key)
    assert not (at_current and at_new), f"half-applied: {len(at_new)} at new, {len(at_current)} at guard"


# ── v1.58.1 Manifest A (the SRD rear-frame rules) ────────────────────────────

MANIFEST_A = _BACKEND.parent / "docs" / "audit" / "srd_rear_frame_2026-09" / "manifest_a.yaml"


def test_manifest_a_is_the_prod_scope_and_one_rule_per_body():
    changes, _sha = PC.load_manifest(MANIFEST_A)
    assert len(changes) == 120 and len({c.body_id for c in changes}) == 14      # prod discovery 29 Sep
    assert {c.field for c in changes} == {"bom_conditions"} and {c.current for c in changes} == {None}
    assert {c.section for c in changes} == {"REAR FRAME & FLOOR PLATE"}
    per_body = {}
    for c in changes:
        per_body.setdefault(c.body_id, set()).add(c.new)
    assert all(len(v) == 1 for v in per_body.values()), "one rule per body"
    for bid, (rule,) in per_body.items():
        conds = json.loads(rule)
        assert all(x["equals"] == "N" for x in conds)                           # "not selected" only
        names = sorted(x["option"] for x in conds)
        assert names == (["SRD"] if bid == 27 else ["SRD EPS", "SRD PU"]), (bid, names)


def test_manifest_a_names_real_lines_and_the_snapshot_is_wholly_before_or_after():
    """The 12 audited bodies are in the committed prod snapshot: every entry there names its real line
    (prod name first in `body:`), and the snapshot carries either NO rule on all of them (before the
    prod apply) or exactly the manifest's rule on all of them (after the close-step regeneration)."""
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["tables"]
    bom = {r["id"]: r for r in snap["bill_of_materials"]}
    tt = {r["id"]: r["name"] for r in snap["trailer_types"]}
    mat = {r["id"]: r["name"] for r in snap["materials"]}
    changes, _sha = PC.load_manifest(MANIFEST_A)
    in_snap = [c for c in changes if c.bom_id in bom]
    assert len(in_snap) == 102                                                  # the 12 audited bodies
    before, after = [], []
    for c in in_snap:
        r = bom[c.bom_id]
        assert (r["trailer_type_id"], tt[r["trailer_type_id"]], r["bom_section"], mat[r["material_id"]]) \
            == (c.body_id, c.bodies[0], c.section, c.line), c.key
        if PC._same(c.field, r["bom_conditions"], c.current):
            before.append(c.key)
        elif PC._same(c.field, r["bom_conditions"], c.new):
            after.append(c.key)
        else:
            pytest.fail(f"{c.key}: snapshot carries {r['bom_conditions']!r}")
    assert not (before and after), f"half-applied: {len(after)} at the rule, {len(before)} without"
