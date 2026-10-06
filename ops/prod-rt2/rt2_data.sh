#!/usr/bin/env bash
# ── RETIRED (RT6, 6 Oct 2026 — RT6_RULING_1 Q7) ─────────────────────────────────────────────────────────────────────
# This kit's reviewed plan is applied on prod, and later releases and data steps build on what it wrote. It no longer
# runs: its apply backed up with a bare `pg_dump … | gzip` (gzip's exit status only — a failed dump passed), and its
# revert would now undo work done since. The file stays as the record its runbook cites. A new data step uses
# ops/lib/icb_backup.sh (checked backup) and ops/lib/icb_where.sh (the safe-paste first line).
echo "RETIRED (RT6, 2026-10-06): $(basename "$0") no longer runs — see its header. Nothing was done." >&2; exit 3
# RT2 — the data manifests on PROD, one paste each, in the v1.59.3 window (dispatch Part 4; RT2_RULING_1 R6 + Part 3):
#   P  docs/audit/rt2_2026-10/manifest_p/manifest_p.yaml  ONE shared PU price: own-price removals + conversions to
#                                                         Burt's row shape (tools/audit_pricing_corrections.py)
#   D  ops/prod-rt2/rt2_defaults.py                       the four 4G body defaults (MEAT HANGER LARGE, MEAT HANGER
#                                                         SMALL-MEDIUM, EXPLOSIVE 4.9 AND UP, RHINORANGE TRAILER)
# Both go only over the v1.59.3 code (alembic 0050), and D only AFTER P (before P, own 4G prices would take the 4G
# factor twice). The operator runs, on the VM, ONE step at a time and sends the CA the output folder name before
# the next:
#
#     sudo bash /tmp/icb-rt2-data/rt2_data.sh dryrun P      read only
#     sudo bash /tmp/icb-rt2-data/rt2_data.sh apply P
#     sudo bash /tmp/icb-rt2-data/rt2_data.sh dryrun D      read only — refuses until P is fully on
#     sudo bash /tmp/icb-rt2-data/rt2_data.sh apply D
#     sudo bash /tmp/icb-rt2-data/rt2_data.sh revert /var/backups/icb-rt2-2026-10/<journal>.json   (D before P)
#
# What each step touches on prod:
#   dryrun  the tool's dry-run inside a READ ONLY transaction — writes nothing
#   apply   the dry-run again (must be exactly the reviewed plan), a data-only pg_dump of what the tool writes
#           (P: bill_of_materials + bom_override_history; D: trailer_types), then the tool's apply: ONE transaction,
#           every guard checked before any write (one mismatch aborts everything); journal + backup + provenance
#           kept in /var/backups/icb-rt2-2026-10/; a second dry-run must find nothing left to apply
#   revert  puts every journaled row back column for column (the tool refuses if a row moved since)
# Nothing under /opt/icb-platform changes; no service is touched; nothing is a deploy. The tools and the manifest are
# staged by the CA's mkstage_data.sh at /tmp/icb-rt2-data/stage (committed bytes, LF); SHA256SUMS at the kit root
# covers this script, expected.env and every staged file.
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt2-data
STAGE=$BASE/stage
KEEP=/var/backups/icb-rt2-2026-10
PY=/opt/icb-platform/.venv/bin/python
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun|apply P|D  |  revert <journal.json>"
case "$MODE" in
  dryrun|apply) case "$ARG" in P|D) ;; *) echo "$USAGE"; exit 1 ;; esac ;;
  revert) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=$BASE/out-$MODE-$( [ "$MODE" = revert ] && echo j || echo "$ARG" )-$TS

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
for v in EXPECT_HEAD EXPECT_ALEMBIC P_TODO D_TODO P_SHA D_SHA STAGED_FROM; do
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
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC (P and D go over v1.59.3 only)"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} mode=$MODE $ARG  $(date -Is)"
[ "$HEAD" = "$EXPECT_HEAD" ] || stop CODE "prod's code is ${HEAD:0:7}; P and D go only over the v1.59.3 release ${EXPECT_HEAD:0:7}"
$PY -c "import yaml, psycopg, app.formula_engine, app.db_guard" || stop IMPORT "PyYAML, psycopg or prod's app code does not import"

MP="$STAGE/docs/audit/rt2_2026-10/manifest_p/manifest_p.yaml"
TP="$STAGE/backend/tools/audit_pricing_corrections.py"
TD="$STAGE/ops/prod-rt2/rt2_defaults.py"
plan_line() { grep -E '^[0-9]+ to apply, [0-9]+ already applied\.$' "$1" | tail -n1; }
dry() { # $1 = P|D, $2 = output file. Exit 2 = a guard refused (prod is not where the manifest says)
  if [ "$1" = P ]; then $PY "$TP" --target prod --manifest "$MP" > "$2" 2>&1
  else $PY "$TD" --target prod > "$2" 2>&1; fi
}
todo_of() { [ "$1" = P ] && echo "$P_TODO" || echo "$D_TODO"; }
p_is_on() { # P fully on prod: its dry-run reads "0 to apply, P_TODO already applied."
  dry P "$OUT/order_P.txt" && [ "$(plan_line "$OUT/order_P.txt")" = "0 to apply, $P_TODO already applied." ]
}
d_is_off() { # none of D on prod: its dry-run reads "D_TODO to apply, 0 already applied." — or refuses on "P first"
  dry D "$OUT/order_D.txt"; local rc=$?
  { [ $rc = 0 ] && [ "$(plan_line "$OUT/order_D.txt")" = "$D_TODO to apply, 0 already applied." ]; } \
    || { [ $rc = 2 ] && grep -q 'P first' "$OUT/order_D.txt"; }
}

[ "$(sha256sum "$MP" | cut -d' ' -f1)" = "$P_SHA" ] || stop KIT "manifest P is not the reviewed bytes"
[ "$(sha256sum "$TD" | cut -d' ' -f1)" = "$D_SHA" ] || stop KIT "rt2_defaults.py (D) is not the reviewed bytes"

if [ "$MODE" = dryrun ] || [ "$MODE" = apply ]; then
  X=$ARG; N=$(todo_of "$X")
  if [ "$X" = D ]; then
    say "order: Manifest P must already be fully on prod"
    p_is_on || { cat "$OUT/order_P.txt"; stop ORDER "Manifest P is not (fully) on prod — apply P first (a 4G default over the own 4G prices would charge 4G twice)"; }
    echo "   ok   P: $(plan_line "$OUT/order_P.txt")"
  fi
  say "dry-run $X (READ ONLY)"
  dry "$X" "$OUT/dryrun.txt"; rc=$?
  cat "$OUT/dryrun.txt"
  [ $rc = 0 ] || stop GUARD "the dry-run refused (exit $rc): a guard mismatch means prod moved; nothing written"
  P=$(plan_line "$OUT/dryrun.txt")
  if [ "$X" = D ]; then
    grep -qx 'OTHERS_4G: 0 (every other body opens on 32D)' "$OUT/dryrun.txt" \
      || stop OTHERS "another body already opens on 4G (see OTHERS_4G above): the window's expected counts assume only D's four"
  fi
  if [ "$P" = "0 to apply, $N already applied." ]; then
    say "Manifest $X is ALREADY on prod ($P) — nothing to do"; chmod -R a+rX "$OUT"
    echo; echo "######## DONE ($MODE $X: already applied) — tell the CA: $OUT"; exit 0
  fi
  [ "$P" = "$N to apply, 0 already applied." ] || stop PLAN "the plan is '$P', the reviewed plan is '$N to apply, 0 already applied.'"
  if [ "$MODE" = dryrun ]; then
    chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun $X: $P) — tell the CA: $OUT"; exit 0
  fi

  mkdir -p "$KEEP" && chmod 700 "$KEEP" || stop BACKUP "cannot create $KEEP"
  BK="$KEEP/pre_apply_${X}_$TS.sql.gz"
  if [ "$X" = P ]; then
    say "pre-apply backup (data only): bill_of_materials + bom_override_history"
    pg_dump "$URL" --data-only -t icb_costings.bill_of_materials -t icb_costings.bom_override_history | gzip > "$BK" \
      || stop BACKUP "pg_dump failed — nothing applied"
  else
    say "pre-apply backup (data only): trailer_types"
    pg_dump "$URL" --data-only -t icb_costings.trailer_types | gzip > "$BK" || stop BACKUP "pg_dump failed — nothing applied"
  fi
  [ -s "$BK" ] && gzip -t "$BK" || stop BACKUP "$BK is empty or not gzip — nothing applied"
  echo "   ok   $BK $(stat -c %s "$BK") bytes sha256 $(sha256sum "$BK" | cut -d' ' -f1)"

  say "apply $X — one transaction"
  if [ "$X" = P ]; then $PY "$TP" --target prod --manifest "$MP" --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?
  else $PY "$TD" --target prod --apply --out-dir "$OUT" > "$OUT/apply.txt" 2>&1; rc=$?; fi
  cat "$OUT/apply.txt"
  [ $rc = 0 ] || stop APPLY "apply refused or failed (exit $rc): the transaction rolled back; nothing changed"
  if [ "$X" = P ]; then J=$(ls "$OUT"/pricing_corrections_journal_prod_*.json 2>/dev/null | head -n1)
  else J=$(ls "$OUT"/rt2_defaults_journal_prod_*.json 2>/dev/null | head -n1); fi
  [ -n "$J" ] || stop JOURNAL "applied but no journal in $OUT — tell the CA NOW"
  JN="journal_${X}_$(basename "$J")"
  cp "$J" "$KEEP/$JN" || stop JOURNAL "journal not copied to $KEEP (it is still in $OUT) — tell the CA"
  { echo "journal      $JN (the tool's own file, unchanged)"
    [ "$X" = P ] && echo "manifest     P  sha256 $P_SHA" || echo "manifest     D  (rt2_defaults.py sha256 $D_SHA)"
    [ "$X" = P ] && echo "tool         sha256 $(sha256sum "$TP" | cut -d' ' -f1)"
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
KIND=$($PY -c 'import json,sys; j=json.load(open(sys.argv[1])); print("D" if j.get("tool") == "rt2_defaults" else j.get("manifest_sha256", "?"))' "$JR" 2>/dev/null) \
  || stop USAGE "not a tool journal: $JR"
if [ "$KIND" = D ]; then X=D
elif [ "$KIND" = "$P_SHA" ]; then X=P
else stop USAGE "the journal is neither Manifest D's nor Manifest P's (manifest sha ${KIND:0:12})"
fi
if [ "$X" = P ]; then
  say "order: D must be off prod before P is reverted"
  d_is_off || { cat "$OUT/order_D.txt"; stop ORDER "Manifest D is still (partly) on prod — revert D first"; }
fi
say "revert Manifest $X from $(basename "$JR")"
if [ "$X" = P ]; then $PY "$TP" --target prod --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?
else $PY "$TD" --target prod --revert "$JR" --out-dir "$OUT" > "$OUT/revert.txt" 2>&1; rc=$?; fi
cat "$OUT/revert.txt"
[ $rc = 0 ] || stop REVERT "revert refused (exit $rc): nothing changed"
cp "$OUT"/pricing_corrections_revert_prod_*.json "$OUT"/rt2_defaults_revert_prod_*.json "$KEEP/" 2>/dev/null || true
chmod -R a+rX "$OUT"
echo; echo "######## DONE (revert $X) — tell the CA: $OUT"
