"""v1.59 — the shared pieces the admin page adds to the audit tool, tested at tool level.

  * the stored-dict renderers ARE the CLI's writers (byte for byte), so the page's
    report is the CLI's report;
  * "changed since the previous run" classification;
  * merging packs for the page's "All";
  * the snapshot loader can list what it inserted and unload exactly that.
"""
import json
from datetime import date

import pytest
from sqlalchemy import text

from tools.costing_audit.accepted import Accepted
from tools.costing_audit.changes import changes_between
from tools.costing_audit.compare import build_report
from tools.costing_audit.mes_probe import MesLine, MesResult
from tools.costing_audit.report import render_csv_doc, render_html_doc, write_csv, write_html
from tools.costing_audit.runner import merge_reports

SHEET = "TEST BODY"


def _golden(sid: str, sections: dict[str, float]) -> dict:
    return {"scenario": {"id": sid, "sheet": SHEET, "trailer_id": 999, "variant": "as_sheet",
                         "length": 5.0, "width": 2.0, "height": 2.0, "door": "drd", "foam": "32D",
                         "panels": {}, "flags": {}, "gate_mode": "as_sheet", "section_map": {}},
            "grand_total": sum(sections.values()), "findings": [],
            "sections": {k: {"total": v, "raw_total": v, "status": "OK", "reason": None, "gates": {},
                             "lines": [{"desc": "SKIN", "qty": 1.0, "price": v, "total": v, "stale": False}],
                             "multiplier": 1.0}
                         for k, v in sections.items()}}


def _mes(sections: dict[str, float]) -> MesResult:
    lines = [MesLine(section=k, desc="SKIN", qty=1.0, price=v, total=v) for k, v in sections.items()]
    return MesResult(trailer_id=999, trailer_name="TEST", sections=dict(sections),
                     grand_total=sum(sections.values()), lines=lines, payload={})


def _report(pack="smoke", mes_total=1000.0, excel_total=1000.0, sid="s1", extra_section=None,
            accepted=None, tolerance=1.0):
    g = _golden(sid, {"FLOOR": excel_total, "ROOF": 500.0})
    secs = {"FLOOR": mes_total, "ROOF": 500.0}
    if extra_section:
        secs[extra_section] = 42.0
    return build_report(pack_name=pack, tolerance_pct=tolerance, manifest={"generated_at": "2026-09-25T14:09:05+00:00"},
                        mes_source="test", goldens={sid: g}, results={sid: _mes(secs)}, scenario_ids=[sid],
                        accepted=accepted or [], warnings=[], today=date(2026, 9, 27))


# ── renderers: stored JSON -> the CLI's exact bytes ──────────────────────────

def test_stored_json_renders_the_cli_bytes(tmp_path):
    rep = _report(mes_total=1100.0)
    write_html(rep, tmp_path / "r.html")
    write_csv(rep, tmp_path / "r.csv")
    stored = json.loads(json.dumps(rep.to_dict(), default=str))      # what the admin page keeps (gzipped)
    # HTML: write_text translates newlines on Windows, so compare as text (identical bytes on Linux)
    assert render_html_doc(stored) == (tmp_path / "r.html").read_text(encoding="utf-8")
    # CSV: written with newline="" everywhere, so the bytes are identical on every platform
    assert render_csv_doc(stored).encode("utf-8") == (tmp_path / "r.csv").read_bytes()
    assert "window.__AUDIT__" in render_html_doc(stored)


# ── changes between runs ─────────────────────────────────────────────────────

def _cells(rep):
    return rep.to_dict()


def test_no_change_between_identical_runs():
    a, b = _cells(_report(mes_total=1100.0)), _cells(_report(mes_total=1100.0))
    assert changes_between(a, b, 1.0) == []


def test_status_change_is_reported_with_both_deltas():
    prev, cur = _cells(_report(mes_total=1100.0)), _cells(_report(mes_total=1000.0))
    ch = changes_between(prev, cur, 1.0)
    assert [(c["kind"], c["section"], c["old_status"], c["new_status"]) for c in ch] == \
        [("status", "FLOOR", "FLAG", "PASS")]
    assert ch[0]["old_delta"] == 100.0 and ch[0]["new_delta"] == 0.0


def test_moved_beyond_tolerance_is_reported_and_within_is_not():
    prev = _cells(_report(mes_total=1100.0))                         # FLAG, +100
    far = changes_between(prev, _cells(_report(mes_total=1150.0)), 1.0)   # FLAG, +150 -> moved R50 > R10
    near = changes_between(prev, _cells(_report(mes_total=1105.0)), 1.0)  # FLAG, +105 -> moved R5 <= R10
    assert [(c["kind"], c["old_delta"], c["new_delta"]) for c in far] == [("moved", 100.0, 150.0)]
    assert near == []


def test_new_and_vanished_cells():
    prev = _cells(_report())
    cur = _cells(_report(extra_section="NEW BITS"))
    ch = changes_between(prev, cur, 1.0)
    assert [(c["kind"], c["section"]) for c in ch] == [("new", "NEW BITS")]
    back = changes_between(cur, prev, 1.0)
    assert [(c["kind"], c["section"], c["old_status"]) for c in back] == [("vanished", "NEW BITS", "PRESENCE")]


def test_acceptance_turning_a_flag_grey_is_a_status_change():
    prev = _cells(_report(mes_total=1100.0))
    acc = [Accepted(body=SHEET, section="FLOOR", variant="*", reason="known", owner="BA",
                    review_by=date(2026, 10, 31), index=0)]
    cur = _cells(_report(mes_total=1100.0, accepted=acc))
    ch = changes_between(prev, cur, 1.0)
    assert [(c["old_status"], c["new_status"]) for c in ch] == [("FLAG", "ACCEPTED")]


# ── merging packs ("All") ────────────────────────────────────────────────────

def test_merge_keeps_every_cell_and_each_packs_golden():
    a = _report(pack="chillers", sid="a1")
    b = _report(pack="freezers", sid="b1", mes_total=1100.0)
    b.warnings.append("golden is stale")
    m = merge_reports([a, b])
    assert m.pack == "all"
    assert len(m.cells) == len(a.cells) + len(b.cells)
    assert set(m.golden_manifest["packs"]) == {"chillers", "freezers"}
    assert m.exit_code == 1                      # b's FLAG survives the merge
    assert "freezers: golden is stale" in m.warnings


# ── snapshot: list what was inserted, unload exactly that ────────────────────

def _fingerprint(conn, tables):
    out = {}
    for t in tables:
        out[t] = conn.execute(text(
            f"SELECT count(*), md5(coalesce(string_agg(md5(x::text), '' ORDER BY md5(x::text)), '')) "
            f"FROM {t} x")).one()
    return tuple(out.items())


def test_unload_removes_exactly_what_load_inserted():
    from app.database import engine
    from tools.costing_audit.mes_snapshot import load_snapshot, snapshot_path, unload_snapshot
    doc = json.loads(snapshot_path("all").read_text(encoding="utf-8"))
    tables = [f"icb_costings.{n}" for n in doc["tables"]]
    with engine.connect() as c:
        before = _fingerprint(c, tables)
    inserted: dict = {}
    load_snapshot(snapshot_path("all"), inserted=inserted, log=lambda *_: None)
    try:
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM icb_costings.trailer_types WHERE id = ANY(:ids)"),
                             {"ids": doc["trailer_ids"]}).scalar() == len(doc["trailer_ids"])
    finally:
        unload_snapshot(inserted, log=lambda *_: None)
    with engine.connect() as c:
        after = _fingerprint(c, tables)
    assert after == before


def test_load_with_rollback_lists_nothing():
    from tools.costing_audit.mes_snapshot import load_snapshot, snapshot_path
    inserted: dict = {}
    load_snapshot(snapshot_path("all"), rollback=True, inserted=inserted, log=lambda *_: None)
    assert inserted == {}
