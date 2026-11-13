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


def writes_after_handover(text: str) -> list[str]:
    """RT11_RULING_0A — prod runs fs.protected_regular=2: once the report in /tmp is chown'd to the sudo user, root may
    no longer open it with O_CREAT (`tee -a`, `>>`). Every write to it after the chown line is a defect."""
    i = text.find('chown "$owner" "$REPORT"')
    tail = text[i:] if i >= 0 else ""
    return [l.strip() for l in tail.splitlines() if re.search(r'(tee -a|>>?)\s*"\$REPORT"', l)]


def test_nothing_is_written_to_the_report_after_it_is_handed_over_and_the_sim_enforces_prods_tmp_rule():
    assert writes_after_handover(CHECK) == []
    assert CHECK.index('| tee -a "$REPORT"\nowner=') < CHECK.index('chown "$owner" "$REPORT"')   # the closing line first
    fake = (KIT / "sim" / "fakeprod.sh").read_text(encoding="utf-8")
    assert "export SUDO_USER=mickeyger" in fake and 'chmod 1777 "$SIM/tmp"' in fake
    assert '[ "$(sysctl -n fs.protected_regular 2>/dev/null)" = 2 ]' in fake
    assert "old_order" in (KIT / "sim" / "run_sim.sh").read_text(encoding="utf-8")   # the sim's negative control


def test_negative_control_the_3eb8def_ending_is_caught():
    old = ('owner=${SUDO_USER:-}\nif [ -n "$owner" ] && [ "$owner" != root ]; then chown "$owner" "$REPORT" 2>/dev/null || '
           'true; fi\nchmod 644 "$REPORT"\necho "== the kit on prod: $kit" | tee -a "$REPORT"\nexit "$rc"\n')
    assert writes_after_handover(old) == ['echo "== the kit on prod: $kit" | tee -a "$REPORT"']


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


# ── 4. the install kit (ops/prod-rt11/install): the release window's apt + pip steps ──────────────────────────────
INST = KIT / "install"
INSTALL = (INST / "rt11_install.sh").read_text(encoding="utf-8")
INSTALL_RUNBOOK = ROOT / "docs" / "runbooks" / "prod-install-rt11.md"
INSTALL_STAGE = r"C:\Users\micge\Documents\icb-rt11-stage\install"
STEPS = ["preflight", "apt", "pip", "verify", "rollback"]


def test_the_lock_is_the_ten_tested_packages_and_carries_the_requirements_pin():
    lock = (INST / "weasyprint-lock.txt").read_text(encoding="utf-8").split()
    assert len(lock) == 10 and all(re.fullmatch(r"[a-z0-9-]+==[0-9.]+", l) for l in lock), lock
    req = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "weasyprint==70.0" in lock and "weasyprint==70.0" in req       # the one pin, the same in both


def test_apt_adds_only_the_one_package_at_its_version_and_pip_only_the_lock_as_the_venv_owner():
    mk = (INST / "mkstage_install.sh").read_text(encoding="utf-8")
    assert "APT_PKG=libharfbuzz-subset0" in mk and "APT_VER=8.3.0-2build2" in mk
    code = [l.strip() for l in INSTALL.splitlines() if not l.lstrip().startswith("#")]
    real_apt = [l for l in code if re.match(r"(DEBIAN_FRONTEND=noninteractive )?apt-get ", l)]    # every apt-get it runs
    assert all("-s " in l for l in code if re.match(r"(\w+=\S+ )*(LC_ALL=C )?apt-get ", l) and l not in real_apt)
    assert real_apt == [
        'DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends --no-upgrade "$APT_PKG=$APT_VER" 2>&1 | grep -E \'^(Setting up|Unpacking|E:|[0-9]+ upgraded)\' | sed \'s/^/   /\'',
        'DEBIAN_FRONTEND=noninteractive apt-get remove -y "$APT_PKG" 2>&1 | grep -E \'^(Removing|E:)\' | sed \'s/^/   /\' || true']
    assert "apt-get update" not in "\n".join(code)
    installs = [l for l in code if "-m pip install" in l and "--dry-run" not in l]
    assert installs == ['pip_as "$vown" -m pip install --no-deps -r "$LOCK" 2>&1 | grep -E \'^(Successfully installed|ERROR)\' | sed \'s/^/   /\'']
    assert 'runuser -u "$u" -- env -i' in INSTALL and "PIP_NO_CACHE_DIR=1" in INSTALL
    assert '[ "$vown" != root ] || stop KIT' in INSTALL                     # never installs as root
    # the order is enforced in code: pip refuses before the RT11 code (the faces) and before apt
    pip = INSTALL[INSTALL.index("  pip)"):INSTALL.index("  verify)")]
    assert pip.index("stop ORDER \"the deployed code is not RT11's") < pip.index("stop ORDER \"$APT_PKG $APT_VER is not installed") < pip.index("--dry-run")


def test_the_install_kit_writes_nothing_to_its_report_after_the_hand_over_and_acts_on_fixed_names():
    assert writes_after_handover(INSTALL) == []
    assert 'rm -rf --one-file-system -- "$BASE" "$BASE.tar"' in INSTALL and "BASE=/tmp/icb-rt11-install" in INSTALL
    assert "set -e\n" not in INSTALL
    vm = (INST / "rt11_install_vm.sh").read_text(encoding="utf-8")
    names = re.search(r'NAMES="([^"]*)"', vm).group(1).replace("$REPORT", "/tmp/icb-rt11-install-report.txt").split()
    assert names == ["/tmp/icb-rt11-install", "/tmp/icb-rt11-install.tar", "/tmp/icb-rt11-install-report.txt"]


def test_the_install_line_runs_one_of_five_fixed_remote_lines_by_path_and_is_ascii():
    raw = (INST / "run_install.ps1").read_bytes()
    assert all(b < 0x80 for b in raw)
    text = raw.decode("ascii")
    assert inline_script_calls(text) == []
    table = dict(re.findall(r"^  '(\w+)'\s*= '(sudo bash /tmp/icb-rt11-install/rt11_install\.sh \w+)'$", text, re.M))
    assert table == {s: f"sudo bash /tmp/icb-rt11-install/rt11_install.sh {s}" for s in STEPS}
    assert "& ssh -t -o BatchMode=yes -o ConnectTimeout=10 $Vm $remote" in text and "$remote = $Steps[$Step]" in text
    assert re.findall(r"'(bash /tmp/icb-rt11-install-vm\.sh \w+)'", text) == [
        "bash /tmp/icb-rt11-install-vm.sh where", "bash /tmp/icb-rt11-install-vm.sh unpack",
        "bash /tmp/icb-rt11-install-vm.sh readback"]
    assert text.count("192.168.0.251") == 1 and "& scp -q" not in text
    for p in (INST / "run_install.ps1", INST / "sim" / "ps51" / "run_blocks.ps1"):
        assert ps_case_collisions(p.read_text(encoding="ascii")) == [], p.name


def test_the_install_runbook_has_the_five_blocks_in_order_in_the_agreed_shape():
    md = INSTALL_RUNBOOK.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = list(BLOCK.finditer(md))
    assert [b["cmd"] for b in blocks] == [
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "{INSTALL_STAGE}\\run_install.ps1" {s}' for s in STEPS]
    line = (INST / "run_install.ps1").read_text(encoding="ascii")
    assert "######## RT11 install: $Step ." in line and "######## DONE - $Step ($what)." in line
    for b, s in zip(blocks, STEPS):
        assert b["win"].startswith("PowerShell (your laptop)") and "VM password" in b["asks"]
        assert b["first"].startswith(f"######## RT11 install: {s} . machine LAPTOP-DGJ0U6RQ -> icb-mes-prod")
        assert b["ends"].startswith(f"######## DONE - {s} ({'read only' if s in ('preflight', 'verify') else 'it changes prod'}).")
