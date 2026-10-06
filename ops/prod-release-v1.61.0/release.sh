#!/usr/bin/env bash
# v1.61.0 prod release (RT6): Burt's insulation rules ENFORCED — migration 0053 (trailer_groups.insulation_rule TEXT
# NULL), the one check (services/insulation_rules + rule_guard: calculate warns; approve, Accept, the pre-job card and
# a job from a costing refuse), the panels grey / Remove / the paste refusal (calculator.js), the family editor's grid,
# the draft save / restore warnings, and the "TEST SERVER" banner (ICB_ENVIRONMENT; /health/version says which
# server). ONE migration (0053, additive), NO dependency, an SPA REBUILD (frontend/: the Accept refusal's sentence):
# backup, fast-forward, alembic upgrade head, npm run build, restart. Burt's two rules themselves are DATA, set after
# the deploy by ops/prod-rt6/rt6_rules.sh. See docs/runbooks/prod-deploy-v1.61.0.md. Staged by mkstage.sh (committed
# blobs, LF) at /tmp/icb-release-v1.61.0; the operator runs ONE line at a time, ON the VM:
#
#     sudo bash /tmp/icb-release-v1.61.0/release.sh preflight   read-only; any time; includes the autologin check
#     sudo bash /tmp/icb-release-v1.61.0/release.sh verify      read-only; before the deploy it must FAIL on exactly
#                                                               the not-yet-deployed checks
#     sudo bash /tmp/icb-release-v1.61.0/release.sh env         appends ICB_ENVIRONMENT=prod to /etc/icb/backend.env
#                                                               by MERGE (refuses another value), reads it back
#     sudo bash /tmp/icb-release-v1.61.0/release.sh deploy      ONLY in the window Michael picked
#
# Every run's FIRST line names the machine, the database (name @ host) and the git HEAD, and it refuses unless they
# are prod's (ops/lib/icb_where.sh — RT6 safe pastes). MES_DEMO_AUTOLOGIN_USER is checked "empty: yes/no" only — its
# value is never printed; "no" STOPS preflight and deploy (RT6_RULING_1: autologin must never be live on prod).
#
# deploy = anchors -> autologin empty -> ICB_ENVIRONMENT=prod present (else the restart would show prod a TEST bar)
# -> served-bytes baseline -> PyYAML present -> backup (ops/lib/icb_backup.sh, checked: alembic_version,
# trailer_groups, trailer_types, calculations) -> fetch (tags) + tag and range guards -> the repo's own
# deploy/prod/icb-deploy.sh (dry run, then --yes) -> post-deploy asserts: the schema (insulation_rule), the families
# untouched, no rule set yet, the three statics, the SPA rebuilt, and the THREE doors: /health/version =
# {"version":"v1.61.0","environment":"prod"}, no TEST banner, every probe_paths.txt path its listed status.
# Deliberately no bare `set -e`.
set -u

MODE=${1:-}
case "$MODE" in preflight|verify|env|deploy) ;; *)
  echo "usage: sudo bash $0 preflight|verify|env|deploy"; exit 1 ;; esac

BASE=/tmp/icb-release-v1.61.0
REPO=/opt/icb-platform
SERVICE=icb-backend
ENV_FILE=/etc/icb/backend.env
ENV_KEY=ICB_ENVIRONMENT
ENV_VALUE=prod
ENV_KEEP=/var/backups/icb-rt6-2026-10
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
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT6 release $MODE · machine $(hostname -s) · db ? · head ?"; OUT=''; stop KIT "lib/icb_where.sh missing: re-stage"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'    # the identity read only; unset before anything else
icb_where "release v1.61.0 $MODE" "$REPO" "$URL"
unset PGOPTIONS
OUT_TMP=$OUT; OUT=''
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -n "$URL" ] || stop KIT "DATABASE_URL not found in $ENV_FILE"
for v in PREV PREV_TAG TARGET BRANCH TAG TAG_OBJ ALEMBIC_BEFORE ALEMBIC_AFTER MIGRATION CHANGED_COUNT CHANGED_SHA \
         STATIC_1 STATIC_2 STATIC_3 SPA_MARK N_PROBES PYYAML_VERSION DEPLOY_SH_SHA WORKERS \
         EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
# preflight / verify / env run over the CURRENT code (v1.60.2) or, after the deploy, the target
EXPECT_HEADS="$PREV $TARGET"
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/lib/icb_backup.sh" || stop KIT "lib/icb_backup.sh missing: re-stage"
OUT=$OUT_TMP
[ -e "$OUT" ] && { OUT=''; stop KIT "$OUT_TMP already exists (two runs in one second?): run again"; }
mkdir -p "$OUT" || { OUT=''; stop KIT "cannot create $OUT_TMP"; }
exec > >(tee -a "$OUT/run.log") 2>&1
echo "(the line above, as run: machine $WHERE_MACHINE, db $WHERE_DB @ $WHERE_DBHOST, head $WHERE_HEAD, mode $MODE)"
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
STATICS="$STATIC_1|$STATIC_2|$STATIC_3"
spa_bundle() { grep -o 'assets/index-[A-Za-z0-9_-]*\.js' "$REPO/frontend/dist/index.html" 2>/dev/null | head -n1; }
spa_report() { # "spa_name spa_disk spa_local spa_lan"
  local b; b=$(spa_bundle)
  echo "${b:-none} $( [ -n "$b" ] && sha256sum "$REPO/frontend/dist/$b" | cut -d' ' -f1 || echo none)" \
       "$( [ -n "$b" ] && sha_url "$LOCAL/mes-app/$b" || echo none) $( [ -n "$b" ] && sha_url "$LAN/mes-app/$b" || echo none)"
}
spa_has_mark() { # $1 door: does the SPA bundle that door serves carry the Accept refusal's sentence?
  local b; b=$(spa_bundle); [ -n "$b" ] || { echo none; return 0; }
  curl -ksS --max-time 20 "$1/mes-app/$b" | grep -c "$SPA_MARK" || true
}
tmpl_v() { grep -o "$2?v=[0-9]*" "$REPO/backend/app/templates/$1" 2>/dev/null | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
static_checks() { # $1 = before | after: each page loads that ?v=, and both doors serve that blob under it
  local IFS='|' s; for s in $STATICS; do
    IFS=' ' read -r tmpl path vb shab va shaa <<< "$s"
    local f=${path##*/} v=$va sha=$shaa; [ "$1" = before ] && { v=$vb; sha=$shab; }
    check "V_${f%.*}" "$(tmpl_v "$tmpl" "$f")" "$v"
    check "LOCAL_${f%.*}" "$(sha_url "$LOCAL/static/$path?v=$v")" "$sha"
    check "LAN_${f%.*}" "$(sha_url "$LAN/static/$path?v=$v")" "$sha"
  done
}
health_version() { curl -ks --max-time 20 "$1/health/version" 2>/dev/null | tr -d ' \n'; }
version_of() { health_version "$1" | sed -n 's/.*"version":"\([^"]*\)".*/\1/p' | head -n1; }
environment_of() { health_version "$1" | sed -n 's/.*"environment":"\([^"]*\)".*/\1/p' | head -n1; }
banner_on() { # $1 door: how many TEST SERVER bars / [TEST] titles the login page carries (prod: 0)
  local page; page=$(curl -ks --max-time 20 "$1/login" 2>/dev/null)
  echo "$(grep -c 'icb-test-banner' <<<"$page" || true)/$(grep -c '<title>\[TEST\]' <<<"$page" || true)"
}
noauth_report() {
  local door=$1 bad="" want path got
  while read -r want path; do
    case "$want" in ''|\#*) continue ;; esac
    got=$(curl -ks -o /dev/null --max-time 20 -H 'Accept: application/json' -w '%{http_code}' "$door$path" 2>/dev/null)
    [ "$got" = "$want" ] || bad="$bad $path=${got:-000}/$want"
  done < "$BASE/probe_paths.txt"
  echo "${bad:-all $N_PROBES as expected}" | sed 's/^ //'
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
# the env key as the FILE carries it: "absent" | "ICB_ENVIRONMENT=<value>" (the value is not secret) | "duplicate"
env_line() {
  local n; n=$(grep -cE "^[[:space:]]*(export[[:space:]]+)?$ENV_KEY=" "$ENV_FILE" || true)
  [ "$n" = 0 ] && { echo absent; return 0; }
  [ "$n" = 1 ] || { echo "duplicate ($n lines)"; return 0; }
  grep -E "^[[:space:]]*(export[[:space:]]+)?$ENV_KEY=" "$ENV_FILE" | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/[[:space:]]+$//'
}
autologin_empty() { [ -z "${MES_DEMO_AUTOLOGIN_USER:-}" ] && echo yes || echo no; }   # the VALUE is never printed
# 0053: the one column, as the migration writes it
COL_SQL="select coalesce(string_agg(column_name || ':' || data_type || ':' || is_nullable || ':' || coalesce(column_default, 'NULL'),
         ' ' order by column_name), 'none') from information_schema.columns where table_schema = 'icb_costings'
         and table_name = 'trailer_groups' and column_name = 'insulation_rule'"
COL_WANT="insulation_rule:text:YES:NULL"
RULES_SQL="select count(*) from icb_costings.trailer_groups where insulation_rule is not null and btrim(insulation_rule) <> ''"
FAMILIES_SQL="select md5(coalesce(string_agg(id || ':' || name || ':' || coalesce(colour, '-') || ':' || sort_order || ':' ||
              coalesce(report_template_id::text, '-') || ':' || coalesce(rule_note, '-'), ',' order by id), '')) from icb_costings.trailer_groups"

FAILS=0
check() { # $1 name, $2 got, $3 want (exact) | $3 '~regex'
  local name=$1 got=$2 want=$3 okk=0
  if [ "${want:0:1}" = "~" ]; then [[ "$got" =~ ${want:1} ]] && okk=1; else [ "$got" = "$want" ] && okk=1; fi
  if [ $okk = 1 ]; then echo "   PASS $name = $got"
  else echo "   FAIL $name = '$got' (want $want)"; FAILS=$((FAILS + 1)); [ "$MODE" = deploy ] && stop "$name" "got '$got', want $want"; fi
  return 0
}
post_checks() { # $1 journal --since, $2 epoch the code moved (deploy) or empty, $3 families md5 before (deploy) or empty
  say "code + tag + schema (0053: trailer_groups.insulation_rule TEXT NULL)"
  check HEAD "$(gitr rev-parse HEAD)" "$TARGET"
  check TAG_LOCAL "$(tag_local)" "$TAG_OBJ"
  check DESCRIBE "$(describe)" "$TAG"
  check ALEMBIC "$(q "select string_agg(version_num, ',') from alembic_version")" "$ALEMBIC_AFTER"
  check COLUMN "$(q "$COL_SQL")" "$COL_WANT"
  [ -n "${3:-}" ] && check FAMILIES_UNCHANGED "$(q "$FAMILIES_SQL")" "$3"
  echo "   families with an insulation rule: $(q "$RULES_SQL") (0 right after the deploy; rt6_rules.sh sets the two)"
  say "the environment key (prod is POSITIVELY prod: the TEST banner is off only for exactly 'prod')"
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
  check TOOL_IMPORT "$(cd "$REPO/backend" && "$PY" -c 'from app.services.insulation_rules import PANELS; from app.services.rule_guard import refuse_saved; from app.env_banner import is_prod; print(len(PANELS), is_prod())' 2>&1 | tail -n1)" "6 True"
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
  say "served bytes: each page loads its new ?v= and both doors serve the target blob; the SPA rebuilt"
  static_checks after
  set -- $(spa_report)
  check SPA_LOCAL "$3" "$2"
  check SPA_LAN "$4" "$2"
  check SPA_HAS_REFUSAL_LOCAL "$(spa_has_mark "$LOCAL")" '~^[1-9]'
  check SPA_HAS_REFUSAL_LAN "$(spa_has_mark "$LAN")" '~^[1-9]'
}

# ==================================================================================================================
if [ "$MODE" = preflight ]; then
  say "anchors"
  check ALEMBIC "$ALEMBIC_NOW" "$ALEMBIC_BEFORE"
  check HEAD "$HEAD" "$PREV"
  check TRACKED_CLEAN "$(gitr status --porcelain --untracked-files=no | wc -l)" 0
  check COLUMN_NOT_YET "$(q "$COL_SQL")" none
  say "autologin: MES_DEMO_AUTOLOGIN_USER must be EMPTY on prod (only 'empty: yes/no' is ever printed)"
  echo "   MES_DEMO_AUTOLOGIN_USER empty: $(autologin_empty)"
  check AUTOLOGIN_EMPTY "$(autologin_empty)" yes
  say "the environment key in $ENV_FILE today (key name and value; the value is not secret)"
  echo "   $(env_line) (absent before the 'env' step; ICB_ENVIRONMENT=prod after it)"
  check ENV_KEY_MERGEABLE "$(env_line)" "~^(absent|$ENV_KEY=$ENV_VALUE)$"
  say "served bytes (the $PREV_TAG scripts are what prod serves today)"
  static_checks before
  set -- $(spa_report)
  check SPA_DISK_NAME "$1" '~^assets/index-'
  check SPA_LOCAL "$3" "$2"; check SPA_LAN "$4" "$2"
  check SPA_HAS_REFUSAL_NOT_YET "$(spa_has_mark "$LOCAL")" 0
  echo "   SPA bundle $1 sha256 $2 (frontend/ changed in the range: the deploy rebuilds it)"
  check HEALTH "$(code_url "$LOCAL/health")" 200
  say "today, on the three doors: $PREV_TAG answers, and RT4's no-session gate holds"
  for d in LOCAL LAN CF; do check "VERSION_$d" "$(version_of "${!d}")" "$PREV_TAG"; done
  check NOAUTH_LOCAL "$(noauth_report "$LOCAL")" "all $N_PROBES as expected"
  check NOAUTH_LAN "$(noauth_report "$LAN")" "all $N_PROBES as expected"
  check NOAUTH_CF "$(noauth_report "$CF")" "all $N_PROBES as expected"
  say "PyYAML (installed by v1.59.0; this release installs nothing)"
  check PYYAML "$(yaml_version)" "$PYYAML_VERSION"
  say "the SPA build tooling (icb-deploy.sh runs npm run build as icb)"
  check NPM "$(sudo -u icb bash -lc 'command -v npm >/dev/null && echo present || echo missing' 2>/dev/null)" present
  check NODE_MODULES "$( [ -d "$REPO/frontend/node_modules" ] && echo present || echo missing)" present
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
if [ "$MODE" = env ]; then
  # RT6_RULING_1: append ICB_ENVIRONMENT=prod by MERGE — never overwrite, never touch any other line (the file is
  # Marnus-owned; its duplicate keys are not RT6's). Read back the key's name and value. A copy of the file as it was
  # (root 600, same box) is kept first. The running service reads it at its NEXT start (the deploy's restart).
  say "the environment key, before"
  BEFORE=$(env_line); echo "   $BEFORE"
  if [ "$BEFORE" = "$ENV_KEY=$ENV_VALUE" ]; then
    ok "already set — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE (env: already $ENV_KEY=$ENV_VALUE) — tell the CA: $OUT"; exit 0
  fi
  [ "$BEFORE" = absent ] || stop ENV "$ENV_KEY is '$BEFORE' in $ENV_FILE — not overwritten. Tell the CA"
  mkdir -p "$ENV_KEEP" && chmod 700 "$ENV_KEEP" || stop ENV "cannot create $ENV_KEEP"
  KEEPF="$ENV_KEEP/backend.env.pre-v1.61.0.$TS"
  cp -p "$ENV_FILE" "$KEEPF" && chmod 600 "$KEEPF" || stop ENV "could not keep a copy of $ENV_FILE — nothing changed"
  PERM_BEFORE=$(stat -c '%U:%G %a' "$ENV_FILE"); LINES_BEFORE=$(wc -l < "$ENV_FILE")
  SHA_BEFORE_REST=$(sha256sum < "$ENV_FILE" | cut -d' ' -f1)
  # a file without a final newline would glue the key onto its last line
  [ -z "$(tail -c1 "$ENV_FILE")" ] || printf '\n' >> "$ENV_FILE"
  printf '%s=%s\n' "$ENV_KEY" "$ENV_VALUE" >> "$ENV_FILE" || stop ENV "append failed — restore from $KEEPF"
  say "read back"
  AFTER=$(env_line); echo "   $AFTER"
  [ "$AFTER" = "$ENV_KEY=$ENV_VALUE" ] || stop ENV "read back '$AFTER' — restore from $KEEPF and tell the CA"
  [ "$(stat -c '%U:%G %a' "$ENV_FILE")" = "$PERM_BEFORE" ] || stop ENV "owner/mode moved from $PERM_BEFORE — tell the CA"
  [ "$(head -c "$(stat -c %s "$KEEPF")" "$ENV_FILE" | sha256sum | cut -d' ' -f1)" = "$SHA_BEFORE_REST" ] \
    || stop ENV "the lines that were there changed — restore from $KEEPF and tell the CA"
  ok "$ENV_FILE: $LINES_BEFORE -> $(wc -l < "$ENV_FILE") lines; every earlier line byte-identical; $PERM_BEFORE kept; copy $KEEPF"
  echo "   names now: $(sed -n 's/^[[:space:]]*\(export[[:space:]]\+\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)=.*/\2/p' "$ENV_FILE" | grep -c . ) key lines (names only, none printed but the new one)"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (env: $AFTER, read back; the service reads it at the deploy's restart) — tell the CA: $OUT"; exit 0
fi

# ==================================================================================================================
# deploy
say "1. anchors"
RESUME=0
if [ "$HEAD" = "$PREV" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC_BEFORE" ]; then
  ok "fresh: code ${PREV:0:7}, alembic $ALEMBIC_BEFORE"
elif [ "$HEAD" = "$TARGET" ] && [ "$ALEMBIC_NOW" = "$ALEMBIC_AFTER" ] && grep -qx "completed $TARGET" "$STATE_FILE" 2>/dev/null; then
  echo "   !!   ALREADY DEPLOYED: code ${TARGET:0:7}, alembic $ALEMBIC_AFTER, completion on record. Nothing is changed;"
  echo "   !!   running the post-deploy asserts against the current service start instead."
  post_checks "$(service_since)" "" ""
  chmod -R a+rX "$OUT"; echo; echo "######## ALREADY DEPLOYED, all asserts PASS — tell the CA: $OUT"; exit 0
elif [ "$HEAD" = "$TARGET" ] && { [ "$ALEMBIC_NOW" = "$ALEMBIC_BEFORE" ] || [ "$ALEMBIC_NOW" = "$ALEMBIC_AFTER" ]; }; then
  RESUME=1; echo "   !!   RESUME: code is already at ${TARGET:0:7} (alembic $ALEMBIC_NOW) — a previous run stopped part way."
else
  stop ANCHORS "code ${HEAD:0:7} / alembic $ALEMBIC_NOW is neither the start (${PREV:0:7}/$ALEMBIC_BEFORE) nor the target"
fi
[ "$(gitr status --porcelain --untracked-files=no | wc -l)" = 0 ] || stop ANCHORS "prod has modified tracked files"
echo "$PREV" > "$OUT/rollback-anchor.txt"; ok "rollback anchor ${PREV:0:7} -> $OUT/rollback-anchor.txt"
FAM_BEFORE=$(q "$FAMILIES_SQL") || stop DB "cannot read the families"
ok "families (id:name:colour:order:template:note) md5 $FAM_BEFORE — the migration and the restart must not move them"

say "2. autologin and the environment key (before anything moves)"
[ "$(autologin_empty)" = yes ] || stop AUTOLOGIN "MES_DEMO_AUTOLOGIN_USER is NOT empty on prod (value not printed). Do not deploy — tell the BA"
ok "MES_DEMO_AUTOLOGIN_USER empty: yes"
[ "$(env_line)" = "$ENV_KEY=$ENV_VALUE" ] || stop ENV "$ENV_FILE has '$(env_line)': run 'release.sh env' first (else prod restarts showing a TEST banner)"
ok "$(env_line) (read at the restart below)"

say "3. served-bytes baseline"
if [ "$RESUME" = 0 ]; then
  BEFORE_FAILS=$FAILS; MODE=verify static_checks before; MODE=deploy
  [ "$FAILS" = "$BEFORE_FAILS" ] || stop BYTES_BEFORE "a page or a door does not serve the $PREV_TAG script (see the FAIL lines above)"
fi
set -- $(spa_report)
B_SPA_NAME=$1; B_SPA=$2
[ "$3" = "$2" ] && [ "$4" = "$2" ] || stop BYTES_BEFORE "SPA bundle $1 served bytes differ from disk"
ok "SPA $B_SPA_NAME ${B_SPA:0:16} (the deploy rebuilds it)"

say "4. PyYAML $PYYAML_VERSION present (nothing is installed by this release)"
YV=$(yaml_version); [ "$YV" = "$PYYAML_VERSION" ] || stop PYYAML "import yaml -> $YV. Do not deploy; tell the CA"
ok "present ($YV)"

say "5. backup — checked (ops/lib/icb_backup.sh): the rollback for 0053, before the code, the schema and the data move"
BK="$BACKUP_DIR/icb_platform_pre-v1.61.0_$TS.dump"
[ -d "$BACKUP_DIR" ] || stop BACKUP "$BACKUP_DIR missing"
icb_backup "$BK" custom "$URL" icb_costings.alembic_version icb_costings.trailer_groups icb_costings.trailer_types \
  icb_costings.calculations icb_costings.bill_of_materials || stop BACKUP "$ICB_BACKUP_WHY"
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
G_MIG=$(gitr diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$G_MIG" = "$MIGRATION" ] || stop GUARD "new migrations are '$G_MIG', expected exactly $MIGRATION"
G_REQ=$(gitr diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' 'frontend/package.json' 'frontend/package-lock.json' | wc -l)
[ "$G_REQ" = 0 ] || stop GUARD "a dependency manifest changed in the range: this kit installs nothing"
G_FE=$(gitr diff --name-only "$PREV" "$TARGET" -- frontend | wc -l)
[ "$G_FE" -gt 0 ] || stop GUARD "frontend/ is unchanged: this kit expects the SPA rebuild (the Accept refusal's sentence)"
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

say "8. deploy (fast-forward, its own backup, alembic upgrade head, npm run build, restart, health, completion record)"
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
S_SPA_NAME=$(spa_bundle)
[ "$RESUME" = 1 ] || [ "$S_SPA_NAME" != "$B_SPA_NAME" ] || stop SPA_REBUILT "the SPA bundle is still $B_SPA_NAME: the build did not run"

say "9. post-deploy asserts, the three doors included (waiting 20 s for all workers to log startup)"
sleep 20
post_checks "@$T0" "$T0" "$FAM_BEFORE"
TB=$(tb_since "@$T0")

cat > "$OUT/OUTCOME.txt" <<EOF
deployed      ${PREV:0:7} -> ${TARGET:0:7} ($TARGET)
tag           $TAG = $TAG_OBJ (local = origin, peels to the target); git describe = $(describe)
alembic       $ALEMBIC_BEFORE -> $(q "select string_agg(version_num, ',') from alembic_version") ($(basename "$MIGRATION")); column $(q "$COL_SQL")
families      md5 $FAM_BEFORE before = $(q "$FAMILIES_SQL") after; with an insulation rule: $(q "$RULES_SQL") (rt6_rules.sh sets the two)
environment   $(env_line) in $ENV_FILE; autologin empty: $(autologin_empty)
backup        $BK  $(stat -c %s "$BK") bytes  sha256 $BK_SHA (checked: alembic_version, trailer_groups, trailer_types, calculations, bill_of_materials)
restart       $AET_BEFORE -> $AET_AFTER (pid $PID_BEFORE -> $PID_AFTER), after the code moved: $(restart_after_code "$T0")
workers       $(workers_since "@$T0") started, $(bootfail_since "@$T0") bootstrap failed, $TB tracebacks
health        $(code_url "$LOCAL/health")
version       local $(health_version "$LOCAL") · lan $(health_version "$LAN") · cloudflare $(health_version "$CF")
test banner   local $(banner_on "$LOCAL") · lan $(banner_on "$LAN") · cloudflare $(banner_on "$CF") (bars/[TEST] titles; prod 0/0)
no session    local: $(noauth_report "$LOCAL") · lan: $(noauth_report "$LAN") · cloudflare: $(noauth_report "$CF")
static        $(IFS='|'; for s in $STATICS; do IFS=' ' read -r t p vb sb va sa <<< "$s"; printf '%s ?v=%s %s  ' "${p##*/}" "$va" "${sa:0:16}"; done)(local = lan = the target blobs)
spa           $B_SPA_NAME -> $S_SPA_NAME (rebuilt; local = lan = disk; carries the Accept refusal)
finished      $(date -Is)
EOF
chmod -R a+rX "$OUT"
echo; cat "$OUT/OUTCOME.txt"; echo
echo "######## DEPLOYED — tell the CA: $OUT  (next: rt6_rules.sh dryrun)"
