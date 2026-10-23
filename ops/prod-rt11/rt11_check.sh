#!/usr/bin/env bash
# RT11 §3.0 — "Generate Quote" (the MES letterhead quote: HTML templates → WeasyPrint → PDF) on prod: what installing
# WeasyPrint would take. READ ONLY. Michael runs ONE line on his laptop (run_check.ps1): it copies this kit to prod
# /tmp, runs THIS file by path under sudo over `ssh -t`, fetches the report, and reads back that prod /tmp holds
# nothing of the check afterwards. On the VM itself:
#
#     sudo bash /tmp/icb-rt11-check/rt11_check.sh
#
# Its FIRST output line names the machine, the database (name and host), the git HEAD and the boot time, and it
# refuses unless they are prod's and the kit was stamped after the last boot (ops/lib/icb_where.sh). Then, each a read:
#   1. the machine: the Ubuntu release, the kernel, the architecture;
#   2. the deployed venv: its python and pip, and whether weasyprint imports today;
#   3. the system libraries WeasyPrint needs (Pango, HarfBuzz and its subsetter, fontconfig) and the fonts: dpkg,
#      fc-list, and what fontconfig hands back for Arial, sans-serif and monospace;
#   4. `apt-get -s install --no-install-recommends <APT_PKGS>`: a SIMULATION on the package lists as they are (no
#      `apt-get update`, no dpkg lock): what would be newly installed, and whether anything would be upgraded;
#   5. `pip install --dry-run -r <the base requirements + WEASY_PIN>` with the deployed venv's python, run as `nobody`
#      (who cannot write the venv) with no cache: what would be installed, and whether an installed package changes;
#   6. who holds quote.generate: the roles granted it and the users per role, and the per-user overrides — role
#      names and counts only (G4: no names); admin is a wildcard in code (deps.user_can);
#   7. the letterhead templates, the body families and body types they serve, the live body costings per template;
#   8. the SUMMARY line, then the DONE line.
# A finding (pip cannot reach PyPI, apt does not know a package) is printed and summarised, not a STOP: this check
# answers questions. It STOPs only when it cannot trust where it is or what it reads.
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on, asserted); every SQL statement is
# a fixed SELECT below (backend/tests/test_ops_rt11.py runs them on the test database). No service is touched;
# nothing under /opt/icb-platform changes. The report is /tmp/icb-rt11-check-report.txt, handed to the sudo user (the
# laptop fetches it, then rt11_vm.sh readback removes it). When this file ends — DONE or STOP — it removes its own kit
# (/tmp/icb-rt11-check and its .tar, by exact name). Deliberately no bare `set -e`: every check is a loud STOP.
set -u
set -o pipefail
BASE=/tmp/icb-rt11-check
KIT_DIR=$BASE          # lib/icb_where.sh's reboot guard: KIT_DIR/.staged_at (written by the copy) must post-date the last boot
ICB_LANE=RT11
REPO=/opt/icb-platform
ENVF=/etc/icb/backend.env
PY=$REPO/.venv/bin/python
REPORT=/tmp/icb-rt11-check-report.txt

# ── the reads: fixed SELECTs on icb_costings (schema-qualified; the session's search_path is not trusted) ──────────
SQL_QG_ROLES="SELECT rp.role FROM icb_costings.role_permissions rp JOIN icb_costings.permissions p ON p.id = rp.permission_id WHERE p.name = 'quote.generate' ORDER BY rp.role"
SQL_USERS_BY_ROLE="SELECT u.role, count(*) FROM icb_costings.users u GROUP BY u.role ORDER BY u.role"
SQL_QG_OVERRIDES="SELECT u.role, up.effect, count(*) FROM icb_costings.user_permissions up JOIN icb_costings.users u ON u.id = up.user_id JOIN icb_costings.permissions p ON p.id = up.permission_id WHERE p.name = 'quote.generate' GROUP BY u.role, up.effect ORDER BY 1, 2"
SQL_TEMPLATES="SELECT t.id, t.slug, t.kind, t.is_active FROM icb_costings.report_templates t ORDER BY t.id"
SQL_GROUPS="SELECT g.id, g.name, coalesce(t.slug, '-'), coalesce(t.is_active::text, '-') FROM icb_costings.trailer_groups g LEFT JOIN icb_costings.report_templates t ON t.id = g.report_template_id ORDER BY g.id"
# a body's template, as services.resolve_report_template decides it: an active override, else its group's active one
SQL_BODIES="SELECT tt.id, tt.name, coalesce(g.name, '-'), coalesce(CASE WHEN ot.is_active THEN ot.slug END, CASE WHEN gt.is_active THEN gt.slug END, '-') FROM icb_costings.trailer_types tt LEFT JOIN icb_costings.trailer_groups g ON g.id = tt.group_id LEFT JOIN icb_costings.report_templates ot ON ot.id = tt.override_report_template_id LEFT JOIN icb_costings.report_templates gt ON gt.id = g.report_template_id WHERE tt.is_active ORDER BY tt.id"
SQL_COSTINGS="SELECT coalesce(CASE WHEN ot.is_active THEN ot.slug END, CASE WHEN gt.is_active THEN gt.slug END, '-'), count(*), count(*) FILTER (WHERE c.created_at >= now() - interval '90 days'), count(*) FILTER (WHERE coalesce(c.discount_amount, 0) > 0) FROM icb_costings.calculations c JOIN icb_costings.trailer_types tt ON tt.id = c.trailer_type_id LEFT JOIN icb_costings.trailer_groups g ON g.id = tt.group_id LEFT JOIN icb_costings.report_templates ot ON ot.id = tt.override_report_template_id LEFT JOIN icb_costings.report_templates gt ON gt.id = g.report_template_id WHERE c.deleted_at IS NULL AND coalesce(c.is_repair, false) = false GROUP BY 1 ORDER BY 1"

stop() { echo; echo "######## STOP [$1]: $2"; echo "######## read only: nothing was changed on prod. Copy the whole window and paste it back to the CA."; exit 1; }
say()  { echo "== $*"; }
q()    { psql "$URL" -XAt -F ' | ' -c "$1" 2>&1; }       # one fixed SELECT; the session is read-only (PGOPTIONS)

main() {
  local ro alembic rc rel py pipv weasy pkgs fam apt_out apt_new apt_up lists pipout would n_new n_chg roles users
  local qg_users=0 over tmpl bodies served
  URL=''
  if [ -r "$ENVF" ]; then
    # only DATABASE_URL is taken, in a subshell: nothing else of the file enters this script, and it is never printed
    URL=$( set -a; . "$ENVF" >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
    URL=${URL/postgresql+psycopg:/postgresql:}
  fi
  export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
  # shellcheck disable=SC1091
  . "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT11 prod check (read only) · machine $(hostname -s) · db ? · head ?"; stop KIT "lib/icb_where.sh missing: paste the same line again"; }
  # shellcheck disable=SC1091
  . "$BASE/expected.env" 2>/dev/null || true
  icb_where "prod check (read only)" "$REPO" "$URL"
  [ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
  [ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENVF"
  for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM WEASY_PIN APT_PKGS; do
    [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
  done
  icb_where_check || stop WHERE "$WHERE_WHY"
  ( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "the kit's files do not match its SHA256SUMS: paste the same line again"
  ro=$(psql "$URL" -XAtc "select current_setting('transaction_read_only')" 2>&1) || stop DB "cannot open a session: $ro"
  [ "$ro" = on ] || stop DB "the session is not read-only ($ro)"
  alembic=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from icb_costings.alembic_version" 2>&1) || stop DB "cannot read alembic_version"
  [ "$alembic" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$alembic', this check expects $EXPECT_ALEMBIC"
  say "prod: alembic $alembic · every session read-only · kit staged from ${STAGED_FROM:0:7} · $(date '+%Y-%m-%d %H:%M:%S %Z')"

  say "1. the machine"
  rel=$( . /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-?}" )
  echo "   $rel · kernel $(uname -r) · $(dpkg --print-architecture 2>/dev/null || uname -m)"

  say "2. the deployed venv ($PY)"
  py=$("$PY" --version 2>&1) || py="? ($py)"
  pipv=$("$PY" -m pip --version 2>/dev/null | awk '{print $2}') || pipv='?'
  weasy=$(runuser -u nobody -- "$PY" -I -c 'import weasyprint; print(weasyprint.__version__)' 2>/dev/null) || weasy=absent
  [ -n "$weasy" ] || weasy=absent
  echo "   $py · pip ${pipv:-?} · weasyprint today: $weasy"

  say "3. the system libraries and fonts (dpkg; fontconfig)"
  pkgs=$(dpkg-query -W -f='${db:Status-Abbrev} ${Package} ${Version}\n' libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 libfontconfig1 fontconfig fontconfig-config libcairo2 2>&1 | sed 's/^dpkg-query: no packages found matching /absent  /')
  printf '%s\n' "$pkgs" | sed 's/^/   /'
  echo "   font packages: $(dpkg-query -W -f='${db:Status-Abbrev} ${Package}\n' 'fonts-*' 2>/dev/null | awk '$1 == "ii" { print $2 }' | paste -sd' ' || true)"
  if command -v fc-list >/dev/null 2>&1; then
    fam=$(fc-list : family 2>/dev/null | sort -u | paste -sd';' || true)
    echo "   font families: ${fam:-none}"
    echo "   fontconfig picks: Arial -> $(fc-match Arial 2>/dev/null || true) · sans-serif -> $(fc-match sans-serif 2>/dev/null || true) · monospace -> $(fc-match monospace 2>/dev/null || true)"
  else
    echo "   fontconfig is not installed (no fc-list)"
  fi

  say "4. apt-get -s install --no-install-recommends $APT_PKGS (a simulation: nothing is installed)"
  lists=$(ls -t /var/lib/apt/lists/*_Packages 2>/dev/null | head -n1)
  echo "   the package lists are as of $( [ -n "$lists" ] && date -r "$lists" '+%Y-%m-%d %H:%M %Z' || echo '?') (no apt-get update here)"
  # shellcheck disable=SC2086
  apt_out=$(LC_ALL=C apt-get -s -o Debug::NoLocking=1 install --no-install-recommends $APT_PKGS 2>&1); rc=$?
  printf '%s\n' "$apt_out" | grep -E '^(Inst |Remv |E: |[0-9]+ upgraded)' | sed 's/^/   /' || true
  apt_new=$(printf '%s\n' "$apt_out" | grep -cE '^Inst [^ ]+ \(' || true)
  apt_up=$(printf '%s\n' "$apt_out" | grep -cE '^Inst [^ ]+ \[' || true)
  [ "$rc" = 0 ] || { apt_new="?"; apt_up="?"; echo "   !! apt-get -s ended with exit $rc"; }

  say "5. pip install --dry-run -r the base requirements + $WEASY_PIN (as nobody, no cache: nothing is installed)"
  mkdir -p "$BASE/pip/home" "$BASE/pip/tmp" && chown -R nobody "$BASE/pip" && chmod -R a+rX "$BASE" || stop KIT "cannot prepare $BASE/pip"
  pipout=$(cd "$BASE/pip" && runuser -u nobody -- env -i PATH=/usr/bin:/bin HOME="$BASE/pip/home" TMPDIR="$BASE/pip/tmp" \
             PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1 \
             "$PY" -m pip install --dry-run -r "$BASE/requirements-rt11.txt" 2>&1); rc=$?
  would=$(printf '%s\n' "$pipout" | sed -n 's/^Would install //p' | tail -n1)
  if [ "$rc" = 0 ]; then
    local installed name ver item
    installed=$(runuser -u nobody -- env -i PATH=/usr/bin:/bin HOME="$BASE/pip/home" "$PY" -m pip list --format=freeze --disable-pip-version-check 2>/dev/null \
                | tr 'A-Z_' 'a-z-')
    n_new=0; n_chg=0
    for item in $would; do
      name=$(printf '%s' "${item%-*}" | tr 'A-Z_' 'a-z-'); ver=${item##*-}
      if printf '%s\n' "$installed" | grep -q "^$name=="; then
        n_chg=$((n_chg + 1)); echo "   CHANGES AN INSTALLED PACKAGE: $(printf '%s\n' "$installed" | grep "^$name==") -> $ver"
      else
        n_new=$((n_new + 1)); echo "   new: $name $ver"
      fi
    done
    [ -n "$would" ] || echo "   pip would install nothing"
  else
    n_new="?"; n_chg="?"
    echo "   !! pip --dry-run FAILED (exit $rc); its last lines:"
    printf '%s\n' "$pipout" | tail -n 6 | sed 's/^/      /'
  fi
  echo "   /etc/pip.conf: $( [ -e /etc/pip.conf ] && echo present || echo absent) · a proxy in /etc/environment: $(grep -qiE '^(https?|all)_proxy=' /etc/environment 2>/dev/null && echo set || echo 'not set')"

  say "6. who holds quote.generate (role names and counts; no names: G4)"
  roles=$(q "$SQL_QG_ROLES") || stop DB "the role grants could not be read: $roles"
  echo "   granted by role: $(printf '%s\n' "$roles" | paste -sd' ' -) (admin is a wildcard in code: deps.user_can)"
  users=$(q "$SQL_USERS_BY_ROLE") || stop DB "the users per role could not be read: $users"
  while IFS='|' read -r r n; do
    r=$(echo "$r" | xargs); n=$(echo "$n" | xargs); [ -n "$r" ] || continue
    if [ "$r" = admin ] || printf '%s\n' "$roles" | grep -qx "$r"; then echo "   role $r: $n user(s) — HOLDS it"; qg_users=$((qg_users + n)); else echo "   role $r: $n user(s) — does not hold it"; fi
  done <<< "$users"
  over=$(q "$SQL_QG_OVERRIDES") || stop DB "the per-user overrides could not be read: $over"
  echo "   per-user overrides (role | allow/deny | count): ${over:-none}"

  say "7. the letterhead templates and the bodies they serve"
  tmpl=$(q "$SQL_TEMPLATES") || stop DB "report_templates could not be read: $tmpl"
  printf '%s\n' "$tmpl" | sed 's/^/   template /'
  q "$SQL_GROUPS" | sed 's/^/   family /' || stop DB "trailer_groups could not be read"
  bodies=$(q "$SQL_BODIES") || stop DB "trailer_types could not be read: $bodies"
  printf '%s\n' "$bodies" | sed 's/^/   body /'
  served=$(printf '%s\n' "$bodies" | awk -F' [|] ' 'NF >= 4 && $4 != "-"' | grep -c . || true)
  echo "   live body costings per template (all · last 90 days · with a discount):"
  q "$SQL_COSTINGS" | sed 's/^/      /' || stop DB "the costings per template could not be read"

  echo
  echo "SUMMARY: $rel · ${py#Python } · pango $(printf '%s\n' "$pkgs" | awk '$1 == "ii" && $2 == "libpango-1.0-0" { v = $3 } END { print v ? v : "absent" }') harfbuzz $(printf '%s\n' "$pkgs" | awk '$1 == "ii" && $2 == "libharfbuzz0b" { v = $3 } END { print v ? v : "absent" }') · harfbuzz-subset $(printf '%s\n' "$pkgs" | awk '$2 == "libharfbuzz-subset0" && $1 == "ii" { f = 1 } END { print f ? "installed" : "absent" }') · apt: $apt_new new, $apt_up upgraded · pip: $n_new new, $n_chg changed · weasyprint $weasy · quote.generate: $(printf 'admin\n%s\n' "$roles" | grep -v '^$' | sort -u | paste -sd'+' -) ($qg_users users by role) · bodies with a template: $served of $(printf '%s\n' "$bodies" | grep -c . || true)"
  echo
  echo "######## DONE (read only)"
}

[ -L "$REPORT" ] && { echo "######## STOP [KIT]: $REPORT is a symbolic link: refusing to write through it"; exit 1; }
rm -f -- "$REPORT"
( set -C; : > "$REPORT" ) 2>/dev/null || { echo "######## STOP [KIT]: cannot create $REPORT"; exit 1; }
chmod 600 "$REPORT"
main 2>&1 | tee -a "$REPORT"
rc=${PIPESTATUS[0]}
# the kit goes now, DONE or STOP; the report stays only until the laptop has fetched it (then rt11_vm.sh readback)
rm -rf --one-file-system -- "$BASE" "$BASE.tar"
if [ -e "$BASE" ] || [ -e "$BASE.tar" ]; then kit="STILL THERE"; else kit="removed"; fi
owner=${SUDO_USER:-}
if [ -n "$owner" ] && [ "$owner" != root ]; then chown "$owner" "$REPORT" 2>/dev/null || true; fi
chmod 644 "$REPORT"
echo "== the kit on prod (/tmp/icb-rt11-check and its .tar): $kit; the report waits at $REPORT for the laptop" | tee -a "$REPORT"
exit "$rc"
