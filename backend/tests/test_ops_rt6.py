"""RT6 — checked backups and safe pastes in ops/ (RT6_DISPATCH defaults 7 and 8; RT6_RULING_1 Q7).

  1. The CI guard: no shell script in ops/ pipes pg_dump anywhere but the shared helper ops/lib/icb_backup.sh, unless
     the script is RETIRED (a header that exits 3 before anything runs). The scanner itself catches a bare pipe,
     a continued line, a pipe after `then`, and ignores `||`, comments and the sims' heredoc stubs.
  2. The six retired kits refuse to run (exit 3, "RETIRED", nothing else done).
  3. The helper: a failed pg_dump stops the step (and the bad file is renamed .FAILED); an "ok" dump that lacks a
     table the step touches stops it; a good dump passes with its size and sha256; the custom format is checked by
     pg_restore -l.
  4. The safe-paste first line (ops/lib/icb_where.sh): it names machine, database (name @ host) and HEAD, never the
     URL's user or password; a wrong machine, database (live or in the URL), host or HEAD is refused.
Runs the real scripts in bash (Git Bash on Windows) with stub pg_dump / pg_restore / psql / hostname on PATH.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
HELPER = OPS / "lib" / "icb_backup.sh"
WHERE = OPS / "lib" / "icb_where.sh"
RETIRED = ["prod-rt1/rt1_data.sh", "prod-rt1/rt1_factor.sh", "prod-rt2/rt2_data.sh", "prod-rt3/rt3_families.sh",
           "prod-rt4/rt4_data.sh", "prod-pricing-corrections/pc_prod.sh"]


def _bash() -> str | None:
    if sys.platform == "win32":
        for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
            if Path(p).exists():
                return p
        return None                       # never WSL's bash.exe: it cannot see these paths
    return shutil.which("bash")


BASH = _bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="no bash (Git Bash) on this machine")


def run(script: str, path_dir: Path | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    # the stubs go first on PATH, in bash's own (POSIX) form: Git Bash re-orders a Windows-style PATH it inherits
    if path_dir is not None:
        script = f'export PATH="{posix(path_dir)}:$PATH"; ' + script
    return subprocess.run([BASH, "-c", script], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, timeout=60)


def posix(p: Path) -> str:
    s = str(p).replace("\\", "/")
    return re.sub(r"^([A-Za-z]):", lambda m: "/" + m.group(1).lower(), s) if sys.platform == "win32" else s


def stub(d: Path, name: str, body: str) -> None:
    f = d / name
    f.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8", newline="\n")
    f.chmod(0o755)


# ── 1. the CI guard ──────────────────────────────────────────────────────────
_CMD = re.compile(r"(?:^\s*|[;&({]\s*|\b(?:then|do|else)\s+|\|\|\s*|&&\s*)pg_dump\b")


def bare_pg_dump_pipes(text: str) -> list[str]:
    """Logical lines (continuations joined, comments and heredoc bodies skipped) where pg_dump's output feeds a pipe."""
    out, heredoc, buf = [], None, ""
    for raw in text.splitlines():
        if heredoc:
            if raw.strip() == heredoc:
                heredoc = None
            continue
        m = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", raw)
        line = buf + raw
        if line.rstrip().endswith("\\"):
            buf = line.rstrip()[:-1] + " "
            continue
        buf = ""
        if m:
            heredoc = m.group(1)
        if line.lstrip().startswith("#"):
            continue
        c = _CMD.search(line)
        if c and re.search(r"(?<!\|)\|(?!\|)", line[c.end():]):
            out.append(line.strip())
    return out


def is_retired(text: str) -> bool:
    head = text.splitlines()[:12]
    return any("RETIRED (RT6" in ln for ln in head) and any(re.search(r";\s*exit 3\s*$", ln) for ln in head)


def test_no_script_in_ops_pipes_pg_dump_outside_the_helper():
    bad = {}
    for f in sorted(OPS.rglob("*.sh")):
        if f == HELPER:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        hits = bare_pg_dump_pipes(text)
        if hits and not is_retired(text):
            bad[str(f.relative_to(ROOT))] = hits
    assert bad == {}, f"pg_dump piped without ops/lib/icb_backup.sh: {bad}"
    assert bare_pg_dump_pipes(HELPER.read_text(encoding="utf-8")), "the helper itself is the one place a pipe lives"


@pytest.mark.parametrize("text,caught", [
    ('pg_dump "$URL" --data-only -t x | gzip > "$BK" || stop BACKUP "x"', True),
    ('  pg_dump "$URL" --data-only -t a -t b \\\n    | gzip > "$BK" || stop', True),
    ('if true; then pg_dump "$URL" | gzip > f; fi', True),
    ('pg_dump "$URL" -Fc -f "$BK" || stop BACKUP "pg_dump failed"', False),
    ('# pg_dump "$URL" | gzip > f   (a comment)', False),
    ('cat > "$SIM/bin/pg_dump" <<\'EOF\'\npg_dump x | y\nEOF', False),
    ('icb_backup "$BK" data-gz "$URL" icb_costings.t || stop BACKUP "$ICB_BACKUP_WHY"', False),
    ('echo "pg_dump stub: unexpected | table"', False),
])
def test_the_scanner_catches_a_bare_pipe_and_nothing_else(text, caught):
    assert bool(bare_pg_dump_pipes(text)) is caught


# ── 2. the retired kits ──────────────────────────────────────────────────────
@needs_bash
@pytest.mark.parametrize("kit", RETIRED)
def test_a_retired_kit_refuses_to_run(kit, tmp_path):
    text = (OPS / kit).read_text(encoding="utf-8")
    assert is_retired(text) and bare_pg_dump_pipes(text)      # retired, so its old pipe can never run again
    r = run(f'cd "{posix(tmp_path)}" && bash "{posix(OPS / kit)}" apply')
    assert r.returncode == 3 and "RETIRED (RT6" in r.stderr and r.stdout == ""
    assert list(tmp_path.iterdir()) == []                      # nothing written


# ── 3. the helper ────────────────────────────────────────────────────────────
@pytest.fixture()
def stubs(tmp_path):
    d = tmp_path / "bin"
    d.mkdir()
    return d


def backup(stubs, tmp_path, fmt="data-gz", tables="icb_costings.trailer_groups"):
    out = tmp_path / "bk.sql.gz"
    r = run(f'. "{posix(HELPER)}"; icb_backup "{posix(out)}" {fmt} "postgresql://u:p@h/db" {tables}; '
            'echo "rc=$?"; echo "why=$ICB_BACKUP_WHY"; echo "sha=$ICB_BACKUP_SHA"', stubs)
    return r, out


@needs_bash
def test_a_failed_pg_dump_stops_the_step(stubs, tmp_path):
    stub(stubs, "pg_dump", 'echo "pg_dump: error: connection refused" >&2; exit 1')
    r, out = backup(stubs, tmp_path)
    assert "rc=1" in r.stdout and "pg_dump exited 1, gzip 0" in r.stdout, r.stdout + r.stderr
    assert not out.exists() and (tmp_path / "bk.sql.gz.FAILED").exists()   # never mistaken for a backup


@needs_bash
def test_a_dump_that_lacks_a_touched_table_stops_the_step(stubs, tmp_path):
    stub(stubs, "pg_dump", 'echo "COPY icb_costings.other (id) FROM stdin;"; echo "\\."')
    r, _ = backup(stubs, tmp_path, tables="icb_costings.trailer_groups")
    assert "rc=1" in r.stdout and "holds no icb_costings.trailer_groups data" in r.stdout


@needs_bash
def test_a_good_dump_passes_with_its_size_and_sha(stubs, tmp_path):
    stub(stubs, "pg_dump", 'echo "COPY icb_costings.trailer_groups (id, name) FROM stdin;"; echo "1\tX"; echo "\\."')
    r, out = backup(stubs, tmp_path)
    assert "rc=0" in r.stdout and re.search(r"sha=[0-9a-f]{64}", r.stdout) and "   ok   backup" in r.stdout
    assert out.exists() and out.stat().st_size > 0


@needs_bash
def test_the_custom_format_is_checked_by_pg_restore(stubs, tmp_path):
    stub(stubs, "pg_dump", 'for a in "$@"; do [ "$prev" = -f ] && echo dump > "$a"; prev=$a; done')
    stub(stubs, "pg_restore", 'echo "4321; 0 1 TABLE DATA icb_costings bill_of_materials icb_app"')
    r, _ = backup(stubs, tmp_path, fmt="custom", tables="icb_costings.bill_of_materials")
    assert "rc=0" in r.stdout, r.stdout + r.stderr
    r2, _ = backup(stubs, tmp_path / ".." / tmp_path.name, fmt="custom", tables="icb_costings.calculations")
    assert "rc=1" in r2.stdout and ("holds no icb_costings.calculations data" in r2.stdout or "already exists" in r2.stdout)


# ── 4. the safe-paste first line ─────────────────────────────────────────────
@pytest.fixture()
def repo(tmp_path):
    g = tmp_path / "repo"
    g.mkdir()
    for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=x@x", "-c", "user.name=x", "commit", "-q",
                                        "--allow-empty", "-m", "x"]):
        subprocess.run(cmd, cwd=g, check=True, capture_output=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=g, capture_output=True, text=True).stdout.strip()
    return g, head


def where(stubs, repo_dir, url, expect: dict, machine="icb-mes-prod", live_db="icb_platform"):
    stub(stubs, "hostname", f'echo {machine}')
    stub(stubs, "psql", f'echo {live_db}')
    exports = " ".join(f'{k}="{v}"' for k, v in expect.items())
    return run(f'{exports}; . "{posix(WHERE)}"; icb_where "test step" "{posix(repo_dir)}" "{url}"; '
               'icb_where_check; echo "rc=$?"; echo "why=$WHERE_WHY"', stubs)


URL = "postgresql://icb_app:s3cret-not-real@127.0.0.1:5432/icb_platform"


@needs_bash
def test_the_first_line_names_machine_database_and_head_and_the_right_place_passes(stubs, repo):
    g, head = repo
    r = where(stubs, g, URL, {"EXPECT_MACHINE": "icb-mes-prod", "EXPECT_DB": "icb_platform",
                              "EXPECT_DBHOST": "127.0.0.1:5432", "EXPECT_HEADS": head})
    first = r.stdout.splitlines()[0]
    assert first.startswith("######## RT6 test step · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head "
                            + head[:7]), first
    assert "rc=0" in r.stdout and "s3cret" not in r.stdout and "icb_app" not in r.stdout


@needs_bash
@pytest.mark.parametrize("case,why", [
    ("machine", "machine is 'dev-laptop'"), ("live_db", "database is 'icb'"), ("url_db", "the URL names database 'icb'"),
    ("host", "database host is 'localhost:5433'"), ("head", "code is at"),
])
def test_a_wrong_machine_database_host_or_head_is_refused(stubs, repo, case, why):
    g, head = repo
    exp = {"EXPECT_MACHINE": "icb-mes-prod", "EXPECT_DB": "icb_platform", "EXPECT_DBHOST": "127.0.0.1:5432",
           "EXPECT_HEADS": head}
    kw, url = {}, URL
    if case == "machine":
        kw["machine"] = "dev-laptop"
    elif case == "live_db":
        kw["live_db"] = "icb"
    elif case == "url_db":
        url = URL.replace("/icb_platform", "/icb")
    elif case == "host":
        url = URL.replace("127.0.0.1:5432", "localhost:5433")
    else:
        exp["EXPECT_HEADS"] = "0" * 40
    r = where(stubs, g, url, exp, **kw)
    assert "rc=1" in r.stdout and "WRONG PLACE" in r.stdout and why in r.stdout and "nothing was run" in r.stdout
