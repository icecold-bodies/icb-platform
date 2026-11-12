#!/usr/bin/env bash
# RT10 (RT10_RULING_1 Q3 ii) — revisions on prod. READ ONLY. Michael runs ONE line on his laptop (run_check.ps1):
# it copies this kit to prod /tmp, runs THIS file by path under sudo over `ssh -t`, fetches the report, and reads
# back that prod /tmp holds nothing of the check afterwards. On the VM itself:
#
#     sudo bash /tmp/icb-rt10-check/rt10_check.sh
#
# Its FIRST output line names the machine, the database (name and host), the git HEAD and the boot time, and it
# refuses unless they are prod's and the kit was stamped after the last boot (ops/lib/icb_where.sh). Then:
#   1. rt10_revisions.py under the DEPLOYED venv's python: quote numbers with 2+ rows (ids, versions, statuses,
#      times, deleted, the production job each was built into), live duplicate versions, rows accepted while a newer
#      live revision existed, jobs built from an older revision — allow-listed reads only (G4: no names);
#   2. the SUMMARY line, then the DONE line.
# Every database session is read-only (PGOPTIONS default_transaction_read_only=on, asserted by psql and again by the
# python). No service is touched; nothing under /opt/icb-platform changes (no __pycache__: run from /tmp).
#
# The report is written to /tmp/icb-rt10-check-report.txt and handed to the sudo user (the laptop fetches it, then
# rt10_vm.sh readback removes it). When this file ends — DONE or STOP — it removes its own kit (/tmp/icb-rt10-check
# and /tmp/icb-rt10-check.tar, by exact name): RT9's lesson, no second paste just to tidy /tmp.
# Deliberately no bare `set -e`: every check is a loud STOP.
set -u
set -o pipefail
BASE=/tmp/icb-rt10-check
KIT_DIR=$BASE          # lib/icb_where.sh's reboot guard: KIT_DIR/.staged_at (written by the copy) must post-date the last boot
ICB_LANE=RT10
REPO=/opt/icb-platform
ENVF=/etc/icb/backend.env
PY=$REPO/.venv/bin/python
REPORT=/tmp/icb-rt10-check-report.txt

stop() { echo; echo "######## STOP [$1]: $2"; echo "######## read only: nothing was changed on prod. Copy the whole window and paste it back to the CA."; exit 1; }
say()  { echo "== $*"; }

main() {
  local url='' ro alembic rc summary
  if [ -r "$ENVF" ]; then
    # only DATABASE_URL is taken, in a subshell: nothing else of the file enters this script, and it is never printed
    url=$( set -a; . "$ENVF" >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
    url=${url/postgresql+psycopg:/postgresql:}
  fi
  export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
  # shellcheck disable=SC1091
  . "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT10 prod check (read only) · machine $(hostname -s) · db ? · head ?"; stop KIT "lib/icb_where.sh missing: paste the same line again"; }
  # shellcheck disable=SC1091
  . "$BASE/expected.env" 2>/dev/null || true
  icb_where "prod check (read only)" "$REPO" "$url"
  [ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
  [ -n "$url" ] || stop KIT "DATABASE_URL not found in $ENVF"
  for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do
    [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
  done
  icb_where_check || stop WHERE "$WHERE_WHY"
  ( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "the kit's files do not match its SHA256SUMS: paste the same line again"
  ro=$(psql "$url" -XAtc "select current_setting('transaction_read_only')" 2>&1) || stop DB "cannot open a session: $ro"
  [ "$ro" = on ] || stop DB "the session is not read-only ($ro)"
  alembic=$(psql "$url" -XAtc "select string_agg(version_num, ',') from alembic_version" 2>&1) || stop DB "cannot read alembic_version"
  [ "$alembic" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$alembic', this check expects $EXPECT_ALEMBIC"
  say "prod: alembic $alembic · every session read-only · kit staged from ${STAGED_FROM:0:7} · $(date '+%Y-%m-%d %H:%M:%S %Z')"
  say "times are as the database stores them; its TimeZone setting is $(psql "$url" -XAtc 'show timezone' 2>/dev/null || echo '?')"

  say "1. revisions: quote numbers with 2 or more rows (ids, versions, statuses, times; no names)"
  ( cd /tmp && RT10_DB_URL="$url" PYTHONDONTWRITEBYTECODE=1 "$PY" -I "$BASE/rt10_revisions.py" ) > "$BASE/revisions.txt" 2>&1; rc=$?
  sed 's/^/   /' "$BASE/revisions.txt"
  [ "$rc" = 0 ] || stop REPORT "the report did not run (exit $rc): $(tail -n1 "$BASE/revisions.txt")"
  summary=$(sed -n 's/^SUMMARY: //p' "$BASE/revisions.txt" | tail -n1)
  [ -n "$summary" ] || stop REPORT "the report printed no SUMMARY line"
  [ -z "$(find "$REPO" -name __pycache__ -newer "$BASE/revisions.txt" 2>/dev/null | head -n1)" ] || echo "   !! a __pycache__ appeared under $REPO: tell the CA"
  echo
  echo "######## DONE (read only): $summary"
}

[ -L "$REPORT" ] && { echo "######## STOP [KIT]: $REPORT is a symbolic link: refusing to write through it"; exit 1; }
rm -f -- "$REPORT"
( set -C; : > "$REPORT" ) 2>/dev/null || { echo "######## STOP [KIT]: cannot create $REPORT"; exit 1; }
chmod 600 "$REPORT"
main 2>&1 | tee -a "$REPORT"
rc=${PIPESTATUS[0]}
# the kit goes now, DONE or STOP; the report stays only until the laptop has fetched it (then rt10_vm.sh readback)
rm -rf --one-file-system -- "$BASE" "$BASE.tar"
if [ -e "$BASE" ] || [ -e "$BASE.tar" ]; then kit="STILL THERE"; else kit="removed"; fi
# The last line goes in BEFORE the report is handed to the sudo user (RT10_RULING_3): prod's fs.protected_regular=2
# refuses even root an O_CREAT open of a file another user owns in the sticky /tmp, so an append after the chown
# printed "tee: … Permission denied" and the line was missing from the report (23 Oct 17:18; RT11 saw it too).
echo "== the kit on prod (/tmp/icb-rt10-check and its .tar): $kit; the report waits at $REPORT for the laptop" | tee -a "$REPORT"
owner=${SUDO_USER:-}
if [ -n "$owner" ] && [ "$owner" != root ]; then chown "$owner" "$REPORT" 2>/dev/null || true; fi
chmod 644 "$REPORT"
exit "$rc"
