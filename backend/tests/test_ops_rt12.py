"""RT12 — the v1.63.0 release kit (ops/prod-release-v1.63.0) and Michael's paste blocks. Each test carries its
negative control (F6): the same check pointed at a known-bad input must fail.

  1. The probe list is the code: every line of probe_paths.txt (47, unchanged from v1.62.0) answers its listed status
     with no session, Accept JSON (NC: a flipped status is caught). No route is new in this range, so release.sh allows
     NO 404 before the deploy (NC: with a route named new, its 404 is allowed, and only its).
  2. Cloudflare keeps the first bytes per URL for 4 h: release.sh asks a door for a static's new ?v= ONLY once the page
     on disk loads that ?v= and the disk holds the new bytes — for calculator2.js as for calculator.js (NC: with them on
     disk, the request is made).
  3. Tracebacks: a CHAINED traceback (anyio.WouldBlock -> anyio.EndOfStream -> starlette.requests.ClientDisconnect) and
     an exception group list EVERY class, time + class only, never the message (G4). RT9's queued finding: its list
     knew only *Error/*Exception/... names and printed "(exception line not found)" — the NC runs RT9's own function
     on the same journal. Only tracebacks since this deploy's restart count (NC: one after the restart fails).
  4. The quotes check names the rows itself (RT9's lesson): the deploy records "id md5" per row; verify names what was
     added, changed or removed since — id, the quote number's first word, created, version, status, deleted Y/N — and
     the SQL reads no other column (G4: the allow-list is asserted on the SQL text, and the SQL runs on the test
     database against marker rows, a repair whose quote number carries a customer's name included).
  5. The window lines never hand a script to ssh as an argument (RT8); no scp runs -q (RT9: it hid ssh's reason); the
     kit never chowns and never writes a file directly in /tmp (RT10: fs.protected_regular=2). NC: RT9's kit has scp -q.
  6. rt12_vm.sh: the cleanup acts on exact /tmp/icb-* names of THIS window only; fetch takes a checked name.
  7. The runbook's paste blocks: ASCII, no placeholder, the full stage path, a step word the line knows, and the first
     and last lines the .ps1 really prints; the view-only acceptance's own line (NC: a placeholder / unknown step).
Bash parts run the real kit functions in Git Bash with stubs on PATH (skipped where there is no bash).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from test_ops_rt6 import needs_bash, posix, run, stub  # noqa: F401  (shared bash helpers)

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "ops" / "prod-release-v1.63.0"
RELEASE = KIT / "release.sh"
PROBES = KIT / "probe_paths.txt"
WINDOW = KIT / "window"
LOCAL = KIT / "local"
RUNBOOK = ROOT / "docs" / "runbooks" / "prod-deploy-v1.63.0.md"
OLD_KIT = ROOT / "ops" / "prod-release-v1.62.0"            # RT9's kit: the negative controls' known-bad shapes
JSON = {"accept": "application/json"}
REPRICE = "/api/calculations/1/reprice-preview"


def probe_lines(text: str) -> list[tuple[str, str, str]]:
    """(status, method, path) per line; a line is '<status> <path>' (GET) or '<status> <METHOD> <path>'."""
    out = []
    for raw in text.splitlines():
        parts = raw.split()
        if not parts or parts[0].startswith("#"):
            continue
        out.append((parts[0], parts[1], parts[2]) if len(parts) == 3 else (parts[0], "GET", parts[1]))
    return out


def functions(path: Path, *names: str) -> str:
    """The named shell functions, verbatim from a script (one-liners end on their line; others at a lone '}')."""
    lines, out = path.read_text(encoding="utf-8").splitlines(), []
    for name in names:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(f"{name}() {{"))
        if lines[start].rstrip().endswith("}") and lines[start].count("{") == lines[start].count("}"):
            out.append(lines[start])
            continue
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
        out.extend(lines[start:end + 1])
    return "\n".join(out) + "\n"


# ── 1. the probe list is the code ───────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as c:
        yield c


def mismatches(client, lines) -> list[str]:
    bad = []
    for want, method, path in lines:
        kw = {"json": {}} if method != "GET" else {}
        got = client.request(method, path, headers=JSON, follow_redirects=False, **kw).status_code
        if str(got) != want:
            bad.append(f"{method} {path} = {got}, listed {want}")
    return bad


def test_every_probe_line_answers_its_listed_status_with_no_session(client):
    lines = probe_lines(PROBES.read_text(encoding="utf-8"))
    assert len(lines) == 47 and ("401", "POST", REPRICE) in lines and ("401", "GET", "/openapi.json") in lines
    # v1.63.0 adds no route: the list is v1.62.0's, line for line
    assert lines == probe_lines((OLD_KIT / "probe_paths.txt").read_text(encoding="utf-8"))
    assert mismatches(client, lines) == []
    # NC: a line whose status is wrong is caught (the check can fail)
    flipped = [("200", m, p) if p == "/api/calculations" else (w, m, p) for w, m, p in lines]
    assert mismatches(client, flipped) == ["GET /api/calculations = 401, listed 200"]


CURL = r'''
method=GET; url=; out=; fmt=
while [ $# -gt 0 ]; do case "$1" in -X) method=$2; shift;; -o) out=$2; shift;; -w) fmt=$2; shift;;
  --data-binary) body=$2; shift;; --max-time|-H) shift;; -*) ;; *) url=$1;; esac; shift; done
echo "$method $url ${body:-}" >> "$CURLLOG"
path="/${url#https://*/}"
code=$(awk -v m="$method" -v p="$path" '$1 == m && $2 == p { print $3; exit }' "$ANSWERS")
if [ -n "$out" ] && [ "$out" != /dev/null ]; then : > "$out"; fi
[ -n "$fmt" ] && printf '%s' "${code:-401}"
case "$url" in */static/*) cat "$STATICFILE" 2>/dev/null ;; esac
exit 0
'''


def noauth(tmp_path: Path, probes: str, answers: str, before: str, new_probes: str = "") -> tuple[str, str]:
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "curl", CURL)
    (tmp_path / "probe_paths.txt").write_text(probes, encoding="utf-8", newline="\n")
    (tmp_path / "answers").write_text(answers, encoding="utf-8", newline="\n")
    log = tmp_path / "curl.log"
    log.unlink(missing_ok=True)
    n = len(probe_lines(probes))
    script = (f'BASE="{posix(tmp_path)}"; N_PROBES={n}; NEW_PROBES="{new_probes}"; ANSWERS="{posix(tmp_path / "answers")}"; '
              f'CURLLOG="{posix(log)}"; export ANSWERS CURLLOG; ' + functions(RELEASE, "noauth_report")
              + f'noauth_report https://door {before}')
    r = run(script, path_dir=tmp_path / "bin")
    return r.stdout.strip(), (log.read_text(encoding="utf-8") if log.exists() else "")


PROBE_TXT = f"# comment\n401 /api/calculations\n401 POST {REPRICE}\n"


@needs_bash
def test_no_route_is_new_so_a_404_before_the_deploy_is_a_failure_everywhere(tmp_path):
    good = f"GET /api/calculations 401\nPOST {REPRICE} 401\n"
    out, log = noauth(tmp_path, PROBE_TXT, good, "before")
    assert out == "all 2 as expected", out
    assert f"POST https://door{REPRICE} {{}}" in log and "GET https://door/api/calculations" in log
    # before the deploy, with NEW_PROBES empty (this release), a 404 on any line is a failure
    out, _ = noauth(tmp_path, PROBE_TXT, f"GET /api/calculations 401\nPOST {REPRICE} 404\n", "before")
    assert out == f"POST {REPRICE}=404/401", out
    # NC: name that route as new (v1.62.0's situation) and the same 404 is allowed, and only before the deploy
    out, _ = noauth(tmp_path, PROBE_TXT, f"GET /api/calculations 401\nPOST {REPRICE} 404\n", "before", REPRICE)
    assert out == f"all 2 as expected (new in this release, 404 before the deploy: POST {REPRICE})", out
    out, _ = noauth(tmp_path, PROBE_TXT, f"GET /api/calculations 401\nPOST {REPRICE} 404\n", "", REPRICE)
    assert out == f"POST {REPRICE}=404/401", out


# ── 2. a new ?v= is never asked of a door before its bytes are on disk ──────
def static_on(tmp_path: Path, tmpl: str, path: str, v_on_disk: str, bytes_on_disk: bytes, ask_v: str, new: bytes) -> tuple[str, str]:
    repo = tmp_path / "repo"
    (repo / "backend/app/static/js").mkdir(parents=True, exist_ok=True)
    (repo / "backend/app/templates").mkdir(parents=True, exist_ok=True)
    (repo / "backend/app/templates" / tmpl).write_text(
        f'<script defer src="/static/{path}?v={v_on_disk}"></script>\n', encoding="utf-8", newline="\n")
    (repo / "backend/app/static" / path).write_bytes(bytes_on_disk)
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "curl", CURL)
    (tmp_path / "answers").write_text("", encoding="utf-8")
    log = tmp_path / "curl.log"
    log.unlink(missing_ok=True)
    sha = hashlib.sha256(new).hexdigest()
    script = (f'REPO="{posix(repo)}"; ANSWERS="{posix(tmp_path / "answers")}"; CURLLOG="{posix(log)}"; '
              f'STATICFILE="{posix(repo / "backend/app/static" / path)}"; export ANSWERS CURLLOG STATICFILE; '
              + functions(RELEASE, "sha_url", "static_v_disk", "static_sha_disk", "static_on")
              + f'static_on https://mes.icecoldgrp.online {tmpl} {path} {ask_v} {sha}')
    r = run(script, path_dir=tmp_path / "bin")
    return r.stdout.strip(), (log.read_text(encoding="utf-8") if log.exists() else "")


@needs_bash
def test_cloudflare_is_never_asked_for_a_new_v_before_the_bytes_are_on_disk(tmp_path):
    out, log = static_on(tmp_path, "calculator2.html", "js/calculator2.js", "128", b"old calc2\n", "129", b"new calc2\n")
    assert out.startswith("not probed (the page on disk loads ?v=128"), out
    assert log == "", log                     # no request at all: the edge cannot pin the old bytes under ?v=129
    out, log = static_on(tmp_path, "calculator.html", "js/calculator.js", "191", b"old calc\n", "192", b"new calc\n")
    assert out.startswith("not probed (the page on disk loads ?v=191") and log == "", (out, log)


@needs_bash
def test_negative_control_with_the_new_bytes_on_disk_the_door_is_asked(tmp_path):
    out, log = static_on(tmp_path, "calculator2.html", "js/calculator2.js", "129", b"new calc2\n", "129", b"new calc2\n")
    assert out == hashlib.sha256(b"new calc2\n").hexdigest(), out
    assert "GET https://mes.icecoldgrp.online/static/js/calculator2.js?v=129" in log, log


# ── 3. tracebacks: every class of a chain, time + class only, counted only since this deploy's restart ──
JOURNAL = r'''
since=0; until=99999999999
while [ $# -gt 0 ]; do case "$1" in --since) since=${2#@}; [ "$2" = now ] && since=99999999999; shift;;
  --until) until=${2#@}; [ "$2" = now ] && until=99999999999; shift;; esac; shift; done
while IFS= read -r line; do ep=${line%% *}; msg=${line#* }; [ "$msg" = "$line" ] && msg=
  [ "$ep" -ge "$since" ] && [ "$ep" -le "$until" ] && echo "Oct 2$((ep % 9)) 11:14:0$((ep % 7)) icb uvicorn[7]: $msg"; done < "$JOURNALFILE"
exit 0
'''
CHAIN = "\n".join(f"100 {m}" for m in (
    "Traceback (most recent call last):",
    '  File "/x/anyio/streams/memory.py", line 98, in receive',
    "    return self.receive_nowait()",
    "           ^^^^^^^^^^^^^^^^^^^^^",
    "anyio.WouldBlock",
    "",
    "During handling of the above exception, another exception occurred:",
    "",
    "Traceback (most recent call last):",
    '  File "/x/starlette/middleware/base.py", line 159, in call_next',
    "    message = await recv_stream.receive()",
    "anyio.EndOfStream",
    "",
    "During handling of the above exception, another exception occurred:",
    "",
    "Traceback (most recent call last):",
    '  File "/x/starlette/middleware/base.py", line 161, in call_next',
    "    raise app_exc",
    "starlette.requests.ClientDisconnect",
)) + "\n"
GROUP = "\n".join((
    '120 INFO:     127.0.0.1:51234 - "GET /api/trailers HTTP/1.1" 401 Unauthorized',
    "130   + Exception Group Traceback (most recent call last):",
    '130   |   File "/x/anyio/_backends/_asyncio.py", line 767, in __aexit__',
    "130   |     raise BaseExceptionGroup(",
    "130   | ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)",
    "130   +-+---------------- 1 ----------------",
    "130     | Traceback (most recent call last):",
    '130     |   File "/x/h11/_connection.py", line 1, in f',
    "130     | KeyError: 'customer-name-would-be-here'",
    "130     +------------------------------------",
)) + "\n"


def tracebacks(tmp_path: Path, journal: str, script_tail: str, release: Path = RELEASE) -> subprocess.CompletedProcess:
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "journalctl", JOURNAL)
    (tmp_path / "journal").write_text(journal, encoding="utf-8", newline="\n")
    script = (f'SERVICE=icb-backend; MODE=verify; FAILS=0; JOURNALFILE="{posix(tmp_path / "journal")}"; export JOURNALFILE; '
              + functions(release, "journal_since", "tb_since", "tb_list", "check", "tracebacks") + script_tail)
    return run(script, path_dir=tmp_path / "bin")


@needs_bash
def test_a_chained_traceback_and_an_exception_group_list_every_class_without_the_message(tmp_path):
    r = tracebacks(tmp_path, CHAIN + GROUP + "300 INFO:     Application startup complete.\n", 'tracebacks 200; echo "fails=$FAILS"')
    listed = [ln for ln in r.stdout.splitlines() if "pre-existing  " in ln]
    classes = [ln.split("  ")[-1] for ln in listed]
    assert classes == ["anyio.WouldBlock", "anyio.EndOfStream", "starlette.requests.ClientDisconnect", "ExceptionGroup", "KeyError"], r.stdout
    assert "(exception line not found)" not in r.stdout and "customer-name-would-be-here" not in r.stdout   # G4
    assert "INFO" not in "".join(classes) and "(listed, not counted): 5" in r.stdout
    assert "PASS TRACEBACKS_SINCE_RESTART = 0" in r.stdout and "fails=0" in r.stdout


@needs_bash
def test_negative_control_rt9s_list_misses_the_chain_halves_and_a_traceback_after_the_restart_fails(tmp_path):
    # RT9's own tb_list (ops/prod-release-v1.62.0) on the same chained journal: the WouldBlock and EndOfStream halves
    # read "(exception line not found)" — the 22 Oct output, reproduced (the function is read from RT9's kit as committed)
    old = tracebacks(tmp_path, CHAIN + "300 INFO:     Application startup complete.\n", 'tb_list @0 @200', OLD_KIT / "release.sh")
    assert old.stdout.count("(exception line not found)") == 2 and "starlette.requests.ClientDisconnect" in old.stdout, old.stdout
    # and with RT12's kit a traceback AFTER the restart fails the check, named by class on its "since the restart" line
    r = tracebacks(tmp_path, CHAIN + "250 Traceback (most recent call last):\n250 ValueError: x\n", 'tracebacks 200; echo "fails=$FAILS"')
    assert "since the restart:  " in r.stdout and "  ValueError" in r.stdout, r.stdout
    assert "FAIL TRACEBACKS_SINCE_RESTART = '1'" in r.stdout and "fails=1" in r.stdout, r.stdout


# ── 4. the quotes check names the rows itself (RT9's lesson) ────────────────
ALLOWED_COLUMNS = {"id", "quote_number", "created_at", "result_json", "status", "deleted_at"}


def kit_sql() -> tuple[str, str]:
    """ROWS_SQL and the naming statement (its $1 left in place), as release.sh carries them."""
    text = RELEASE.read_text(encoding="utf-8")
    rows = re.search(r'^ROWS_SQL="(.*)"$', text, re.M).group(1)
    fn = functions(RELEASE, "name_rows_sql")
    echo = re.search(r'echo "(select .*)"\s*$', fn, re.M).group(1).replace('\\"', '"')
    return rows, echo


def test_the_naming_sql_reads_only_the_allow_listed_columns():
    rows, name = kit_sql()
    assert rows == "select c.id || ' ' || md5(c::text) from icb_costings.calculations c order by c.id"
    cols = set(re.findall(r"\bc\.([a-z_]+)", name))
    assert cols == ALLOWED_COLUMNS, cols
    assert "split_part(coalesce(c.quote_number, '(none)'), ' ', 1)" in name     # a repair's number carries a name: first word only
    assert "substring(c.result_json from '\"version\": *([0-9]+)')" in name    # one key out of result_json's text
    assert re.search(r"customer|contact|user|email|phone|rep\b|name\b|notes|net_total|selling", name) is None
    # NC: the same scan flags a statement that reaches for a person
    assert set(re.findall(r"\bc\.([a-z_]+)", name + " || c.contact_name")) - ALLOWED_COLUMNS == {"contact_name"}


PSQL = r'''
sql=; while [ $# -gt 0 ]; do case "$1" in -c) sql=$2; shift;; esac; shift; done
case "$sql" in
  *"md5(c::text) from icb_costings.calculations c order by c.id"*) cat "$ROWS_NOW" ;;
  *split_part*"where c.id in ("*) ids=${sql##*where c.id in (}; ids=${ids%%)*}
      for i in $(tr ',' ' ' <<<"$ids"); do grep "^$i | " "$NAMES"; done ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
'''


@needs_bash
def test_verify_names_the_rows_added_changed_and_removed_since_the_deploy(tmp_path):
    (tmp_path / "bin").mkdir()
    stub(tmp_path / "bin", "psql", PSQL)
    deploy = tmp_path / "rows_at_deploy"
    deploy.write_text("1 aaaa\n2 bbbb\n3 cccc\n", encoding="utf-8", newline="\n")
    (tmp_path / "rows_now").write_text("1 aaa1\n3 cccc\n4 dddd\n", encoding="utf-8", newline="\n")
    (tmp_path / "names").write_text("1 | N10021/10/2026 | 2026-10-19 15:02:44 | 1 | pending | Y\n"
                                    "4 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N\n", encoding="utf-8", newline="\n")
    out = tmp_path / "out"; out.mkdir()
    rows_sql, _ = kit_sql()
    script = (f'OUT="{posix(out)}"; URL=x; ROWS_NOW="{posix(tmp_path / "rows_now")}"; NAMES="{posix(tmp_path / "names")}"; '
              f'export ROWS_NOW NAMES; ROWS_SQL="{rows_sql}"; ' + functions(RELEASE, "q", "name_rows_sql", "quotes_rows_report")
              + f'quotes_rows_report "{posix(deploy)}"')
    r = run(script, path_dir=tmp_path / "bin")
    lines = r.stdout.splitlines()
    assert lines[0] == "   since the deploy: added 1 row(s), changed 1, removed 1  (id | quote | created as stored | version | status | deleted)", r.stdout
    assert lines[1:] == ["   -- added: 4", "      4 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N",
                         "   -- changed: 1", "      1 | N10021/10/2026 | 2026-10-19 15:02:44 | 1 | pending | Y",
                         "   -- removed: 2", "      (a removed row cannot be named from the live table: ids only)"], r.stdout
    # NC: nothing moved -> the report says so and names nothing
    (tmp_path / "rows_now").write_text("1 aaaa\n2 bbbb\n3 cccc\n", encoding="utf-8", newline="\n")
    r = run(script, path_dir=tmp_path / "bin")
    assert r.stdout.splitlines() == ["   since the deploy: added 0 row(s), changed 0, removed 0  (id | quote | created as stored | version | status | deleted)"]


def test_the_naming_sql_runs_on_the_test_database_and_prints_only_the_allow_list(client):
    """Marker rows (RT12Q) on the live test DB: a body quote at version 2 and a soft-deleted repair whose quote number
    carries a (made-up) customer's name; the kit's two statements run as written (driver SQL: psql sends them raw)."""
    from app.database import CalculationRecord, SessionLocal
    rows_sql, name = kit_sql()
    created = datetime(2026, 10, 24, 9, 30, 0)
    with SessionLocal() as db:
        r1 = CalculationRecord(quote_number="N99912/10/2026", status="pending", created_at=created,
                               result_json=json.dumps({"version": 2, "grand_total": 1.0, "customer_name": "RT12Q Never Printed"}))
        r2 = CalculationRecord(quote_number="R-9912 RT12Q Example Farming (Pty) Ltd 001 ICB GP", status="pending", created_at=created,
                               result_json=json.dumps({"version": 1}), deleted_at=datetime.now(timezone.utc), deleted_by="RT12Q Person")
        db.add_all([r1, r2])
        db.commit()
        ids = [r1.id, r2.id]
        try:
            conn = db.connection()
            rows = [r[0] for r in conn.exec_driver_sql(rows_sql).fetchall()]
            named = [r[0] for r in conn.exec_driver_sql(name.replace("$1", ",".join(map(str, ids)))).fetchall()]
        finally:
            db.rollback()
            db.query(CalculationRecord).filter(CalculationRecord.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
    assert all(re.fullmatch(r"\d+ [0-9a-f]{32}", r) for r in rows) and {int(r.split()[0]) for r in rows} >= set(ids)
    assert named == [f"{ids[0]} | N99912/10/2026 | 2026-10-24 09:30:00 | 2 | pending | N",
                     f"{ids[1]} | R-9912 | 2026-10-24 09:30:00 | 1 | pending | Y"], named
    assert "RT12Q" not in "\n".join(named) and "Example" not in "\n".join(named) and "Person" not in "\n".join(named)   # G4


# ── 5. no inline script to ssh; no scp -q; no chown; nothing written directly in /tmp ──
_CALL = re.compile(r"&\s*(ssh|scp)\b(?P<rest>[^\r\n]*)")


def inline_script_calls(ps1: str) -> list[str]:
    """ssh calls whose remote command is not a plain `[sudo] bash /tmp/<file> <words>`: an inline script (a
    here-string or quoted text with shell syntax or double quotes) — the shape that ran nothing on 21 Oct."""
    bad = []
    here = dict(re.findall(r"\$(\w+)\s*=\s*@'\r?\n(.*?)\r?\n'@", ps1, re.S))
    for m in _CALL.finditer(ps1):
        tool, rest = m.group(1), re.sub(r"\s+\d?>\S+\s*$", "", m.group("rest"))   # drop a trailing 2>$errFile
        if tool == "scp":
            continue
        var = re.search(r"\$(\w+)\s*$", rest.strip())
        if var and var.group(1) in here:
            bad.append(f"{m.group(0).strip()}  (here-string ${var.group(1)})")
            continue
        if var and var.group(1) == "remote":       # run_window_step.ps1: the plan's fixed lines (checked below)
            continue
        q = re.search(r'"(?P<cmd>[^"]*)"\s*$', rest) or re.search(r"'(?P<cmd>[^']*)'\s*$", rest)
        cmd = q.group("cmd") if q else ""
        if not re.fullmatch(r"(sudo )?bash /tmp/[\w./-]+(?: [^\"`;&|#<>]*)?", cmd):
            bad.append(m.group(0).strip())
    return bad


def quiet_scp(ps1: str) -> list[str]:
    """scp calls that pass -q: it also silences ssh's own reason for a refused login (RT9, 22 Oct 12:12)."""
    return [m.group(0).strip() for m in re.finditer(r"&\s*scp\b[^\r\n]*", ps1) if re.search(r"\s-q\b", m.group(0))]


def test_the_window_lines_run_files_by_path_never_quiet_never_an_inline_script_and_are_ascii():
    ps1s = sorted(WINDOW.glob("*.ps1"))
    assert [p.name for p in ps1s] == ["run_window_cleanup.ps1", "run_window_copy.ps1", "run_window_fetch.ps1",
                                      "run_window_step.ps1", "window_common.ps1"]
    for p in ps1s + sorted(LOCAL.glob("*.ps1")):
        raw = p.read_bytes()
        assert all(b < 0x80 for b in raw), f"{p.name} is not ASCII (Windows PowerShell 5.1 reads it as ANSI)"
        text = raw.decode("ascii")
        assert inline_script_calls(text) == [], p.name
        assert quiet_scp(text) == [], p.name
    assert "ssh" not in (LOCAL / "check_8000.ps1").read_text(encoding="ascii").replace("ssh-", "")   # the :8000 line never reaches prod
    step = (WINDOW / "run_window_step.ps1").read_text(encoding="ascii")
    remotes = re.findall(r"'((?:sudo )?bash /tmp/[^']+)'", step)
    assert len(remotes) == 6 and all(re.fullmatch(r"sudo bash /tmp/icb-[a-z0-9.-]+/[a-z0-9_]+\.sh( [a-z]+)?", r) for r in remotes)
    assert "| Out-Host" not in step and "& ssh -t" in step      # no pipe: sudo needs the terminal


def test_negative_controls_rt8_v1_cleanup_shape_and_rt9s_quiet_scp_are_flagged():
    v1 = ("$Vm = 'mickeyger@192.168.0.251'\n$remote = @'\n"
          "sudo bash -c 'set -u; echo \"######## RT8 cleanup\"; rm -rf -- /tmp/x'\n'@\n& ssh -t $Vm $remote\n")
    assert len(inline_script_calls(v1)) == 1
    assert len(inline_script_calls("& ssh -o BatchMode=yes $Vm \"cd /tmp && tar -xf x.tar && echo 'ok'\"\n")) == 1
    # RT9's copy and fetch lines ran scp -q (the finding queued on 22 Oct): the same scan flags them
    assert quiet_scp((OLD_KIT / "window" / "run_window_copy.ps1").read_text(encoding="ascii")) == ['& scp -q -o BatchMode=yes @tars "${Vm}:/tmp/"']
    assert len(quiet_scp((OLD_KIT / "window" / "run_window_fetch.ps1").read_text(encoding="ascii"))) == 1


def test_the_kit_never_chowns_and_writes_only_under_its_own_folder():
    """prod runs fs.protected_regular=2 (RT10, 23 Oct): a root append to a /tmp file another user owns is refused."""
    rel = RELEASE.read_text(encoding="utf-8")
    vm = (WINDOW / "rt12_vm.sh").read_text(encoding="utf-8")
    code = lambda s: "\n".join(ln for ln in s.splitlines() if not ln.lstrip().startswith("#"))   # the scripts' code, not their comments
    assert not re.search(r"\bchown\b", code(rel)) and not re.search(r"\bchown\b", code(vm))
    # every redirect to a /tmp path in release.sh goes under $BASE (= /tmp/icb-release-v1.63.0) or $OUT, never bare /tmp
    for m in re.finditer(r">>?\s*\"?(/tmp/[^\s\"]*)", rel):
        assert m.group(1).startswith("/tmp/icb-release-v1.63.0/"), m.group(0)
    assert re.search(r"^RESTART_MARK=\$BASE/", rel, re.M) and re.search(r"^QUOTES_ROWS_MARK=\$BASE/", rel, re.M)
    assert "tee -a /tmp" not in rel and "tee -a /tmp" not in vm
    # NC: RT10's 23 Oct shape (a report in /tmp, chowned, then appended) is what the scan refuses
    bad = 'REPORT=/tmp/icb-rt10-check-report.txt\nchown "$owner" "$REPORT"\necho x | tee -a "$REPORT"\n'
    assert "chown" in bad and re.search(r"tee -a \"\$REPORT\"", bad)


# ── 6. rt12_vm.sh: exact names; checked fetch names ─────────────────────────
def test_the_cleanup_names_are_exact_and_cover_this_window_only():
    text = (WINDOW / "rt12_vm.sh").read_text(encoding="utf-8")
    block = re.search(r'NAMES="([^"]*)"', text, re.S).group(1)
    names = block.replace("$MARK", "/tmp/icb-rt12-window.started").split()
    assert all(re.fullmatch(r"/tmp/icb-[A-Za-z0-9.-]+", n) for n in names), names     # no glob, no other dir
    for k in ("icb-release-v1.63.0", "icb-rt2-all", "icb-rt2-doors"):
        assert f"/tmp/{k}" in names and f"/tmp/{k}.tar" in names, k
    assert "/tmp/icb-rt12-window.started" in names and len(names) == 7
    assert not any("v1.62.0" in n or "v1.61.1" in n or "rt9" in n for n in names)        # RT9 closed its own (22 Oct)
    assert re.search(r"case \"\$p\" in /tmp/icb-\*\) ;; \*\) stop CLEANUP", text)              # refuses anything else
    assert 'KITS="icb-release-v1.63.0 icb-rt2-all icb-rt2-doors"' in text


@needs_bash
def test_fetch_takes_only_a_checked_name(tmp_path):
    vm = posix(WINDOW / "rt12_vm.sh")
    r = run(f'bash "{vm}" fetch ../../etc/passwd; echo "rc=$?"')
    assert "STOP [FETCH]: fetch: the name must be rt12-window-back-" in r.stdout and "rc=1" in r.stdout
    # NC: a well-formed name passes the name check and reaches the next one (no window start mark here)
    r = run(f'bash "{vm}" fetch rt12-window-back-20261027-180000; echo "rc=$?"')
    assert "the name must be" not in r.stdout and "STOP [FETCH]" in r.stdout, r.stdout


# ── 7. the runbook's paste blocks ───────────────────────────────────────────
BLOCK = re.compile(r"PASTE INTO: (?P<win>[^\n]+)\n```\n(?P<cmd>[^\n]+)\n```\nFIRST LINE YOU SHOULD SEE: (?P<first>[^\n]+)\n"
                   r"IT WILL ASK FOR: (?P<asks>[^\n]+)\nWHEN IT ENDS: (?P<ends>[^\n]+)\nIF YOU SEE \"STOP\": (?P<stop>[^\n]+)")
STAGE = r"C:\Users\micge\Documents\icb-rt12-stage\window"
LOCAL_STAGE = r"C:\Users\micge\Documents\icb-rt12-stage\local"


def block_problems(md: str) -> list[str]:
    rows = re.findall(r"'([a-z-]+)'\s*=\s*@\('(\d)', '([^']+)'", (WINDOW / "run_window_step.ps1").read_text(encoding="ascii"))
    plan = {k: n for k, n, _ in rows}
    plan_label = {k: label for k, _, label in rows}
    probs = []
    for b in BLOCK.finditer(md.replace("\r\n", "\n")):
        cmd = b["cmd"]
        if not all(0x20 <= ord(c) < 0x7F for c in cmd):
            probs.append(f"not ASCII: {cmd}")
        if re.search(r"<[a-z]+>|__[A-Z_]+__", cmd):
            probs.append(f"placeholder: {cmd}")
        m = re.fullmatch(r'powershell -NoProfile -ExecutionPolicy Bypass -File "(?P<path>[^"]+)"(?: (?P<step>\S+))?', cmd)
        if m:
            path, step = m["path"], m["step"]
            folder, name = path.rsplit("\\", 1)
            staged = {STAGE: [WINDOW], LOCAL_STAGE: [LOCAL]}.get(folder, [])
            if not any((d / name).exists() for d in staged):
                probs.append(f"not a staged line: {path}")
            if path.endswith("run_window_step.ps1"):
                if step not in plan:
                    probs.append(f"unknown step '{step}'")
                elif not b["first"].startswith(f"######## RT12 window step {plan[step]} {plan_label[step]} . machine "
                                               "LAPTOP-DGJ0U6RQ -> icb-mes-prod . head "):
                    probs.append(f"first line for {step}: {b['first']}")
                elif not b["ends"].startswith(f"######## DONE - step {plan[step]} ({step}) ended with exit 0."):
                    probs.append(f"end line for {step}: {b['ends']}")
                if ("sudo" in b["asks"]) is False:
                    probs.append(f"{step}: says it asks for nothing, but runs sudo")
    return probs


def test_the_runbook_blocks_are_paste_safe_and_name_what_the_lines_print():
    md = RUNBOOK.read_text(encoding="utf-8")
    blocks = list(BLOCK.finditer(md.replace("\r\n", "\n")))
    # :8000 start + :8000 check, the 8 window lines (7 is the browser), the close's cleanup (10)
    assert len(blocks) == 11, len(blocks)
    assert block_problems(md) == []
    steps = [re.search(r'run_window_step\.ps1" (\S+)$', b["cmd"]) for b in blocks]
    assert [s[1] for s in steps if s] == ["preflight", "all-before", "deploy", "all-after", "doors", "verify"]
    assert [b["cmd"] for b in blocks][:2] == ['"C:\\Users\\micge\\Documents\\icb-platform\\scripts\\start.bat"',
                                             f'powershell -NoProfile -ExecutionPolicy Bypass -File "{LOCAL_STAGE}\\check_8000.ps1"']
    # each .ps1 prints the first line the runbook names
    for d, name, label in ((WINDOW, "run_window_copy.ps1", "copy (step 1)"), (WINDOW, "run_window_fetch.ps1", "fetch (step 9)"),
                           (WINDOW, "run_window_cleanup.ps1", "close (step 10): prod /tmp cleanup")):
        assert f"Enter-Window '{label}'" in (d / name).read_text(encoding="ascii")
        assert f"######## RT12 window {label} . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head" in md
    assert '"######## RT12 window $label . machine $env:COMPUTERNAME -> $vmHost . head $short . boot $vmBoot' \
        in (WINDOW / "window_common.ps1").read_text(encoding="ascii")
    assert "######## RT12 :8000 check (read only) . http://127.0.0.1:8000" in md
    # the view-only acceptance (RT9's lesson, ratified default 5): its own line, and the prod URL Michael opens
    assert "\n**Do not click Accept, Update or Save.**\n" in md.replace("\r\n", "\n")
    assert "https://mes.icecoldgrp.online/mes-app/costings" in md


def test_negative_control_a_placeholder_or_an_unknown_step_is_caught():
    md = RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    bad = md.replace('run_window_step.ps1" doors', 'run_window_step.ps1" door', 1)
    assert any("unknown step 'door'" in p for p in block_problems(bad))
    bad = md.replace('run_window_fetch.ps1"', 'run_window_fetch.ps1" <ts>', 1)
    assert any(p.startswith("placeholder:") for p in block_problems(bad))


# ── the reboot guard, the stager, the SPA rebuild's guards ──────────────────
def test_the_kit_carries_the_reboot_guard_and_the_stager_fills_every_placeholder():
    rel = RELEASE.read_text(encoding="utf-8")
    assert re.search(r"^KIT_DIR=\$BASE$", rel, re.M) and re.search(r"^ICB_LANE=RT12$", rel, re.M)
    st = (KIT / "mkstage_window.sh").read_text(encoding="utf-8")
    assert "REBOOT_GUARD=1" in st and "rt12_vm.sh" in st
    for ph in re.findall(r"__[A-Z_]+__", "".join(p.read_text(encoding="ascii") for p in WINDOW.glob("*.ps1"))):
        assert f"s/{ph}/" in st, ph
    assert 'date +%s > "/tmp/$k/.staged_at"' in (WINDOW / "rt12_vm.sh").read_text(encoding="utf-8")
    # the release stager: the SPA rebuild is expected (frontend/ changed; RT10's text in the target's source only), the
    # two statics moved, no route is new (and none is declared), the audit does not move
    mk = (KIT / "mkstage.sh").read_text(encoding="utf-8")
    assert '[ "$N_FRONTEND" -gt 0 ] ||' in mk and 'SPA_MARK="is the latest. Accept REV"' in mk
    assert "! git grep -q -F \"$SPA_MARK\" \"$PREV\" -- frontend/src ||" in mk
    assert 'static_of calculator.html js/calculator.js' in mk and 'static_of calculator2.html js/calculator2.js' in mk
    assert '[ -z "$NEW_PROBES" ] ||' in mk and 'N_ROUTE_DECL' in mk
    assert "PREV_TAG=v1.62.0" in mk and 'TAG=v1.63.0' in mk and '${3:-a29db35}' in mk
    # and release.sh asserts the plan the stager derived: SPA rebuild YES, no migration, restart; the bundle renamed
    assert "grep -q 'SPA rebuild *YES'" in rel and "grep -q 'DB migration *no '" in rel and "stop SPA_REBUILT" in rel
    assert 'SPA_MARK_NOT_YET' in rel and 'check "SPA_MARK_$d"' in rel and 'check "SPA_$d"' in rel


# ── RT12_RULING_1: #232 in the range — one manifest pin, nothing installed, WeasyPrint-only statics, the gate ──
def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def test_the_range_adds_exactly_the_weasyprint_pin_and_weasyprint_only_statics():
    """The facts the stager derives, read from the tree itself (skipped on a shallow checkout without v1.62.0)."""
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "a29db35^{commit}"], capture_output=True).returncode != 0:
        pytest.skip("a29db35 (v1.62.0) is not in this checkout's history")
    deps = git("diff", "--name-only", "a29db35", "HEAD", "--", "backend/requirements.txt", "backend/requirements-dev.txt",
               "frontend/package.json", "frontend/package-lock.json").split()
    assert deps == ["backend/requirements.txt"]
    added = [ln[1:].split("#")[0].strip() for ln in git("diff", "a29db35", "HEAD", "--", "backend/requirements.txt").splitlines()
             if ln.startswith("+") and not ln.startswith("++") and ln[1:].split("#")[0].strip()]
    removed = [ln[1:].split("#")[0].strip() for ln in git("diff", "a29db35", "HEAD", "--", "backend/requirements.txt").splitlines()
               if ln.startswith("-") and not ln.startswith("--") and ln[1:].split("#")[0].strip()]
    assert added == ["weasyprint==70.0"] and removed == []
    statics = set(git("diff", "--name-only", "a29db35", "HEAD", "--", "backend/app/static").split())
    calcs = {"backend/app/static/js/calculator.js", "backend/app/static/js/calculator2.js"}
    weasy = statics - calcs
    assert calcs <= statics and weasy and all(re.fullmatch(r"backend/app/static/(css/report\.css|fonts/[^/]+)", p) for p in weasy), weasy
    # WeasyPrint-only: read from disk by report_engine, named by no template -> browser-served by nothing, no ?v= moves
    assert git("grep", "-l", "-E", r"report\.css|static/fonts", "HEAD", "--", "backend/app/templates") == ""
    assert 'css_path_fs   = os.path.join(STATIC_DIR, "css", "report.css")' in (ROOT / "backend/app/report_engine.py").read_text(encoding="utf-8")
    # no route is new (#232's 503 is a changed response): no decorator added in the whole range
    assert re.search(r"^\+\s*@\w+\.(get|post|put|patch|delete|api_route)\(", git("diff", "a29db35", "HEAD", "--", "backend/app"), re.M) is None
    # NC: the same scan on the range that added RT8's route finds its decorator
    assert re.search(r"^\+\s*@\w+\.post\(", git("diff", "5511355", "a29db35", "--", "backend/app/routers/calculator.py"), re.M) is not None


def test_the_kit_expects_the_one_dependency_warning_and_never_installs():
    rel = RELEASE.read_text(encoding="utf-8")
    mk = (KIT / "mkstage.sh").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in rel.splitlines() if not ln.lstrip().startswith("#"))
    # the stager pins the fact: exactly backend/requirements.txt, exactly +weasyprint==70.0, and the WeasyPrint-only files
    assert '[ "$REQ_ADDED" = "weasyprint==70.0" ] && [ -z "$REQ_REMOVED" ] ||' in mk
    assert '[ "$REQ_CHANGED" = "$REQ_FILE" ] ||' in mk and "REQ_FILE=backend/requirements.txt" in mk
    assert "WEASY_STATIC=" in mk and "report\\.css|fonts/[^/]+" in mk and "git grep -c -E 'report\\.css|static/fonts'" in mk
    # release.sh: the warning once in the dry run AND the deploy, no pip, the venv read before and after, the gate False
    assert '[ "$(deps_warnings "$OUT/icb-deploy-dryrun.txt")" = 1 ]' in code and '[ "$(deps_warnings "$OUT/icb-deploy.txt")" = 1 ]' in code
    assert code.count("grep -qiE 'pip (install|sync)'") == 2
    assert not re.search(r"\bpip3? +(install|sync)\b", code)                        # the kit itself never installs
    assert code.count('check WEASYPRINT_IN_VENV "$(weasyprint_in_venv)" absent') == 2   # preflight + post_checks (deploy and verify)
    assert 'stop WEASYPRINT "prod' in code and "importlib.util.find_spec(\"weasyprint\")" in code
    assert 'check LETTERHEAD_GATE "$(gate_since "$since")" False' in code
    assert "Letterhead quote (Generate Quote) available: " in (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    # the deploy tool only warns (line 199) and runs no pip: the kit's expectation is the tool's behaviour
    tool = (ROOT / "deploy/prod/icb-deploy.sh").read_text(encoding="utf-8")
    assert 'warn "dependency manifests changed ($n_deps)' in tool and not re.search(r"\bpip\b.*install", tool)
    # NC: RT9's kit stopped on any warning (its range had none) — the two kits must differ here
    assert "grep -q 'dependency manifests changed' \"$OUT/icb-deploy-dryrun.txt\" && stop DRYRUN" in (OLD_KIT / "release.sh").read_text(encoding="utf-8")


def test_the_copy_line_stops_under_5_gb_free_before_anything_reaches_prod():
    ps1 = (WINDOW / "run_window_copy.ps1").read_text(encoding="ascii")
    disk = ps1.index("STOP [DISK]")
    assert disk < ps1.index("Enter-Window 'copy (step 1)'")          # before the first ssh/scp
    assert "(Get-PSDrive C).Free / 1GB" in ps1 and "-lt 5" in ps1 and "the window needs 5 GB or more" in ps1
    assert "RT12_SIM_FREE_GB" in ps1                                   # the sim's negative control hook, named as such
    assert "RT12_SIM_FREE_GB" in (KIT / "sim/ps51/run_blocks.ps1").read_text(encoding="ascii")
    md = RUNBOOK.read_text(encoding="utf-8")
    assert "under 5 GB it\nSTOPs before anything reaches prod" in md.replace("\r\n", "\n") or "under 5 GB it STOPs" in md
