#!/usr/bin/env bash
# v1.53.1 OPTIONAL - #184 server-side default thicknesses for prod "Manni RIGIDS CB".
# Separate from the code deploy on purpose: this WRITES to the database (one draft row).
#
#   bash seed_manni_defaults.sh [RUN_ID] dry-run          read-only: what would be set (needs 94ed70b)
#   bash seed_manni_defaults.sh [RUN_ID] apply            backup + snapshot + write + verify (needs 94ed70b)
#   bash seed_manni_defaults.sh [RUN_ID] restore FILE     backup + guarded put-back (works at 94ed70b OR 04b332f)
#
# Values come from backend/tools/set_manni_flag_defaults.py at 94ed70b:
#   FRONT PU 0.062 | DRD PU 0.038 | SIDES PU 0.038 | ROOF PU 0.038 | FLOOR PU 0.076
# Before ANY step the helper proves exactly one trailer is named 'Manni RIGIDS CB', that it is
# id 41 (ICB_MANNI_TID), active and configurator_v2, with exactly one draft row.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$KIT/lib.sh"
RUN_ARG=""; MODE=""; FILE=""
for a in "$@"; do
  case "$a" in
    dry-run|apply|restore) MODE="$a" ;;
    "") ;;
    *[!0-9-]*) if [ "$MODE" = "restore" ] && [ -z "$FILE" ]; then FILE="$a"; else echo "unknown argument: $a"; exit 2; fi ;;
    *) RUN_ARG="$a" ;;
  esac
done
MODE="${MODE:-dry-run}"
MANNI_TID="${ICB_MANNI_TID:-41}"
BACKUP_UNIT="${ICB_BACKUP_UNIT:-icb-pg-backup.service}"
BACKUP_DIR="${ICB_BACKUP_DIR:-/var/backups/postgres}"
init_run "seed-$MODE" "$RUN_ARG"

app_py() {   # app_py READONLY(1|0) ARGS... - run a python file from backend/ with the app env
  local ro="$1"; shift
  if [ -n "$SUDO" ]; then
    $SUDO bash -c 'ro="$1"; env_file="$2"; repo="$3"; py="$4"; shift 4
      set -a; . "$env_file"; set +a; cd "$repo/backend" || exit 2
      if [ "$ro" = "1" ]; then export PGOPTIONS="-c default_transaction_read_only=on"; fi
      PYTHONDONTWRITEBYTECODE=1 "$py" -B "$@"' _ "$ro" "$ENV_FILE" "$REPO" "$PY" "$@"
  else
    ( set -a; . "$ENV_FILE"; set +a; cd "$REPO/backend" || exit 2
      if [ "$ro" = "1" ]; then export PGOPTIONS="-c default_transaction_read_only=on"; fi
      PYTHONDONTWRITEBYTECODE=1 "$PY" -B "$@" )
  fi
}

fresh_backup() {
  step "BACKUP - fresh database dump before writing"
  $SUDO systemctl start "$BACKUP_UNIT" || die "could not start $BACKUP_UNIT - nothing written"
  $SUDO systemctl status "$BACKUP_UNIT" --no-pager 2>/dev/null | tail -3   # a finished oneshot exits 3; informational only
  FRESH="$($SUDO find "$BACKUP_DIR" -name '*.dump.gz' -mmin -10 2>/dev/null | sort | tail -1)"
  [ -n "$FRESH" ] || die "no backup newer than 10 minutes in $BACKUP_DIR - nothing written"
  ok "fresh backup: $FRESH"
}

step "PREFLIGHT (read-only)"
HEAD_NOW="$(head_sha)"
say "  HEAD: $HEAD_NOW   expected Manni trailer id: $MANNI_TID"
case "$MODE" in
  dry-run|apply)
    [ "$HEAD_NOW" = "$TARGET_SHA" ] || die "prod is not at 94ed70b - deploy the code first (the tool and the calculator that reads the defaults ship in it)"
    [ "$(tracked_dirty)" = "0" ] || die "tracked modifications in $REPO - the tool/models on disk are not the reviewed 94ed70b files; investigate first"
    ;;
  restore) [ "$HEAD_NOW" = "$TARGET_SHA" ] || [ "$HEAD_NOW" = "$BASE_SHA" ] || die "prod HEAD is $HEAD_NOW - neither 94ed70b nor 04b332f" ;;
esac
if [ "$MODE" != "restore" ]; then
  app_py 1 "$KIT/manni_draft.py" check --tid "$MANNI_TID" || die "identity check failed - see the ABORT line; nothing done"
  app_py 1 "$KIT/manni_draft.py" show --tid "$MANNI_TID" || die "could not read the Manni draft"
fi

case "$MODE" in
dry-run)
  step "DRY-RUN (read-only session - the tool cannot write even if asked)"
  app_py 1 tools/set_manni_flag_defaults.py
  rc=$?
  [ "$rc" = "0" ] || die "the tool reported a problem (exit $rc) - see above; nothing was written"
  say ""
  say "  Nothing was written. To apply: -Action SeedApply"
  RC=0; exit 0
  ;;

apply)
  step "PLAN"
  app_py 1 tools/set_manni_flag_defaults.py || die "dry-run inside apply failed - nothing written"
  say ""
  say "PLAN: write the flagVarDefault values above onto the 'Manni RIGIDS CB' draft (trailer $MANNI_TID, one row)"
  confirm SEED "Ready." || die "not confirmed - nothing written"
  fresh_backup
  step "SNAPSHOT - the draft row as it is now (for a precise restore)"
  SNAP="$OUT/manni_draft_before.json"
  app_py 1 "$KIT/manni_draft.py" dump --tid "$MANNI_TID" "$SNAP" || die "snapshot failed - nothing written"
  [ -n "$SUDO" ] && $SUDO chown "$(id -u):$(id -g)" "$SNAP" 2>/dev/null
  cp "$SNAP" "$KIT/manni_draft_before_$RUN_ID.json" || die "could not keep the snapshot - nothing written"
  ok "snapshot kept at $KIT/manni_draft_before_$RUN_ID.json"
  step "APPLY"
  app_py 1 "$KIT/manni_draft.py" check --tid "$MANNI_TID" || die "identity changed between snapshot and apply - nothing written"
  app_py 0 tools/set_manni_flag_defaults.py --apply || die "the tool failed while applying - run SeedDryRun to see the state; snapshot: $KIT/manni_draft_before_$RUN_ID.json"
  step "VERIFY (read-only)"
  app_py 1 "$KIT/manni_draft.py" show --tid "$MANNI_TID" --expect || die "the draft does not carry the expected defaults - restore with -Action SeedRestore -RestoreFile $KIT/manni_draft_before_$RUN_ID.json"
  say ""
  say "  Applied and verified. Fresh browsers now inherit the five thicknesses on Manni RIGIDS CB."
  say "  Undo (guarded): -Action SeedRestore -RestoreFile ~/$(basename "$KIT")/manni_draft_before_$RUN_ID.json"
  RC=0; exit 0
  ;;

restore)
  [ -n "$FILE" ] && [ -f "$FILE" ] || die "restore needs the snapshot file path, e.g. $KIT/manni_draft_before_<RUN_ID>.json" 2
  cp "$FILE" "$OUT/restore_input.json" || die "cannot read $FILE"
  app_py 1 "$KIT/manni_draft.py" show --tid "$MANNI_TID" --snapshot "$OUT/restore_input.json" || die "identity check / read failed - see the ABORT line; nothing written"
  app_py 1 "$KIT/manni_draft.py" restore --tid "$MANNI_TID" --check "$OUT/restore_input.json"
  crc=$?
  if [ "$crc" = "3" ]; then say ""; say "  The draft already equals the snapshot - nothing to restore, nothing written."; RC=0; exit 0; fi
  [ "$crc" = "0" ] || die "this restore would be refused (see the ABORT line) - nothing written, no backup taken"
  say ""
  say "PLAN: put the 'Manni RIGIDS CB' draft (trailer $MANNI_TID) back to $FILE - refused automatically unless the draft is exactly 'snapshot + the seeded defaults'"
  confirm RESTORE "Ready." || die "not confirmed - nothing written"
  fresh_backup
  step "RESTORE"
  app_py 0 "$KIT/manni_draft.py" restore --tid "$MANNI_TID" "$OUT/restore_input.json" || die "restore refused or failed - see the message above"
  step "VERIFY (read-only)"
  app_py 1 "$KIT/manni_draft.py" show --tid "$MANNI_TID" --snapshot "$OUT/restore_input.json" || die "could not re-read the draft after restore"
  RC=0; exit 0
  ;;
esac
