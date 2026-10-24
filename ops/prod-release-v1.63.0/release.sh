#!/usr/bin/env bash
# v1.63.0 prod release (RT12): RT10's "revisions visible, accept by record" (#229) and its follow-up, the letterhead
# quote's capability gate (#230). NO migration (alembic stays 0053), NO dependency. The SPA (frontend/) changes, so
# the deploy REBUILDS it (npm run build, as v1.61.0's did); Python changes (routers/calculator.py, services/
# revisions.py, report_engine.py, main.py, ...), so the service restarts; the browser's two calculators move —
# calculator.js ?v=191 -> ?v=192 and calculator2.js ?v=128 -> ?v=129 (each template and file, both from disk).
# See docs/runbooks/prod-deploy-v1.63.0.md. Staged by mkstage.sh (committed blobs, LF) at /tmp/icb-release-v1.63.0.
# Michael runs each mode from his laptop through the window line (run_window_step.ps1: ssh to the VM, then this script
# BY PATH, under sudo):
#
#     sudo bash /tmp/icb-release-v1.63.0/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.63.0/release.sh deploy      ONLY in the window Michael picked
#     sudo bash /tmp/icb-release-v1.63.0/release.sh verify      read-only; after the deploy (and after the view-only
#                                                               acceptance: no quote saved since the deploy)
#
# Every run's FIRST line names the machine, the database (name @ host), the git HEAD and the BOOT TIME, and it
# refuses unless they are prod's — and refuses a kit staged before the last boot (ops/lib/icb_where.sh, the RT7
# reboot guard: the copy line stamps KIT_DIR/.staged_at). MES_DEMO_AUTOLOGIN_USER is checked "empty: yes/no" only.
#
# deploy = anchors -> autologin empty, ICB_ENVIRONMENT=prod, the 4G factor exact, the saved costings' digest AND the
# per-row digests (the window saves no quote; verify names any row that moved, by id) -> served-bytes baseline (the two
# statics at their old ?v= = disk on the three doors; the SPA served = disk) -> PyYAML, npm + node_modules -> backup
# (ops/lib/icb_backup.sh, pg_dump -Fc, checked) -> fetch (tags) + tag and range guards -> the repo's own
# deploy/prod/icb-deploy.sh (dry run: no migration, SPA rebuild YES, restart YES; then --yes) -> post-deploy asserts:
# alembic 0053, the factor, the deployed audit list, the restart after the code moved, 0 tracebacks SINCE THIS RESTART
# (earlier ones are listed, never counted: RT7's lesson; a chained traceback lists every class: RT9's queued fix),
# the two statics' new ?v= and bytes on disk, the SPA REBUILT (a new bundle name) and carrying RT10's text, then the
# THREE doors in order (D4) — 127.0.0.1, LAN, Cloudflare — each: /health/version = {"version":"v1.63.0",
# "environment":"prod"}, no TEST banner, calculator.js?v=192 and calculator2.js?v=129 served = the target blobs, the SPA
# bundle served = the one built, every probe_paths.txt line its listed status (47; no route is new in this range).
# Cloudflare caches by URL for 4 h: a new ?v= is NEVER requested from any door before the target's bytes are on disk.
#
# prod runs fs.protected_regular=2 (RT10's lesson, 23 Oct): this script never chowns anything and writes only under
# its own kit folder (/tmp/icb-release-v1.63.0/out-*, its three .marks) — never a file directly in /tmp.
# Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.63.0
KIT_DIR=$BASE
ICB_LANE=RT12
REPO=/opt/icb-platform
SERVICE=icb-backend
ENV_FILE=/etc/icb/backend.env
ENV_KEY=ICB_ENVIRONMENT
ENV_VALUE=prod
PY=$REPO/.venv/bin/python
BACKUP_DIR=/var/backups/postgres
STATE_FILE=/var/tmp/icb-deploy-state
LOCAL=https://127.0.0.1
LAN=https://192.168.0.251
CF=https://mes.icecoldgrp.online
DOORS="LOCAL LAN CF"                 # D4: always in this order
RESTART_MARK=$BASE/.deploy_restart_epoch       # this deploy's restart: verify counts tracebacks from it
QUOTES_MARK=$BASE/.quotes_digest_at_deploy     # the saved costings as the deploy found them: "count md5"
QUOTES_ROWS_MARK=$BASE/.quotes_rows_at_deploy  # ... and per row: "id md5" (ids and hashes only), so verify can NAME a change
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$MODE-$TS
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## nothing after this point ran. Tell the CA${OUT:+: $OUT}";
         [ -n "$OUT" ] && [ -d "$OUT" ] && chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }
ok()   { echo "   ok   $*"; }

# ---- where am I? (the first line, before anything else) ----------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r "$ENV_FILE" ]; then
  URL=$( set -a; . "$ENV_FILE" >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT12 release $MODE · machine $(hostname -s) · db ? · head ? · boot ?"; OUT=''; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'    # the identity read only; unset before anything else
icb_where "release v1.63.0 $MODE" "$REPO" "$URL"
unset PGOPTIONS
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENV_FILE"
for v in PREV PREV_TAG TARGET BRANCH TAG TAG_OBJ ALEMBIC CHANGED_COUNT CHANGED_SHA N_PROBES PYYAML_VERSION \
         DEPLOY_SH_SHA WORKERS FACTOR LIST_ENTRIES PAIR_SHA GOLDEN_MONTH STATIC_1 STATIC_2 SPA_MARK N_FRONTEND \
         EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
[ -n "${NEW_PROBES+x}" ] || stop KIT "expected.env has no NEW_PROBES (empty is right for this release: no route is new)"
# the two statics: "<template> <path under static/> <?v= before> <sha before> <?v= after> <sha after>"
read -r S1_TMPL S1_PATH S1_VB S1_SB S1_VA S1_SA <<< "$STATIC_1"
read -r S2_TMPL S2_PATH S2_VB S2_SB S2_VA S2_SA <<< "$STATIC_2"
[ -n "$S1_SA" ] && [ -n "$S2_SA" ] || stop KIT "expected.env's STATIC_1 / STATIC_2 do not carry six fields"
# preflight / verify run over the CURRENT code (v1.62.0) or, after the deploy, the target
EXPECT_HEADS="$PREV $TARGET"
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: copy the kit again"
# shellcheck disable=SC1091
. "$BASE/lib/icb_backup.sh" || stop KIT "lib/icb_backup.sh missing: copy the kit again"
OUT=$OUT_TMP
[ -e "$OUT" ] && { OUT=''; stop KIT "$OUT_TMP already exists (two runs in one second?): run again"; }
mkdir -p "$OUT" || { OUT=''; stop KIT "cannot create $OUT_TMP"; }
exec > >(tee -a "$OUT/run.log") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD, boot $WHERE_BOOT_TXT, mode $MODE)"
# the rest of the env file, for the autologin emptiness check and the deploy tooling (values are never printed)
set -a; . "$ENV_FILE"; set +a
export PYTHONDONTWRITEBYTECODE=1      # never leave root-owned __pycache__ in the icb-owned repo
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
gitr() { sudo -u icb git -C "$REPO" "$@"; }
sha_url() { curl -ksS --max-time 20 "$1" | sha256sum | cut -d' ' -f1; }
code_url() { curl -ks -o /dev/null --max-time 20 -w '%{http_code}' "$1" || true; }

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
ALEMBIC_NOW=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
HEAD=$WHERE_HEAD
say "prod: db=$DBNAME alembic=$ALEMBIC_NOW code=${HEAD:0:7} mode=$MODE target=${TARGET:0:7} ($TAG) $(date -Is)"

# ---- helpers -----------------------------------------------------------------------------------------------------
each_static() { # $1 = a function taking: template path v_before sha_before v_after sha_after. IFS is never changed
  # here: a `local IFS` would reach the called function too (bash scopes are dynamic) and break its word splitting —
  # the happy sim's first run stopped on exactly that ("LOCAL LAN CF: invalid variable name").
  local s t p vb sb va sa
  for s in "$STATIC_1" "$STATIC_2"; do read -r t p vb sb va sa <<< "$s"; "$1" "$t" "$p" "$vb" "$sb" "$va" "$sa"; done
}
static_v_disk() { grep -o "${2##*/}?v=[0-9]*" "$REPO/backend/app/templates/$1" 2>/dev/null | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
static_sha_disk() { sha256sum "$REPO/backend/app/static/$1" 2>/dev/null | cut -d' ' -f1 || echo missing; }
static_on() { # $1 door URL, $2 template, $3 path under static/, $4 the ?v= to ask for, $5 the sha256 the disk must hold
  # first. A door that caches by URL (Cloudflare: 4 h) keeps whatever bytes it is first given under that address, so a
  # ?v= is requested from a door ONLY once the page on disk loads it and the disk holds those bytes — never a new ?v=
  # before the deploy.
  [ "$(static_v_disk "$2" "$3")" = "$4" ] && [ "$(static_sha_disk "$3")" = "$5" ] \
    || { echo "not probed (the page on disk loads ?v=$(static_v_disk "$2" "$3"), its bytes ${5:0:12} are not on disk yet)"; return 0; }
  sha_url "$1/static/$3?v=$4"
}
spa_bundle() { grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1; }
spa_disk() { local b; b=$(spa_bundle); [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none; }
spa_on() { local b; b=$(spa_bundle); [ -n "$b" ] && sha_url "$1/mes-app/$b" || echo none; }   # a bundle's name is new per build: never cached stale
spa_mark_on() { # $1 door: how many times the SPA bundle that door serves carries RT10's text (0 on v1.62.0; 1+ after)
  local b; b=$(spa_bundle); [ -n "$b" ] || { echo none; return 0; }
  curl -ksS --max-time 20 "$1/mes-app/$b" | grep -c -F "$SPA_MARK" || true
}
health_version() { curl -ks --max-time 20 "$1/health/version" 2>/dev/null | tr -d ' \n'; }
version_of() { health_version "$1" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' | head -n1; }
environment_of() { health_version "$1" | sed -n 's/.*"environment":"\([^"]*\)".*/\1/p' | head -n1; }
banner_on() { # $1 door: how many TEST SERVER bars / [TEST] titles the login page carries (prod: 0)
  local page; page=$(curl -ks --max-time 20 "$1/login" 2>/dev/null)
  grep -qi '<title>' <<<"$page" || { echo "no login page"; return 0; }   # an empty answer is not "no banner"
  echo "$(grep -c 'icb-test-banner' <<<"$page" || true)/$(grep -c '<title>\[TEST\]' <<<"$page" || true)"
}
noauth_report() { # $1 door; $2 = "before" while prod still runs the OLD code (RT6_RULING_3): a path in NEW_PROBES —
  # its route is new in this release, so the old code answers 404 — may answer 404, and only those paths (none in
  # v1.63.0: NEW_PROBES is empty, so a 404 anywhere is a failure). A line is "<status> <path>" (GET) or
  # "<status> <METHOD> <path>".
  local door=$1 before=${2:-} bad="" early="" want a b method path got
  while read -r want a b; do
    case "$want" in ''|\#*) continue ;; esac
    if [ -n "$b" ]; then method=$a; path=$b; else method=GET; path=$a; fi
    if [ "$method" = GET ]; then
      got=$(curl -ks -o /dev/null --max-time 20 -H 'Accept: application/json' -w '%{http_code}' "$door$path" 2>/dev/null)
    else   # a body route: an empty JSON body with its length, as a browser sends it (the gate answers before the body is read)
      got=$(curl -ks -o /dev/null --max-time 20 -X "$method" -H 'Accept: application/json' -H 'Content-Type: application/json' \
            --data-binary '{}' -w '%{http_code}' "$door$path" 2>/dev/null)
    fi
    [ "$got" = "$want" ] && continue
    if [ "$before" = before ] && [ "$got" = 404 ] && [ -n "$NEW_PROBES" ] && [[ " $NEW_PROBES " == *" $path "* ]]; then early="$early $method $path"; continue; fi
    bad="$bad $( [ "$method" = GET ] || echo "$method ")$path=${got:-000}/$want"
  done < "$BASE/probe_paths.txt"
  if [ -n "$bad" ]; then echo "${bad# }"; else echo "all $N_PROBES as expected${early:+ (new in this release, 404 before the deploy:$early)}"; fi
}
NOAUTH_OK="~^all $N_PROBES as expected( [(]new in this release, 404 before the deploy: .*[)])?$"
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
npm_present() { sudo -u icb bash -lc 'command -v npm >/dev/null && echo present || echo missing' 2>/dev/null || echo missing; }
node_modules_present() { [ -d "$REPO/frontend/node_modules" ] && echo present || echo missing; }
tag_local() { gitr rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || echo missing; }
describe() { gitr describe --tags --abbrev=0 HEAD 2>/dev/null || echo none; }
journal_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null; }
workers_since() { journal_since "$1" | grep -c 'Application startup complete' || true; }
bootfail_since() { journal_since "$1" | grep -c 'BOOTSTRAP FAILED' || true; }
tb_since() { journal_since "$1" | grep -c 'Traceback' || true; }
tb_list() { # $1 --since, $2 --until, $3 label: each traceback's time and its exception CLASS only (never the message:
  # G4, no personal data). The class is the first word of the first unindented line after a traceback's frames,
  # whatever its name: a chained traceback ("During handling of the above exception, another exception occurred",
  # "The above exception was the direct cause of the following exception") and an exception group ("+ Exception Group
  # Traceback", its "|"-prefixed lines) list one class per Traceback header. RT9's list knew only names ending in
  # Error/Exception/Disconnect/Exit/Timeout/Interrupt, so the anyio.WouldBlock and anyio.EndOfStream halves of every
  # ClientDisconnect chain read "(exception line not found)" on 22 Oct (queued; fixed here). Log lines whose first
  # word is an all-caps level (INFO:, WARNING:) or a frame (File) are never taken for a class.
  journalctl -u "$SERVICE" --since "$1" --until "$2" --no-pager 2>/dev/null | awk -v label="${3:-pre-existing}" '
    function flush() { if (t != "") print "   " label "  " t "  (exception line not found)"; t = "" }
    { m = $0; sub(/^[^]]*\]: /, "", m); sub(/^[ \t|+]*/, "", m) }
    m ~ /Traceback \(most recent call last\)/ { flush(); t = $1 " " $2 " " $3; next }
    t == "" { next }
    m ~ /^(During handling of the above exception|The above exception was the direct cause)/ { next }
    m ~ /^[A-Za-z_][A-Za-z0-9_.]*(:|$)/ && m !~ /^[A-Z0-9_]+(:|$)/ && m !~ /^(File|Traceback)/ {
      c = m; sub(/[: ].*/, "", c); print "   " label "  " t "  " c; t = "" }
    END { flush() }'
}
service_start_epoch() {
  awk -v mono="$(systemctl show "$SERVICE" -p ActiveEnterTimestampMonotonic --value)" -v now="$(date +%s.%N)" \
      '{ printf "%d\n", now - $1 + mono / 1000000 }' /proc/uptime
}
service_since() { echo "@$(( $(service_start_epoch) - 1 ))"; }
head_moved_epoch() { gitr reflog show -1 --date=unix --format=%gd HEAD 2>/dev/null | sed -n 's/.*@{\([0-9]*\)}.*/\1/p'; }
restart_after_code() {
  local moved start; start=$(service_start_epoch); moved=${1:-$(head_moved_epoch)}
  [ -n "$moved" ] || { echo "unknown (no reflog)"; return 0; }
  [ "$start" -ge $(( moved - 1 )) ] && echo yes || echo "no (service $start < code $moved)"
}
env_line() { # the env key as the FILE carries it: "absent" | "ICB_ENVIRONMENT=<value>" (the value is not secret) | "duplicate"
  local n; n=$(grep -cE "^[[:space:]]*(export[[:space:]]+)?$ENV_KEY=" "$ENV_FILE" || true)
  [ "$n" = 0 ] && { echo absent; return 0; }
  [ "$n" = 1 ] || { echo "duplicate ($n lines)"; return 0; }
  grep -E "^[[:space:]]*(export[[:space:]]+)?$ENV_KEY=" "$ENV_FILE" | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/[[:space:]]+$//'
}
autologin_empty() { [ -z "${MES_DEMO_AUTOLOGIN_USER:-}" ] && echo yes || echo no; }   # the VALUE is never printed
FACTOR_SQL="select value from icb_costings.admin_settings where key = 'costings.pu_foam_4g_factor'"
# the saved costings, whole rows, as one md5 (only the digest and the count are printed: G4). The window saves no
# quote (D5; the acceptance is view-only), so verify after it must read the deploy's. Beside the one digest the deploy
# records every row's own md5 by id, so a difference is NAMED (RT9's lesson, 22 Oct: "95 vs 92" needed a second kit).
QUOTES_SQL="select count(*) || ' ' || md5(coalesce(string_agg(md5(c::text), '' order by c.id), '')) from icb_costings.calculations c"
ROWS_SQL="select c.id || ' ' || md5(c::text) from icb_costings.calculations c order by c.id"
name_rows_sql() { # $1 = comma-separated ids. G4: the id, the quote number's FIRST WORD (a repair's carries the
  # customer's name), created_at as stored, the version (the one key read out of result_json's text), the status, and
  # soft-deleted Y/N — no other column, no name, no total.
  echo "select c.id || ' | ' || split_part(coalesce(c.quote_number, '(none)'), ' ', 1) || ' | ' || to_char(c.created_at, 'YYYY-MM-DD HH24:MI:SS') || ' | ' || coalesce(substring(c.result_json from '\"version\": *([0-9]+)'), '?') || ' | ' || coalesce(c.status, '-') || ' | ' || case when c.deleted_at is null then 'N' else 'Y' end from icb_costings.calculations c where c.id in ($1) order by c.id"
}
quotes_rows_report() { # $1 = the deploy's "id md5" file: the rows added, changed and removed since, each NAMED (G4)
  local now="$OUT/quotes_rows_now.txt" added changed removed kind v
  [ -r "$1" ] || { echo "   (no per-row record from the deploy in this kit: nothing to name)"; return 0; }
  q "$ROWS_SQL" > "$now" || { echo "   (cannot read the rows: $(head -n1 "$now"))"; return 0; }
  added=$(awk 'NR == FNR { d[$1] = 1; next } !($1 in d) { print $1 }' "$1" "$now" | sort -n | paste -sd,)
  removed=$(awk 'NR == FNR { n[$1] = 1; next } !($1 in n) { print $1 }' "$now" "$1" | sort -n | paste -sd,)
  changed=$(awk 'NR == FNR { d[$1] = $2; next } ($1 in d) && d[$1] != $2 { print $1 }' "$1" "$now" | sort -n | paste -sd,)
  cnt() { if [ -n "$1" ]; then tr ',' '\n' <<<"$1" | grep -c .; else echo 0; fi; }
  echo "   since the deploy: added $(cnt "$added") row(s), changed $(cnt "$changed"), removed $(cnt "$removed")  (id | quote | created as stored | version | status | deleted)"
  for kind in added changed removed; do
    v=${!kind}; [ -n "$v" ] || continue
    echo "   -- $kind: $v"
    if [ "$kind" = removed ]; then echo "      (a removed row cannot be named from the live table: ids only)"
    else q "$(name_rows_sql "$v")" | sed 's/^/      /'; fi
  done
  return 0
}
# the DEPLOYED audit list and snapshot: the prod list loads strictly (every entry pinned), and its pair is the snapshot
list_report() {
  (cd "$REPO/backend" && "$PY" - 2>&1 <<'PYL'
from tools.costing_audit import ACCEPTED_FILE, MES_SNAPSHOT_DIR
from tools.costing_audit.accepted import load_accepted_doc
from tools.costing_audit.mes_snapshot import snapshot_digest
h, e = load_accepted_doc(ACCEPTED_FILE.with_name("accepted_differences.prod.yaml"))
pair = (h.get("pair") or {}).get("snapshot_sha256")
same = "pair=snapshot" if pair == snapshot_digest(MES_SNAPSHOT_DIR / "all.json") else "pair!=snapshot"
print(f"{len(e)} {pair} {same}")
PYL
  ) | tail -n1
}
golden_month() { grep -ho '"workbook_month": *"[^"]*"' "$REPO"/backend/tests/costing_audit/golden/*/_manifest.json 2>/dev/null | sort -u | sed 's/.*: *"//; s/"$//' | tr '\n' ' ' | sed 's/ $//'; }

FAILS=0
check() { # $1 name, $2 got, $3 want (exact) | $3 '~regex'
  local name=$1 got=$2 want=$3 okk=0
  if [ "${want:0:1}" = "~" ]; then [[ "$got" =~ ${want:1} ]] && okk=1; else [ "$got" = "$want" ] && okk=1; fi
  if [ $okk = 1 ]; then echo "   PASS $name = $got"
  else echo "   FAIL $name = '$got' (want $want)"; FAILS=$((FAILS + 1)); [ "$MODE" = deploy ] && stop "$name" "got '$got', want $want"; fi
  return 0
}
tracebacks() { # $1 = this deploy's restart (epoch) or empty while the old code runs. RT7's lesson (ratified default 2):
  # only tracebacks since THIS deploy's restart count; earlier ones are listed, read-only, as pre-existing.
  local start=$1 pre_from
  if [ -z "$start" ]; then
    pre_from=$(service_since)
    echo "   (the old code still runs: tracebacks since its start $pre_from are listed as pre-existing, not counted)"
    tb_list "$pre_from" now
    echo "   pre-existing tracebacks since the running service started: $(tb_since "$pre_from")"
    return 0
  fi
  local pre tb; pre=$(tb_list "@$(( start - 14 * 86400 ))" "@$start")
  [ -n "$pre" ] && echo "$pre"
  echo "   pre-existing tracebacks in the 14 days before this deploy's restart (listed, not counted): $(grep -c pre-existing <<<"$pre" || true)"
  tb=$(tb_since "@$start")
  [ "$tb" = 0 ] || tb_list "@$start" now "since the restart:"
  check TRACEBACKS_SINCE_RESTART "$tb" 0
}
static_disk_checks() { # $1 = before | after: each page on disk loads that ?v= and the file on disk is that blob
  local which=$1
  sd() { local v=$5 s=$6; [ "$which" = before ] && { v=$3; s=$4; }
         check "V_${2##*/}" "$(static_v_disk "$1" "$2")" "$v"; check "DISK_${2##*/}" "$(static_sha_disk "$2")" "$s"; }
  each_static sd
}
door() { # $1 LOCAL | LAN | CF, $2 "before" while the old code runs — one door, every check, before the next door (D4)
  local d=$1 url=${!1}
  check "VERSION_$d" "$(version_of "$url")" "$TAG"
  check "ENVIRONMENT_$d" "$(environment_of "$url")" "$ENV_VALUE"
  check "NO_TEST_BANNER_$d" "$(banner_on "$url")" "0/0"
  sdoor() { check "${2##*/}_$d" "$(static_on "$url" "$1" "$2" "$5" "$6")" "$6"; }
  each_static sdoor
  check "SPA_$d" "$(spa_on "$url")" "$(spa_disk)"
  check "SPA_MARK_$d" "$(spa_mark_on "$url")" '~^[1-9][0-9]*$'
  check "NOAUTH_$d" "$(noauth_report "$url" "${2:-}")" "$NOAUTH_OK"
}
post_checks() { # $1 this deploy's restart (epoch) or empty, $2 epoch the code moved (deploy) or empty, $3 SPA "name sha" before (deploy) or empty
  local before=''; [ "$(gitr rev-parse HEAD)" = "$PREV" ] && before=before    # verify before the deploy: the old code runs
  say "code + tag; the schema and the data do not move (no migration; the 4G factor is data)"
  check HEAD "$(gitr rev-parse HEAD)" "$TARGET"
  check TAG_LOCAL "$(tag_local)" "$TAG_OBJ"
  check DESCRIBE "$(describe)" "$TAG"
  check ALEMBIC "$(q "select string_agg(version_num, ',') from alembic_version")" "$ALEMBIC"
  check FACTOR "$(q "$FACTOR_SQL")" "$FACTOR"
  say "the deployed audit: the prod list loads strictly (every entry pinned) and is paired with the deployed snapshot"
  check LIST "$(list_report)" "$LIST_ENTRIES $PAIR_SHA pair=snapshot"
  check GOLDEN_MONTH "$(golden_month)" "$GOLDEN_MONTH"
  say "the environment key and autologin"
  check ENV_KEY "$(env_line)" "$ENV_KEY=$ENV_VALUE"
  check AUTOLOGIN_EMPTY "$(autologin_empty)" yes
  say "service (the Python is new only if the service started after the code moved)"
  local since; since=$( [ -n "${1:-}" ] && echo "@$1" || service_since )
  check ACTIVE "$(systemctl is-active "$SERVICE" || true)" active
  check RESTART_AFTER_CODE "$(restart_after_code "${2:-}")" yes
  check WORKERS "$(workers_since "$since")" "$WORKERS"
  check BOOTSTRAP_FAILED "$(bootfail_since "$since")" 0
  say "tracebacks: counted from this deploy's restart only"
  tracebacks "$( [ -z "$before" ] && echo "${1:-$(cat "$RESTART_MARK" 2>/dev/null || service_start_epoch)}")"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "the two statics on disk: each page loads its new ?v= ($S1_VA / $S2_VA) and the file is the target's blob (before any door is asked for it)"
  static_disk_checks after
  say "the SPA on disk: rebuilt by this deploy (a new bundle$( [ -n "${3:-}" ] && echo ", not $3")), carrying RT10's text"
  check SPA_DISK_NAME "$(spa_bundle)" '~^assets/index-'
  [ -n "${3:-}" ] && check SPA_REBUILT "$( [ "$(spa_bundle) $(spa_disk)" != "$3" ] && echo yes || echo "no: still $3")" yes
  check SPA_MARK_DISK "$(grep -c -F "$SPA_MARK" "$REPO/frontend/dist/$(spa_bundle)" 2>/dev/null || true)" '~^[1-9][0-9]*$'
  for d in $DOORS; do
    say "door $d (${!d}): /health/version, no TEST banner, calculator.js?v=$S1_VA and calculator2.js?v=$S2_VA = the target, the SPA bundle served = the one built, the $N_PROBES no-session probes"
    door "$d" "$before"
  done
  say "no quote saved since the deploy (the saved costings: count + md5 of the whole rows; a difference is named row by row: id, quote, created, version, status, deleted)"
  if [ ! -r "$QUOTES_MARK" ]; then echo "   (no deploy record in this kit yet: $(q "$QUOTES_SQL" | cut -c1-24)...)"
  elif [ "$MODE" = deploy ]; then echo "   saved costings at the deploy $(cat "$QUOTES_MARK"), now $(q "$QUOTES_SQL") (verify judges this after the acceptance)"
  else
    local qn; qn=$(q "$QUOTES_SQL")
    check QUOTES_UNCHANGED_SINCE_DEPLOY "$qn" "$(cat "$QUOTES_MARK")"
    [ "$qn" = "$(cat "$QUOTES_MARK")" ] || quotes_rows_report "$QUOTES_ROWS_MARK"
  fi
  return 0
}

# ==================================================================================================================
if [ "$MODE" = preflight ]; then
  say "anchors"
  check ALEMBIC "$ALEMBIC_NOW" "$ALEMBIC"
  check HEAD "$HEAD" "$PREV"
  check TRACKED_CLEAN "$(gitr status --porcelain --untracked-files=no | wc -l)" 0
  say "autologin: MES_DEMO_AUTOLOGIN_USER must be EMPTY on prod (only 'empty: yes/no' is ever printed)"
  check AUTOLOGIN_EMPTY "$(autologin_empty)" yes
  check ENV_KEY "$(env_line)" "$ENV_KEY=$ENV_VALUE"
  say "the 4G factor (RT7_RULING_1A: exactly 5400/4100, set by Michael on 19 Oct; v1.63.0 does not touch it)"
  check FACTOR "$(q "$FACTOR_SQL")" "$FACTOR"
  say "served bytes today: calculator.js ?v=$S1_VB and calculator2.js ?v=$S2_VB (the pages on disk) = disk = $PREV_TAG's blobs, on the three doors in order; the SPA served = disk, without RT10's text yet"
  static_disk_checks before
  sb() { local d; for d in $DOORS; do check "${2##*/}_$d" "$(static_on "${!d}" "$1" "$2" "$3" "$4")" "$4"; done; }
  each_static sb
  check SPA_DISK_NAME "$(spa_bundle)" '~^assets/index-'
  for d in $DOORS; do check "SPA_$d" "$(spa_on "${!d}")" "$(spa_disk)"; done
  check SPA_MARK_NOT_YET "$(spa_mark_on "$LOCAL")" 0
  echo "   SPA bundle $(spa_bundle) sha256 $(spa_disk) (frontend/ changed in the range, $N_FRONTEND file(s): the deploy rebuilds it)"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "today, on the three doors in order: $PREV_TAG answers, and RT4's no-session gate holds (no route is new in this release: no 404 is allowed)"
  for d in $DOORS; do
    check "VERSION_$d" "$(version_of "${!d}")" "$PREV_TAG"
    check "NOAUTH_$d" "$(noauth_report "${!d}" before)" "$NOAUTH_OK"
  done
  echo "   routes new in this release (404 on $PREV_TAG, so allowed 404 here and nowhere else): ${NEW_PROBES:-none}"
  say "tracebacks (read only: the old code runs, nothing is counted)"
  tracebacks ""
  say "PyYAML (installed by v1.59.0; this release installs nothing)"
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "the SPA build tooling (icb-deploy.sh runs npm run build as icb)"
  check NPM "$(npm_present)" present
  check NODE_MODULES "$(node_modules_present)" present
  say "the tag is on origin BEFORE the window"
  RT=$(sudo -u icb git -C "$REPO" ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | cut -f1 | head -n1)
  check TAG_ON_ORIGIN "${RT:-missing}" "$TAG_OBJ"
  say "backup location"
  check BACKUP_DIR "$( [ -d "$BACKUP_DIR" ] && [ -w "$BACKUP_DIR" ] && echo writable || echo no)" writable
  echo "   free space: $(df -h "$BACKUP_DIR" | tail -n1 || true)"
  say "deploy tooling on prod"
  check DEPLOY_SCRIPT "$(sha256sum "$REPO/deploy/prod/icb-deploy.sh" 2>/dev/null | cut -d' ' -f1 || echo missing)" "$DEPLOY_SH_SHA"
  check ICB_SUDO "$(sudo -u icb sudo -n true 2>/dev/null && echo nopasswd || echo password)" nopasswd
  echo "   deploy record: $(cat "$STATE_FILE" 2>/dev/null || echo none) (owner $(stat -c %U "$STATE_FILE" 2>/dev/null || echo -))"
  echo "   saved costings now (count md5): $(q "$QUOTES_SQL")"
  chmod -R a+rX "$OUT"
  if [ "$FAILS" -gt 0 ]; then echo; echo "######## PREFLIGHT: $FAILS check(s) FAILED — do not deploy. Tell the CA: $OUT"; exit 1; fi
  echo; echo "######## PREFLIGHT PASSED — tell the CA: $OUT"; exit 0
fi

# ==================================================================================================================
if [ "$MODE" = verify ]; then
  post_checks "$( [ "$HEAD" = "$TARGET" ] && cat "$RESTART_MARK" 2>/dev/null)" "" ""
  chmod -R a+rX "$OUT"
  echo; echo "######## VERIFY: $FAILS check(s) failed — tell the CA: $OUT"
  [ "$FAILS" -eq 0 ]; exit $?
fi

# ==================================================================================================================
# deploy
say "1. anchors"
RESUME=0
if [ "$HEAD" = "$PREV" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ]; then
  ok "fresh: code ${PREV:0:7}, alembic $ALEMBIC"
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ] && grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null; then
  echo "   !!   ALREADY DEPLOYED: code ${TARGET:0:7}, alembic $ALEMBIC, completion on record. Nothing is changed;"
  echo "   !!   running the post-deploy asserts (as verify does) instead."
  post_checks "$(cat "$RESTART_MARK" 2>/dev/null)" "" ""
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ]; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} — a previous run stopped part way."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC_NOW is neither the start (${PREV:0:7}/$ALEMBIC) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt (the code; then npm run build: this range changed frontend/)"

say "2. autologin, the environment key, the 4G factor, the saved costings (before anything moves)"
[ "$(autologin_empty)" = yes ] || stop AUTOLOGIN "MES_DEMO_AUTOLOGIN_USER is NOT empty on prod (value not printed). Do not deploy — tell the BA"
ok "MES_DEMO_AUTOLOGIN_USER empty: yes"
[ "$(env_line)" = "$ENV_KEY=$ENV_VALUE" ] || stop ENV "$ENV_FILE has '$(env_line)', not $ENV_KEY=$ENV_VALUE (set since RT6) — tell the CA"
ok "$(env_line)"
F=$(q "$FACTOR_SQL"); [ "$F" = "$FACTOR" ] || stop FACTOR "costings.pu_foam_4g_factor reads '$F', not exactly '$FACTOR' — the pins assume it; tell the BA"
ok "4G factor '$F' (5400/4100)"
QD=$(q "$QUOTES_SQL"); [[ "$QD" =~ ^[0-9]+\ [0-9a-f]{32}$ ]] || stop QUOTES "cannot read the saved costings' digest: $QD"
if [ "$RESUME" = 0 ] || [ ! -r "$QUOTES_MARK" ]; then
  echo "$QD" > "$QUOTES_MARK"
  q "$ROWS_SQL" > "$QUOTES_ROWS_MARK" || stop QUOTES "cannot read the saved costings' rows: $(head -n1 "$QUOTES_ROWS_MARK")"
  [ "$(grep -c . "$QUOTES_ROWS_MARK")" = "${QD%% *}" ] || stop QUOTES "the per-row record holds $(grep -c . "$QUOTES_ROWS_MARK") rows, the count says ${QD%% *}"
fi
ok "saved costings: $(cat "$QUOTES_MARK"); $(grep -c . "$QUOTES_ROWS_MARK") rows recorded by id and md5 (verify after the acceptance must read the same, and names any row that moved)"

say "3. served-bytes baseline (the doors in order; the old ?v= only — a new one is never asked for before it is on disk)"
if [ "$RESUME" = 0 ]; then
  bl() { # template path v_before sha_before v_after sha_after
    [ "$(static_v_disk "$1" "$2")" = "$3" ] && [ "$(static_sha_disk "$2")" = "$4" ] \
      || stop BYTES_BEFORE "the page $1 on disk loads ${2##*/} ?v=$(static_v_disk "$1" "$2") with bytes $(static_sha_disk "$2" | cut -c1-12), not $PREV_TAG's ?v=$3"
    local d got; for d in $DOORS; do
      got=$(static_on "${!d}" "$1" "$2" "$3" "$4")
      [ "$got" = "$4" ] || stop BYTES_BEFORE "door $d serves ${2##*/}?v=$3 as ${got:0:16}, not the disk's ${4:0:16}"
    done
    ok "${2##*/}?v=$3 ${4:0:16} = disk on 127.0.0.1, LAN, Cloudflare"
  }
  each_static bl
else
  ok "RESUME: the code already moved, so the old baseline is gone; the post-deploy asserts check the new bytes"
fi
B_SPA_NAME=$(spa_bundle); B_SPA_SHA=$(spa_disk)
[ -n "$B_SPA_NAME" ] && [ "$B_SPA_SHA" != none ] || stop BYTES_BEFORE "no SPA bundle on disk (frontend/dist/index.html)"
for d in $DOORS; do got=$(spa_on "${!d}"); [ "$got" = "$B_SPA_SHA" ] || stop BYTES_BEFORE "door $d serves the SPA bundle $B_SPA_NAME as ${got:0:16}, not the disk's ${B_SPA_SHA:0:16}"; done
if [ "$RESUME" = 0 ]; then
  [ "$(spa_mark_on "$LOCAL")" = 0 ] || stop BYTES_BEFORE "the SPA served today already carries RT10's text: is this really $PREV_TAG?"
  ok "SPA $B_SPA_NAME ${B_SPA_SHA:0:16} = disk on the three doors, without RT10's text (the deploy rebuilds it)"
else
  ok "SPA $B_SPA_NAME ${B_SPA_SHA:0:16} = disk on the three doors (RESUME: it may be the rebuilt one already)"
fi

say "4. PyYAML $PYYAML_VERSION present (nothing is installed by this release); npm and node_modules for the SPA rebuild"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV. Do not deploy; tell the CA"
ok "present ($YV)"
[ "$(npm_present)" = present ] || stop TOOLING "npm is not on icb's PATH: the SPA rebuild would fail. Do not deploy; tell the CA"
[ "$(node_modules_present)" = present ] || stop TOOLING "$REPO/frontend/node_modules is missing: the SPA rebuild would fail. Do not deploy; tell the CA"
ok "npm present, node_modules present"

say "5. backup — checked (ops/lib/icb_backup.sh, pg_dump -Fc: size and sha256 printed); no migration, the backup comes first"
BK="$BACKUP_DIR/icb_platform_pre-v1.63.0_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
icb_backup "$BK" custom "$URL" icb_costings.alembic_version icb_costings.admin_settings icb_costings.trailer_types \
  icb_costings.bill_of_materials icb_costings.materials icb_costings.calculations || stop BACKUP "$ICB_BACKUP_WHY"
chmod 600 "$BK" || true
BK_SHA=$ICB_BACKUP_SHA
[ "$(stat -c %s "$BK")" = "$ICB_BACKUP_BYTES" ] && [ "$(sha256sum "$BK" | cut -d' ' -f1)" = "$BK_SHA" ] \
  || stop BACKUP "the backup's size or sha256 changed after the check"
ok "backup size $ICB_BACKUP_BYTES and sha256 ${BK_SHA:0:16} read back"

say "6. fetch (with tags) + tag and range guards"
sudo -u icb git -C "$REPO" fetch origin --tags --progress 2>&1 | sed 's/^/   /' || true
ORIGIN=$(gitr rev-parse "origin/$BRANCH") || stop GUARD "origin/$BRANCH not resolvable"
[ "$ORIGIN" = "$TARGET" ] || gitr merge-base --is-ancestor "$TARGET" "$ORIGIN" \
  || stop GUARD "origin/$BRANCH is ${ORIGIN:0:7}, which does not contain the staged target ${TARGET:0:7}: re-stage"
[ "$(tag_local)" = "$TAG_OBJ" ] || stop TAG "refs/tags/$TAG is '$(tag_local)', expected the tag object ${TAG_OBJ:0:12} (tag first, then deploy)"
[ "$(gitr rev-parse "$TAG^{commit}" 2>/dev/null)" = "$TARGET" ] || stop TAG "$TAG does not peel to ${TARGET:0:7}"
DESC=$(gitr describe --tags --abbrev=0 "$TARGET" 2>/dev/null || echo none)
[ "$DESC" = "$TAG" ] || stop TAG "git describe at the target says '$DESC': the footer and /health/version would not read $TAG"
ok "$TAG = tag object ${TAG_OBJ:0:12} -> ${TARGET:0:7}; git describe at the target = $DESC"
gitr merge-base --is-ancestor "$PREV" "$TARGET" || stop GUARD "${PREV:0:7} is not an ancestor of ${TARGET:0:7}"
G_COUNT=$(gitr diff --name-only "$PREV" "$TARGET" | wc -l)
G_SHA=$(gitr diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
[ "$G_COUNT" = "$CHANGED_COUNT" ] && [ "$G_SHA" = "$CHANGED_SHA" ] || stop GUARD "changed-file list differs: $G_COUNT files ${G_SHA:0:16}, staged $CHANGED_COUNT ${CHANGED_SHA:0:16}"
G_MIG=$(gitr diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*' | wc -l)
[ "$G_MIG" = 0 ] || stop GUARD "a migration was added in the range: this kit migrates nothing"
G_REQ=$(gitr diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' 'frontend/package.json' 'frontend/package-lock.json' | wc -l)
[ "$G_REQ" = 0 ] || stop GUARD "a dependency manifest changed in the range: this kit installs nothing"
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend | wc -l)
[ "$G_FE" = "$N_FRONTEND" ] && [ "$G_FE" -gt 0 ] || stop GUARD "frontend/ changed in $G_FE file(s), the stage counted $N_FRONTEND: this kit expects the SPA rebuild of exactly those"
G_ST=$(gitr diff --name-only "$PREV" "$TARGET" -- backend/app/static | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//')
E_ST=$(printf '%s\n' "backend/app/static/$S1_PATH" "backend/app/static/$S2_PATH" | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//')
[ "$G_ST" = "$E_ST" ] || stop GUARD "backend/app/static changed beyond the two calculators: '$G_ST' (a file would be served stale under its old ?v=)"
G_DEP=$(gitr diff --name-only "$PREV" "$TARGET" -- deploy | wc -l)
[ "$G_DEP" = 0 ] || stop GUARD "deploy/ changed in the range: the icb-deploy.sh that runs is not the simulated one"
gb() { [ "$(gitr cat-file blob "$TARGET:backend/app/static/$2" | sha256sum | cut -d' ' -f1)" = "$6" ] || stop GUARD "the target's $2 is not the staged blob ${6:0:16}"; }
each_static gb
gitr grep -q -F "$SPA_MARK" "$TARGET" -- frontend/src || stop GUARD "the target's frontend/src has no '$SPA_MARK': the SPA mark is wrong"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}): no migration, no dependency, $G_FE frontend file(s) (the SPA rebuild), static = the two calculators only, deploy/ untouched"

say "7. the repo's deploy script — dry run"
DS="$REPO/deploy/prod/icb-deploy.sh"
[ "$(sha256sum "$DS" | cut -d' ' -f1)" = "$DEPLOY_SH_SHA" ] || stop DRYRUN "$DS is not the expected blob"
sudo -u icb bash "$DS" "$TARGET" --dry-run > "$OUT/icb-deploy-dryrun.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy-dryrun.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DRYRUN "icb-deploy.sh --dry-run exited $rc"
if [ "$RESUME" = 0 ]; then
  grep -q 'DB migration *no ' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: DB migration no"
  grep -q 'SPA rebuild *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: SPA rebuild YES"
  grep -q 'Service restart *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: service restart YES"
  grep -q 'dependency manifests changed' "$OUT/icb-deploy-dryrun.txt" && stop DRYRUN "the plan warns that dependency manifests changed"
fi
if [ "$RESUME" = 0 ]; then ok "plan: no migration, SPA rebuild, restart"
else ok "plan: RESUME — icb-deploy.sh re-runs its idempotent steps (alembic at head, the SPA rebuilt from the same sources), restart"; fi

say "8. deploy (fast-forward, its own backup, npm run build, restart, health, completion record)"
PID_BEFORE=$(systemctl show "$SERVICE" -p MainPID --value)
AET_BEFORE=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
T0=$(date +%s)
sudo -u icb bash "$DS" "$TARGET" --yes > "$OUT/icb-deploy.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DEPLOY "icb-deploy.sh exited $rc. Run the same deploy line again ONLY on the CA's word: it resumes. Rollback: the runbook (anchor ${PREV:0:7} + npm run build, backup $BK)"
grep -q "DEPLOYED" "$OUT/icb-deploy.txt" || stop DEPLOY "icb-deploy.sh did not print DEPLOYED"
PID_AFTER=$(systemctl show "$SERVICE" -p MainPID --value)
AET_AFTER=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
[ "$PID_AFTER" != "$PID_BEFORE" ] || stop RESTART "MainPID unchanged ($PID_AFTER): the service did not restart"
service_start_epoch > "$RESTART_MARK"
ok "restart: $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER); tracebacks count from $(date -d "@$(cat "$RESTART_MARK")" '+%H:%M:%S')"
grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null || stop RECORD "no 'completed $TARGET' in $STATE_FILE"
ok "deploy record: completed ${TARGET:0:7}"
S_SPA_NAME=$(spa_bundle)
[ "$RESUME" = 1 ] || [ "$S_SPA_NAME $(spa_disk)" != "$B_SPA_NAME $B_SPA_SHA" ] || stop SPA_REBUILT "the SPA bundle is still $B_SPA_NAME ${B_SPA_SHA:0:12}: the build did not run"
ok "SPA bundle $B_SPA_NAME -> $S_SPA_NAME"

say "9. post-deploy asserts: the disk first, then the three doors in order (waiting 20 s for all workers to log startup)"
sleep 20
# a RESUME re-runs icb-deploy.sh's idempotent steps, its SPA build among them: the SPA_REBUILT assert compares with the
# bundle the FRESH deploy found; after a resume the SPA must still be served = disk and carry the mark (checked either way)
post_checks "$(cat "$RESTART_MARK")" "$T0" "$( [ "$RESUME" = 0 ] && echo "$B_SPA_NAME $B_SPA_SHA")"

st_line() { printf '%s ?v=%s %s -> ?v=%s %s  ' "${2##*/}" "$3" "${4:0:12}" "$5" "$(static_sha_disk "$2" | cut -c1-12)"; }
cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
tag           $TAG = $TAG_OBJ (local = origin, peels to the target); git describe = $(describe)
alembic       $ALEMBIC -> $(q "select string_agg(version_num, ',') from alembic_version") (no migration)
4G factor     $(q "$FACTOR_SQL") (unchanged; Michael's 19 Oct value, 5400/4100)
audit list    $(list_report) (entries, pair sha256, pair = the deployed snapshot)
golden month  $(golden_month)
environment   $(env_line) in $ENV_FILE; autologin empty: $(autologin_empty)
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA (pg_dump -Fc; checked: alembic_version, admin_settings, trailer_types, bill_of_materials, materials, calculations)
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER), after the code moved: $(restart_after_code "$T0")
workers       $(workers_since "@$(cat "$RESTART_MARK")") started, $(bootfail_since "@$(cat "$RESTART_MARK")") bootstrap failed, $(tb_since "@$(cat "$RESTART_MARK")") tracebacks since this restart
health        $(code_url "$LOCAL/health")
statics       $(each_static st_line)(disk = 127.0.0.1 = LAN = Cloudflare)
version       local $(health_version "$LOCAL") · lan $(health_version "$LAN") · cloudflare $(health_version "$CF")
test banner   local $(banner_on "$LOCAL") · lan $(banner_on "$LAN") · cloudflare $(banner_on "$CF") (bars/[TEST] titles; prod 0/0)
no session    local: $(noauth_report "$LOCAL") · lan: $(noauth_report "$LAN") · cloudflare: $(noauth_report "$CF")
spa           $B_SPA_NAME ${B_SPA_SHA:0:12} -> $(spa_bundle) $(spa_disk | cut -c1-12) (rebuilt$( [ "$RESUME" = 1 ] && echo " by the resume"); local = lan = cloudflare = disk; RT10's text $(spa_mark_on "$LOCAL")x)
quotes        $(cat "$QUOTES_MARK") at the deploy (count md5; $(grep -c . "$QUOTES_ROWS_MARK") rows recorded by id); now $(q "$QUOTES_SQL")
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (next: All after, on the page and the CLI)"
