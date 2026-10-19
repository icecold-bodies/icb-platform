#!/usr/bin/env bash
# v1.61.1 prod release (RT7): the audit's truth — the accepted list PINS its amounts (ACCEPTED_AMOUNT_CHANGED), the
# CI snapshot = prod (19 Oct export, 15 bodies) paired with that list, the golden refreshed for Burt's 19 Oct 4G rate
# (PU!C19 R5 581 -> R5 400), all five packs in CI, the flaky journeys' init-ready wait, the reboot guard. NO
# migration (alembic stays 0053), NO dependency, NO SPA rebuild, NO static ?v= bump; Python changes (the audit tool),
# so the service restarts — prod's Admin -> Costing audit page reads the accepted list and the golden from the
# deployed code. See docs/runbooks/prod-deploy-v1.61.1.md. Staged by mkstage.sh (committed blobs, LF) at
# /tmp/icb-release-v1.61.1; the operator runs ONE line at a time, ON the VM:
#
#     sudo bash /tmp/icb-release-v1.61.1/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.61.1/release.sh verify      read-only; before the deploy it fails on exactly the
#                                                               not-yet-deployed checks (version, list, golden)
#     sudo bash /tmp/icb-release-v1.61.1/release.sh deploy      ONLY in the window Michael picked
#
# Every run's FIRST line names the machine, the database (name @ host), the git HEAD and the BOOT TIME, and it
# refuses unless they are prod's — and refuses a kit staged before the last boot (ops/lib/icb_where.sh, the RT7
# reboot guard: the copy line stamps KIT_DIR/.staged_at). MES_DEMO_AUTOLOGIN_USER is checked "empty: yes/no" only.
#
# deploy = anchors -> autologin empty, ICB_ENVIRONMENT=prod -> the 4G factor exact -> served-bytes baseline (the SPA)
# -> PyYAML present -> backup (ops/lib/icb_backup.sh, checked) -> fetch (tags) + tag and range guards -> the repo's
# own deploy/prod/icb-deploy.sh (dry run: no migration, no SPA rebuild, restart; then --yes) -> post-deploy asserts:
# alembic 0053 unchanged, the factor unchanged, the deployed prod list loads strictly with its entries and its pair
# equals the deployed snapshot, the SPA byte-identical, and the THREE doors: /health/version =
# {"version":"v1.61.1","environment":"prod"}, no TEST banner, every probe_paths.txt path its listed status.
# Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.61.1
KIT_DIR=$BASE
ICB_LANE=RT7
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
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT7 release $MODE · machine $(hostname -s) · db ? · head ? · boot ?"; OUT=''; stop KIT "lib/icb_where.sh missing: copy the kit again"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'    # the identity read only; unset before anything else
icb_where "release v1.61.1 $MODE" "$REPO" "$URL"
unset PGOPTIONS
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENV_FILE"
for v in PREV PREV_TAG TARGET BRANCH TAG TAG_OBJ ALEMBIC CHANGED_COUNT CHANGED_SHA N_PROBES PYYAML_VERSION \
         DEPLOY_SH_SHA WORKERS FACTOR LIST_ENTRIES PAIR_SHA GOLDEN_MONTH EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
# preflight / verify run over the CURRENT code (v1.61.0) or, after the deploy, the target
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
noauth_report() { # $1 door. v1.61.1 adds no route (NEW_PROBES is empty), so every path answers its status throughout
  local door=$1 bad="" want path got
  while read -r want path; do
    case "$want" in ''|\#*) continue ;; esac
    got=$(curl -ks -o /dev/null --max-time 20 -H 'Accept: application/json' -w '%{http_code}' "$door$path" 2>/dev/null)
    [ "$got" = "$want" ] || bad="$bad $path=${got:-000}/$want"
  done < "$BASE/probe_paths.txt"
  if [ -n "$bad" ]; then echo "${bad# }"; else echo "all $N_PROBES as expected"; fi
}
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
tag_local() { gitr rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || echo missing; }
describe() { gitr describe --tags --abbrev=0 HEAD 2>/dev/null || echo none; }
workers_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Application startup complete' || true; }
bootfail_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'BOOTSTRAP FAILED' || true; }
tb_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Traceback' || true; }
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
post_checks() { # $1 journal --since, $2 epoch the code moved (deploy) or empty, $3 SPA "name sha" before (deploy) or empty
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
  check ACTIVE "$(systemctl is-active "$SERVICE" || true)" active
  check RESTART_AFTER_CODE "$(restart_after_code "${2:-}")" yes
  check WORKERS "$(workers_since "$1")" "$WORKERS"
  check BOOTSTRAP_FAILED "$(bootfail_since "$1")" 0
  local tb; tb=$(tb_since "$1")
  [ "$tb" = 0 ] || { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -B2 -A8 Traceback | tail -n 40 || true; }
  check TRACEBACKS "$tb" 0
  check HEALTH "$(code_url "$LOCAL/health")" 200
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "/health/version on the three doors (no session): the version and the environment the RUNNING process reports"
  for d in LOCAL LAN CF; do
    check "VERSION_$d" "$(version_of "${!d}")" "$TAG"
    check "ENVIRONMENT_$d" "$(environment_of "${!d}")" "$ENV_VALUE"
    check "NO_TEST_BANNER_$d" "$(banner_on "${!d}")" "0/0"
  done
  say "no session, Accept JSON: every path in probe_paths.txt answers its listed status, on the three doors"
  check NOAUTH_LOCAL "$(noauth_report "$LOCAL")" "all $N_PROBES as expected"
  check NOAUTH_LAN "$(noauth_report "$LAN")" "all $N_PROBES as expected"
  check NOAUTH_CF "$(noauth_report "$CF")" "all $N_PROBES as expected"
  say "served bytes: the SPA served = the bundle on disk (local = lan = disk$( [ -n "${3:-}" ] && echo ' = before: untouched by this release'))"
  set -- "$1" "${2:-}" "${3:-}" $(spa_report)
  check SPA_LOCAL "$6" "$5"
  check SPA_LAN "$7" "$5"
  [ -n "$3" ] && check SPA_UNCHANGED "$4 $5" "$3"
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
  say "the 4G factor (RT7_RULING_1A: exactly 5400/4100, set by Michael on 19 Oct)"
  check FACTOR "$(q "$FACTOR_SQL")" "$FACTOR"
  say "served bytes (the SPA: unchanged by this release)"
  set -- $(spa_report)
  check SPA_DISK_NAME "$1" '~^assets/index-'
  check SPA_LOCAL "$3" "$2"; check SPA_LAN "$4" "$2"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "today, on the three doors: $PREV_TAG answers, and RT4's no-session gate holds (this release adds no route)"
  for d in LOCAL LAN CF; do check "VERSION_$d" "$(version_of "${!d}")" "$PREV_TAG"; done
  check NOAUTH_LOCAL "$(noauth_report "$LOCAL")" "all $N_PROBES as expected"
  check NOAUTH_LAN "$(noauth_report "$LAN")" "all $N_PROBES as expected"
  check NOAUTH_CF "$(noauth_report "$CF")" "all $N_PROBES as expected"
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
  chmod -R a+rX "$OUT"
  if [ "$FAILS" -gt 0 ]; then echo; echo "######## PREFLIGHT: $FAILS check(s) FAILED — do not deploy. Tell the CA: $OUT"; exit 1; fi
  echo; echo "######## PREFLIGHT PASSED — tell the CA: $OUT"; exit 0
fi

# ==================================================================================================================
if [ "$MODE" = verify ]; then
  post_checks "$(service_since)" "" ""
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
  echo "   !!   running the post-deploy asserts against the current service start instead."
  post_checks "$(service_since)" "" ""
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ]; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} — a previous run stopped part way."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC_NOW is neither the start (${PREV:0:7}/$ALEMBIC) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"

say "2. autologin, the environment key and the 4G factor (before anything moves)"
[ "$(autologin_empty)" = yes ] || stop AUTOLOGIN "MES_DEMO_AUTOLOGIN_USER is NOT empty on prod (value not printed). Do not deploy — tell the BA"
ok "MES_DEMO_AUTOLOGIN_USER empty: yes"
[ "$(env_line)" = "$ENV_KEY=$ENV_VALUE" ] || stop ENV "$ENV_FILE has '$(env_line)', not $ENV_KEY=$ENV_VALUE (set since RT6) — tell the CA"
ok "$(env_line)"
F=$(q "$FACTOR_SQL"); [ "$F" = "$FACTOR" ] || stop FACTOR "costings.pu_foam_4g_factor reads '$F', not exactly '$FACTOR' — the pins assume it; tell the BA"
ok "4G factor '$F' (5400/4100)"

say "3. served-bytes baseline (the SPA must come through byte-identical)"
set -- $(spa_report)
B_SPA="$1 $2"
[ "$3" = "$2" ] && [ "$4" = "$2" ] || stop BYTES_BEFORE "SPA bundle $1 served bytes differ from disk"
ok "SPA $1 ${2:0:16}"

say "4. PyYAML $PYYAML_VERSION present (nothing is installed by this release)"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV. Do not deploy; tell the CA"
ok "present ($YV)"

say "5. backup — checked (ops/lib/icb_backup.sh); no migration, but the backup comes first (the dispatch's window step 2)"
BK="$BACKUP_DIR/icb_platform_pre-v1.61.1_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
icb_backup "$BK" custom "$URL" icb_costings.alembic_version icb_costings.admin_settings icb_costings.trailer_types \
  icb_costings.bill_of_materials icb_costings.materials icb_costings.calculations || stop BACKUP "$ICB_BACKUP_WHY"
chmod 600 "$BK" || true
BK_SHA=$ICB_BACKUP_SHA

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
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend backend/app/static | wc -l)
[ "$G_FE" = 0 ] || stop GUARD "frontend/ or backend/app/static changed: this kit expects the browser's files untouched"
G_DEP=$(gitr diff --name-only "$PREV" "$TARGET" -- deploy | wc -l)
[ "$G_DEP" = 0 ] || stop GUARD "deploy/ changed in the range: the icb-deploy.sh that runs is not the simulated one"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}): no migration, no dependency, no browser file, deploy/ untouched"

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
[ $rc = 0 ] || stop DEPLOY "icb-deploy.sh exited $rc. Rollback: see the runbook (anchor ${PREV:0:7}, backup $BK)"
grep -q "DEPLOYED" "$OUT/icb-deploy.txt" || stop DEPLOY "icb-deploy.sh did not print DEPLOYED"
PID_AFTER=$(systemctl show "$SERVICE" -p MainPID --value)
AET_AFTER=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
[ "$PID_AFTER" != "$PID_BEFORE" ] || stop RESTART "MainPID unchanged ($PID_AFTER): the service did not restart"
ok "restart: $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER)"
grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null || stop RECORD "no 'completed $TARGET' in $STATE_FILE"
ok "deploy record: completed ${TARGET:0:7}"

say "9. post-deploy asserts, the three doors included (waiting 20 s for all workers to log startup)"
sleep 20
# a RESUME re-runs icb-deploy.sh's idempotent steps, its SPA build among them: only a FRESH deploy must leave the
# bundle byte-identical; after a resume the SPA must still be served = disk (checked in post_checks either way)
post_checks "@$T0" "$T0" "$( [ "$RESUME" = 0 ] && echo "$B_SPA")"
TB=$(tb_since "@$T0")

cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
tag           $TAG = $TAG_OBJ (local = origin, peels to the target); git describe = $(describe)
alembic       $ALEMBIC -> $(q "select string_agg(version_num, ',') from alembic_version") (no migration)
4G factor     $(q "$FACTOR_SQL") (unchanged; Michael's 19 Oct value, 5400/4100)
audit list    $(list_report) (entries, pair sha256, pair = the deployed snapshot)
golden month  $(golden_month)
environment   $(env_line) in $ENV_FILE; autologin empty: $(autologin_empty)
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA (checked: alembic_version, admin_settings, trailer_types, bill_of_materials, materials, calculations)
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER), after the code moved: $(restart_after_code "$T0")
workers       $(workers_since "@$T0") started, $(bootfail_since "@$T0") bootstrap failed, $TB tracebacks
health        $(code_url "$LOCAL/health")
version       local $(health_version "$LOCAL") · lan $(health_version "$LAN") · cloudflare $(health_version "$CF")
test banner   local $(banner_on "$LOCAL") · lan $(banner_on "$LAN") · cloudflare $(banner_on "$CF") (bars/[TEST] titles; prod 0/0)
no session    local: $(noauth_report "$LOCAL") · lan: $(noauth_report "$LAN") · cloudflare: $(noauth_report "$CF")
spa           $B_SPA -> $(spa_report | cut -d' ' -f1-2) ($( [ "$RESUME" = 0 ] && echo untouched || echo "rebuilt by the resume"); local = lan = disk)
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (next: All after, on the page and the CLI)"
