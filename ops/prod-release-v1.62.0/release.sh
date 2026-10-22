#!/usr/bin/env bash
# v1.62.0 prod release (RT9): RT8's "a re-opened quote is the saved quote" — frozen editing at the saved prices,
# re-pricing as a new revision, the reprice preview route, the refusals in plain words. NO migration (alembic stays
# 0053), NO dependency, NO SPA rebuild. Python changes (routers/calculator.py, services/frozen_quote.py, free_hand.py,
# rule_guard.py), so the service restarts; the browser's calculator moves calculator.js ?v=189 -> ?v=191 (the
# template and the file, both from disk). See docs/runbooks/prod-deploy-v1.62.0.md. Staged by mkstage.sh (committed
# blobs, LF) at /tmp/icb-release-v1.62.0. Michael runs each mode from his laptop through the window line
# (run_window_step.ps1: ssh to the VM, then this script BY PATH, under sudo):
#
#     sudo bash /tmp/icb-release-v1.62.0/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.62.0/release.sh deploy      ONLY in the window Michael picked
#     sudo bash /tmp/icb-release-v1.62.0/release.sh verify      read-only; after the deploy (and after the N10022
#                                                               acceptance: no quote saved since the deploy)
#
# Every run's FIRST line names the machine, the database (name @ host), the git HEAD and the BOOT TIME, and it
# refuses unless they are prod's — and refuses a kit staged before the last boot (ops/lib/icb_where.sh, the RT7
# reboot guard: the copy line stamps KIT_DIR/.staged_at). MES_DEMO_AUTOLOGIN_USER is checked "empty: yes/no" only.
#
# deploy = anchors -> autologin empty, ICB_ENVIRONMENT=prod, the 4G factor exact, the saved costings' digest (the
# window saves no quote) -> served-bytes baseline (calculator.js ?v=189 = disk on the three doors; the SPA) -> PyYAML
# -> backup (ops/lib/icb_backup.sh, pg_dump -Fc, checked) -> fetch (tags) + tag and range guards -> the repo's own
# deploy/prod/icb-deploy.sh (dry run: no migration, no SPA rebuild, restart; then --yes) -> post-deploy asserts:
# alembic 0053, the factor, the deployed audit list, the restart after the code moved, 0 tracebacks SINCE THIS
# RESTART (earlier ones are listed, never counted: RT7's lesson), calculator.js ?v=191 and its bytes on disk, then
# the THREE doors in order — 127.0.0.1, LAN, Cloudflare — each: /health/version = {"version":"v1.62.0",
# "environment":"prod"}, no TEST banner, calculator.js?v=191 served = the target blob, every probe_paths.txt line
# its listed status (the new POST /api/calculations/{id}/reprice-preview: 401 with no session). Cloudflare caches by
# URL for 4 h: the new ?v= is NEVER requested from any door before the target's bytes are on disk.
# Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.62.0
KIT_DIR=$BASE
ICB_LANE=RT9
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
CALC_REL=backend/app/static/js/calculator.js
CALC_TMPL=backend/app/templates/calculator.html
RESTART_MARK=$BASE/.deploy_restart_epoch   # this deploy's restart: verify counts tracebacks from it
QUOTES_MARK=$BASE/.quotes_digest_at_deploy  # the saved costings as the deploy found them
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
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT9 release $MODE · machine $(hostname -s) · db ? · head ? · boot ?"; OUT=''; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'    # the identity read only; unset before anything else
icb_where "release v1.62.0 $MODE" "$REPO" "$URL"
unset PGOPTIONS
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENV_FILE"
for v in PREV PREV_TAG TARGET BRANCH TAG TAG_OBJ ALEMBIC CHANGED_COUNT CHANGED_SHA N_PROBES NEW_PROBES PYYAML_VERSION \
         DEPLOY_SH_SHA WORKERS FACTOR LIST_ENTRIES PAIR_SHA GOLDEN_MONTH CALC_V_PREV CALC_SHA_PREV CALC_V CALC_SHA \
         EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
# preflight / verify run over the CURRENT code (v1.61.1) or, after the deploy, the target
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
spa_bundle() { grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1; }
spa_report() { # "spa_name spa_disk spa_local spa_lan"
  local b; b=$(spa_bundle)
  echo "${b:-none} $( [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none)" \
       "$( [ -n "$b" ] && sha_url "$LOCAL/mes-app/$b" || echo none) $( [ -n "$b" ] && sha_url "$LAN/mes-app/$b" || echo none)"
}
health_version() { curl -ks --max-time 20 "$1/health/version" 2>/dev/null | tr -d ' \n'; }
version_of() { health_version "$1" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' | head -n1; }
environment_of() { health_version "$1" | sed -n 's/.*"environment":"\([^"]*\)".*/\1/p' | head -n1; }
banner_on() { # $1 door: how many TEST SERVER bars / [TEST] titles the login page carries (prod: 0)
  local page; page=$(curl -ks --max-time 20 "$1/login" 2>/dev/null)
  grep -qi '<title>' <<<"$page" || { echo "no login page"; return 0; }   # an empty answer is not "no banner"
  echo "$(grep -c 'icb-test-banner' <<<"$page" || true)/$(grep -c '<title>\[TEST\]' <<<"$page" || true)"
}
# calculator.js: the ?v= the page on disk loads, and the bytes on disk
calc_v_disk() { grep -o 'calculator\.js?v=[0-9]*' "$REPO/$CALC_TMPL" 2>/dev/null | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
calc_sha_disk() { sha256sum "$REPO/$CALC_REL" 2>/dev/null | cut -d' ' -f1 || echo missing; }
calc_on() { # $1 door URL, $2 the ?v= to ask for, $3 the sha256 the disk must hold first. A door that caches by URL
  # (Cloudflare: 4 h) keeps whatever bytes it is first given under that address, so a ?v= is requested from a door
  # ONLY once the page on disk loads it and the disk holds those bytes — never the new ?v= before the deploy.
  [ "$(calc_v_disk)" = "$2" ] && [ "$(calc_sha_disk)" = "$3" ] \
    || { echo "not probed (the page on disk loads ?v=$(calc_v_disk), its bytes ${3:0:12} are not on disk yet)"; return 0; }
  sha_url "$1/static/js/calculator.js?v=$2"
}
noauth_report() { # $1 door; $2 = "before" while prod still runs the OLD code (RT6_RULING_3): a path in NEW_PROBES —
  # its route is new in this release, so the old code answers 404 — may answer 404, and only those paths.
  # A line is "<status> <path>" (GET) or "<status> <METHOD> <path>".
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
    if [ "$before" = before ] && [ "$got" = 404 ] && [[ " $NEW_PROBES " == *" $path "* ]]; then early="$early $method $path"; continue; fi
    bad="$bad $( [ "$method" = GET ] || echo "$method ")$path=${got:-000}/$want"
  done < "$BASE/probe_paths.txt"
  if [ -n "$bad" ]; then echo "${bad# }"; else echo "all $N_PROBES as expected${early:+ (new in this release, 404 before the deploy:$early)}"; fi
}
NOAUTH_OK="~^all $N_PROBES as expected( [(]new in this release, 404 before the deploy: .*[)])?$"
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
tag_local() { gitr rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || echo missing; }
describe() { gitr describe --tags --abbrev=0 HEAD 2>/dev/null || echo none; }
journal_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null; }
workers_since() { journal_since "$1" | grep -c 'Application startup complete' || true; }
bootfail_since() { journal_since "$1" | grep -c 'BOOTSTRAP FAILED' || true; }
tb_since() { journal_since "$1" | grep -c 'Traceback' || true; }
tb_list() { # $1 --since, $2 --until: each traceback's time and exception CLASS only (no message: G4, no personal data)
  journalctl -u "$SERVICE" --since "$1" --until "$2" --no-pager 2>/dev/null | awk '
    /Traceback \(most recent call last\)/ { if (t != "") print "   pre-existing  " t "  (exception line not found)"; t = $1 " " $2 " " $3; next }
    t != "" { for (i = 4; i <= NF; i++) if ($i ~ /^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Disconnect|Exit|Timeout|Interrupt):?$/) {
                c = $i; sub(/:$/, "", c); print "   pre-existing  " t "  " c; t = ""; break } }
    END { if (t != "") print "   pre-existing  " t "  (exception line not found)" }'
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
# quote (D5; Michael's N10022 acceptance ends in Cancel edit), so verify after the acceptance must read the deploy's.
QUOTES_SQL="select count(*) || ' ' || md5(coalesce(string_agg(md5(c::text), '' order by c.id), '')) from icb_costings.calculations c"
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
  [ "$tb" = 0 ] || { journal_since "@$start" | grep -A12 'Traceback' | grep -oE '[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Disconnect|Exit|Timeout|Interrupt)\b' | sort | uniq -c | sed 's/^/   since the restart: /' || true; }
  check TRACEBACKS_SINCE_RESTART "$tb" 0
}
door() { # $1 LOCAL | LAN | CF, $2 "before" while the old code runs — one door, every check, before the next door
  local d=$1 url=${!1}
  check "VERSION_$d" "$(version_of "$url")" "$TAG"
  check "ENVIRONMENT_$d" "$(environment_of "$url")" "$ENV_VALUE"
  check "NO_TEST_BANNER_$d" "$(banner_on "$url")" "0/0"
  check "CALCJS_$d" "$(calc_on "$url" "$CALC_V" "$CALC_SHA")" "$CALC_SHA"
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
  say "calculator.js on disk: the page loads ?v=$CALC_V and the file is the target's blob (before any door is asked for it)"
  check CALCJS_V "$(calc_v_disk)" "$CALC_V"
  check CALCJS_DISK "$(calc_sha_disk)" "$CALC_SHA"
  for d in $DOORS; do
    say "door $d (${!d}): /health/version, no TEST banner, calculator.js?v=$CALC_V = the target, the $N_PROBES no-session probes"
    door "$d" "$before"
  done
  say "served bytes: the SPA served = the bundle on disk (local = lan = disk$( [ -n "${3:-}" ] && echo ' = before: untouched by this release'))"
  set -- "${1:-}" "${2:-}" "${3:-}" $(spa_report)
  check SPA_LOCAL "$6" "$5"
  check SPA_LAN "$7" "$5"
  [ -n "$3" ] && check SPA_UNCHANGED "$4 $5" "$3"
  say "no quote saved since the deploy (the saved costings: count + md5 of the whole rows; only those are printed)"
  if [ ! -r "$QUOTES_MARK" ]; then echo "   (no deploy record in this kit yet: $(q "$QUOTES_SQL" | cut -c1-24)...)"
  elif [ "$MODE" = deploy ]; then echo "   saved costings at the deploy $(cat "$QUOTES_MARK"), now $(q "$QUOTES_SQL") (verify judges this after the acceptance)"
  else check QUOTES_UNCHANGED_SINCE_DEPLOY "$(q "$QUOTES_SQL")" "$(cat "$QUOTES_MARK")"; fi
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
  say "the 4G factor (RT7_RULING_1A: exactly 5400/4100, set by Michael on 19 Oct; v1.62.0 does not touch it)"
  check FACTOR "$(q "$FACTOR_SQL")" "$FACTOR"
  say "served bytes today: calculator.js ?v=$CALC_V_PREV (the page on disk) = disk = $PREV_TAG's blob, on the three doors in order; the SPA"
  check CALCJS_V "$(calc_v_disk)" "$CALC_V_PREV"
  check CALCJS_DISK "$(calc_sha_disk)" "$CALC_SHA_PREV"
  for d in $DOORS; do check "CALCJS_$d" "$(calc_on "${!d}" "$CALC_V_PREV" "$CALC_SHA_PREV")" "$CALC_SHA_PREV"; done
  set -- $(spa_report)
  check SPA_DISK_NAME "$1" '~^assets/index-'
  check SPA_LOCAL "$3" "$2"; check SPA_LAN "$4" "$2"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "today, on the three doors in order: $PREV_TAG answers, and RT4's no-session gate holds (the new route is not there yet: 404)"
  for d in $DOORS; do
    check "VERSION_$d" "$(version_of "${!d}")" "$PREV_TAG"
    check "NOAUTH_$d" "$(noauth_report "${!d}" before)" "$NOAUTH_OK"
  done
  echo "   routes new in this release (404 on $PREV_TAG, so allowed 404 here and nowhere else): $NEW_PROBES"
  say "tracebacks (read only: the old code runs, nothing is counted)"
  tracebacks ""
  say "PyYAML (installed by v1.59.0; this release installs nothing)"
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
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
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"

say "2. autologin, the environment key, the 4G factor, the saved costings (before anything moves)"
[ "$(autologin_empty)" = yes ] || stop AUTOLOGIN "MES_DEMO_AUTOLOGIN_USER is NOT empty on prod (value not printed). Do not deploy — tell the BA"
ok "MES_DEMO_AUTOLOGIN_USER empty: yes"
[ "$(env_line)" = "$ENV_KEY=$ENV_VALUE" ] || stop ENV "$ENV_FILE has '$(env_line)', not $ENV_KEY=$ENV_VALUE (set since RT6) — tell the CA"
ok "$(env_line)"
F=$(q "$FACTOR_SQL"); [ "$F" = "$FACTOR" ] || stop FACTOR "costings.pu_foam_4g_factor reads '$F', not exactly '$FACTOR' — the pins assume it; tell the BA"
ok "4G factor '$F' (5400/4100)"
QD=$(q "$QUOTES_SQL"); [[ "$QD" =~ ^[0-9]+\ [0-9a-f]{32}$ ]] || stop QUOTES "cannot read the saved costings' digest: $QD"
if [ "$RESUME" = 0 ] || [ ! -r "$QUOTES_MARK" ]; then echo "$QD" > "$QUOTES_MARK"; fi
ok "saved costings: $(cat "$QUOTES_MARK") (verify after the N10022 acceptance must read the same)"

say "3. served-bytes baseline (the doors in order; the old ?v= only — the new one is never asked for before it is on disk)"
if [ "$RESUME" = 0 ]; then
  [ "$(calc_v_disk)" = "$CALC_V_PREV" ] && [ "$(calc_sha_disk)" = "$CALC_SHA_PREV" ] \
    || stop BYTES_BEFORE "the page on disk loads calculator.js ?v=$(calc_v_disk) with bytes $(calc_sha_disk | cut -c1-12), not $PREV_TAG's ?v=$CALC_V_PREV"
  for d in $DOORS; do
    got=$(calc_on "${!d}" "$CALC_V_PREV" "$CALC_SHA_PREV")
    [ "$got" = "$CALC_SHA_PREV" ] || stop BYTES_BEFORE "door $d serves calculator.js?v=$CALC_V_PREV as ${got:0:16}, not the disk's ${CALC_SHA_PREV:0:16}"
  done
  ok "calculator.js?v=$CALC_V_PREV ${CALC_SHA_PREV:0:16} = disk on 127.0.0.1, LAN, Cloudflare"
else
  ok "RESUME: the code already moved, so the old baseline is gone; the post-deploy asserts check the new bytes"
fi
set -- $(spa_report)
B_SPA="$1 $2"
[ "$3" = "$2" ] && [ "$4" = "$2" ] || stop BYTES_BEFORE "SPA bundle $1 served bytes differ from disk"
ok "SPA $1 ${2:0:16}"

say "4. PyYAML $PYYAML_VERSION present (nothing is installed by this release)"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV. Do not deploy; tell the CA"
ok "present ($YV)"

say "5. backup — checked (ops/lib/icb_backup.sh, pg_dump -Fc: size and sha256 printed); no migration, the backup comes first"
BK="$BACKUP_DIR/icb_platform_pre-v1.62.0_$TS.dump"
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
[ "$G_FE" = 0 ] || stop GUARD "frontend/ changed: this kit expects the SPA untouched (no rebuild)"
G_ST=$(gitr diff --name-only "$PREV" "$TARGET" -- backend/app/static | tr '\n' ' ' | sed 's/ $//')
[ "$G_ST" = "$CALC_REL" ] || stop GUARD "backend/app/static changed beyond $CALC_REL: '$G_ST' (a file would be served stale under its old ?v=)"
G_DEP=$(gitr diff --name-only "$PREV" "$TARGET" -- deploy | wc -l)
[ "$G_DEP" = 0 ] || stop GUARD "deploy/ changed in the range: the icb-deploy.sh that runs is not the simulated one"
[ "$(gitr cat-file blob "$TARGET:$CALC_REL" | sha256sum | cut -d' ' -f1)" = "$CALC_SHA" ] \
  || stop GUARD "the target's $CALC_REL is not the staged blob ${CALC_SHA:0:16}"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}): no migration, no dependency, no SPA file, static = calculator.js only, deploy/ untouched"

say "7. the repo's deploy script — dry run"
DS="$REPO/deploy/prod/icb-deploy.sh"
[ "$(sha256sum "$DS" | cut -d' ' -f1)" = "$DEPLOY_SH_SHA" ] || stop DRYRUN "$DS is not the expected blob"
sudo -u icb bash "$DS" "$TARGET" --dry-run > "$OUT/icb-deploy-dryrun.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy-dryrun.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DRYRUN "icb-deploy.sh --dry-run exited $rc"
if [ "$RESUME" = 0 ]; then
  grep -q 'DB migration *no ' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: DB migration no"
  grep -q 'SPA rebuild *no ' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: SPA rebuild no"
  grep -q 'Service restart *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: service restart YES"
  grep -q 'dependency manifests changed' "$OUT/icb-deploy-dryrun.txt" && stop DRYRUN "the plan warns that dependency manifests changed"
fi
if [ "$RESUME" = 0 ]; then ok "plan: no migration, no SPA rebuild, restart"
else ok "plan: RESUME — icb-deploy.sh re-runs its idempotent steps (alembic at head, the SPA rebuilt from the same sources), restart"; fi

say "8. deploy (fast-forward, its own backup, restart, health, completion record)"
PID_BEFORE=$(systemctl show "$SERVICE" -p MainPID --value)
AET_BEFORE=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
T0=$(date +%s)
sudo -u icb bash "$DS" "$TARGET" --yes > "$OUT/icb-deploy.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DEPLOY "icb-deploy.sh exited $rc. Run the same deploy line again ONLY on the CA's word: it resumes. Rollback: the runbook (anchor ${PREV:0:7}, backup $BK)"
grep -q "DEPLOYED" "$OUT/icb-deploy.txt" || stop DEPLOY "icb-deploy.sh did not print DEPLOYED"
PID_AFTER=$(systemctl show "$SERVICE" -p MainPID --value)
AET_AFTER=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
[ "$PID_AFTER" != "$PID_BEFORE" ] || stop RESTART "MainPID unchanged ($PID_AFTER): the service did not restart"
service_start_epoch > "$RESTART_MARK"
ok "restart: $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER); tracebacks count from $(date -d "@$(cat "$RESTART_MARK")" '+%H:%M:%S')"
grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null || stop RECORD "no 'completed $TARGET' in $STATE_FILE"
ok "deploy record: completed ${TARGET:0:7}"

say "9. post-deploy asserts: the disk first, then the three doors in order (waiting 20 s for all workers to log startup)"
sleep 20
# a RESUME re-runs icb-deploy.sh's idempotent steps, its SPA build among them: only a FRESH deploy must leave the
# bundle byte-identical; after a resume the SPA must still be served = disk (checked in post_checks either way)
post_checks "$(cat "$RESTART_MARK")" "$T0" "$( [ "$RESUME" = 0 ] && echo "$B_SPA")"

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
calculator.js ?v=$CALC_V_PREV ${CALC_SHA_PREV:0:16} -> ?v=$(calc_v_disk) $(calc_sha_disk | cut -c1-16) (disk = 127.0.0.1 = LAN = Cloudflare)
version       local $(health_version "$LOCAL") · lan $(health_version "$LAN") · cloudflare $(health_version "$CF")
test banner   local $(banner_on "$LOCAL") · lan $(banner_on "$LAN") · cloudflare $(banner_on "$CF") (bars/[TEST] titles; prod 0/0)
no session    local: $(noauth_report "$LOCAL") · lan: $(noauth_report "$LAN") · cloudflare: $(noauth_report "$CF")
spa           $B_SPA -> $(spa_report | cut -d' ' -f1-2) ($( [ "$RESUME" = 0 ] && echo untouched || echo "rebuilt by the resume"); local = lan = disk)
quotes        $(cat "$QUOTES_MARK") at the deploy (count md5); now $(q "$QUOTES_SQL")
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (next: All after, on the page and the CLI)"
