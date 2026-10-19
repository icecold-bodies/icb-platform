"""RT7 (v1.61.1): every PROD accepted entry pins its amounts; a cause alone no longer hides a gap.

  * a covered cell is ACCEPTED only at the difference every covering entry pinned (±R0.01); otherwise a FLAG whose
    reason starts ACCEPTED_AMOUNT_CHANGED and names the pinned and actual amounts;
  * the prod list refuses an entry without amounts / mechanism / refs / review_by (the dev list stays unpinned);
  * `review_by` expiry fails the run loudly (EXPIRED, exit 1);
  * `audit pin` writes the amounts and the pair from a reference run;
  * the committed prod list and the committed CI snapshot are a MATCHED PAIR (one digest, LF-normalised).
Each check carries its negative control.
"""
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.costing_audit import ACCEPTED_FILE, MES_SNAPSHOT_DIR                    # noqa: E402
from tools.costing_audit.accepted import MECHANISMS, Accepted, load_accepted, load_accepted_doc  # noqa: E402
from tools.costing_audit.cli import main as audit_main                              # noqa: E402
from tools.costing_audit.compare import (AMOUNT_CHANGED, build_report, compare_scenario,  # noqa: E402
                                         reapply_accepted)
from tools.costing_audit.mes_snapshot import snapshot_digest                       # noqa: E402
from tests.costing_audit.test_compare import _golden, _gsec, _line, _mes, _ml       # noqa: E402

FAR = date(2099, 1, 1)
SEC = "DRD DOOR FITTINGS"
KEY = f"t~as_sheet | {SEC}"
PROD_LIST = ACCEPTED_FILE.with_name("accepted_differences.prod.yaml")


def _case(hinges=4.0, rivet_price=1.0):
    """FREEZER MEDIUM's E-03 shape: Burt's sheet has 6 CSLB HINGES on the double rear door, the MES 4 (-R293.46)."""
    g = _golden({SEC: _gsec([_line("CSLB HINGES", 6.0, 146.73), _line("RIVETS", 10.0, 1.0)])})
    m = _mes({SEC: [_ml(SEC, "CSLB HINGES", hinges, 146.73), _ml(SEC, "RIVETS", 10.0, rivet_price)]})
    return g, m


def _entry(amounts, i=0, cause="CSLB HINGES", review_by=FAR):
    return Accepted(body="*", section=SEC, variant="*", reason="E-03", owner="BA", review_by=review_by, index=i,
                    cause=cause, amounts=amounts, mechanism="mes_updated_ahead_of_burt", refs=["E-03"])


def _cell(entries, today=None, **kw):
    g, m = _case(**kw)
    return next(c for c in compare_scenario(g, m, tolerance_pct=1.0, accepted=entries, today=today)
                if c.section_mes == SEC)


# ── the pin ──────────────────────────────────────────────────────────────────

def test_a_pinned_cell_is_accepted_at_its_amount():
    c = _cell([_entry({KEY: -293.46})])
    assert c.status == "ACCEPTED" and c.accepted["pinned"] == -293.46 and c.accepted["mechanism"] == "mes_updated_ahead_of_burt"


def test_the_pin_holds_to_one_cent_and_no_further():
    assert _cell([_entry({KEY: -293.47})]).status == "ACCEPTED"        # R0.01 away: inside the tolerance
    c = _cell([_entry({KEY: -293.48})])                                 # R0.02 away: a FLAG
    assert c.status == "FLAG" and c.reason == f"{AMOUNT_CHANGED} entry 0 pinned -293.48; actual -293.46"


def test_a_moved_amount_flags_naming_pinned_and_actual():
    c = _cell([_entry({KEY: -293.46})], hinges=3.0)                    # one more hinge gone: -R440.19
    assert c.status == "FLAG" and c.failing
    assert c.reason == f"{AMOUNT_CHANGED} entry 0 pinned -293.46; actual -440.19"


def test_negative_control_without_a_pin_the_cause_alone_hides_the_moved_amount():
    # the pre-RT7 behaviour, and still the dev list's: the same moved cell, the same cause, no amounts -> greyed
    assert _cell([_entry(None)], hinges=3.0).status == "ACCEPTED"


def test_a_cell_newly_in_scope_flags():
    c = _cell([_entry({"another~scenario | " + SEC: -293.46})])
    assert c.status == "FLAG" and c.reason == f"{AMOUNT_CHANGED} entry 0 pins no amount for this cell; actual -293.46"
    assert _cell([_entry({})]).status == "FLAG"                          # an entry that pins nothing accepts nothing


def test_a_shared_cell_needs_every_covering_entry_to_pin_it():
    # two mechanisms in one cell (hinges -293.46, rivets +5.00): each entry pins the cell's whole difference
    net = -288.46
    both = [_entry({KEY: net}, 0), _entry({KEY: net}, 1, cause="RIVETS")]
    assert _cell(both, rivet_price=1.5).status == "ACCEPTED"
    one_off = [_entry({KEY: net}, 0), _entry({KEY: net + 5}, 1, cause="RIVETS")]
    c = _cell(one_off, rivet_price=1.5)
    assert c.status == "FLAG" and c.reason == f"{AMOUNT_CHANGED} entry 1 pinned -283.46; actual -288.46"


def test_a_one_sided_cell_keeps_its_own_reason_through_reaccept():
    """A PRESENCE cell (MISSING_IN_MES) whose pin fails becomes a FLAG with the pin's reason; a later reaccept with a
    right pin must judge it on its OWN reason again (base_reason) — not on ACCEPTED_AMOUNT_CHANGED."""
    g = _golden({"FLOOR": _gsec([_line("12MM PF PLYWOOD", 8.5775, 223.15)])})
    m = _mes({"FLOOR": []})
    key = "t~as_sheet | FLOOR"
    def ent(v):
        return Accepted(body="*", section="FLOOR", variant="*", reason="probe", owner="BA", review_by=FAR, index=0,
                        cause="12MM PF PLYWOOD", amounts={key: v}, mechanism="probe_limit", refs=["the probe"])
    rep = build_report(pack_name="t", tolerance_pct=1.0, manifest={}, mes_source="t", goldens={"s": g},
                       results={"s": m}, scenario_ids=["s"], accepted=[ent(0.0)], warnings=[])
    c = rep.cells[0]
    assert c.status == "FLAG" and c.reason.startswith(AMOUNT_CHANGED) and c.base_reason == "MISSING_IN_MES"
    net = round(0.0 - 8.5775 * 223.15, 2)                              # -1914.07
    again = reapply_accepted(json.loads(json.dumps(rep.to_dict(), default=str)), [ent(net)])
    assert again.cells[0].status == "ACCEPTED", again.cells[0].reason


def test_a_cell_accepted_on_its_own_reason_alone_gets_that_reason_back():
    """A whole MES section Burt's sheet lacks: the cell's reason (EXTRA_SECTION_IN_MES) is the ONLY text that names
    the mechanism — its likely cause is a line ('EXTRA_IN_MES ...'). Without base_reason a reaccept would judge it on
    the line alone and leave it a PRESENCE."""
    g = _golden({"FLOOR": _gsec([_line("PLY", 1.0, 100.0)])})
    m = _mes({"FLOOR": [_ml("FLOOR", "PLY", 1.0, 100.0)], "LIGHT BOX": [_ml("LIGHT BOX", "LED STRIP", 2.0, 50.0)]})
    key = "t~as_sheet | LIGHT BOX"
    def ent(v):
        return Accepted(body="*", section="LIGHT BOX", variant="*", reason="x", owner="BA", review_by=FAR, index=0,
                        cause="EXTRA_SECTION_IN_MES", amounts={key: v}, mechanism="burt_decision_pending", refs=["B-99"])
    rep = build_report(pack_name="t", tolerance_pct=1.0, manifest={}, mes_source="t", goldens={"s": g},
                       results={"s": m}, scenario_ids=["s"], accepted=[ent(1.0)], warnings=[])
    c = next(x for x in rep.cells if x.section_mes == "LIGHT BOX")
    assert c.status == "FLAG" and c.base_reason == "EXTRA_SECTION_IN_MES"
    again = reapply_accepted(json.loads(json.dumps(rep.to_dict(), default=str)), [ent(100.0)])
    cell = next(x for x in again.cells if x.section_mes == "LIGHT BOX")
    assert cell.status == "ACCEPTED", (cell.status, cell.reason)


# ── review_by ────────────────────────────────────────────────────────────────

def test_review_by_expiry_fails_the_run_loudly():
    def run(today):
        g, m = _case()
        return build_report(pack_name="t", tolerance_pct=1.0, manifest={}, mes_source="t", goldens={"s": g},
                            results={"s": m}, scenario_ids=["s"], today=today,
                            accepted=[_entry({KEY: -293.46}, review_by=date(2026, 11, 30))], warnings=[])
    on_the_day, after = run(date(2026, 11, 30)), run(date(2026, 12, 1))
    assert on_the_day.counts.get("ACCEPTED") == 1 and on_the_day.exit_code == 0     # negative control
    assert after.counts.get("EXPIRED") == 1 and after.exit_code == 1
    assert "review_by 2026-11-30 has passed" in after.cells[0].reason


# ── the prod list is strict; the dev list is not ─────────────────────────────

GOOD = {"body": "*", "section": SEC, "variant": "*", "cause": "CSLB HINGES", "kind": "tolerated",
        "mechanism": "mes_updated_ahead_of_burt", "refs": ["E-03"], "reason": "x", "owner": "BA",
        "review_by": "2026-11-30", "amounts": {KEY: -293.46}}


@pytest.mark.parametrize("drop", ["amounts", "mechanism", "refs", "review_by"])
def test_the_prod_list_refuses_an_entry_missing_a_pin_field(tmp_path, drop):
    e = {k: v for k, v in GOOD.items() if k != drop}
    prod, dev = tmp_path / "accepted_differences.prod.yaml", tmp_path / "accepted_differences.yaml"
    for p in (prod, dev):
        p.write_text(yaml.safe_dump([e]), encoding="utf-8")
    with pytest.raises(ValueError, match=f"needs .*{drop}"):
        load_accepted(prod)
    assert len(load_accepted(dev)) == 1                                  # negative control: the dev list loads it
    full = tmp_path / "ok.prod.yaml"
    full.write_text(yaml.safe_dump([GOOD]), encoding="utf-8")
    assert load_accepted(full)[0].amounts == {KEY: -293.46}              # and the complete entry loads on prod


def test_a_mechanism_outside_the_vocabulary_is_refused(tmp_path):
    p = tmp_path / "accepted_differences.prod.yaml"
    p.write_text(yaml.safe_dump([dict(GOOD, mechanism="because")]), encoding="utf-8")
    with pytest.raises(ValueError, match="mechanism 'because' is not one of"):
        load_accepted(p)
    assert "mes_updated_ahead_of_burt" in MECHANISMS and "burt_sheet_formula_slip" in MECHANISMS


# ── audit pin ────────────────────────────────────────────────────────────────

def _write_report(tmp_path, extra_flag=False):
    g, m = _case()
    if extra_flag:
        g["sections"]["ROOF"] = _gsec([_line("SKIN", 1.0, 100.0)])
        m.sections["ROOF"] = 150.0
        m.lines.append(_ml("ROOF", "SKIN", 1.0, 150.0))
    rep = build_report(pack_name="t", tolerance_pct=1.0, manifest={}, mes_source="t", goldens={"s": g},
                       results={"s": m}, scenario_ids=["s"], accepted=[], warnings=[])
    p = tmp_path / "prod_t.json"
    p.write_text(json.dumps(rep.to_dict(), default=str), encoding="utf-8")
    return p


def test_audit_pin_writes_the_amounts_and_the_pair(tmp_path):
    report, snap = _write_report(tmp_path), tmp_path / "all.json"
    snap.write_bytes(b'{"tables": {}}\r\n')
    lst = tmp_path / "accepted_differences.prod.yaml"
    lst.write_text(yaml.safe_dump([{k: v for k, v in GOOD.items() if k != "amounts"}]), encoding="utf-8")
    rc = audit_main(["pin", "--report", str(report), "--accepted", str(lst), "--write", "--snapshot", str(snap),
                     "--exported-at", "2026-10-19T15:00:00+02:00", "--prod-code", "5e37b0a", "--alembic", "0053"])
    assert rc == 0
    header, entries = load_accepted_doc(lst)                             # strict: it now loads as a prod list
    assert entries[0].amounts == {KEY: -293.46}
    assert header["pair"]["snapshot_sha256"] == snapshot_digest(snap) and header["pair"]["alembic"] == "0053"
    again = reapply_accepted(json.loads(report.read_text(encoding="utf-8")), entries)
    assert again.counts == {"ACCEPTED": 1}


def test_audit_pin_refuses_to_write_while_a_cell_is_unaccepted(tmp_path):
    report = _write_report(tmp_path, extra_flag=True)                   # ROOF +50 % and no entry for it
    lst = tmp_path / "accepted_differences.prod.yaml"
    lst.write_text(yaml.safe_dump([{k: v for k, v in GOOD.items() if k != "amounts"}]), encoding="utf-8")
    before = lst.read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="1 unaccepted cell"):
        audit_main(["pin", "--report", str(report), "--accepted", str(lst), "--write"])
    assert lst.read_text(encoding="utf-8") == before


# ── the matched pair (H2/H3) ─────────────────────────────────────────────────

def test_the_snapshot_digest_ignores_line_endings_and_sees_one_byte(tmp_path):
    lf, crlf, moved = tmp_path / "lf.json", tmp_path / "crlf.json", tmp_path / "moved.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')
    moved.write_bytes(b'{"a": 1}\n{"b": 3}\n')
    assert snapshot_digest(lf) == snapshot_digest(crlf) != snapshot_digest(moved)


def test_the_committed_prod_list_and_snapshot_are_a_matched_pair(tmp_path):
    header, entries = load_accepted_doc(PROD_LIST)                       # strict: every entry pinned
    pair = header.get("pair") or {}
    snap = MES_SNAPSHOT_DIR / "all.json"
    assert pair.get("snapshot_sha256") == snapshot_digest(snap), \
        "mes_snapshot/all.json and accepted_differences.prod.yaml were not committed together (H3)"
    assert entries and all(e.amounts for e in entries)
    one_byte = tmp_path / "all.json"                                     # negative control: one byte moved
    data = bytearray(snap.read_bytes())
    data[data.index(b"0")] = ord("1")
    one_byte.write_bytes(bytes(data))
    assert snapshot_digest(one_byte) != pair["snapshot_sha256"]


# ── the loader: the SNAPSHOT's rows win (RT7_RULING_1B §1, G1, F6 — the CI red RT7's first PR run found) ──────────

FACTOR = "costings.pu_foam_4g_factor"
SEED = "1.363109048723898"              # migration 0046's FACTOR_SEED


def _needs_test_db():
    from app.config import settings
    from app.db_guard import resolve_db_name
    if not resolve_db_name(settings.DATABASE_URL).endswith("_test"):
        pytest.skip("needs the isolated _test database")


@pytest.fixture
def txn():
    """One connection inside a transaction that is rolled back: the shared test database is left as found."""
    _needs_test_db()
    from app.database import engine
    c = engine.connect()
    t = c.begin()
    try:
        yield c
    finally:
        t.rollback()
        c.close()


def _seed_the_factor_under_another_id(c) -> dict:
    """What `alembic upgrade head` leaves on a fresh CI database: the factor row, seeded under its own id."""
    from sqlalchemy import text
    from tools.costing_audit.mes_snapshot import snapshot_path
    row = next(r for r in json.loads(snapshot_path("all").read_text(encoding="utf-8"))["tables"]["admin_settings"]
               if r["key"] == FACTOR)
    assert row["value"] != SEED
    c.execute(text("DELETE FROM admin_settings WHERE key = :k"), {"k": FACTOR})
    c.execute(text("INSERT INTO admin_settings (id, key, value) "
                   "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM admin_settings WHERE id <> :sid) + :sid, :k, :v)"),
              {"k": FACTOR, "v": SEED, "sid": row["id"]})
    return row


def test_the_snapshots_rows_win_over_a_migration_seed_and_the_fidelity_check_proves_it(txn):
    """Migration 0046 seeds the 4G factor under its own id; the loader was ON CONFLICT DO NOTHING, so on CI's fresh
    database the snapshot's row was skipped and 4G priced at the seed (PR #220's first run: 81 foam_4g cells FLAG).
    Now the snapshot's row replaces the seeded one, id and value, and check_fidelity finds every snapshot row as
    written."""
    from sqlalchemy import text
    from tools.costing_audit.mes_snapshot import check_fidelity, load_snapshot, snapshot_path
    row = _seed_the_factor_under_another_id(txn)
    load_snapshot(snapshot_path("all"), conn=txn, log=lambda *_: None)
    got = txn.execute(text("SELECT id, value FROM admin_settings WHERE key = :k"), {"k": FACTOR}).one()
    assert tuple(got) == (row["id"], row["value"])
    assert check_fidelity(snapshot_path("all"), conn=txn, log=lambda *_: None) == []


def test_negative_control_with_do_nothing_put_back_the_fidelity_check_names_the_seeded_row(txn, monkeypatch):
    """F6: the loader as it was (ON CONFLICT DO NOTHING, nothing moved aside) — the check fails on admin_settings."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from tools.costing_audit import mes_snapshot as ms
    row = _seed_the_factor_under_another_id(txn)
    monkeypatch.setattr(ms, "_unique_keys", lambda t: [])
    monkeypatch.setattr(ms, "_write", lambda conn, t, chunk, pk_cols:
                        conn.execute(pg_insert(t).values(chunk).on_conflict_do_nothing()))
    ms.load_snapshot(ms.snapshot_path("all"), conn=txn, log=lambda *_: None)
    monkeypatch.undo()
    problems = ms.check_fidelity(ms.snapshot_path("all"), conn=txn, log=lambda *_: None)
    assert f"admin_settings id={row['id']} (key='{FACTOR}'): not in the database" in problems


def _rows(c, table, ids):
    from sqlalchemy import text
    return [tuple(r) for r in c.execute(text(f"SELECT * FROM {table} WHERE id = ANY(:ids) ORDER BY id"), {"ids": ids})]


def test_a_seeded_row_under_another_id_is_replaced_its_referrers_follow_and_unload_puts_it_all_back(txn, tmp_path):
    """The app's startup seeds (the FREEZER group, the freezer_quote template, the recipes) hold snapshot rows'
    natural keys under their own ids, and other rows point at them. The load moves the seeded row aside, writes the
    snapshot's, re-points the referrers and deletes the seeded row; unload_snapshot replays the log backwards."""
    from sqlalchemy import text
    from tools.costing_audit.mes_snapshot import UNDO, check_fidelity, load_snapshot, unload_snapshot
    base = txn.execute(text("SELECT COALESCE(MAX(id), 0) FROM report_templates")).scalar()
    gid = txn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM trailer_groups")).scalar()
    snap_id, seeded_id = base + 1, base + 2
    txn.execute(text("INSERT INTO report_templates (id, name, slug, kind, is_active) "
                     "VALUES (:i, 'seeded', 'rt7-loader-test', 'html', true)"), {"i": seeded_id})
    txn.execute(text("INSERT INTO trailer_groups (id, name, report_template_id, sort_order) "
                     "VALUES (:g, 'RT7 LOADER TEST', :t, 100)"), {"g": gid, "t": seeded_id})
    before = (_rows(txn, "report_templates", [snap_id, seeded_id]), _rows(txn, "trailer_groups", [gid]))
    snap = tmp_path / "one.json"
    snap.write_text(json.dumps({"tables": {"report_templates": [{
        "id": snap_id, "name": "from the snapshot", "slug": "rt7-loader-test", "description": None, "is_active": True,
        "kind": "html", "pdf_template_id": None, "created_at": "2026-10-19T12:00:00",
        "updated_at": "2026-10-19T12:00:00"}]}}), encoding="utf-8")
    inserted: dict = {}
    load_snapshot(snap, conn=txn, inserted=inserted, log=lambda *_: None)
    assert [r[0] for r in _rows(txn, "report_templates", [snap_id, seeded_id])] == [snap_id]     # the seeded row gone
    assert txn.execute(text("SELECT report_template_id FROM trailer_groups WHERE id = :g"), {"g": gid}).scalar() == snap_id
    assert check_fidelity(snap, conn=txn, log=lambda *_: None) == []
    assert inserted["report_templates"] == [(snap_id,)] and inserted[UNDO]
    unload_snapshot(inserted, conn=txn, log=lambda *_: None)
    assert (_rows(txn, "report_templates", [snap_id, seeded_id]), _rows(txn, "trailer_groups", [gid])) == before


def test_a_row_under_a_snapshot_parent_that_the_snapshot_lacks_is_flagged_then_removed(txn):
    """A body's BOM rows and a recipe's items are the snapshot's to say: a row under a snapshot parent that the
    snapshot does not carry (deleted on prod since, or left by a seed) would be priced. The check names it (the
    negative control); the load removes it."""
    from sqlalchemy import text
    from app.database import Base
    from tools.costing_audit.mes_snapshot import check_fidelity, load_snapshot, snapshot_path
    snap = snapshot_path("all")
    item = json.loads(snap.read_text(encoding="utf-8"))["tables"]["skin_formula_items"][0]
    load_snapshot(snap, conn=txn, log=lambda *_: None)
    extra = txn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM skin_formula_items")).scalar()
    txn.execute(Base.metadata.tables["skin_formula_items"].insert().values({**item, "id": extra}))
    assert check_fidelity(snap, conn=txn, log=lambda *_: None) == [
        f"skin_formula_items id={extra}: formula_id={item['formula_id']} is a snapshot skin_formulas, "
        "but the row is not in the snapshot"]
    load_snapshot(snap, conn=txn, log=lambda *_: None)
    assert _rows(txn, "skin_formula_items", [extra]) == []
    assert check_fidelity(snap, conn=txn, log=lambda *_: None) == []


def test_a_rolled_back_load_never_leaves_a_sequence_behind(txn, tmp_path):
    """setval is not transactional. The load deletes a replaced row; if it set the sequence to the remaining MAX(id), a
    rolled-back load would leave the sequence below the row it puts back, and the next insert collides (the full suite
    found it: test_rt3_bootstrap's report template, id 5). The loader only moves a sequence forward."""
    from sqlalchemy import text
    from tools.costing_audit.mes_snapshot import load_snapshot
    x = txn.execute(text("INSERT INTO report_templates (name, slug, kind, is_active) "
                         "VALUES ('placeholder', 'rt7-seq-placeholder', 'html', true) RETURNING id")).scalar()
    d = txn.execute(text("INSERT INTO report_templates (name, slug, kind, is_active) "
                         "VALUES ('seeded', 'rt7-seq-test', 'html', true) RETURNING id")).scalar()
    txn.execute(text("DELETE FROM report_templates WHERE id = :x"), {"x": x})      # a free id below the seeded row's
    snap = tmp_path / "one.json"
    snap.write_text(json.dumps({"tables": {"report_templates": [{
        "id": x, "name": "from the snapshot", "slug": "rt7-seq-test", "description": None, "is_active": True,
        "kind": "html", "pdf_template_id": None, "created_at": "2026-10-19T12:00:00",
        "updated_at": "2026-10-19T12:00:00"}]}}), encoding="utf-8")
    sp = txn.begin_nested()
    load_snapshot(snap, conn=txn, log=lambda *_: None)               # replaces the seeded row d with the snapshot's x
    sp.rollback()                                                    # d is back
    seq = txn.execute(text("SELECT pg_get_serial_sequence('report_templates', 'id')")).scalar()
    assert txn.execute(text(f"SELECT last_value FROM {seq}")).scalar() >= d
