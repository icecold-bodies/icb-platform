#!/usr/bin/env bash
# RT6 §3.0 — Burt's rules as data: what the check would see on prod today. READ ONLY on prod. Michael runs ONE line
# on Windows (run_discovery.ps1 copies the kit, runs this over `ssh -t`, and fetches the result); on the VM itself:
#
#     sudo bash /tmp/icb-rt6-discovery/rt6_discovery.sh
#
# Its FIRST output line names the machine, the database (name and host) and the git HEAD, and it refuses unless they
# are prod's (ops/lib/icb_where.sh — RT6 safe pastes). Then:
#   1. rt6_discovery.py (psycopg only, one read-only session; the classifier is the staged copy of
#      backend/app/services/insulation_rules.py): the classification of every insulation master on the CHILLER and
#      FREEZER bodies, today's breaches under Burt's two rules (quote numbers only), the references, the drafts and
#      their backups that would offer a forbidden choice;
#   2. the environment files the service reads, KEY NAMES ONLY (the TEST SERVER banner's key);
#   3. /tmp, listed (the tidy's input): what would move, what stays.
#
# Against icb_platform it only SELECTs (every session read-only). Writes only under /tmp/icb-rt6-discovery/. No
# service is touched and nothing under /opt/icb-platform changes: not a deploy. Never prints a value from an
# environment file. Selects no customer, contact, end-user, user or person column (see rt6_discovery.py).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt6-discovery
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "${OUT:-/nonexistent}" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r /etc/icb/backend.env ]; then
  # only DATABASE_URL is taken, in a subshell: nothing else of the file enters this script
  URL=$( set -a; . /etc/icb/backend.env >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
export PGOPTIONS='-c default_transaction_read_only=on'     # every session below is read-only (libpq reads it)
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT6 discovery · machine $(hostname -s) · db ? · head ?"; stop KIT "lib/icb_where.sh missing: re-stage"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
icb_where "discovery (read only)" /opt/icb-platform "$URL"
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in /etc/icb/backend.env"
for v in EXPECT_MACHINE EXPECT_DB EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD)"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
RO=$(psql "$URL" -XAtc "select current_setting('transaction_read_only')") || stop DB "cannot read the session mode"
[ "$RO" = on ] || stop DB "the session is not read-only ($RO)"
say "prod: alembic=$ALEMBIC · read-only sessions · staged=${STAGED_FROM:0:7} · $(date -Is)"
export PYTHONDONTWRITEBYTECODE=1

# ---- 1. the rules on prod's data ---------------------------------------------------------------------------------
say "1. discovery (read-only session)"
"$PY" "$BASE/rt6_discovery.py" "$URL" "$OUT" > "$OUT/discovery.log" 2>&1; rc=$?
grep -E '^== |^   [A-Z#]|^      !!|^   LIVE|^      [A-Z0-9(]' "$OUT/discovery.log" | grep -v ' -> ' | head -n 120
[ $rc = 0 ] || { tail -n 20 "$OUT/discovery.log"; stop DISCOVERY "the discovery failed (exit $rc)"; }

# ---- 2. the environment the service reads: key NAMES only --------------------------------------------------------
say "2. the service's environment: key names only"
{
  echo "# icb-backend environment — KEY NAMES ONLY (no value is ever read out)"
  EF=$(systemctl show -p EnvironmentFiles --value icb-backend 2>/dev/null | sed 's/ *([a-z_]*=[a-z]*)//g')
  echo "EnvironmentFiles: ${EF:-(none)}"
  EKEYS=$(systemctl show -p Environment --value icb-backend 2>/dev/null | tr ' ' '\n' | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' | LC_ALL=C sort | tr '\n' ' ')
  echo "Environment keys set in the unit itself: ${EKEYS:-(none)}"
  for f in /etc/icb/backend.env /opt/icb-platform/backend/.env /opt/icb-platform/.env; do
    if [ -e "$f" ]; then
      echo "$f ($(stat -c '%U:%G %a' "$f")): $(sed -n 's/^[[:space:]]*\(export[[:space:]]\+\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)=.*/\2/p' "$f" | LC_ALL=C sort | tr '\n' ' ')"
    else
      echo "$f: absent"
    fi
  done
  for k in ICB_ENVIRONMENT ENVIRONMENT APP_ENV DEPLOYMENT_MODE DEBUG; do
    hit=$(grep -lE "^[[:space:]]*(export[[:space:]]+)?$k=" /etc/icb/backend.env /opt/icb-platform/backend/.env /opt/icb-platform/.env 2>/dev/null | tr '\n' ' ')
    echo "key $k: ${hit:-in no env file}"
  done
} > "$OUT/env_keys.txt" 2>&1
grep -E '^EnvironmentFiles|^key ' "$OUT/env_keys.txt" | sed 's/^/   /'

# ---- 3. /tmp, listed (read only) ---------------------------------------------------------------------------------
say "3. /tmp (read only): what the tidy would move, what stays"
{
  echo "# /tmp on $(hostname -s) at $(date -Is) — listed only; nothing moved"
  echo "# class  mtime  owner  type  bytes  files  name"
  find /tmp -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort | while IFS= read -r n; do
    p="/tmp/$n"
    case "$n" in
      systemd-private-*|snap-private-tmp|.X11-unix|.ICE-unix|.XIM-unix|.font-unix|.Test-unix|tmux-*) cls=OS-STAYS ;;
      node-compile-cache) cls=STAYS ;;
      icb-rt6-*|icb-rt6-*.tar) cls=RT6-KIT ;;
      *) cls=MOVE? ;;
    esac
    b=$(du -sb "$p" 2>/dev/null | cut -f1); nf=$(find "$p" -type f 2>/dev/null | wc -l)
    printf '%-8s %s %s %s %s %s %s\n' "$cls" "$(stat -c '%y' "$p" | cut -c1-16)" "$(stat -c '%U' "$p")" \
      "$(stat -c '%F' "$p" | tr ' ' _)" "${b:-?}" "$nf" "$n"
  done
  echo "# sha256 of every file under a MOVE? item (the archive will carry the same list)"
  find /tmp -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort | while IFS= read -r n; do
    case "$n" in systemd-private-*|snap-private-tmp|.X11-unix|.ICE-unix|.XIM-unix|.font-unix|.Test-unix|tmux-*|node-compile-cache|icb-rt6-*) continue ;; esac
    find "/tmp/$n" -type f -print0 2>/dev/null | LC_ALL=C sort -z | xargs -0 -r sha256sum 2>/dev/null
  done
} > "$OUT/tmp_listing.txt" 2>&1
grep -E '^(MOVE\?|STAYS|OS-STAYS|RT6-KIT) ' "$OUT/tmp_listing.txt" | awk '{c[$1]++; if ($1=="MOVE?") print "   MOVE?  "$7"  ("$5" bytes, "$6" files, "$2")"} END {for (k in c) printf "   %s: %d item(s)\n", k, c[k]}'

# ---- gate + pack -------------------------------------------------------------------------------------------------
# no email-shaped value, and no value from an env file, may leave the VM
EM=$(cat "$OUT/discovery.json" "$OUT/discovery.txt" "$OUT/env_keys.txt" | grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' || true)
[ "$EM" = 0 ] || { rm -f "$OUT"/discovery.* "$OUT/env_keys.txt"; stop GATE "an email-shaped value in the output — files deleted"; }
grep -qE '://|[A-Za-z0-9_]=' "$OUT/env_keys.txt" && { rm -f "$OUT/env_keys.txt"; stop GATE "env_keys.txt holds more than key names — deleted"; }
echo "   gate ok: no email-shaped value; env_keys.txt holds key names only"
( cd "$OUT" && find . -type f ! -name SHA256SUMS.out ! -name run.txt | LC_ALL=C sort | xargs sha256sum > SHA256SUMS.out )
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" && chmod a+r "out-$TS.tar" ) || stop TAR "cannot tar $OUT"
echo
echo "######## DONE — tell the CA: $OUT  ($BASE/out-$TS.tar)"
