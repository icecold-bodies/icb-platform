"""RT10 (RT10_RULING_1 Q3 ii) — the read-only prod check of revisions (ops/prod-rt10).

  1. the allow-lists: no personal column or key, with a negative control;
  2. the findings, on hand-made chains: older accepted while a newer live revision existed, a job built from an
     older revision, live duplicate versions — each with the negative controls the rule needs (accepted BEFORE the
     newer one existed; the newer one deleted before the accept; deleted duplicates);
  3. the real reads against the test database (marker rows RT10T*, created and removed here), in a read-only
     session; a session that is not read-only is refused (negative control);
  4. the laptop line: ASCII, files run by path (no inline script), every name it acts on fixed; the runbook's block.
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from test_ops_rt6 import needs_bash  # noqa: F401  (shared bash helpers)
from test_ops_rt9 import BLOCK, inline_script_calls

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "ops" / "prod-rt10"
RUNBOOK = ROOT / "docs" / "runbooks" / "prod-check-rt10.md"
STAGE = r"C:\Users\micge\Documents\icb-rt10-stage\check"


def _load():
    spec = importlib.util.spec_from_file_location("rt10_revisions", KIT / "rt10_revisions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rv = _load()
T0 = datetime(2026, 10, 19, 9, 0, 0)


def row(i, qn, version, created_h, *, accepted_h=None, deleted_h=None, status="pending"):
    return {"id": i, "quote_number": qn, "status": status, "version": version,
            "created_at": T0 + timedelta(hours=created_h),
            "approved_at": None if accepted_h is None else T0 + timedelta(hours=accepted_h),
            "deleted_at": None if deleted_h is None else T0 + timedelta(hours=deleted_h), "is_repair": False}


def job(i, calc_id, created_h):
    return {"id": i, "calculation_record_id": calc_id, "status": "accepted", "accepted_at": None,
            "created_at": T0 + timedelta(hours=created_h)}


# ── 1. the allow-lists ───────────────────────────────────────────────────────
def test_the_allowlists_carry_no_personal_column_and_the_sql_reads_only_them():
    rv.assert_allowlist_clean(rv.CALC_COLUMNS, rv.RESULT_KEYS, rv.JOB_COLUMNS)
    for sql, cols in ((rv.SQL_CALCS, rv.CALC_COLUMNS), (rv.SQL_JOBS, rv.JOB_COLUMNS)):
        selected = re.match(r"SELECT (.*?) FROM", sql).group(1)
        assert [c.split(".", 1)[1] for c in selected.split(", ")] == list(cols)
    assert "customer" not in rv.SQL_CALCS + rv.SQL_JOBS + rv.SQL_COUNTS


@pytest.mark.parametrize("bad", ["customer_id", "contact_name", "user_id", "sales_rep_user_id", "decline_reason",
                                 "pre_job_signoff_sales_by", "end_user_company", "customer_name"])
def test_negative_control_a_personal_column_is_refused(bad):
    with pytest.raises(RuntimeError, match="personal-looking"):
        rv.assert_allowlist_clean(rv.CALC_COLUMNS + (bad,))


def test_only_the_version_key_is_read_from_the_saved_copy():
    assert rv.version_of(json.dumps({"version": 3, "customer_name": "X", "input_state": {"a": 1}})) == 3
    assert rv.version_of(json.dumps({"items": []})) == 1              # no key: version 1, as the API reads it
    assert rv.version_of("{not json") is None


# ── 2. the findings ──────────────────────────────────────────────────────────
def test_an_older_revision_accepted_while_a_newer_live_one_existed_is_named_and_its_job_too():
    rows = [row(1, "A1/10/2026", 1, 0), row(2, "A1/10/2026", 2, 5, ), ]
    rows[0]["approved_at"] = T0 + timedelta(hours=6)                    # REV 0 accepted after REV 1 was saved
    found = rv.analyse(rows, [job(9, 1, 6.1)])
    assert [(a["row"]["id"], a["newer"]["id"]) for a in found["older_accepted"]] == [(1, 2)]
    assert [(a["job"]["id"], a["row"]["id"], a["newer"]["id"]) for a in found["older_jobs"]] == [(9, 1, 2)]
    lines = rv.render((2, 2, 1), found)
    assert any("id 1 v1 REV 0 accepted 2026-10-19 15:00:00; id 2 v2 REV 1" in ln for ln in lines), lines
    assert lines[-1].startswith("SUMMARY: 2 costings; 1 quote numbers with 2+ rows; 0 live duplicate versions; "
                                "1 accepted while a newer live revision existed; 1 jobs built from an older revision")


def test_negative_controls_accepted_before_the_newer_existed_or_after_it_was_deleted_is_not_named():
    before = [row(1, "B1/10/2026", 1, 0, accepted_h=2), row(2, "B1/10/2026", 2, 5)]
    gone = [row(3, "C1/10/2026", 1, 0, accepted_h=8), row(4, "C1/10/2026", 2, 5, deleted_h=7)]
    found = rv.analyse(before + gone, [job(9, 1, 2.5), job(10, 3, 8.5)])
    assert found["older_accepted"] == [] and found["older_jobs"] == []
    # and the latest itself accepted: nothing to name
    latest = [row(5, "D1/10/2026", 1, 0), row(6, "D1/10/2026", 2, 5, accepted_h=6)]
    assert rv.analyse(latest, [job(11, 6, 6.5)])["older_accepted"] == []


def test_live_duplicate_versions_are_listed_and_deleted_ones_are_not():
    # Michael's 22 Oct shape: the original (v1) live, three v2 saves — two live here, one deleted
    rows = [row(1, "N1/10/2026", 1, 0), row(2, "N1/10/2026", 2, 70), row(3, "N1/10/2026", 2, 71),
            row(4, "N1/10/2026", 2, 72, deleted_h=73)]
    found = rv.analyse(rows, [])
    assert found["dup_live"] == [{"quote_number": "N1/10/2026", "version": 2, "ids": [2, 3]}]
    # NC: all three v2 deleted (prod after the 22 Oct close) → no live duplicate
    for r in rows[1:]:
        r["deleted_at"] = T0 + timedelta(hours=80)
    assert rv.analyse(rows, [])["dup_live"] == []


def test_a_tie_on_version_goes_to_the_newer_created_time_like_the_latest_rule():
    rows = [row(1, "E1/10/2026", 2, 0), row(2, "E1/10/2026", 2, 3)]
    rows[0]["approved_at"] = T0 + timedelta(hours=4)
    found = rv.analyse(rows, [])
    assert [(a["row"]["id"], a["newer"]["id"]) for a in found["older_accepted"]] == [(1, 2)]


# ── 3. the real reads, on the test database ─────────────────────────────────
def _dsn() -> str:
    from app.config import settings
    return settings.DATABASE_URL.replace("postgresql+psycopg:", "postgresql:", 1)


@pytest.fixture()
def marked():
    import psycopg
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM icb_mes.production_jobs WHERE calculation_record_id IN "
                        "(SELECT id FROM icb_costings.calculations WHERE quote_number LIKE 'RT10T%')")
            cur.execute("DELETE FROM icb_costings.calculations WHERE quote_number LIKE 'RT10T%'")
            ids = []
            for qn, ver, created_h, accepted_h, deleted_h in (
                    ("RT10T-1", 1, 0, 6, None), ("RT10T-1", 2, 5, None, None),      # REV 0 accepted after REV 1
                    ("RT10T-2", 1, 0, None, None), ("RT10T-2", 2, 1, None, None), ("RT10T-2", 2, 2, None, None)):
                cur.execute(
                    "INSERT INTO icb_costings.calculations (quote_number, status, created_at, approved_at, deleted_at, "
                    "is_repair, result_json, dimensions_json, contact_name) VALUES (%s, %s, %s, %s, %s, false, %s, '{}', "
                    "'RT10T PERSON') RETURNING id",
                    (qn, "accepted" if accepted_h is not None else "pending", T0 + timedelta(hours=created_h),
                     None if accepted_h is None else T0 + timedelta(hours=accepted_h),
                     None if deleted_h is None else T0 + timedelta(hours=deleted_h),
                     json.dumps({"version": ver, "customer_name": "RT10T PERSON"})))
                ids.append(cur.fetchone()[0])
            cur.execute("SELECT id FROM icb_costings.branches ORDER BY id LIMIT 1")
            branch = cur.fetchone()[0]
            cur.execute("INSERT INTO icb_mes.production_jobs (calculation_record_id, branch_id, status, created_at) "
                        "VALUES (%s, %s, 'accepted', %s) RETURNING id", (ids[0], branch, T0 + timedelta(hours=6, minutes=5)))
            job_id = cur.fetchone()[0]
        conn.commit()
    yield {"ids": ids, "job": job_id}
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM icb_mes.production_jobs WHERE id = %s", (job_id,))
            cur.execute("DELETE FROM icb_costings.calculations WHERE quote_number LIKE 'RT10T%'")
        conn.commit()


def test_the_real_reads_in_a_read_only_session_name_the_marked_rows_and_print_no_names(marked):
    import psycopg
    with psycopg.connect(_dsn(), options="-c default_transaction_read_only=on") as conn:
        counts, rows, jobs = rv.read(conn)
        conn.rollback()
    mine = [r for r in rows if r["quote_number"].startswith("RT10T")]
    assert [(r["quote_number"], r["version"]) for r in mine] == [("RT10T-1", 1), ("RT10T-1", 2), ("RT10T-2", 1),
                                                                ("RT10T-2", 2), ("RT10T-2", 2)]
    assert all(set(r) == set(rv.CALC_COLUMNS) - {"result_json"} | {"version"} for r in mine)
    found = rv.analyse(mine, [j for j in jobs if j["calculation_record_id"] in marked["ids"]])
    assert [a["row"]["id"] for a in found["older_accepted"]] == [marked["ids"][0]]
    assert [a["job"]["id"] for a in found["older_jobs"]] == [marked["job"]]
    assert found["dup_live"] == [{"quote_number": "RT10T-2", "version": 2, "ids": marked["ids"][3:5]}]
    text = "\n".join(rv.render(counts, found))
    assert "RT10T PERSON" not in text and "job " + str(marked["job"]) + " built from this row" in text


def test_negative_control_a_session_that_is_not_read_only_is_refused(marked):
    import psycopg
    with psycopg.connect(_dsn()) as conn:
        with pytest.raises(RuntimeError, match="not read-only"):
            rv.read(conn)


# ── 4. the laptop line, the VM helper, the runbook block ─────────────────────
def test_the_line_is_ascii_runs_files_by_path_and_never_pipes_the_sudo_session():
    raw = (KIT / "run_check.ps1").read_bytes()
    assert all(b < 0x80 for b in raw), "run_check.ps1 is not ASCII (Windows PowerShell 5.1 reads it as ANSI)"
    text = raw.decode("ascii")
    assert inline_script_calls(text) == []
    remotes = re.findall(r"'((?:sudo )?bash /tmp/[^']+)'", text)
    assert remotes == ["bash /tmp/icb-rt10-vm.sh where", "bash /tmp/icb-rt10-vm.sh unpack",
                       "sudo bash /tmp/icb-rt10-check/rt10_check.sh", "bash /tmp/icb-rt10-vm.sh readback"]
    assert text.count("192.168.0.251") == 1 and "$Vm     = 'mickeyger@192.168.0.251'" in text   # the sim's one host line
    assert "& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm 'sudo bash" in text and "| Out-Host" not in text
    assert "& scp -q" not in text                               # RT9's finding: -q hides ssh's own reason


def test_the_vm_helper_acts_only_on_fixed_names():
    text = (KIT / "rt10_vm.sh").read_text(encoding="utf-8")
    names = re.search(r'NAMES="([^"]*)"', text).group(1).replace("$REPORT", "/tmp/icb-rt10-check-report.txt").split()
    assert names == ["/tmp/icb-rt10-check", "/tmp/icb-rt10-check.tar", "/tmp/icb-rt10-check-report.txt"]
    check = (KIT / "rt10_check.sh").read_text(encoding="utf-8")
    assert 'rm -rf --one-file-system -- "$BASE" "$BASE.tar"' in check and "BASE=/tmp/icb-rt10-check" in check
    assert "set -e\n" not in check and "set -e\n" not in text


def test_the_runbook_block_is_the_agreed_shape_and_names_the_stage_line():
    md = RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = list(BLOCK.finditer(md))
    assert len(blocks) == 1, [b["cmd"] for b in blocks]
    b = blocks[0]
    assert b["win"].startswith("PowerShell (your laptop)")
    assert b["cmd"] == f'powershell -NoProfile -ExecutionPolicy Bypass -File "{STAGE}\\run_check.ps1"'
    assert all(0x20 <= ord(c) < 0x7F for c in b["cmd"])
    line = (KIT / "run_check.ps1").read_text(encoding="ascii")
    assert b["first"].startswith("######## RT10 prod check (read only)") and "######## RT10 prod check (read only)" in line
    assert b["ends"].startswith("######## DONE - read only.") and "######## DONE - read only." in line
    assert "VM password" in b["asks"]
