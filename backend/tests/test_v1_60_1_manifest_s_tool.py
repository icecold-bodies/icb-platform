"""v1.60.1 (RT4 Manifest S) — the correction tool's three new things, through its real CLI (main()):

  * `field: section` — bom_section_id + bom_section guarded and written TOGETHER (a drift in either column is a
    guard mismatch), idempotent, and --revert is byte-exact;
  * `drafts:` — a body's draft re-keyed by the A2 rule (services.sections), journaled, reverted to the exact bytes;
    a draft that already has the new key is a guard mismatch (the A2 rule would leave it);
  * `expect_unused_after` — a STOP when anything outside the manifest still names the section.
The output lines asserted here are the ones ops/prod-rt4/rt4_data.sh matches.

Plus the COMMITTED manifest: the generator reproduces it byte for byte from the committed prod exports, and it is
exactly RT4_RULING_1's S (46 line moves + id 41's two draft keys, 83/84/85 expected unused).
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parent.parent
_REPO = _BACKEND.parent
MS_DIR = _REPO / "docs" / "audit" / "rt4_2026-10" / "manifest_s"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _BACKEND / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PC = _load("audit_pricing_corrections")
MARK = "PCS-TEST v1.60.1"


def _draft(*keys) -> str:
    nodes = {f"c{i}": {"id": f"c{i}", "type": "category", "sourceCategoryKey": k, "label": k}
             for i, k in enumerate(keys)}
    return json.dumps({"rootIds": list(nodes), "nodes": nodes})


@pytest.fixture
def world():
    from app.database import (BillOfMaterial, BOMSection, ConfiguratorDraft, Material, SessionLocal, TrailerType,
                              engine)
    with SessionLocal() as db:
        t = TrailerType(name=f"{MARK} BODY")
        other = TrailerType(name=f"{MARK} OTHER")
        m = Material(name=f"{MARK} HINGE", price_per_unit=1.0)
        old = BOMSection(name=f"{MARK} DOOR FITTINGS SRD")
        new = BOMSection(name=f"{MARK} SRD DOOR FITTINGS")
        db.add_all([t, other, m, old, new])
        db.flush()
        l1 = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, bom_section=old.name, bom_section_id=old.id)
        l2 = BillOfMaterial(trailer_type_id=t.id, material_id=m.id, bom_section=old.name, bom_section_id=old.id)
        db.add_all([l1, l2])
        db.add(ConfiguratorDraft(trailer_type_id=t.id, payload=_draft(old.name, "FRONT")))
        db.commit()
        ids = {"t": t.id, "other": other.id, "m": m.id, "old": old.id, "new": new.id, "old_name": old.name,
               "new_name": new.name, "l1": l1.id, "l2": l2.id}
    yield ids
    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM bill_of_materials WHERE material_id = :m"), {"m": ids["m"]})
        c.execute(sa.text("DELETE FROM configurator_drafts WHERE trailer_type_id = ANY(:t)"),
                  {"t": [ids["t"], ids["other"]]})
        c.execute(sa.text("DELETE FROM materials WHERE id = :m"), {"m": ids["m"]})
        c.execute(sa.text("DELETE FROM trailer_types WHERE id = ANY(:t)"), {"t": [ids["t"], ids["other"]]})
        c.execute(sa.text("DELETE FROM bom_sections WHERE id = ANY(:s)"), {"s": [ids["old"], ids["new"]]})


def _manifest(tmp_path, w, *, new_name=None, unused=True) -> Path:
    q = json.dumps
    lines = ["note: \"S test\""]
    if unused:
        lines.append(f"expect_unused_after: [{w['old']}]")
    lines.append("changes:")
    for k in ("l1", "l2"):
        lines += [f"  - finding: S1", f"    body_id: {w['t']}", f"    body: {q(MARK + ' BODY')}",
                  f"    section: {q(w['old_name'])}", f"    bom_id: {w[k]}", f"    line: {q(MARK + ' HINGE')}",
                  "    field: section", f"    current: {{id: {w['old']}, name: {q(w['old_name'])}}}",
                  f"    new: {{id: {w['new']}, name: {q(new_name or w['new_name'])}}}"]
    lines += ["drafts:", "  - finding: S3", f"    body_id: {w['t']}", f"    body: {q(MARK + ' BODY')}",
              f"    old_key: {q(w['old_name'])}", f"    new_key: {q(w['new_name'])}", "    nodes: 1"]
    p = tmp_path / "manifest_s.yaml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _rows(w):
    from app.database import engine
    with engine.connect() as c:
        return {r[0]: (r[1], r[2]) for r in c.execute(sa.text(
            "SELECT id, bom_section_id, bom_section FROM bill_of_materials WHERE id = ANY(:i)"),
            {"i": [w["l1"], w["l2"]]})}


def _draft_of(tid):
    from app.database import engine
    with engine.connect() as c:
        return c.execute(sa.text("SELECT payload FROM configurator_drafts WHERE trailer_type_id = :t"),
                         {"t": tid}).scalar()


def _run(*argv) -> int:
    return PC.main(["--target", "test", *argv])


def test_dry_run_apply_second_dry_run_and_a_byte_exact_revert(world, tmp_path, capsys):
    w = world
    mf = _manifest(tmp_path, w)
    rows0, draft0 = _rows(w), _draft_of(w["t"])
    assert _run("--manifest", str(mf)) == 0
    out = capsys.readouterr().out
    assert "\n2 to apply, 0 already applied.\n" in out
    assert "\ndrafts: 1 to apply, 0 already applied.\n" in out
    assert (f"expect_unused_after [{w['old']}]: no other line or draft names them — "
            f"they are unused once this applies.") in out
    assert _rows(w) == rows0 and _draft_of(w["t"]) == draft0                  # a dry-run writes nothing

    assert _run("--manifest", str(mf), "--apply", "--out-dir", str(tmp_path)) == 0
    capsys.readouterr()
    assert _rows(w) == {w["l1"]: (w["new"], w["new_name"]), w["l2"]: (w["new"], w["new_name"])}
    keys = [n["sourceCategoryKey"] for n in json.loads(_draft_of(w["t"]))["nodes"].values()]
    assert keys == [w["new_name"], "FRONT"]

    assert _run("--manifest", str(mf)) == 0                                  # the second dry-run
    out = capsys.readouterr().out
    assert "\n0 to apply, 2 already applied.\n" in out and "\ndrafts: 0 to apply, 1 already applied.\n" in out
    assert "they are unused now." in out and "nothing to apply." in out

    journal = next(tmp_path.glob("pricing_corrections_journal_test_*.json"))
    assert _run("--revert", str(journal), "--out-dir", str(tmp_path)) == 0
    assert "1 draft(s) restored" in capsys.readouterr().out
    assert _rows(w) == rows0 and _draft_of(w["t"]) == draft0                  # byte-exact, rows AND draft


@pytest.mark.parametrize("drift", ["id", "string"])
def test_the_guard_covers_both_columns(world, tmp_path, capsys, drift):
    from app.database import engine
    w = world
    with engine.begin() as c:
        col = "bom_section_id = NULL" if drift == "id" else "bom_section = 'SOMETHING ELSE'"
        c.execute(sa.text(f"UPDATE bill_of_materials SET {col} WHERE id = :i"), {"i": w["l1"]})
    before = _rows(w)
    assert _run("--manifest", str(_manifest(tmp_path, w)), "--apply", "--out-dir", str(tmp_path)) == 2
    assert "GUARD" in capsys.readouterr().out
    assert _rows(w) == before and not list(tmp_path.glob("*journal*"))       # nothing written, no journal


def test_another_line_naming_the_section_is_a_stop(world, tmp_path, capsys):
    from app.database import BillOfMaterial, SessionLocal
    w = world
    with SessionLocal() as db:                # another body names OLD by the legacy string only
        db.add(BillOfMaterial(trailer_type_id=w["other"], material_id=w["m"], bom_section=w["old_name"]))
        db.commit()
    assert _run("--manifest", str(_manifest(tmp_path, w)), "--apply", "--out-dir", str(tmp_path)) == 2
    out = capsys.readouterr().out
    assert out.count("STOP — after this manifest") == 1 and f"(body {w['other']})" in out
    assert _rows(w)[w["l1"]] == (w["old"], w["old_name"])


def test_another_draft_naming_the_section_is_a_stop(world, tmp_path, capsys):
    from app.database import ConfiguratorDraft, SessionLocal
    w = world
    with SessionLocal() as db:
        db.add(ConfiguratorDraft(trailer_type_id=w["other"], payload=_draft(w["old_name"])))
        db.commit()
    assert _run("--manifest", str(_manifest(tmp_path, w))) == 2
    assert f"named by the draft of body {w['other']}" in capsys.readouterr().out


def test_a_target_that_is_not_that_section_is_refused(world, tmp_path, capsys):
    w = world
    assert _run("--manifest", str(_manifest(tmp_path, w, new_name="NOT ITS NAME"))) == 2
    assert f"target section {w['new']} is" in capsys.readouterr().out


def test_a_draft_that_already_has_the_new_key_is_a_guard_mismatch(world, tmp_path, capsys):
    from app.database import ConfiguratorDraft, SessionLocal
    w = world
    with SessionLocal() as db:
        db.query(ConfiguratorDraft).filter_by(trailer_type_id=w["t"]).update(
            {"payload": _draft(w["old_name"], w["new_name"])})
        db.commit()
    assert _run("--manifest", str(_manifest(tmp_path, w))) == 2
    assert "1 keyed new" in capsys.readouterr().out


def test_the_manifest_refuses_a_malformed_section_or_draft(tmp_path):
    bad = tmp_path / "m.yaml"
    bad.write_text("changes:\n  - finding: X\n    body_id: 1\n    body: B\n    section: S\n    bom_id: 1\n"
                   "    line: L\n    field: section\n    current: {id: 1, name: T}\n    new: {id: 2, name: U}\n")
    with pytest.raises(PC.ManifestError, match="must be the line's current section"):
        PC.load_manifest(bad)
    bad.write_text("changes: []\ndrafts:\n  - {finding: X, body_id: 1, body: B, old_key: A, new_key: a, nodes: 1}\n")
    with pytest.raises(PC.ManifestError, match="no-op"):
        PC.load_drafts(bad)


# ── the committed Manifest S ──────────────────────────────────────────────────────

def test_the_committed_manifest_is_exactly_what_the_generator_makes_from_the_prod_exports(tmp_path):
    before = (MS_DIR / "manifest_s.yaml").read_bytes()
    r = subprocess.run([sys.executable, str(MS_DIR / "make_manifest_s.py")], capture_output=True, text=True)
    try:
        assert r.returncode == 0, r.stderr
        assert (MS_DIR / "manifest_s.yaml").read_bytes() == before        # byte for byte
    finally:
        (MS_DIR / "manifest_s.yaml").write_bytes(before)


def test_the_committed_manifest_is_rt4_ruling_1s_s():
    m = MS_DIR / "manifest_s.yaml"
    changes, _sha = PC.load_manifest(m)
    drafts = PC.load_drafts(m)
    assert len(changes) == 46 and all(c.field == "section" for c in changes)
    assert sorted({c.body_id for c in changes}) == [7, 41]
    s1 = [c for c in changes if c.body_id == 7]
    assert sorted(c.bom_id for c in s1) == [793, 794, 795, 796, 843, 844, 845]
    assert all(c.current["name"] == c.new["name"] and c.current["id"] != c.new["id"] for c in s1)
    s2 = [c for c in changes if c.body_id == 41]
    moves = {(c.current["id"], c.new["id"]) for c in s2}
    assert len(s2) == 39 and moves == {(83, 26), (84, 15), (85, 21)}
    assert [(d.body_id, d.old_key, d.new_key, d.nodes) for d in drafts] == [
        (41, "DOOR FITTINGS SRD", "SRD DOOR FITTINGS", 1), (41, "DOOR FITTINGS DRD", "DRD DOOR FITTINGS", 1)]
    assert PC.load_expect_unused(m) == [83, 84, 85]
