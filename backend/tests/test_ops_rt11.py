"""RT11 §3.0 — the read-only prod check for the letterhead quote (ops/prod-rt11).

  1. the reads: every SQL statement in rt11_check.sh is ONE schema-qualified SELECT that names no personal column
     (G4), with a negative control;
  2. the real reads on the test database in a read-only session: each statement runs; the body → template rule is
     the app's own (services.resolve_report_template) on an override, an inactive override, a group's template and
     no template — rows made inside a transaction that is rolled back; negative control: a rule without the
     override check disagrees;
  3. the laptop line, the VM helper and the runbook's block: ASCII, files run by path, fixed names, the agreed shape.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_ops_rt9 import BLOCK, inline_script_calls
from test_ops_rt10 import ps_case_collisions

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "ops" / "prod-rt11"
CHECK = (KIT / "rt11_check.sh").read_text(encoding="utf-8")
RUNBOOK = ROOT / "docs" / "runbooks" / "prod-check-rt11.md"
STAGE = r"C:\Users\micge\Documents\icb-rt11-stage\check"

SQL = dict(re.findall(r'^(SQL_[A-Z_]+)="([^"]+)"$', CHECK, re.M))
# what a statement may read from each table: role names, counts, slugs and body names only (G4)
PERSONAL = re.compile(r"\b(username|email|password\w*|contact_\w+|customer\w*|first_name|last_name|full_name|"
                      r"deleted_by|decline_reason|sales_rep_user_id|user_id\b(?! =))", re.I)


def sql_problems(sql: str) -> list[str]:
    probs = []
    if not re.match(r"SELECT ", sql):
        probs.append("not a SELECT")
    if ";" in sql or re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|TRUNCATE|GRANT|COPY|SET)\b", sql.replace("OFFSET", "")):
        probs.append("more than one plain read")
    for t in re.findall(r"\b(?:FROM|JOIN)\s+([\w.]+)", sql):
        if not t.startswith("icb_costings."):
            probs.append(f"table {t} is not schema-qualified")
    select_list = sql.split(" FROM ", 1)[0]
    if PERSONAL.search(select_list):
        probs.append(f"a personal column is selected: {PERSONAL.search(select_list).group(0)}")
    return probs


# ── 1. the reads ──────────────────────────────────────────────────────────────
def test_every_read_is_one_schema_qualified_select_of_no_personal_column():
    assert set(SQL) == {"SQL_QG_ROLES", "SQL_USERS_BY_ROLE", "SQL_QG_OVERRIDES", "SQL_TEMPLATES", "SQL_GROUPS",
                        "SQL_BODIES", "SQL_COSTINGS"}
    assert {k: sql_problems(v) for k, v in SQL.items()} == {k: [] for k in SQL}
    # the users table is read for its role column and a count, nothing else
    assert SQL["SQL_USERS_BY_ROLE"] == "SELECT u.role, count(*) FROM icb_costings.users u GROUP BY u.role ORDER BY u.role"


@pytest.mark.parametrize("bad", [
    "SELECT u.username, count(*) FROM icb_costings.users u GROUP BY 1",
    "SELECT u.role, u.email FROM icb_costings.users u",
    "SELECT c.contact_name FROM icb_costings.calculations c",
    "SELECT role FROM role_permissions",
    "SELECT 1; DELETE FROM icb_costings.users",
])
def test_negative_control_a_personal_column_a_bare_table_or_a_second_statement_is_caught(bad):
    assert sql_problems(bad)


def test_the_check_reads_through_its_session_only_and_asserts_read_only_first():
    assert "export PGOPTIONS='-c default_transaction_read_only=on'" in CHECK
    assert CHECK.index('[ "$ro" = on ] || stop DB') < CHECK.index('q "$SQL_QG_ROLES"')
    # every SELECT goes through q() — psql with the read-only PGOPTIONS — never another client
    assert re.findall(r'q "\$(SQL_[A-Z_]+)"', CHECK) == ["SQL_QG_ROLES", "SQL_USERS_BY_ROLE", "SQL_QG_OVERRIDES",
                                                         "SQL_TEMPLATES", "SQL_GROUPS", "SQL_BODIES", "SQL_COSTINGS"]


def test_pip_runs_dry_as_nobody_with_no_cache_and_apt_only_simulates():
    assert re.search(r'runuser -u nobody -- env -i .*\n.*PIP_NO_CACHE_DIR=1.*\n.*"\$PY" -m pip install --dry-run -r '
                     r'"\$BASE/requirements-rt11\.txt"', CHECK)
    code = [l for l in CHECK.splitlines() if not l.lstrip().startswith("#")]
    runs = [l.strip() for l in code if re.search(r"(^|[(=]\s*|LC_ALL=C )apt-get ", l.strip())]
    assert runs == ['apt_out=$(LC_ALL=C apt-get -s -o Debug::NoLocking=1 install --no-install-recommends $APT_PKGS 2>&1); rc=$?']
    assert not [l for l in code if "apt-get update" in l and "(no apt-get update here)" not in l]
    mk = (KIT / "mkstage_check.sh").read_text(encoding="utf-8")
    assert "WEASY_PIN=weasyprint==70.0" in mk
    assert 'APT_PKGS="libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0"' in mk


# ── 2. the real reads ───────────────────────────────────────────────────────
def _dsn() -> str:
    from app.config import settings
    return settings.DATABASE_URL.replace("postgresql+psycopg:", "postgresql:", 1)


def _arity(sql: str) -> int:
    return len(re.split(r",\s*(?![^()]*\))", sql[len("SELECT "):sql.index(" FROM ")]))


def test_every_read_runs_in_a_read_only_session_on_the_real_schema():
    import psycopg
    with psycopg.connect(_dsn(), options="-c default_transaction_read_only=on") as conn:
        assert conn.execute("select current_setting('transaction_read_only')").fetchone()[0] == "on"
        for name, sql in SQL.items():
            rows = conn.execute(sql).fetchall()
            assert all(len(r) == _arity(sql) for r in rows), name
        conn.rollback()


def _bodies_rule(conn) -> dict:
    return {r[0]: (None if r[3] == "-" else r[3]) for r in conn.execute(SQL["SQL_BODIES"]).fetchall()}


def test_the_body_to_template_rule_is_the_apps_own_and_the_nc_without_the_override_disagrees(monkeypatch):
    """Rows made in ONE transaction that is rolled back: nothing is left on the test database."""
    import psycopg
    from types import SimpleNamespace
    from app.services import resolve_report_template
    with psycopg.connect(_dsn()) as conn:
        cur = conn.cursor()
        mk_t = lambda slug, active: cur.execute(
            "INSERT INTO icb_costings.report_templates (name, slug, is_active, kind) VALUES (%s, %s, %s, 'html') RETURNING id",
            (slug, slug, active)).fetchone()[0]
        t_grp, t_ovr, t_off = mk_t("rt11t_group", True), mk_t("rt11t_override", True), mk_t("rt11t_off", False)
        g = cur.execute("INSERT INTO icb_costings.trailer_groups (name, report_template_id) VALUES ('RT11T GROUP', %s) RETURNING id",
                        (t_grp,)).fetchone()[0]
        g_none = cur.execute("INSERT INTO icb_costings.trailer_groups (name) VALUES ('RT11T NONE') RETURNING id").fetchone()[0]
        mk_b = lambda name, grp, ovr: cur.execute(
            "INSERT INTO icb_costings.trailer_types (name, is_active, configurator_v2, group_id, "
            "override_report_template_id) VALUES (%s, true, false, %s, %s) RETURNING id", (name, grp, ovr)).fetchone()[0]
        bodies = {mk_b("RT11T OVERRIDE", g, t_ovr): "rt11t_override",       # an active override wins
                  mk_b("RT11T OFF", g, t_off): "rt11t_group",               # an inactive override falls to the group
                  mk_b("RT11T GROUP", g, None): "rt11t_group",              # the group's template
                  mk_b("RT11T NOTHING", g_none, None): None}                # no template at all
        rule = _bodies_rule(conn)
        # the app's own resolver, over the same rows
        tmpl = {i: SimpleNamespace(slug=s, is_active=a) for i, s, a in
                cur.execute("SELECT id, slug, is_active FROM icb_costings.report_templates").fetchall()}
        grp = {i: SimpleNamespace(report_template=tmpl.get(t)) for i, t in
               cur.execute("SELECT id, report_template_id FROM icb_costings.trailer_groups").fetchall()}
        app = {}
        for i, gid, ov in cur.execute("SELECT id, group_id, override_report_template_id FROM icb_costings.trailer_types "
                                      "WHERE is_active").fetchall():
            tt = SimpleNamespace(override_report_template_id=ov, override_template=tmpl.get(ov), group=grp.get(gid))
            r = resolve_report_template(tt)
            app[i] = r.slug if r else None
        assert {b: rule[b] for b in bodies} == bodies
        assert rule == app                                  # every active body on the test database, not only mine
        # negative control: the same rule without the override check names the group's template for RT11T OVERRIDE
        nc = SQL["SQL_BODIES"].replace("CASE WHEN ot.is_active THEN ot.slug END, ", "")
        nc_rule = {r[0]: r[3] for r in cur.execute(nc).fetchall()}
        assert [b for b in bodies if (nc_rule[b] if nc_rule[b] != "-" else None) != bodies[b]] == [next(iter(bodies))]
        conn.rollback()
    with psycopg.connect(_dsn()) as conn:
        assert conn.execute("SELECT count(*) FROM icb_costings.trailer_types WHERE name LIKE 'RT11T %'").fetchone()[0] == 0


# ── 3. the laptop line, the VM helper, the runbook block ─────────────────────
def test_the_line_is_ascii_runs_files_by_path_and_never_pipes_the_sudo_session():
    raw = (KIT / "run_check.ps1").read_bytes()
    assert all(b < 0x80 for b in raw), "run_check.ps1 is not ASCII (Windows PowerShell 5.1 reads it as ANSI)"
    text = raw.decode("ascii")
    assert inline_script_calls(text) == []
    remotes = re.findall(r"'((?:sudo )?bash /tmp/[^']+)'", text)
    assert remotes == ["bash /tmp/icb-rt11-vm.sh where", "bash /tmp/icb-rt11-vm.sh unpack",
                       "sudo bash /tmp/icb-rt11-check/rt11_check.sh", "bash /tmp/icb-rt11-vm.sh readback"]
    assert text.count("192.168.0.251") == 1 and "$Vm     = 'mickeyger@192.168.0.251'" in text   # the sim's one host line
    assert "& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm 'sudo bash" in text and "| Out-Host" not in text
    assert "& scp -q" not in text
    for p in (KIT / "run_check.ps1", KIT / "sim" / "ps51" / "run_block.ps1"):
        assert ps_case_collisions(p.read_text(encoding="ascii")) == [], p.name


def test_the_vm_helper_and_the_check_act_only_on_fixed_names():
    text = (KIT / "rt11_vm.sh").read_text(encoding="utf-8")
    names = re.search(r'NAMES="([^"]*)"', text).group(1).replace("$REPORT", "/tmp/icb-rt11-check-report.txt").split()
    assert names == ["/tmp/icb-rt11-check", "/tmp/icb-rt11-check.tar", "/tmp/icb-rt11-check-report.txt"]
    assert 'rm -rf --one-file-system -- "$BASE" "$BASE.tar"' in CHECK and "BASE=/tmp/icb-rt11-check" in CHECK
    assert "set -e\n" not in CHECK and "set -e\n" not in text
    # pip's home, temp and report live under the kit, which the check removes: nothing of pip is left in /tmp
    assert 'HOME="$BASE/pip/home" TMPDIR="$BASE/pip/tmp"' in CHECK


def test_the_runbook_block_is_the_agreed_shape_and_names_the_stage_line():
    md = RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = list(BLOCK.finditer(md))
    assert len(blocks) == 1, [b["cmd"] for b in blocks]
    b = blocks[0]
    assert b["win"].startswith("PowerShell (your laptop)")
    assert b["cmd"] == f'powershell -NoProfile -ExecutionPolicy Bypass -File "{STAGE}\\run_check.ps1"'
    assert all(0x20 <= ord(c) < 0x7F for c in b["cmd"])
    line = (KIT / "run_check.ps1").read_text(encoding="ascii")
    assert b["first"].startswith("######## RT11 prod check (read only)") and "######## RT11 prod check (read only)" in line
    assert b["ends"].startswith("######## DONE - read only.") and "######## DONE - read only." in line
    assert "VM password" in b["asks"]
