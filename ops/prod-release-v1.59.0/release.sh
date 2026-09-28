#!/usr/bin/env bash
# v1.59.0 prod release: the costing audit admin page (migration 0049). See
# docs/runbooks/prod-deploy-v1.59.0-costing-audit-admin.md. Staged by the CA with mkstage.sh
# (committed blobs, LF) at /tmp/icb-release-v1.59.0; the operator runs, ON the VM:
#
#     sudo bash /tmp/icb-release-v1.59.0/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.59.0/release.sh verify      read-only; any time (before the deploy it
#                                                               must FAIL on exactly the 0049 checks)
#     sudo bash /tmp/icb-release-v1.59.0/release.sh deploy      ONLY in the window Michael picked
#
# deploy = anchors -> served-bytes baseline -> PyYAML -> backup -> fetch + range guard -> the repo's
# own deploy/prod/icb-deploy.sh (dry run, then --yes; it fast-forwards, runs alembic, restarts, and
# records completion) -> post-deploy asserts. Every real outcome is its own assert and a loud named
# STOP; decorative pipelines carry `|| true`. Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.59.0
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
for v in PREV TARGET BRANCH ALEMBIC_BEFORE ALEMBIC_AFTER MIGRATION CHANGED_COUNT CHANGED_SHA CALC_V CALC_SHA \
         NEW_PATHS PYYAML_VERSION PERM WORKERS; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
[ -r "$ENV_FILE" ] || stop KIT "$ENV_FILE not readable"
set -a; . "$ENV_FILE"; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
export PYTHONDONTWRITEBYTECODE=1      # never leave root-owned __pycache__ in the icb-owned repo
# One statement per call, in a server-enforced read-only session.
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
# git reads run AS icb: a root `git status` can rewrite .git/index as root and break icb's git.
gitr() { sudo -u icb git -C "$REPO" "$@"; }
sha_url() { curl -ksS --max-time 20 "$1" | sha256sum | cut -d' ' -f1; }
code_url() { curl -ks -o /dev/null --max-time 20 -w '%{http_code}' "$1" || true; }

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
HEAD=$(gitr rev-parse HEAD) || stop GIT "cannot read $REPO HEAD"
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} mode=$MODE target=${TARGET:0:7} $(date -Is)"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"

# ---- helpers shared by preflight / verify / deploy --------------------------------------------
spa_bundle() {   # the SPA bundle prod serves: the name in dist/index.html
  grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1
}
bytes_report() { # prints "calc_local calc_lan spa_name spa_disk spa_local spa_lan"
  local b; b=$(spa_bundle)
  echo "$(sha_url "$LOCAL/static/js/calculator.js?v=$CALC_V") $(sha_url "$LAN/static/js/calculator.js?v=$CALC_V")" \
       "${b:-none} $( [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none)" \
       "$( [ -n "$b" ] && sha_url "$LOCAL/mes-app/$b" || echo none) $( [ -n "$b" ] && sha_url "$LAN/mes-app/$b" || echo none)"
}
openapi_missing() { # the NEW_PATHS absent from a door's /openapi.json (empty = all present)
  curl -ksS --max-time 20 "$1/openapi.json" | "$PY" -c '
import json, sys
try:
    have = set(json.load(sys.stdin).get("paths", {}))
except Exception as e:
    print("UNPARSEABLE:", e); sys.exit(0)
print(" ".join(p for p in sys.argv[1:] if p not in have))' $NEW_PATHS
}
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
workers_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Application startup complete' || true; }
bootfail_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'BOOTSTRAP FAILED' || true; }
tb_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Traceback' || true; }
service_since() { # journalctl --since for the current service start (monotonic -> seconds ago)
  local mono up; mono=$(systemctl show "$SERVICE" -p ActiveEnterTimestampMonotonic --value)
  up=$(cut -d' ' -f1 /proc/uptime | cut -d. -f1)
  echo "-$(( up - mono / 1000000 + 5 ))s"
}

# ---- post-deploy checks, used by verify (report all) and deploy (stop at first) ----------------
# check NAME "command whose stdout must equal EXPECTED" EXPECTED
FAILS=0
check() { # $1 name, $2 got, $3 want (exact) | $3 '~regex'
  local name=$1 got=$2 want=$3 okk=0
  if [ "${want:0:1}" = "~" ]; then [[ "$got" =~ ${want:1} ]] && okk=1; else [ "$got" = "$want" ] && okk=1; fi
  if [ $okk = 1 ]; then echo "   PASS $name = $got"
  else echo "   FAIL $name = '$got' (want $want)"; FAILS=$((FAILS + 1)); [ "$MODE" = deploy ] && stop "$name" "got '$got', want $want"; fi
  return 0
}
post_checks() { # $1 = journal --since for this service start
  say "code + schema"
  check HEAD "$(gitr rev-parse HEAD)" "$TARGET"
  check ALEMBIC "$(q "select string_agg(version_num, ',') from alembic_version")" "$ALEMBIC_AFTER"
  check TABLE "$(q "select count(*) from information_schema.tables where table_schema='icb_costings' and table_name='costing_audit_runs'")" 1
  check INDEXES "$(q "select count(*) from pg_indexes where schemaname='icb_costings' and indexname in ('ix_costing_audit_runs_pack_env_started','ix_costing_audit_runs_started')")" 2
  check PERMISSION "$(q "select count(*) from permissions where name='$PERM'")" 1
  check ADMIN_GRANT "$(q "select count(*) from role_permissions rp join permissions p on p.id=rp.permission_id where p.name='$PERM' and rp.role='admin'")" 1
  say "service"
  check ACTIVE "$(systemctl is-active "$SERVICE" || true)" active
  check WORKERS "$(workers_since "$1")" "$WORKERS"
  check BOOTSTRAP_FAILED "$(bootfail_since "$1")" 0
  check HEALTH "$(code_url "$LOCAL/health")" 200
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  check TOOL_IMPORT "$(cd "$REPO/backend" && "$PY" -c 'from tools.costing_audit.cli import build_parser; print("ok")' 2>&1 | tail -n1)" ok
  say "the page is live and gated (unauthenticated probes)"
  check OPENAPI_LOCAL_MISSING "$(openapi_missing "$LOCAL")" ""
  check OPENAPI_LAN_MISSING "$(openapi_missing "$LAN")" ""
  check OPENAPI_DOORS_EQUAL "$( [ "$(sha_url "$LOCAL/openapi.json")" = "$(sha_url "$LAN/openapi.json")" ] && echo yes || echo no)" yes
  check PAGE_UNAUTH "$(code_url "$LOCAL/admin/costing-audit")" '~^(301|302|303|307|401|403)$'
  check API_UNAUTH "$(code_url "$LOCAL/api/admin/costing-audit/runs")" '~^(401|403)$'
  say "served bytes (static + SPA untouched by this range)"
  set -- $(bytes_report)
  check CALC_LOCAL "$1" "$CALC_SHA"
  check CALC_LAN "$2" "$CALC_SHA"
  check SPA_LOCAL "$5" "$4"
  check SPA_LAN "$6" "$4"
}

# ================================================================================================
if [ "$MODE" = preflight ]; then
  say "anchors"
  check ALEMBIC "$ALEMBIC" "$ALEMBIC_BEFORE"
  check HEAD "$HEAD" "$PREV"
  check TRACKED_CLEAN "$(gitr status --porcelain --untracked-files=no | wc -l)" 0
  say "served bytes (expected from the target tree: calculator.js is the same blob at $PREV and $TARGET)"
  set -- $(bytes_report)
  check CALC_LOCAL "$1" "$CALC_SHA"; check CALC_LAN "$2" "$CALC_SHA"
  check SPA_DISK_NAME "$3" '~^assets/index-'
  check SPA_LOCAL "$5" "$4"; check SPA_LAN "$6" "$4"
  echo "   SPA bundle $3 sha256 $4 (frontend/ unchanged in the range: the deploy must leave it as is)"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "PyYAML (v1.59 needs it in prod's venv)"
  echo "   venv python: $("$PY" --version 2>&1 || true)   venv owner: $(stat -c %U "$REPO/.venv" 2>/dev/null || true)"
  echo "   import yaml -> $(yaml_version)"
  echo "   pip --dry-run PyYAML==$PYYAML_VERSION:"
  "$PY" -m pip install --disable-pip-version-check --dry-run --no-deps "PyYAML==$PYYAML_VERSION" 2>&1 | sed 's/^/      /' | tail -n 5 || true
  echo "   pip --dry-run -r the target requirements.txt (report only; the deploy installs PyYAML alone):"
  "$PY" -m pip install --disable-pip-version-check --dry-run -r "$BASE/requirements.txt" 2>&1 | grep -E '^Would install|ERROR' | sed 's/^/      /' || true
  say "backup location"
  check BACKUP_DIR "$( [ -d "$BACKUP_DIR" ] && [ -w "$BACKUP_DIR" ] && echo writable || echo no)" writable
  echo "   free space: $(df -h "$BACKUP_DIR" | tail -n1 || true)"
  echo "   latest backups:"; ls -lt "$BACKUP_DIR" 2>/dev/null | head -n 4 | sed 's/^/      /' || true
  say "deploy tooling on prod"
  check DEPLOY_SCRIPT "$( [ -f "$REPO/deploy/prod/icb-deploy.sh" ] && echo present || echo missing)" present
  check ICB_SUDO "$(sudo -u icb sudo -n true 2>/dev/null && echo nopasswd || echo password)" nopasswd
  echo "   deploy record: $(cat "$STATE_FILE" 2>/dev/null || echo none) (owner $(stat -c %U "$STATE_FILE" 2>/dev/null || echo -))"
  chmod -R a+rX "$OUT"
  if [ "$FAILS" -gt 0 ]; then echo; echo "######## PREFLIGHT: $FAILS check(s) FAILED — do not deploy. Tell the CA: $OUT"; exit 1; fi
  echo; echo "######## PREFLIGHT PASSED — tell the CA: $OUT"; exit 0
fi

# ================================================================================================
if [ "$MODE" = verify ]; then
  post_checks "$(service_since)"
  chmod -R a+rX "$OUT"
  echo; echo "######## VERIFY: $FAILS check(s) failed — tell the CA: $OUT"
  [ "$FAILS" -eq 0 ]; exit $?
fi

# ================================================================================================
# deploy
say "1. anchors"
RESUME=0
if [ "$HEAD" = "$PREV" ] && [ "$ALEMBIC" = "$ALEMBIC_BEFORE" ]; then
  ok "fresh: code ${PREV:0:7}, alembic $ALEMBIC_BEFORE"
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC" = "$ALEMBIC_AFTER" ] && grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null; then
  echo "   !!   ALREADY DEPLOYED: code ${TARGET:0:7}, alembic $ALEMBIC_AFTER, completion on record. Nothing is changed;"
  echo "   !!   running the post-deploy asserts against the current service start instead."
  post_checks "$(service_since)"
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && { [ "$ALEMBIC" = "$ALEMBIC_BEFORE" ] || [ "$ALEMBIC" = "$ALEMBIC_AFTER" ]; }; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} (alembic $ALEMBIC) — a previous run stopped part way."
  echo "   !!   icb-deploy.sh re-runs migrate + restart (idempotent); every assert below still runs."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC is neither the start (${PREV:0:7}/$ALEMBIC_BEFORE) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"

say "2. served-bytes baseline (must be unchanged by the deploy)"
set -- $(bytes_report)
B_CALC=$1; B_SPA_NAME=$3; B_SPA=$4
[ "$1" = "$CALC_SHA" ] && [ "$2" = "$CALC_SHA" ] || stop BYTES_BEFORE "calculator.js?v=$CALC_V is not the expected blob (local $1 / lan $2)"
[ "$5" = "$4" ] && [ "$6" = "$4" ] || stop BYTES_BEFORE "SPA bundle $3 served bytes differ from disk"
ok "calculator.js?v=$CALC_V ${B_CALC:0:16}  ·  SPA $B_SPA_NAME ${B_SPA:0:16}"

say "3. PyYAML $PYYAML_VERSION in prod's venv"
YV=$(yaml_version)
if [ "$YV" = "$PYYAML_VERSION" ]; then ok "already present ($YV) — nothing installed"
else
  echo "   import yaml -> $YV; installing PyYAML==$PYYAML_VERSION (no deps) as the venv owner"
  VOWN=$(stat -c %U "$REPO/.venv") || stop PYYAML "cannot stat the venv"
  sudo -u "$VOWN" "$PY" -m pip install --disable-pip-version-check --no-deps "PyYAML==$PYYAML_VERSION" 2>&1 | tail -n 3 || true
  YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "after install import yaml -> $YV"
  ok "installed ($YV)"
fi

say "4. backup (the rollback for 0049)"
BK="$BACKUP_DIR/icb_platform_pre-v1.59.0_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
pg_dump "$URL" -Fc -f "$BK" || stop BACKUP "pg_dump failed"
chmod 600 "$BK" || true
[ -s "$BK" ] || stop BACKUP "$BK is empty"
BK_TOC=$(pg_restore --list "$BK" 2>/dev/null | grep -c 'TABLE DATA' || true)
[ "$BK_TOC" -gt 0 ] || stop BACKUP "$BK has no TABLE DATA entries"
pg_restore --list "$BK" 2>/dev/null | grep -q 'TABLE DATA icb_costings alembic_version' || stop BACKUP "no alembic_version in $BK"
BK_SHA=$(sha256sum "$BK" | cut -d' ' -f1)
ok "$BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA  ($BK_TOC table-data entries)"

say "5. fetch + range guard"
sudo -u icb git -C "$REPO" fetch origin --tags --progress 2>&1 | sed 's/^/   /' || true
ORIGIN=$(gitr rev-parse "origin/$BRANCH") || stop GUARD "origin/$BRANCH not resolvable"
[ "$ORIGIN" = "$TARGET" ] || stop GUARD "origin/$BRANCH is ${ORIGIN:0:7}, the staged target is ${TARGET:0:7}: re-stage"
gitr merge-base --is-ancestor "$PREV" "$TARGET" || stop GUARD "${PREV:0:7} is not an ancestor of ${TARGET:0:7}"
G_COUNT=$(gitr diff --name-only "$PREV" "$TARGET" | wc -l)
G_SHA=$(gitr diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
[ "$G_COUNT" = "$CHANGED_COUNT" ] && [ "$G_SHA" = "$CHANGED_SHA" ] || stop GUARD "changed-file list differs: $G_COUNT files ${G_SHA:0:16}, staged $CHANGED_COUNT ${CHANGED_SHA:0:16}"
G_MIG=$(gitr diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$G_MIG" = "$MIGRATION" ] || stop GUARD "new migrations are '$G_MIG', expected exactly $MIGRATION"
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend | wc -l)
[ "$G_FE" = 0 ] || stop GUARD "$G_FE frontend file(s) changed: the SPA would need a rebuild with the port stopped"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}), one migration ($(basename "$MIGRATION")), frontend untouched: no SPA rebuild"

say "6. the repo's deploy script — dry run"
DS="$REPO/deploy/prod/icb-deploy.sh"
sudo -u icb bash "$DS" "$TARGET" --dry-run > "$OUT/icb-deploy-dryrun.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy-dryrun.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DRYRUN "icb-deploy.sh --dry-run exited $rc"
if [ "$RESUME" = 0 ]; then
  grep -q 'DB migration *YES - 0049_costing_audit_runs.py' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: migration YES 0049"
  grep -q 'SPA rebuild *no' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: SPA rebuild no"
  grep -q 'Service restart *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: service restart YES"
fi
ok "plan: migrate 0049, no SPA rebuild, restart"

say "7. deploy (fast-forward, alembic upgrade head, restart, health)"
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
post_checks "@$T0"
TB=$(tb_since "@$T0"); [ "$TB" = 0 ] || { journalctl -u "$SERVICE" --since "@$T0" --no-pager | grep -B2 -A8 Traceback | tail -n 40 || true; stop TRACEBACKS "$TB traceback(s) since the restart"; }
ok "0 tracebacks since the restart"
[ "$B_SPA_NAME" = "$(spa_bundle)" ] || stop BYTES_AFTER "the SPA bundle name changed"

cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
alembic       $ALEMBIC_BEFORE -> $(q "select string_agg(version_num, ',') from alembic_version")
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA
pyyaml        $(yaml_version)
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER)
workers       $(workers_since "@$T0") started, $(bootfail_since "@$T0") bootstrap failed, $TB tracebacks
health        $(code_url "$LOCAL/health")
calculator.js ?v=$CALC_V ${B_CALC} (local = lan = the git blob; unchanged)
spa           $B_SPA_NAME ${B_SPA} (local = lan = disk; unchanged, no rebuild)
openapi       local = lan, the $(echo $NEW_PATHS | wc -w) new paths present
page          unauthenticated /admin/costing-audit -> $(code_url "$LOCAL/admin/costing-audit"), /api/admin/costing-audit/runs -> $(code_url "$LOCAL/api/admin/costing-audit/runs")
permission    $PERM seeded, granted to admin
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (Cloudflare is probed by the CA from outside, now that the disk matches)"
