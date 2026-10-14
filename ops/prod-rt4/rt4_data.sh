#!/usr/bin/env bash
# ── RETIRED (RT6, 6 Oct 2026 — RT6_RULING_1 Q7) ─────────────────────────────────────────────────────────────────────
# This kit's reviewed plan is applied on prod, and later releases and data steps build on what it wrote. It no longer
# runs: its apply backed up with a bare `pg_dump … | gzip` (gzip's exit status only — a failed dump passed), and its
# revert would now undo work done since. The file stays as the record its runbook cites. A new data step uses
# ops/lib/icb_backup.sh (checked backup) and ops/lib/icb_where.sh (the safe-paste first line).
echo "RETIRED (RT6, 2026-10-06): $(basename "$0") no longer runs — see its header. Nothing was done." >&2; exit 3
# RT4 — Manifest S on PROD (RT4_RULING_1 Q2 + Q3), in the v1.60.1 window AFTER the deploy (window step 4):
#   S  docs/audit/rt4_2026-10/manifest_s/manifest_s.yaml
#        46 line moves — bom_section_id + bom_section TOGETHER, each guarded on its exact current id AND string:
#          7 MANNI DF lines whose id disagreed with their string (-> the section the string names),
#          deleted id 41's 39 lines off 83/84/85 (-> 26 / 15 / 21; id 41 stays deleted);
#        + deleted id 41's own draft re-keyed by the A2 rule (2 keys; its snapshot is never touched);
#        + expect_unused_after [83, 84, 85]: if any OTHER line or draft still names one of them, the run STOPS.
#   tool: backend/tools/audit_pricing_corrections.py (the correction tool, extended — field: section, drafts:).
# S goes only over the v1.60.1 code (the tool uses app.services.sections, new in v1.60.1). The operator runs, on the
# VM, ONE step at a time and sends the CA the output folder name before the next:
#
#     sudo bash /tmp/icb-rt4-data/rt4_data.sh dryrun                read only
#     sudo bash /tmp/icb-rt4-data/rt4_data.sh apply
#     sudo bash /tmp/icb-rt4-data/rt4_data.sh revert /var/backups/icb-rt4-2026-10/<journal>.json
#
# What each step touches on prod:
#   dryrun  the tool's dry-run inside a READ ONLY transaction — writes nothing
#   apply   the dry-run again (must be exactly the reviewed plan: 46 lines + 2 draft keys), a data-only pg_dump of
#           what the tool writes (bill_of_materials + configurator_drafts), then the tool's apply: ONE transaction,
#           every guard checked before any write (one mismatch aborts everything); journal + backup + provenance
#           kept in /var/backups/icb-rt4-2026-10/; a second dry-run must find nothing left to apply
#   revert  puts every journaled line and the draft back (the tool refuses if one moved since)
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy. The tool and the manifest are
# staged by the CA's mkstage_data.sh at /tmp/icb-rt4-data/stage (committed bytes, LF); SHA256SUMS at the kit root
# covers this script, expected.env and every staged file.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt4-data
STAGE=$BASE/stage
KEEP=/var/backups/icb-rt4-2026-10
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | revert <journal.json>"
case "$MODE" in
  dryrun|apply) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  revert) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-S-$TS

[ -e "$OUT" ] && { echo "STOP: $OUT already exists (two runs in one second?): run again"; exit 1; }
mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEAD EXPECT_ALEMBIC S_TODO S_DRAFTS S_SHA STAGED_FROM; do
  [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"
done
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
q() { PGOPTIONS='-c default_transaction_read_only=on' psql "$URL" -XAtq -v ON_ERROR_STOP=1 -c "$1" 2>&1; }
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/opt/icb-platform/backend

DBNAME=$(q "select current_database()") || stop DB "cannot reach the database: $DBNAME"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(q "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE  $(date -Is)"
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}; S goes only over the v1.60.1 release ${EXPECT_HEAD:0:7} (deploy first)"
$PY -c "import yaml, psycopg, app.formula_engine, app.db_guard, app.services.sections" \
  || stop IMPORT "PyYAML, psycopg or prod's app code (app.services.sections, new in v1.60.1) does not import"

MS="$STAGE/docs/audit/rt4_2026-10/manifest_s/manifest_s.yaml"
TP="$STAGE/backend/tools/audit_pricing_corrections.py"
plan_line()  { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
draft_line() { grep -E '^drafts: [0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
dry() { $PY "$TP" --target prod --manifest "$MS" > "$1" 2>&1; }   # exit 2 = a guard or the unused check refused

[ "$(sha256sum "$MS" | cut -d' ' -f1)" = "$S_SHA" ] || stop KIT "manifest S is not the reviewed bytes"

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  say "dry-run S (READ ONLY)"
  dry "$OUT/dryrun.txt"; rc=$?
  cat "$OUT/dryrun.txt"
  if [ $rc != 0 ]; then
    grep -q '^STOP — after this manifest' "$OUT/dryrun.txt" \
      && stop UNUSED "another line or draft still names 83/84/85 (listed above) — RT4_RULING_1 Q3: STOP and report; nothing written"
    stop GUARD "the dry-run refused (exit $rc): a guard mismatch means prod moved; nothing written"
  fi
  P=$(plan_line "$OUT/dryrun.txt"); D=$(draft_line "$OUT/dryrun.txt")
  if [ "$P" = "0 to apply, $S_TODO already applied." ] && [ "$D" = "drafts: 0 to apply, $S_DRAFTS already applied." ]; then
    say "Manifest S is ALREADY on prod ($P; $D) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE S: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$S_TODO to apply, 0 already applied." ] && [ "$D" = "drafts: $S_DRAFTS to apply, 0 already applied." ] \
    || stop PLAN "the plan is '$P' / '$D', the reviewed plan is '$S_TODO to apply, 0 already applied.' / 'drafts: $S_DRAFTS to apply, 0 already applied.'"
  grep -q 'expect_unused_after \[83, 84, 85\]: no other line or draft names them' "$OUT/dryrun.txt" \
    || stop UNUSED "the dry-run did not confirm that 83/84/85 end up unused"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun S: $P; $D) — tell the CA: $OUT"; exit 0
  fi

  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_S_$TS.sql.gz"
  say "pre-apply backup (data only): bill_of_materials + configurator_drafts"
  pg_dump "$URL" --data-only -t icb_costings.bill_of_materials -t icb_costings.configurator_drafts | gzip > "$BK" \
    || stop BACKUP "pg_dump failed — nothing applied"
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply S — one transaction"
  $PY "$TP" --target prod --manifest "$MS" --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/pricing_corrections_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_S_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "manifest     S  sha256 $S_SHA"
    echo "tool         sha256 $(sha256sum "$TP" | cut -d' ' -f1)"
    echo "staged_from  $STAGED_FROM"
    echo "prod_code    $HEAD"
    echo "alembic      $ALEMBIC"
    echo "backup       $(basename "$BK")"
    echo "run_folder   $OUT"
  } > "$KEEP/${JN%.json}.provenance.txt" || stop JOURNAL "provenance note not written — tell the CA"
  echo "   ok   journal $KEEP/$JN  sha256 $(sha256sum "$KEEP/$JN" | cut -d' ' -f1)"

  say "second dry-run (must find nothing left to apply, and 83/84/85 unused)"
  dry "$OUT/after.txt"; rc=$?
  cat "$OUT/after.txt"
  [ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "0 to apply, $S_TODO already applied." ] \
    && [ "$(draft_line "$OUT/after.txt")" = "drafts: 0 to apply, $S_DRAFTS already applied." ] \
    && grep -q 'they are unused now\.' "$OUT/after.txt" \
    || stop AFTER "the second dry-run still finds work, or 83/84/85 are not unused — tell the CA"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (apply S) — journal $KEEP/$JN — tell the CA: $OUT"; exit 0
fi

# revert
JR=$ARG
[ -f "$JR" ] || stop USAGE "no such journal: $JR (see $KEEP)"
KIND=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1])).get("manifest_sha256", "?"))' "$JR" 2>/dev/null) \
  || stop USAGE "not a tool journal: $JR"
[ "$KIND" = "$S_SHA" ] || stop USAGE "the journal is not Manifest S's (manifest sha ${KIND:0:12})"
say "revert Manifest S from $(basename "$JR")"
$PY "$TP" --target prod --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused (exit $rc): nothing changed"
cp "$OUT"/pricing_corrections_revert_prod_*.json "$KEEP/" 2>/dev/null || true
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert S) — tell the CA: $OUT"
