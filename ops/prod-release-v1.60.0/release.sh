#!/usr/bin/env bash
# v1.60.0 prod release (RT3): body families in colour — migration 0051 (trailer_groups.colour + sort_order), the
# fixed startup bootstrap (it never re-creates a renamed or deleted group), the family on every body API row, the
# BODY TYPE optgroups + chips on the MES screens, the admin family editor. ONE migration (0051, additive), NO
# dependency, an SPA REBUILD (frontend/ changed: the costings list's family chip): backup, fast-forward, alembic
# upgrade head, npm run build, restart. See docs/runbooks/prod-deploy-v1.60.0.md. Staged by the CA with mkstage.sh
# (committed blobs, LF) at /tmp/icb-release-v1.60.0; the operator runs, ON the VM:
#
#     sudo bash /tmp/icb-release-v1.60.0/release.sh preflight   read-only; any time
#     sudo bash /tmp/icb-release-v1.60.0/release.sh verify      read-only; any time (before the deploy it
#                                                               must FAIL on exactly the not-yet-deployed checks)
#     sudo bash /tmp/icb-release-v1.60.0/release.sh deploy      ONLY in the window Michael picked
#
# deploy = anchors -> served-bytes baseline -> the groups + bindings baseline -> backup (the rollback for 0051) ->
# fetch (tags) + tag and range guards -> the repo's own deploy/prod/icb-deploy.sh (dry run, then --yes:
# fast-forward, its own backup, alembic upgrade head, npm run build, restart, health, completion record) ->
# post-deploy asserts. The six families are NOT set here: they are data (ops/prod-rt3/rt3_families.sh), after the
# deploy. Every real outcome is its own assert and a loud named STOP; decorative pipelines carry `|| true`.
# Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.60.0
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

[ -e "$OUT" ] && { echo "STOP: $OUT already exists (two runs in one second?): run again"; exit 1; }
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
for v in PREV TARGET BRANCH TAG TAG_OBJ ALEMBIC_BEFORE ALEMBIC_AFTER MIGRATION CHANGED_COUNT CHANGED_SHA \
         STATIC_1 STATIC_2 STATIC_3 STATIC_4 STATIC_5 SPA_MARK PYYAML_VERSION DEPLOY_SH_SHA WORKERS; do
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
# The five static files this release moves. Each STATIC_n in expected.env is
#   "<template> <path under static/> <v before|-> <sha before|-> <v after> <sha after>"   (derived by mkstage.sh)
# '-' before = the file is NEW in this release: the page does not load it yet.
STATICS="$STATIC_1|$STATIC_2|$STATIC_3|$STATIC_4|$STATIC_5"
spa_bundle() {   # the SPA bundle prod serves: the name in dist/index.html
  grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1
}
spa_report() { # "spa_name spa_disk spa_local spa_lan"
  local b; b=$(spa_bundle)
  echo "${b:-none} $( [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none)" \
       "$( [ -n "$b" ] && sha_url "$LOCAL/mes-app/$b" || echo none) $( [ -n "$b" ] && sha_url "$LAN/mes-app/$b" || echo none)"
}
spa_has_mark() { # $1 door: does the SPA bundle that door serves carry the family chip's field?
  local b; b=$(spa_bundle); [ -n "$b" ] || { echo none; return 0; }
  curl -ksS --max-time 20 "$1/mes-app/$b" | grep -c "$SPA_MARK" || true
}
tmpl_v() { # $1 template, $2 file name: every ?v= the page on disk loads (templates reload from disk)
  grep -o "$2?v=[0-9]*" "$REPO/backend/app/templates/$1" 2>/dev/null | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'
}
static_checks() { # $1 = before | after: each page loads that ?v=, and both doors serve that blob under it
  local IFS='|' s; for s in $STATICS; do
    IFS=' ' read -r tmpl path vb shab va shaa <<< "$s"
    local f=${path##*/} v=$va sha=$shaa; [ "$1" = before ] && { v=$vb; sha=$shab; }
    if [ "$v" = - ]; then check "V_${f%.*}_NOT_YET" "$(tmpl_v "$tmpl" "$f")" ""; continue; fi
    check "V_${f%.*}" "$(tmpl_v "$tmpl" "$f")" "$v"
    check "LOCAL_${f%.*}" "$(sha_url "$LOCAL/static/$path?v=$v")" "$sha"
    check "LAN_${f%.*}" "$(sha_url "$LAN/static/$path?v=$v")" "$sha"
  done
}
yaml_version() { "$PY" -c 'import yaml; print(yaml.__version__)' 2>/dev/null || echo missing; }
tag_local() { gitr rev-parse -q --verify "refs/tags/$TAG" 2>/dev/null || echo missing; }
describe() { gitr describe --tags --abbrev=0 HEAD 2>/dev/null || echo none; }   # what _app_version() reads
workers_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Application startup complete' || true; }
bootfail_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'BOOTSTRAP FAILED' || true; }
seeded_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Seeded TrailerGroup' || true; }
tb_since() { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -c 'Traceback' || true; }
service_start_epoch() { # the current service start, as epoch seconds (monotonic math: no timezone parsing)
  awk -v mono="$(systemctl show "$SERVICE" -p ActiveEnterTimestampMonotonic --value)" -v now="$(date +%s.%N)" \
      '{ printf "%d\n", now - $1 + mono / 1000000 }' /proc/uptime
}
service_since() { echo "@$(( $(service_start_epoch) - 1 ))"; }   # journalctl --since for the current start (1 s rounding margin)
head_moved_epoch() { # when HEAD last moved (the fast-forward), from icb's reflog
  gitr reflog show -1 --date=unix --format=%gd HEAD 2>/dev/null | sed -n 's/.*@{\([0-9]*\)}.*/\1/p'
}
restart_after_code() { # "yes" when the running service started AFTER the code last moved (no half-deploy).
  local moved start; start=$(service_start_epoch); moved=${1:-$(head_moved_epoch)}
  [ -n "$moved" ] || { echo "unknown (no reflog)"; return 0; }
  [ "$start" -ge $(( moved - 1 )) ] && echo yes || echo "no (service $start < code $moved)"
}
# 0051: the two columns and the CHECK, as the migration writes them
COL_SQL="select string_agg(column_name || ':' || data_type || ':' || coalesce(character_maximum_length::text, '-') || ':' ||
         is_nullable || ':' || coalesce(column_default, 'NULL'), ' ' order by column_name)
         from information_schema.columns where table_schema = 'icb_costings' and table_name = 'trailer_groups'
         and column_name in ('colour', 'sort_order')"
COL_WANT="colour:character varying:7:YES:NULL sort_order:integer:-:NO:100"
CK_SQL="select count(*) from pg_constraint c join pg_class t on t.oid = c.conrelid join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'icb_costings' and t.relname = 'trailer_groups' and c.contype = 'c'
        and c.conname = 'ck_trailer_groups_colour'"
# the groups and every body's binding (id|group|override): the startup bootstrap must leave them exactly as they were
GROUPS_SQL="select coalesce(string_agg(id || ':' || name || ':' || coalesce(report_template_id::text, '-'), ' ' order by id), 'none')
            from icb_costings.trailer_groups"
BINDINGS_SQL="select md5(coalesce(string_agg(id || ':' || coalesce(group_id::text, '-') || ':' ||
              coalesce(override_report_template_id::text, '-'), ',' order by id), '')) from icb_costings.trailer_types"
FAMILIES_SQL="select count(*) from icb_costings.trailer_groups where colour is not null"

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
  say "code + tag + schema (0051: colour + sort_order and the CHECK)"
  check HEAD "$(gitr rev-parse HEAD)" "$TARGET"
  check TAG_LOCAL "$(tag_local)" "$TAG_OBJ"
  check DESCRIBE "$(describe)" "$TAG"
  check ALEMBIC "$(q "select string_agg(version_num, ',') from alembic_version")" "$ALEMBIC_AFTER"
  check COLUMNS "$(q "$COL_SQL")" "$COL_WANT"
  check CHECK_CONSTRAINT "$(q "$CK_SQL")" 1
  echo "   families coloured: $(q "$FAMILIES_SQL") (0 right after the deploy; rt3_families.sh sets the six)"
  say "service (the Python is new only if the service started after the code moved)"
  check ACTIVE "$(systemctl is-active "$SERVICE" || true)" active
  check RESTART_AFTER_CODE "$(restart_after_code "${2:-}")" yes
  check WORKERS "$(workers_since "$1")" "$WORKERS"
  check BOOTSTRAP_FAILED "$(bootfail_since "$1")" 0
  check BOOTSTRAP_SEEDED_GROUPS "$(seeded_since "$1")" 0
  local tb; tb=$(tb_since "$1")
  [ "$tb" = 0 ] || { journalctl -u "$SERVICE" --since "$1" --no-pager 2>/dev/null | grep -B2 -A8 Traceback | tail -n 40 || true; }
  check TRACEBACKS "$tb" 0
  check HEALTH "$(code_url "$LOCAL/health")" 200
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  check TOOL_IMPORT "$(cd "$REPO/backend" && "$PY" -c 'from tools.costing_audit.cli import build_parser; import tools.costing_audit.mes_probe; print("ok")' 2>&1 | tail -n1)" ok
  check OPENAPI_DOORS_EQUAL "$( [ "$(sha_url "$LOCAL/openapi.json")" = "$(sha_url "$LAN/openapi.json")" ] && echo yes || echo no)" yes
  say "served bytes: each page loads the target ?v=, and both doors serve the target blob under it"
  static_checks after
  set -- $(spa_report)
  check SPA_LOCAL "$3" "$2"
  check SPA_LAN "$4" "$2"
  check SPA_HAS_FAMILY_LOCAL "$(spa_has_mark "$LOCAL")" '~^[1-9]'
  check SPA_HAS_FAMILY_LAN "$(spa_has_mark "$LAN")" '~^[1-9]'
}

# ================================================================================================
if [ "$MODE" = preflight ]; then
  say "anchors"
  check ALEMBIC "$ALEMBIC_NOW" "$ALEMBIC_BEFORE"
  check HEAD "$HEAD" "$PREV"
  check TRACKED_CLEAN "$(gitr status --porcelain --untracked-files=no | wc -l)" 0
  check COLUMNS_ABSENT "$(q "select count(*) from information_schema.columns where table_schema = 'icb_costings' and table_name = 'trailer_groups' and column_name in ('colour', 'sort_order')")" 0
  echo "   groups today: $(q "$GROUPS_SQL")"
  echo "   bindings md5: $(q "$BINDINGS_SQL")"
  say "served bytes (the v1.59.3 files are what prod serves today)"
  static_checks before
  set -- $(spa_report)
  check SPA_DISK_NAME "$1" '~^assets/index-'
  check SPA_LOCAL "$3" "$2"; check SPA_LAN "$4" "$2"
  echo "   SPA bundle $1 sha256 $2 (frontend/ changed in the range: the deploy rebuilds it)"
  check SPA_HAS_FAMILY_NOT_YET "$(spa_has_mark "$LOCAL")" 0
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "PyYAML (installed by v1.59.0; this release installs nothing)"
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "the SPA build tooling (icb-deploy.sh runs npm run build as icb)"
  check NPM "$(sudo -u icb bash -lc 'command -v npm >/dev/null && echo present || echo missing' 2>/dev/null)" present
  check NODE_MODULES "$( [ -d "$REPO/frontend/node_modules" ] && echo present || echo missing)" present
  say "the tag is on origin BEFORE the window (the footer reads it at startup)"
  RT=$(sudo -u icb git -C "$REPO" ls-remote --tags origin "refs/tags/$TAG" 2>/dev/null | cut -f1 | head -n1)
  check TAG_ON_ORIGIN "${RT:-missing}" "$TAG_OBJ"
  say "backup location (deploy takes a pg_dump before the migration)"
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
if [ "$HEAD" = "$PREV" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC_BEFORE" ]; then
  ok "fresh: code ${PREV:0:7}, alembic $ALEMBIC_BEFORE"
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC_AFTER" ] && grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null; then
  echo "   !!   ALREADY DEPLOYED: code ${TARGET:0:7}, alembic $ALEMBIC_AFTER, completion on record. Nothing is changed;"
  echo "   !!   running the post-deploy asserts against the current service start instead."
  post_checks "$(service_since)" ""
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && { [ "$ALEMBIC_NOW" = "$ALEMBIC_BEFORE" ] || [ "$ALEMBIC_NOW" = "$ALEMBIC_AFTER" ]; }; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} (alembic $ALEMBIC_NOW) — a previous run stopped part way."
  echo "   !!   icb-deploy.sh re-runs its idempotent steps (migrate, build, restart); every assert below still runs."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC_NOW is neither the start (${PREV:0:7}/$ALEMBIC_BEFORE) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"

say "2. served-bytes baseline"
if [ "$RESUME" = 0 ]; then
  static_checks before
else
  echo "   (resume: the code is already at the target; the files are asserted after the restart)"
fi
set -- $(spa_report)
B_SPA_NAME=$1; B_SPA=$2
[ "$3" = "$2" ] && [ "$4" = "$2" ] || stop BYTES_BEFORE "SPA bundle $1 served bytes differ from disk"
ok "SPA $B_SPA_NAME ${B_SPA:0:16} (the deploy rebuilds it)"

say "3. the groups and every body's binding, before (the restart must leave both exactly as they are)"
G_BEFORE=$(q "$GROUPS_SQL") || stop DB "cannot read trailer_groups: $G_BEFORE"
B_BEFORE=$(q "$BINDINGS_SQL") || stop DB "cannot read trailer_types: $B_BEFORE"
echo "$G_BEFORE" > "$OUT/groups-before.txt"; echo "$B_BEFORE" > "$OUT/bindings-before.txt"
ok "groups: $G_BEFORE"
ok "bindings md5: $B_BEFORE"

say "4. PyYAML $PYYAML_VERSION present (nothing is installed by this release)"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV: the v1.59.0 install is gone. Do not deploy; tell the CA"
ok "present ($YV)"

say "5. backup (the rollback for 0051, before the code, the schema and the data move)"
BK="$BACKUP_DIR/icb_platform_pre-v1.60.0_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
pg_dump "$URL" -Fc -f "$BK" || stop BACKUP "pg_dump failed"
chmod 600 "$BK" || true
[ -s "$BK" ] || stop BACKUP "$BK is empty"
BK_TOC=$(pg_restore --list "$BK" 2>/dev/null | grep -c 'TABLE DATA' || true)
[ "$BK_TOC" -gt 0 ] || stop BACKUP "$BK has no TABLE DATA entries"
for t in alembic_version trailer_groups trailer_types; do
  pg_restore --list "$BK" 2>/dev/null | grep -q "TABLE DATA icb_costings $t " || stop BACKUP "no $t in $BK"
done
BK_SHA=$(sha256sum "$BK" | cut -d' ' -f1)
ok "$BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA  ($BK_TOC table-data entries, incl. alembic_version, trailer_groups, trailer_types)"

say "6. fetch (with tags) + tag and range guards"
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
G_MIG=$(gitr diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$G_MIG" = "$MIGRATION" ] || stop GUARD "new migrations are '$G_MIG', expected exactly $MIGRATION"
G_REQ=$(gitr diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' 'frontend/package.json' 'frontend/package-lock.json' | wc -l)
[ "$G_REQ" = 0 ] || stop GUARD "a dependency manifest changed in the range: this kit installs nothing"
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend | wc -l)
[ "$G_FE" -gt 0 ] || stop GUARD "frontend/ is unchanged: this kit expects the SPA rebuild (the costings list chip)"
G_DEP=$(gitr diff --name-only "$PREV" "$TARGET" -- deploy | wc -l)
[ "$G_DEP" = 0 ] || stop GUARD "deploy/ changed in the range: the icb-deploy.sh that runs is not the simulated one"
ok "$G_COUNT files (C-sorted sha256 ${G_SHA:0:16}): one migration ($(basename "$MIGRATION")), no dependency, $G_FE frontend file(s), deploy/ untouched"

say "7. the repo's deploy script — dry run"
DS="$REPO/deploy/prod/icb-deploy.sh"
[ "$(sha256sum "$DS" | cut -d' ' -f1)" = "$DEPLOY_SH_SHA" ] || stop DRYRUN "$DS is not the expected blob"
sudo -u icb bash "$DS" "$TARGET" --dry-run > "$OUT/icb-deploy-dryrun.txt" 2>&1; rc=$?
sed 's/\x1b\[[0-9;]*m//g' "$OUT/icb-deploy-dryrun.txt" | sed 's/^/   | /' || true
[ $rc = 0 ] || stop DRYRUN "icb-deploy.sh --dry-run exited $rc"
if [ "$RESUME" = 0 ]; then
  grep -q "DB migration *YES - $(basename "$MIGRATION")" "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: DB migration YES - $(basename "$MIGRATION")"
  grep -q 'SPA rebuild *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: SPA rebuild YES"
  grep -q 'Service restart *YES' "$OUT/icb-deploy-dryrun.txt" || stop DRYRUN "plan does not say: service restart YES"
  grep -q 'dependency manifests changed' "$OUT/icb-deploy-dryrun.txt" && stop DRYRUN "the plan warns that dependency manifests changed"
fi
ok "plan: migrate $(basename "$MIGRATION" .py), rebuild the SPA, restart"

say "8. deploy (fast-forward, alembic upgrade head, npm run build, restart, health, completion record)"
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

say "9. post-deploy asserts (waiting 20 s for all workers to log startup)"
sleep 20
post_checks "@$T0" "$T0"
check GROUPS_UNCHANGED "$(q "$GROUPS_SQL")" "$G_BEFORE"
check BINDINGS_UNCHANGED "$(q "$BINDINGS_SQL")" "$B_BEFORE"
check FAMILIES_NOT_YET "$(q "$FAMILIES_SQL")" 0
S_SPA_NAME=$(spa_bundle)
[ "$S_SPA_NAME" != "$B_SPA_NAME" ] || stop SPA_REBUILT "the SPA bundle is still $B_SPA_NAME: the build did not run"
TB=$(tb_since "@$T0")

cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
tag           $TAG = $TAG_OBJ (local = origin, peels to the target); git describe = $(describe)
alembic       $ALEMBIC_BEFORE -> $(q "select string_agg(version_num, ',') from alembic_version") ($(basename "$MIGRATION"))
columns       trailer_groups $(q "$COL_SQL"); CHECK present: $(q "$CK_SQL")
groups        unchanged by the restart: $(q "$GROUPS_SQL"); bindings md5 $(q "$BINDINGS_SQL") (= before)
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER), after the code moved: $(restart_after_code "$T0")
workers       $(workers_since "@$T0") started, $(bootfail_since "@$T0") bootstrap failed, $(seeded_since "@$T0") groups seeded, $TB tracebacks
health        $(code_url "$LOCAL/health")
static        $(IFS='|'; for s in $STATICS; do IFS=' ' read -r t p vb sb va sa <<< "$s"; printf '%s ?v=%s %s  ' "${p##*/}" "$va" "${sa:0:16}"; done)(local = lan = the target blobs)
spa           $B_SPA_NAME -> $S_SPA_NAME (rebuilt; local = lan = disk; carries the family chip)
openapi       local = lan
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (next: rt3_families.sh dryrun; Cloudflare is probed by the CA from outside)"
