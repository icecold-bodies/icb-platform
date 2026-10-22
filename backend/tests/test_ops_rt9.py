"""RT9 — the v1.62.0 release kit (ops/prod-release-v1.62.0) and Michael's paste blocks. Each test carries its
negative control (F6): the same check pointed at a known-bad input must fail.

  1. The probe list is the code: every line of probe_paths.txt (method-aware since RT9) answers its listed status with
     no session, Accept JSON — and the new reprice preview is a POST route: a GET to it answers 405, so only a POST
     probe tests the gate (NC: a flipped status is caught; a GET probe proves nothing).
  2. release.sh's no-session probe sends each line with its method; before the deploy ONLY the routes new in the range
     may answer 404 (NC: an old route answering 404 before the deploy, the new one answering 404 after it, a POST line
     written without its method).
  3. Cloudflare keeps the first bytes per URL for 4 h: release.sh asks a door for calculator.js?v=<new> ONLY once the
     page on disk loads that ?v= and the disk holds the new bytes (NC: with them on disk, the request is made).
  4. Tracebacks: listed with time + exception class only (never the message: G4); only those since this deploy's
     restart count (NC: one after the restart fails the check).
  5. The window lines never hand a script to ssh as an argument (RT8, 21 Oct): every ssh/scp call runs a file by path
     (NC: RT8's cleanup_check.ps1 v1 shape is flagged by the same scan). The .ps1 files are ASCII.
  6. rt9_vm.sh: the cleanup acts on exact /tmp/icb-* names only; fetch takes a checked name (NC: a path is refused).
  7. The runbook's paste blocks: ASCII, no placeholder, the full stage path, a step word the line knows, and the first
     and last lines the .ps1 really prints (NC: a block with a placeholder or an unknown step is caught).
Bash parts run the real kit functions in Git Bash with stubs on PATH (skipped where there is no bash).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from test_ops_rt6 import needs_bash, posix, run, stub  # noqa: F401  (shared bash helpers)

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "ops" / "prod-release-v1.62.0"
RELEASE = KIT / "release.sh"
PROBES = KIT / "probe_paths.txt"
WINDOW = KIT / "window"
CLOSE = KIT / "close"
RUNBOOK = ROOT / "docs" / "runbooks" / "prod-deploy-v1.62.0.md"
JSON = {"accept": "application/json"}
NEW_ROUTE = "/api/calculations/1/reprice-preview"


def probe_lines(text: str) -> list[tuple[str, str, str]]:
    """(status, method, path) per line; a line is '<status> <path>' (GET) or '<status> <METHOD> <path>'."""
    out = []
    for raw in text.splitlines():
        parts = raw.split()
        if not parts or parts[0].startswith("#"):
            continue
        out.append((parts[0], parts[1], parts[2]) if len(parts) == 3 else (parts[0], "GET", parts[1]))
    return out


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
    assert len(lines) == 47 and ("401", "POST", NEW_ROUTE) in lines and ("401", "GET", "/openapi.json") in lines
    assert mismatches(client, lines) == []
    # NC: a line whose status is wrong is caught (the check can fail)
    flipped = [("200", m, p) if p == NEW_ROUTE else (w, m, p) for w, m, p in lines]
    assert mismatches(client, flipped) == [f"POST {NEW_ROUTE} = 401, listed 200"]


def test_the_reprice_preview_probe_must_be_a_post(client):
    assert client.post(NEW_ROUTE, json={}, headers=JSON).status_code == 401
    # NC: a GET never reaches the gate — the route takes POST only — so a GET probe would prove nothing
    assert client.get(NEW_ROUTE, headers=JSON).status_code == 405
    # and a path that is no route at all answers 404 (what v1.61.1 answers for the new one)
    assert client.post("/api/calculations/1/reprice-preview-nope", json={}, headers=JSON).status_code == 404


# ── helpers: the real functions out of release.sh ───────────────────────────
def functions(*names: str) -> str:
    """The named shell functions, verbatim from release.sh (one-liners end on their line; others at a lone '}')."""
    lines, out = RELEASE.read_text(encoding="utf-8").splitlines(), []
    for name in names:
        start = next(i for i, ln in enumerate(lines) if ln.startswith(f"{name}() {{"))
        if lines[start].rstrip().endswith("}") and lines[start].count("{") == lines[start].count("}"):
            out.append(lines[start])
            continue
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
        out.extend(lines[start:end + 1])
    return "\n".join(out) + "\n"


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


def noauth(tmp_path: Path, probes: str, answers: str, before: str) -> tuple[str, str]:
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "curl", CURL)
    (tmp_path / "probe_paths.txt").write_text(probes, encoding="utf-8", newline="\n")
    (tmp_path / "answers").write_text(answers, encoding="utf-8", newline="\n")
    log = tmp_path / "curl.log"
    log.unlink(missing_ok=True)
    n = len(probe_lines(probes))
    script = (f'BASE="{posix(tmp_path)}"; N_PROBES={n}; NEW_PROBES="{NEW_ROUTE}"; ANSWERS="{posix(tmp_path / "answers")}"; '
              f'CURLLOG="{posix(log)}"; export ANSWERS CURLLOG; ' + functions("noauth_report")
              + f'noauth_report https://door {before}')
    r = run(script, path_dir=tmp_path / "bin")
    return r.stdout.strip(), (log.read_text(encoding="utf-8") if log.exists() else "")


PROBE_TXT = f"# comment\n401 /api/calculations\n401 POST {NEW_ROUTE}\n"


# ── 2. the no-session probe: methods, and 404 only for the new route, only before ──
@needs_bash
def test_the_probe_sends_each_line_with_its_method_and_allows_404_only_for_the_new_route_before(tmp_path):
    after = f"GET /api/calculations 401\nPOST {NEW_ROUTE} 401\nGET {NEW_ROUTE} 405\n"
    out, log = noauth(tmp_path, PROBE_TXT, after, "")
    assert out == "all 2 as expected", out
    assert f"POST https://door{NEW_ROUTE} {{}}" in log and "GET https://door/api/calculations" in log
    before = f"GET /api/calculations 401\nPOST {NEW_ROUTE} 404\n"
    out, _ = noauth(tmp_path, PROBE_TXT, before, "before")
    assert out == f"all 2 as expected (new in this release, 404 before the deploy: POST {NEW_ROUTE})", out


@needs_bash
def test_negative_controls_old_route_404_new_route_404_after_and_a_post_line_without_its_method(tmp_path):
    # an OLD route answering 404 before the deploy is a failure, not an allowance
    out, _ = noauth(tmp_path, PROBE_TXT, f"GET /api/calculations 404\nPOST {NEW_ROUTE} 404\n", "before")
    assert out == "/api/calculations=404/401", out
    # after the deploy the new route must answer 401: 404 is a failure
    out, _ = noauth(tmp_path, PROBE_TXT, f"GET /api/calculations 401\nPOST {NEW_ROUTE} 404\n", "")
    assert out == f"POST {NEW_ROUTE}=404/401", out
    # the same route written without its method is sent as a GET, which a POST-only route answers 405
    out, log = noauth(tmp_path, f"401 /api/calculations\n401 {NEW_ROUTE}\n",
                      f"GET /api/calculations 401\nPOST {NEW_ROUTE} 401\nGET {NEW_ROUTE} 405\n", "")
    assert out == f"{NEW_ROUTE}=405/401" and f"GET https://door{NEW_ROUTE}" in log, (out, log)


# ── 3. the new ?v= is never asked of a door before its bytes are on disk ────
def calc_on(tmp_path: Path, v_on_disk: str, bytes_on_disk: bytes, new: bytes) -> tuple[str, str]:
    import hashlib
    repo = tmp_path / "repo"
    (repo / "backend/app/static/js").mkdir(parents=True, exist_ok=True)
    (repo / "backend/app/templates").mkdir(parents=True, exist_ok=True)
    (repo / "backend/app/templates/calculator.html").write_text(
        f'<script defer src="/static/js/calculator.js?v={v_on_disk}"></script>\n', encoding="utf-8", newline="\n")
    (repo / "backend/app/static/js/calculator.js").write_bytes(bytes_on_disk)
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "curl", CURL)
    (tmp_path / "answers").write_text("", encoding="utf-8")
    log = tmp_path / "curl.log"
    log.unlink(missing_ok=True)
    sha = hashlib.sha256(new).hexdigest()
    script = (f'REPO="{posix(repo)}"; CALC_REL=backend/app/static/js/calculator.js; '
              f'CALC_TMPL=backend/app/templates/calculator.html; ANSWERS="{posix(tmp_path / "answers")}"; '
              f'CURLLOG="{posix(log)}"; STATICFILE="{posix(repo / "backend/app/static/js/calculator.js")}"; '
              'export ANSWERS CURLLOG STATICFILE; '
              + functions("sha_url", "calc_v_disk", "calc_sha_disk", "calc_on")
              + f'calc_on https://mes.icecoldgrp.online 191 {sha}')
    r = run(script, path_dir=tmp_path / "bin")
    return r.stdout.strip(), (log.read_text(encoding="utf-8") if log.exists() else "")


@needs_bash
def test_cloudflare_is_never_asked_for_the_new_v_before_the_bytes_are_on_disk(tmp_path):
    out, log = calc_on(tmp_path, "189", b"old calculator\n", b"new calculator\n")
    assert out.startswith("not probed (the page on disk loads ?v=189"), out
    assert log == "", log                     # no request at all: the edge cannot pin the old bytes under ?v=191


@needs_bash
def test_negative_control_with_the_new_bytes_on_disk_the_door_is_asked(tmp_path):
    import hashlib
    out, log = calc_on(tmp_path, "191", b"new calculator\n", b"new calculator\n")
    assert out == hashlib.sha256(b"new calculator\n").hexdigest(), out
    assert "GET https://mes.icecoldgrp.online/static/js/calculator.js?v=191" in log, log


# ── 4. tracebacks: listed (time + class only), counted only since this deploy's restart ──
JOURNAL = r'''
since=0; until=99999999999
while [ $# -gt 0 ]; do case "$1" in --since) since=${2#@}; [ "$2" = now ] && since=99999999999; shift;;
  --until) until=${2#@}; [ "$2" = now ] && until=99999999999; shift;; esac; shift; done
while read -r ep msg; do [ "$ep" -ge "$since" ] && [ "$ep" -le "$until" ] && echo "Oct 2$((ep % 9)) 11:14:0$((ep % 7)) icb uvicorn[7]: $msg"; done < "$JOURNALFILE"
exit 0
'''


def tracebacks(tmp_path: Path, journal: str, start: int) -> subprocess.CompletedProcess:
    (tmp_path / "bin").mkdir(exist_ok=True)
    stub(tmp_path / "bin", "journalctl", JOURNAL)
    (tmp_path / "journal").write_text(journal, encoding="utf-8", newline="\n")
    script = (f'SERVICE=icb-backend; MODE=verify; FAILS=0; JOURNALFILE="{posix(tmp_path / "journal")}"; export JOURNALFILE; '
              + functions("journal_since", "tb_since", "tb_list", "check", "tracebacks")
              + f'tracebacks {start}; echo "fails=$FAILS"')
    return run(script, path_dir=tmp_path / "bin")


OLD = ("100 Traceback (most recent call last):\n100   File \"/x/requests.py\", line 9, in receive\n"
       "100 starlette.requests.ClientDisconnect\n"
       "150 Traceback (most recent call last):\n150 KeyError: 'customer-name-would-be-here'\n")


@needs_bash
def test_tracebacks_before_the_restart_are_listed_by_class_only_and_not_counted(tmp_path):
    r = tracebacks(tmp_path, OLD + "300 INFO:     Application startup complete.\n", 200)
    assert "starlette.requests.ClientDisconnect" in r.stdout and "  KeyError" in r.stdout, r.stdout
    assert "customer-name-would-be-here" not in r.stdout            # G4: never the message
    assert "(listed, not counted): 2" in r.stdout and "PASS TRACEBACKS_SINCE_RESTART = 0" in r.stdout
    assert "fails=0" in r.stdout


@needs_bash
def test_negative_control_a_traceback_after_the_restart_fails(tmp_path):
    r = tracebacks(tmp_path, OLD + "250 Traceback (most recent call last):\n250 ValueError: x\n", 200)
    assert "FAIL TRACEBACKS_SINCE_RESTART = '1'" in r.stdout and "fails=1" in r.stdout, r.stdout


# ── 5. no script is ever handed to ssh as an argument; the lines are ASCII ───
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


def test_the_window_lines_run_files_by_path_never_an_inline_script_and_are_ascii():
    ps1s = sorted(WINDOW.glob("*.ps1"))
    assert [p.name for p in ps1s] == ["run_window_cleanup.ps1", "run_window_copy.ps1", "run_window_fetch.ps1",
                                      "run_window_step.ps1", "window_common.ps1"]
    for p in ps1s:
        raw = p.read_bytes()
        assert all(b < 0x80 for b in raw), f"{p.name} is not ASCII (Windows PowerShell 5.1 reads it as ANSI)"
        assert inline_script_calls(raw.decode("ascii")) == [], p.name
    for p in sorted(CLOSE.glob("*.ps1")):                 # the close's line: the same rules
        raw = p.read_bytes()
        assert all(b < 0x80 for b in raw), p.name
        assert inline_script_calls(raw.decode("ascii")) == [], p.name
    step = (WINDOW / "run_window_step.ps1").read_text(encoding="ascii")
    remotes = re.findall(r"'((?:sudo )?bash /tmp/[^']+)'", step)
    assert len(remotes) == 6 and all(re.fullmatch(r"sudo bash /tmp/icb-[a-z0-9.-]+/[a-z0-9_]+\.sh( [a-z]+)?", r) for r in remotes)
    assert "| Out-Host" not in step and "& ssh -t" in step      # no pipe: sudo needs the terminal


def test_negative_control_rt8_v1_cleanup_shape_is_flagged():
    v1 = ("$Vm = 'mickeyger@192.168.0.251'\n$remote = @'\n"
          "sudo bash -c 'set -u; echo \"######## RT8 cleanup\"; rm -rf -- /tmp/x'\n'@\n& ssh -t $Vm $remote\n")
    assert len(inline_script_calls(v1)) == 1
    assert len(inline_script_calls("& ssh -o BatchMode=yes $Vm \"cd /tmp && tar -xf x.tar && echo 'ok'\"\n")) == 1


# ── 6. rt9_vm.sh: exact names; checked fetch names ──────────────────────────
def test_the_cleanup_names_are_exact_and_cover_every_kit():
    text = (WINDOW / "rt9_vm.sh").read_text(encoding="utf-8")
    block = re.search(r'NAMES="([^"]*)"', text, re.S).group(1)
    names = block.replace("$MARK", "/tmp/icb-rt9-window.started").split()
    assert all(re.fullmatch(r"/tmp/icb-[A-Za-z0-9.-]+", n) for n in names), names     # no glob, no other dir
    for k in ("icb-release-v1.62.0", "icb-rt2-all", "icb-rt2-doors"):
        assert f"/tmp/{k}" in names and f"/tmp/{k}.tar" in names, k
    assert "/tmp/icb-release-v1.61.1" in names and "/tmp/icb-release-v1.61.1.tar" in names   # RT7's leftovers
    assert "/tmp/icb-rt9-quotes" in names and "/tmp/icb-rt9-quotes.tar" in names             # the close's check kit
    assert re.search(r"case \"\$p\" in /tmp/icb-\*\) ;; \*\) stop CLEANUP", text)              # refuses anything else


@needs_bash
def test_fetch_takes_only_a_checked_name(tmp_path):
    vm = posix(WINDOW / "rt9_vm.sh")
    r = run(f'bash "{vm}" fetch ../../etc/passwd; echo "rc=$?"')
    assert "STOP [FETCH]: fetch: the name must be rt9-window-back-" in r.stdout and "rc=1" in r.stdout
    # NC: a well-formed name passes the name check and reaches the next one (no window start mark here)
    r = run(f'bash "{vm}" fetch rt9-window-back-20261022-180000; echo "rc=$?"')
    assert "the name must be" not in r.stdout and "STOP [FETCH]" in r.stdout, r.stdout


# ── 7. the runbook's paste blocks ───────────────────────────────────────────
BLOCK = re.compile(r"PASTE INTO: (?P<win>[^\n]+)\n```\n(?P<cmd>[^\n]+)\n```\nFIRST LINE YOU SHOULD SEE: (?P<first>[^\n]+)\n"
                   r"IT WILL ASK FOR: (?P<asks>[^\n]+)\nWHEN IT ENDS: (?P<ends>[^\n]+)\nIF YOU SEE \"STOP\": (?P<stop>[^\n]+)")
STAGE = r"C:\Users\micge\Documents\icb-rt9-stage\window"
CLOSE_STAGE = r"C:\Users\micge\Documents\icb-rt9-stage\close"


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
            # the close folder holds its own line plus the window files mkstage_close.sh re-stages (fetch, cleanup)
            staged = {STAGE: [WINDOW], CLOSE_STAGE: [CLOSE, WINDOW]}.get(folder, [])
            if not any((d / name).exists() for d in staged):
                probs.append(f"not a staged line: {path}")
            if path.endswith("run_window_step.ps1"):
                if step not in plan:
                    probs.append(f"unknown step '{step}'")
                elif not b["first"].startswith(f"######## RT9 window step {plan[step]} {plan_label[step]} . machine "
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
    # :8000 start + health, the 8 window lines (7 is the browser), the close's quotes check, fetch again, cleanup
    assert len(blocks) == 13, len(blocks)
    assert block_problems(md) == []
    steps = [re.search(r'run_window_step\.ps1" (\S+)$', b["cmd"]) for b in blocks]
    assert [s[1] for s in steps if s] == ["preflight", "all-before", "deploy", "all-after", "doors", "verify"]
    # the close's lines come from the close folder, never the window's (its helper does not know the quotes kit)
    close_lines = [b["cmd"] for b in blocks if "run_quotes_check" in b["cmd"] or "run_window_cleanup" in b["cmd"]]
    assert close_lines and all(CLOSE_STAGE + "\\" in c for c in close_lines), close_lines
    # each .ps1 prints the first line the runbook names
    for d, name, label in ((WINDOW, "run_window_copy.ps1", "copy (step 1)"), (WINDOW, "run_window_fetch.ps1", "fetch (step 9)"),
                           (WINDOW, "run_window_cleanup.ps1", "close: prod /tmp cleanup"),
                           (CLOSE, "run_quotes_check.ps1", "quotes check (read only)")):
        assert f"Enter-Window '{label}'" in (d / name).read_text(encoding="ascii")
        assert f"######## RT9 window {label} . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod . head" in md
    assert '"######## RT9 window $label . machine $env:COMPUTERNAME -> $vmHost . head $short . boot $vmBoot' \
        in (WINDOW / "window_common.ps1").read_text(encoding="ascii")


def test_negative_control_a_placeholder_or_an_unknown_step_is_caught():
    md = RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    bad = md.replace('run_window_step.ps1" doors', 'run_window_step.ps1" door', 1)
    assert any("unknown step 'door'" in p for p in block_problems(bad))
    bad = md.replace('run_window_fetch.ps1"', 'run_window_fetch.ps1" <ts>', 1)
    assert any(p.startswith("placeholder:") for p in block_problems(bad))


# ── the reboot guard and the stager ─────────────────────────────────────────
def test_the_kit_carries_the_reboot_guard_and_the_stager_fills_every_placeholder():
    rel = RELEASE.read_text(encoding="utf-8")
    assert re.search(r"^KIT_DIR=\$BASE$", rel, re.M) and re.search(r"^ICB_LANE=RT9$", rel, re.M)
    st = (KIT / "mkstage_window.sh").read_text(encoding="utf-8")
    assert "REBOOT_GUARD=1" in st
    for ph in re.findall(r"__[A-Z_]+__", "".join(p.read_text(encoding="ascii") for p in WINDOW.glob("*.ps1"))):
        assert f"s/{ph}/" in st, ph
    # the close's stager fills every placeholder of the files IT stages: the close's line and the three window files
    # it re-stages (window_common, the fetch, the cleanup)
    cl = (KIT / "mkstage_close.sh").read_text(encoding="utf-8")
    close_files = [*CLOSE.glob("*.ps1"), WINDOW / "window_common.ps1", WINDOW / "run_window_fetch.ps1", WINDOW / "run_window_cleanup.ps1"]
    for f in close_files:
        assert f.name in cl, f.name
    for ph in re.findall(r"__[A-Z_]+__", "".join(p.read_text(encoding="ascii") for p in close_files)):
        assert f"s/{ph}/" in cl, ph
    assert 'date +%s > "/tmp/$k/.staged_at"' in (WINDOW / "rt9_vm.sh").read_text(encoding="utf-8")


# ── the close's quotes check: the filter on two COPY streams (RT9_RULING_2 Q1) ──
FILTER = CLOSE / "rt9_quotes_filter.py"
COLS = ["id", "branch_id", "quote_number", "created_at", "status", "deleted_at", "deleted_by", "net_total",
        "result_json", "contact_name", "customer_id"]


def copy_field(v) -> str:
    if v is None:
        return "\\N"
    return str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def copy_row(*vals) -> str:
    return "\t".join(copy_field(v) for v in vals)


def rj(version, total, **extra) -> str:
    import json
    return json.dumps({"version": version, "grand_total": total, "customer_name": "Never Printed Ltd", **extra})


R1 = (1, 1, "N10021/10/2026", "2026-10-19 15:02:44", "pending", None, None, 289000, rj(1, 289000.0), "Alice Example", 7)
R2 = (2, 1, "R-2003 Karan Beef Farming (Pty) Ltd 001 ICB GP", "2026-10-22 08:55:30", "pending", None, None, 23410, rj(1, 23410.0), "Bob Example", 9)
R3 = (3, 1, "N10022/10/2026", "2026-10-19 14:41:09", "pending", None, None, 391853.38, rj(1, 391853.38), "Alice Example", 7)
R4 = (4, 1, "N10022/10/2026", "2026-10-22 13:02:10", "pending", None, None, 389120, rj(4, 389120.0, repriced={"from_version": 1}), "Alice Example", 7)
R2_CHANGED = R2[:9] + ("Carol Example", 9)
R3_DELETED = R3[:5] + ("2026-10-22 13:30:00", "admin") + R3[7:]


def streams(tmp_path: Path, dump_rows, now_rows, table: str = "icb_costings.calculations"):
    dump = tmp_path / "dump.sql"
    dump.write_text("SET statement_timeout = 0;\nSELECT pg_catalog.set_config('search_path', '', false);\n\n"
                    f"COPY {table} ({', '.join(COLS)}) FROM stdin;\n"
                    + "".join(copy_row(*r) + "\n" for r in dump_rows) + "\\.\n\n-- complete\n", encoding="utf-8", newline="\n")
    now = tmp_path / "now.copy"
    now.write_text("".join(copy_row(*r) + "\n" for r in now_rows), encoding="utf-8", newline="\n")
    return dump, now


def run_filter(dump: Path, now: Path, deploy_count: int = 3, today: str = "2026-10-22") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(FILTER), "--dump", str(dump), "--now", str(now), "--columns", ",".join(COLS),
                          "--deploy-count", str(deploy_count), "--today", today], capture_output=True, text=True, encoding="utf-8")


def test_the_filter_names_added_changed_and_removed_rows_and_prints_only_the_allow_list(tmp_path):
    dump, now = streams(tmp_path, [R1, R2, R3], [R1, R2_CHANGED, R3_DELETED, R4])
    r = run_filter(dump, now)
    out = r.stdout
    assert r.returncode == 0, out + r.stderr
    assert "== the backup: 3 rows (max id 3); now: 4 rows (max id 4)" in out
    assert "== added since the backup: 1" in out and "   4 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N | 389120.00 | 389120.00" in out
    assert "== changed since the backup: 2" in out
    assert "   2 | R-2003 | contact_name" in out                       # the changed column's NAME; the repair's first word
    assert "   3 | N10022/10/2026 | deleted_at, deleted_by" in out      # a soft delete reads as exactly these two
    assert "== removed since the backup: 0" in out
    # created today: the added revision (flagged) and the repair saved this morning (not flagged: it is in the backup)
    assert "newest first: 2" in out
    today = out.split("newest first: 2")[1]
    assert "   4 | N10022/10/2026 | 2026-10-22 13:02:10 | 4 | pending | N | 389120.00 | 389120.00   <- added since the backup" in today
    assert "   2 | R-2003 | 2026-10-22 08:55:30 | 1 | pending | N | 23410.00 | 23410.00\n" in today
    assert out.rstrip().endswith("SUMMARY: backup 3 rows; now 4 rows; added 1, changed 2, removed 0; created today 2")
    # G4: no contact's name, no customer's name (from a repair's quote number or from result_json), no value of a changed column
    for leak in ("Alice", "Bob", "Carol", "Karan", "Beef", "Never Printed", "admin"):
        assert leak not in out, leak


def test_negative_controls_the_allow_list_refuses_a_field_and_a_wrong_table_or_count_stops(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("rt9_quotes_filter", FILTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(mod.RefusedOutput, match="customer_name"):
        mod.emit({"id": 1, "quote": "N1/10/2026", "customer_name": "x"})
    assert mod.emit({"id": 1, "quote": "N1/10/2026"}) == "1 | N1/10/2026"
    # the wrong table in the stream: refused before any row is read
    dump, now = streams(tmp_path, [R1], [R1], table="icb_mes.calculations")
    r = run_filter(dump, now, deploy_count=1)
    assert r.returncode == 2 and "REFUSED: the stream holds icb_mes.calculations" in r.stdout
    # a backup that is not the deploy's state (row count): exit 3, nothing compared
    dump, now = streams(tmp_path, [R1, R2], [R1, R2])
    r = run_filter(dump, now, deploy_count=3)
    assert r.returncode == 3 and "the backup holds 2 rows; the deploy recorded 3" in r.stdout and "added" not in r.stdout
    # the kit itself: the dump goes down a pipe (no file in /tmp), the live rows are a read-only COPY, and the dump's
    # own listing check is the backup helper's, not a restore
    kit = (CLOSE / "rt9_quotes.sh").read_text(encoding="utf-8")
    assert "--dump <(pg_restore --data-only -n icb_costings -t calculations -f - \"$BACKUP\")" in kit
    assert "--now <(psql \"$URL\" -XAtq -v ON_ERROR_STOP=1 -c \"copy (select * from icb_costings.calculations order by id) to stdout\")" in kit
    assert "pg_restore -d" not in kit and "createdb" not in kit and "default_transaction_read_only=on" in kit
