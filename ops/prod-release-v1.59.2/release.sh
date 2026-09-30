#!/usr/bin/env bash
# v1.59.2 prod release (RT1): #199-#203 on top of v1.59.0 — the NOT SELECTED section header, the
# Trailer Designer keeping rules it cannot show, rule chips from the database, the repair category
# ORDER BY. NO migration, NO dependency, NO SPA rebuild: a restart. See
# docs/runbooks/prod-deploy-v1.59.2.md. Staged by the CA with mkstage.sh (committed blobs, LF) at
# /tmp/icb-release-v1.59.2; the operator runs, ON the VM:
#
#     sudo bash /tmp/icb-release-v1.59.2/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.59.2/release.sh verify      read-only; any time (before the deploy it
#                                                               must FAIL on exactly the 6 not-yet-deployed checks)
#     sudo bash /tmp/icb-release-v1.59.2/release.sh deploy      ONLY in the window Michael picked
#
# deploy = anchors -> served-bytes baseline -> PyYAML present -> backup -> fetch (tags) + tag and range
# guards -> the repo's own deploy/prod/icb-deploy.sh (dry run, then --yes: fast-forward, restart,
# health, completion record) -> post-deploy asserts. Every real outcome is its own assert and a loud
# named STOP; decorative pipelines carry `|| true`. Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.59.2
REPO=/opt/icb-platform
SERVICE=icb-backend
ENV_FILE=/etc/icb/backend.env
PY=$REPO/.venv/bin/python
BACKUP_DIR=/var/backups/postgres
STATE_FILE=/var/tmp/icb-deploy-state
LOCAL=https://127.0.0.1
LAN=https://192.168.0.251
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$MODE-$TS

mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## nothing after this point ran. Tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }
ok()   { echo "   ok   $*"; }

# ---- 0. the staged kit ------------------------------------------------------------------------
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in PREV TARGET BRANCH TAG TAG_OBJ ALEMBIC CHANGED_COUNT CHANGED_SHA CALC_V_BEFORE CALC_SHA_BEFORE \
         CALC_V CALC_SHA PYYAML_VERSION DEPLOY_SH_SHA WORKERS; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
[ -r "$ENV_FILE" ] || stop KIT "$ENV_FILE not readable"
set -a; . "$ENV_FILE"; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PYTHONDONTWRITEBYTECODE=1      # never leave root-owned __pycache__ in the icb-owned repo
# One statement per call, in a server-enforced read-only session.
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
# git runs AS icb: a root `git status` can rewrite .git/index as root and break icb's git.
gitr() { sudo -u icb git -C "$REPO" "$@"; }
sha_url() { curl -ksS --max-time 20 "$1" | sha256sum | cut -d' ' -f1; }
code_url() { curl -ks -o /dev/null --max-time 20 -w '%{http_code}' "$1" || true; }

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
ALEMBIC_NOW=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
HEAD=$(gitr rev-parse HEAD) || stop GIT "cannot read $REPO HEAD"
say "prod: db=$DBNAME alembic=$ALEMBIC_NOW code=${HEAD:0:7} mode=$MODE target=${TARGET:0:7} ($TAG) $(date -Is)"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"

# ---- helpers shared by preflight / verify / deploy --------------------------------------------
spa_bundle() {   # the SPA bundle prod serves: the name in dist/index.html
  grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1
}
bytes_report() { # $1 = the ?v= to fetch. Prints "calc_local calc_lan spa_name spa_disk spa_local spa_lan"
  local b; b=$(spa_bundle)
  echo "$(sha_url "$LOCAL/static/js/calculator.js?v=$1") $(sha_url "$LAN/static/js/calculator.js?v=$1")" \
       "${b:-none} $( [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none)" \
       "$( [ -n "$b" ] && sha_url "$LOCAL/mes-app/$b" || echo none) $( [ -n "$b" ] && sha_url "$LAN/mes-app/$b" || echo none)"
}
tmpl_v() { # every calculator.js?v= the calculator page on disk loads (templates reload from disk)
  grep -o 'calculator\.js?v=[0-9]*' "$REPO/backend/app/templates/calculator.html" 2>/dev/null | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'
}
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
tag_local() { gitr rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || echo missing; }
describe() { gitr describe --tags --abbrev=0 HEAD 2>/dev/null || echo none; }   # what _app_version() reads
workers_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Application startup complete' || true; }
bootfail_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'BOOTSTRAP FAILED' || true; }
tb_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Traceback' || true; }
service_start_epoch() { # the current service start, as epoch seconds (monotonic math: no timezone parsing)
  local mono up now; mono=$(systemctl show "$SERVICE" -p ActiveEnterTimestampMonotonic --value)
  up=$(cut -d' ' -f1 /proc/uptime | cut -d. -f1); now=$(date +%s)
  echo $(( now - up + mono / 1000000 ))
}
service_since() { echo "@$(( $(service_start_epoch) - 5 ))"; }   # journalctl --since for the current start
head_moved_epoch() { # when HEAD last moved (the fast-forward), from icb's reflog
  gitr reflog show -1 --date=unix --format=%gd HEAD 2>/dev/null | sed -n 's/.*@{\([0-9]*\)}.*/\1/p'
}
restart_after_code() { # "yes" when the running service started AFTER the code last moved (no half-deploy)
  local moved start; start=$(service_start_epoch); moved=${1:-$(head_moved_epoch)}
  [ -n "$moved" ] || { echo "unknown (no reflog)"; return 0; }
  [ "$start" -ge "$moved" ] && echo yes || echo "no (service $start < code $moved)"
}

# ---- post-deploy checks, used by verify (report all) and deploy (stop at first) ----------------
FAILS=0
check() { # $1 name, $2 got, $3 want (exact) | $3 '~regex'
  local name=$1 got=$2 want=$3 okk=0
  if [ "${want:0:1}" = "~" ]; then [[ "$got" =~ ${want:1} ]] && okk=1; else [ "$got" = "$want" ] && okk=1; fi
  if [ $okk = 1 ]; then echo "   PASS $name = $got"
  else echo "   FAIL $name = '$got' (want $want)"; FAILS=$((FAILS + 1)); [ "$MODE" = deploy ] && stop "$name" "got '$got', want $want"; fi
  return 0
}
post_checks() { # $1 = journal --since for this service start, $2 = epoch the code moved (deploy) or empty
  say "code + tag + schema"
  check HEAD "$(gitr rev-parse HEAD)" "$TARGET"
  check TAG_LOCAL "$(tag_local)" "$TAG_OBJ"
  check DESCRIBE "$(describe)" "$TAG"
  check ALEMBIC "$(q "select string_agg(version_num, ',') from alembic_version")" "$ALEMBIC"
  say "service (the Python is new only if the service started after the code moved)"
  check ACTIVE "$(systemctl is-active "$SERVICE" || true)" active
  check RESTART_AFTER_CODE "$(restart_after_code "${2:-}")" yes
  check WORKERS "$(workers_since "$1")" "$WORKERS"
  check BOOTSTRAP_FAILED "$(bootfail_since "$1")" 0
  check HEALTH "$(code_url "$LOCAL/health")" 200
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  check TOOL_IMPORT "$(cd "$REPO/backend" && "$PY" -c 'from tools.costing_audit.cli import build_parser; import tools.audit_pricing_corrections; print("ok")' 2>&1 | tail -n1)" ok
  check OPENAPI_DOORS_EQUAL "$( [ "$(sha_url "$LOCAL/openapi.json")" = "$(sha_url "$LAN/openapi.json")" ] && echo yes || echo no)" yes
  say "served bytes: the calculator page loads ?v=$CALC_V, and both doors serve the target blob"
  check TEMPLATE_V "$(tmpl_v)" "$CALC_V"
  set -- $(bytes_report "$CALC_V")
  check CALC_LOCAL "$1" "$CALC_SHA"
  check CALC_LAN "$2" "$CALC_SHA"
  check SPA_LOCAL "$5" "$4"
  check SPA_LAN "$6" "$4"
}

# ================================================================================================
if [ "$MODE" = preflight ]; then
  say "anchors"
  check ALEMBIC "$ALEMBIC_NOW" "$ALEMBIC"
  check HEAD "$HEAD" "$PREV"
  check TRACKED_CLEAN "$(gitr status --porcelain --untracked-files=no | wc -l)" 0
  say "served bytes (the v1.59.0 calculator is what prod serves today)"
  check TEMPLATE_V "$(tmpl_v)" "$CALC_V_BEFORE"
  set -- $(bytes_report "$CALC_V_BEFORE")
  check CALC_LOCAL "$1" "$CALC_SHA_BEFORE"; check CALC_LAN "$2" "$CALC_SHA_BEFORE"
  check SPA_DISK_NAME "$3" '~^assets/index-'
  check SPA_LOCAL "$5" "$4"; check SPA_LAN "$6" "$4"
  echo "   SPA bundle $3 sha256 $4 (frontend/ unchanged in the range: the deploy must leave it as is)"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "PyYAML (installed by v1.59.0; this release installs nothing)"
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "the tag is on origin BEFORE the window (the footer reads it at startup)"
  RT=$(sudo -u icb git -C "$REPO" ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | cut -f1 | head -n1)
  check TAG_ON_ORIGIN "${RT:-missing}" "$TAG_OBJ"
  say "backup location"
  check BACKUP_DIR "$( [ -d "$BACKUP_DIR" ] && [ -w "$BACKUP_DIR" ] && echo writable || echo no)" writable
  echo "   free space: $(df -h "$BACKUP_DIR" | tail -n1 || true)"
  echo "   latest backups:"; ls -lt "$BACKUP_DIR" 2>/dev/null | head -n 4 | sed 's/^/      /' || true
  say "deploy tooling on prod"
  check DEPLOY_SCRIPT "$(sha256sum "$REPO/deploy/prod/icb-deploy.sh" 2>/dev/null | cut -d' ' -f1 || echo missing)" "$DEPLOY_SH_SHA"
  check ICB_SUDO "$(sudo -u icb sudo -n true 2>/dev/null && echo nopasswd || echo password)" nopasswd
  echo "   deploy record: $(cat "$STATE_FILE" 2>/dev/null || echo none) (owner $(stat -c %U "$STATE_FILE" 2>/dev/null || echo -))"
  echo "   footer today: git describe -> $(describe) (the tag arrives with the deploy's fetch)"
  chmod -R a+rX "$OUT"
  if [ "$FAILS" -gt 0 ]; then echo; echo "######## PREFLIGHT: $FAILS check(s) FAILED — do not deploy. Tell the CA: $OUT"; exit 1; fi
  echo; echo "######## PREFLIGHT PASSED — tell the CA: $OUT"; exit 0
fi

# ================================================================================================
if [ "$MODE" = verify ]; then
  post_checks "$(service_since)" ""
  chmod -R a+rX "$OUT"
  echo; echo "######## VERIFY: $FAILS check(s) failed — tell the CA: $OUT"
  [ "$FAILS" -eq 0 ]; exit $?
fi

# ================================================================================================
# deploy
say "1. anchors"
RESUME=0
if [ "$HEAD" = "$PREV" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ]; then
  ok "fresh: code ${PREV:0:7}, alembic $ALEMBIC"
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ] && grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null; then
  echo "   !!   ALREADY DEPLOYED: code ${TARGET:0:7}, completion on record. Nothing is changed;"
  echo "   !!   running the post-deploy asserts against the current service start instead."
  post_checks "$(service_since)" ""
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC" ]; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} — a previous run stopped part way."
  echo "   !!   icb-deploy.sh re-runs its idempotent steps (restart); every assert below still runs."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC_NOW is neither the start (${PREV:0:7}/$ALEMBIC) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"

say "2. served-bytes baseline"
if [ "$RESUME" = 0 ]; then
  set -- $(bytes_report "$CALC_V_BEFORE")
  [ "$1" = "$CALC_SHA_BEFORE" ] && [ "$2" = "$CALC_SHA_BEFORE" ] || stop BYTES_BEFORE "calculator.js is not the v1.59.0 blob (local $1 / lan $2)"
  [ "$(tmpl_v)" = "$CALC_V_BEFORE" ] || stop BYTES_BEFORE "calculator.html loads ?v=$(tmpl_v), expected $CALC_V_BEFORE"
else
  set -- $(bytes_report "$CALC_V")
fi
B_SPA_NAME=$3; B_SPA=$4
[ "$5" = "$4" ] && [ "$6" = "$4" ] || stop BYTES_BEFORE "SPA bundle $3 served bytes differ from disk"
ok "calculator.js ${1:0:16}  ·  SPA $B_SPA_NAME ${B_SPA:0:16}"

say "3. PyYAML $PYYAML_VERSION present (nothing is installed by this release)"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV: the v1.59.0 install is gone. Do not deploy; tell the CA"
ok "present ($YV)"

say "4. backup (no migration: this is the window's restore point, before the code and the data move)"
BK="$BACKUP_DIR/icb_platform_pre-v1.59.2_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
pg_dump "$URL" -Fc -f "$BK" || stop BACKUP "pg_dump failed"
chmod 600 "$BK" || true
[ -s "$BK" ] || stop BACKUP "$BK is empty"
BK_TOC=$(pg_restore --list "$BK" 2>/dev/null | grep -c 'TABLE DATA' || true)
[ "$BK_TOC" -gt 0 ] || stop BACKUP "$BK has no TABLE DATA entries"
pg_restore --list "$BK" 2>/dev/null | grep -q 'TABLE DATA icb_costings bill_of_materials' || stop BACKUP "no bill_of_materials in $BK"
BK_SHA=$(sha256sum "$BK" | cut -d' ' -f1)
ok "$BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA  ($BK_TOC table-data entries)"

say "5. fetch (with tags) + tag and range guards"
sudo -u icb git -C "$REPO" fetch origin --tags --progress 2>&1 | sed 's/^/   /' || true
ORIGIN=$(gitr rev-parse "origin/$BRANCH") || stop GUARD "origin/$BRANCH not resolvable"
[ "$ORIGIN" = "$TARGET" ] || stop GUARD "origin/$BRANCH is ${ORIGIN:0:7}, the staged target is ${TARGET:0:7}: re-stage"
[ "$(tag_local)" = "$TAG_OBJ" ] || stop TAG "refs/tags/$TAG is '$(tag_local)', expected the tag object ${TAG_OBJ:0:12} (tag first, then deploy)"
[ "$(gitr rev-parse "$TAG^{commit}" 2>/dev/null)" = "$TARGET" ] || stop TAG "$TAG does not peel to ${TARGET:0:7}"
DESC=$(gitr describe --tags --abbrev=0 "$TARGET" 2>/dev/null || echo none)
[ "$DESC" = "$TAG" ] || stop TAG "git describe at the target says '$DESC': the footer would not read $TAG"
ok "$TAG = tag object ${TAG_OBJ:0:12} -> ${TARGET:0:7}; git describe at the target = $DESC"
gitr merge-base --is-ancestor "$PREV" "$TARGET" || stop GUARD "${PREV:0:7} is not an ancestor of ${TARGET:0:7}"
G_COUNT=$(gitr diff --name-only "$PREV" "$TARGET" | wc -l)
G_SHA=$(gitr diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
[ "$G_COUNT" = "$CHANGED_COUNT" ] && [ "$G_SHA" = "$CHANGED_SHA" ] || stop GUARD "changed-file list differs: $G_COUNT files ${G_SHA:0:16}, staged $CHANGED_COUNT ${CHANGED_SHA:0:16}"
G_MIG=$(gitr diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*' | wc -l)
[ "$G_MIG" = 0 ] || stop GUARD "$G_MIG new migration(s) in the range: this kit deploys none"
G_REQ=$(gitr diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' | wc -l)
[ "$G_REQ" = 0 ] || stop GUARD "requirements changed in the range: this kit installs nothing"
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend | wc -l)
[ "$G_FE" = 0 ] || stop GUARD "$G_FE frontend file(s) changed: the SPA would need a rebuild"
G_DEP=$(gitr diff --name-only "$PREV" "$TARGET" -- deploy | wc -l)
[ "$G_DEP" = 0 ] || stop GUARD "deploy/ changed in the range: the icb-deploy.sh that runs is not the simulated one"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}): no migration, no requirements, frontend/ and deploy/ untouched"

say "6. the repo's deploy script — dry run"
DS="$REPO/deploy/prod/icb-deploy.sh"
[ "$(sha256sum "$DS" | cut -d' ' -f1)" = "$DEPLOY_SH_SHA" ] || stop DRYRUN "$DS is not the expected blob"
sudo -u icb bash "$DS" "$TARGET" --dry-run > "$OUT/icb-deploy-dryrun.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy-dryrun.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DRYRUN "icb-deploy.sh --dry-run exited $rc"
if [ "$RESUME" = 0 ]; then
  grep -q 'DB migration *no' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: DB migration no"
  grep -q 'SPA rebuild *no' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: SPA rebuild no"
  grep -q 'Service restart *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: service restart YES"
fi
ok "plan: no migration, no SPA rebuild, restart"

say "7. deploy (fast-forward, restart, health, completion record)"
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

say "8. post-deploy asserts (waiting 20 s for all workers to log startup)"
sleep 20
post_checks "@$T0" "$T0"
TB=$(tb_since "@$T0"); [ "$TB" = 0 ] || { journalctl -u "$SERVICE" --since "@$T0" --no-pager | grep -B2 -A8 Traceback | tail -n 40 || true; stop TRACEBACKS "$TB traceback(s) since the restart"; }
ok "0 tracebacks since the restart"
[ "$B_SPA_NAME" = "$(spa_bundle)" ] || stop BYTES_AFTER "the SPA bundle name changed"

cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
tag           $TAG = $TAG_OBJ (local = origin, peels to the target); git describe = $(describe)
alembic       $ALEMBIC -> $(q "select string_agg(version_num, ',') from alembic_version") (no migration)
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER), after the code moved: $(restart_after_code "$T0")
workers       $(workers_since "@$T0") started, $(bootfail_since "@$T0") bootstrap failed, $TB tracebacks
health        $(code_url "$LOCAL/health")
calculator    calculator.html loads ?v=$(tmpl_v); calculator.js ${CALC_SHA} (local = lan = the target blob)
spa           $B_SPA_NAME ${B_SPA} (local = lan = disk; unchanged, no rebuild)
openapi       local = lan
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (Cloudflare is probed by the CA from outside, now that the disk matches)"
