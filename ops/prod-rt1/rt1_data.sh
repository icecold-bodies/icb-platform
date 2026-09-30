#!/usr/bin/env bash
# RT1 — the two data manifests on PROD, one paste each, in the order code -> A -> B (RT1 ruling 3):
#   A  docs/audit/srd_rear_frame_2026-09/manifest_a.yaml  REAR FRAME & FLOOR PLATE not costed on a single rear door
#   B  docs/audit/srd_rear_frame_2026-09/manifest_b.yaml  MEAT HANGER SRD PU lines to the F1 shape + own R4 100;
#                                                         5585 / 2415 / 3576 own R4 100
# The operator runs, on the VM, ONE step at a time and sends the CA the output folder name before the next:
#
#     sudo bash /tmp/icb-rt1-data/rt1_data.sh dryrun A      read only
#     sudo bash /tmp/icb-rt1-data/rt1_data.sh apply A       only after the code release is accepted (window step 2c)
#     sudo bash /tmp/icb-rt1-data/rt1_data.sh dryrun B      read only
#     sudo bash /tmp/icb-rt1-data/rt1_data.sh apply B       only after A is on prod (asserted)
#     sudo bash /tmp/icb-rt1-data/rt1_data.sh revert /var/backups/icb-rt1-2026-09/<journal>.json   (B first, then A)
#
# What each step touches on prod:
#   dryrun  the tool's dry-run inside a READ ONLY transaction — writes nothing
#   apply   the dry-run again (must be exactly the reviewed plan), a data-only pg_dump of bill_of_materials +
#           bom_override_history, then the tool's apply: ONE transaction, every guard checked before any write
#           (one mismatch aborts everything); journal + backup + provenance kept in /var/backups/icb-rt1-2026-09/;
#           a second dry-run must find nothing left to apply
#   revert  puts every journaled line back column for column (the tool refuses if a line moved since)
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy. The tool and both
# manifests are staged by the CA's mkstage_data.sh at /tmp/icb-rt1-data/stage (committed bytes, LF); SHA256SUMS at the kit root covers this script, expected.env and every staged file.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt1-data
STAGE=$BASE/stage
KEEP=/var/backups/icb-rt1-2026-09
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
case "$MODE" in
  dryrun|apply) case "$ARG" in A|B) ;; *) echo "usage: sudo bash $0 dryrun|apply A|B  |  revert <journal.json>"; exit 1 ;; esac ;;
  revert) [ -n "$ARG" ] || { echo "usage: sudo bash $0 revert <journal.json>"; exit 1; } ;;
  *) echo "usage: sudo bash $0 dryrun|apply A|B  |  revert <journal.json>"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-$( [ "$MODE" = revert ] && echo j || echo "$ARG" )-$TS

mkdir -p "$OUT" || { echo "STOP: cannot create $OUT"; exit 1; }
chmod 700 "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
stop() { echo; echo "######## STOP [$1]: $2"; echo "######## tell the CA: $OUT"; chmod -R a+rX "$OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEAD EXPECT_ALEMBIC A_TODO B_TODO A_SHA B_SHA STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
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
# The rules are safe in the Trailer Designer only from v1.59.1 (it keeps out-of-branch conditions):
# the data goes on after the code release, never before.
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}, the data goes on only over the v1.59.2 release ${EXPECT_HEAD:0:7}"
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE $ARG  $(date -Is)"
$PY -c "import yaml, app.formula_engine, app.db_guard" || stop IMPORT "PyYAML or prod's app code does not import"

manifest() { echo "$STAGE/docs/audit/srd_rear_frame_2026-09/manifest_$(echo "$1" | tr AB ab).yaml"; }
tool() { $PY "$STAGE/backend/tools/audit_pricing_corrections.py" --target prod "$@"; }
plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
dry() { # $1 = A|B, $2 = output file. Exit 2 = a guard mismatch (prod is not where the manifest says)
  tool --manifest "$(manifest "$1")" > "$2" 2>&1
}
todo_of() { eval "echo \${${1}_TODO}"; }

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  X=$ARG; N=$(todo_of "$X")
  [ "$X" = B ] && [ "$B_TODO" = 0 ] && stop PLAN "Manifest B is not part of this release (RT1_RULING_1): nothing staged for B"
  [ "$(sha256sum "$(manifest "$X")" | cut -d' ' -f1)" = "$(eval "echo \${${X}_SHA}")" ] || stop KIT "manifest $X is not the reviewed bytes"
  if [ "$X" = B ] && [ "$MODE" = apply ]; then
    say "order: Manifest A must already be on prod"
    dry A "$OUT/order_A.txt"; rc=$?
    [ $rc = 0 ] && [ "$(plan_line "$OUT/order_A.txt")" = "0 to apply, $A_TODO already applied." ] \
      || { cat "$OUT/order_A.txt"; stop ORDER "Manifest A is not (fully) on prod — apply A first"; }
    echo "   ok   A: $(plan_line "$OUT/order_A.txt")"
  fi
  say "dry-run $X (READ ONLY)"
  dry "$X" "$OUT/dryrun.txt"; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop GUARD "the dry-run refused (exit $rc): a guard mismatch means prod moved; nothing written"
  P=$(plan_line "$OUT/dryrun.txt")
  if [ "$P" = "0 to apply, $N already applied." ]; then
    say "Manifest $X is ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE $X: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$N to apply, 0 already applied." ] || stop PLAN "the plan is '$P', the reviewed plan is '$N to apply, 0 already applied.'"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun $X: $P) — tell the CA: $OUT"; exit 0
  fi

  say "pre-apply backup (data only): bill_of_materials + bom_override_history"
  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_${X}_$TS.sql.gz"
  pg_dump "$URL" --data-only -t icb_costings.bill_of_materials -t icb_costings.bom_override_history | gzip > "$BK" \
    || stop BACKUP "pg_dump failed — nothing applied"
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply $X — one transaction"
  tool --manifest "$(manifest "$X")" --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  J=$(ls "$OUT"/pricing_corrections_journal_prod_*.json 2>/dev/null | head -n1)
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_${X}_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    echo "manifest     $X  sha256 $(sha256sum "$(manifest "$X")" | cut -d' ' -f1)"
    echo "tool         sha256 $(sha256sum "$STAGE/backend/tools/audit_pricing_corrections.py" | cut -d' ' -f1)"
    echo "staged_from  $STAGED_FROM"
    echo "prod_code    $HEAD"
    echo "alembic      $ALEMBIC"
    echo "backup       $(basename "$BK")"
    echo "run_folder   $OUT"
  } > "$KEEP/${JN%.json}.provenance.txt" || stop JOURNAL "provenance note not written — tell the CA"
  echo "   ok   journal $KEEP/$JN  sha256 $(sha256sum "$KEEP/$JN" | cut -d' ' -f1)"

  say "second dry-run (must find nothing left to apply)"
  dry "$X" "$OUT/after.txt"; rc=$?
  cat "$OUT/after.txt"
  [ $rc = 0 ] && [ "$(plan_line "$OUT/after.txt")" = "0 to apply, $N already applied." ] \
    || stop AFTER "the second dry-run still finds work — tell the CA"
  chmod -R a+rX "$OUT"
  echo; echo "######## DONE (apply $X) — journal $KEEP/$JN — tell the CA: $OUT"; exit 0
fi

# revert
JR=$ARG
[ -f "$JR" ] || stop USAGE "no such journal: $JR (see $KEEP)"
SHA_J=$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' "$JR" 2>/dev/null) || stop USAGE "not a tool journal: $JR"
if [ "$SHA_J" = "$A_SHA" ]; then
  if [ "$B_TODO" != 0 ]; then
    say "order: B must be reverted before A"
    dry B "$OUT/order_B.txt"
    [ "$(plan_line "$OUT/order_B.txt")" = "$B_TODO to apply, 0 already applied." ] \
      || { cat "$OUT/order_B.txt"; stop ORDER "Manifest B is still (partly) on prod — revert B first"; }
  fi
elif [ "$B_TODO" = 0 ] || [ "$SHA_J" != "$B_SHA" ]; then
  stop USAGE "the journal's manifest sha ${SHA_J:0:12} is neither A's nor B's"
fi
tool --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused (exit $rc): nothing changed"
cp "$OUT"/pricing_corrections_revert_prod_*.json "$KEEP/" 2>/dev/null || true
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert) — tell the CA: $OUT"
