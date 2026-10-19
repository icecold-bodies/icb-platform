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
