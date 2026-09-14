#!/usr/bin/env bash
# v1.53.1 PROD DEPLOY - 04b332f -> 94ed70b (calculator.js + 2 templates; no python,
# no migration, no frontend build). Runs ON the prod VM:
#     bash ~/icb-deploy-v1531/deploy.sh [RUN_ID] [--restart]
#
# Steps (each asserts; any failure STOPs with a clear message):
#   1 preflight (read-only)  HEAD must be 04b332f (already 94ed70b -> verify-only),
#                            no tracked modifications, alembic 0047, service active
#   2 fetch                  git fetch origin (as icb) - the only network step
#   3 change-set guard       04b332f..94ed70b must be EXACTLY expected_changes.txt, and
#                            contain no app .py / alembic / frontend / requirements
#   4 confirm                you type DEPLOY
#   5 fast-forward           git merge --ff-only 94ed70b (as icb); Ctrl-C/hang-up ignored
#                            for the few milliseconds it takes
#   6 restart                only with --restart (not needed: JS + templates reload from disk)
#   7 verify                 disk + served bytes + Cloudflare (after the disk matches) +
#                            health + alembic + service
#   8 record                 DEPLOYED_94ed70b (naming the verified HEAD) written ONLY after 7 passed
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$KIT/lib.sh"
. "$KIT/checks.sh"
RUN_ARG=""; RESTART=0
for a in "$@"; do
  case "$a" in
    --restart) RESTART=1 ;;
    *[!0-9-]*) echo "unknown argument: $a"; exit 2 ;;
    *) RUN_ARG="$a" ;;
  esac
done
init_run deploy "$RUN_ARG"

do_restart() {   # restart + assert a clean 4-worker boot (polls the journal, up to 90 s)
  step "6 RESTART (requested)"
  local since w b i
  since="$(date '+%Y-%m-%d %H:%M:%S')"
  $SUDO systemctl restart "$SERVICE" || die "systemctl restart failed - check: systemctl is-active $SERVICE"
  for i in $(seq 1 45); do
    sleep 2
    w="$($SUDO journalctl -u "$SERVICE" --since "$since" --no-pager 2>/dev/null | grep -Ec 'Application startup complete')"
    [ "${w:-0}" -ge 4 ] && break
  done
  b="$($SUDO journalctl -u "$SERVICE" --since "$since" --no-pager 2>/dev/null | grep -c 'BOOTSTRAP FAILED')"
  say "  workers started: ${w:-0}   bootstrap failures: ${b:-0}"
  [ "$(systemctl is-active "$SERVICE" 2>/dev/null)" = "active" ] || die "$SERVICE is not active after the restart - run: sudo systemctl status $SERVICE"
  [ "$(service_ts)" != "$TS_BEFORE" ] || die "ActiveEnterTimestamp did not change - the restart did not take effect"
  [ "${w:-0}" -ge 4 ] || die "only ${w:-0} of 4 workers logged 'Application startup complete' within 90 s - read: sudo journalctl -u $SERVICE --since '$since'"
  [ "${b:-0}" = "0" ] || die "BOOTSTRAP FAILED appears in the journal since the restart - read it before anything else"
  ok "restarted cleanly (since $(service_ts))"
}

# -- 1. preflight (read-only) --------------------------------------------------
step "1 PREFLIGHT (read-only)"
HEAD_NOW="$(head_sha)"
DIRTY="$(tracked_dirty)"
say "  repo:      $REPO"
say "  HEAD:      ${HEAD_NOW:-<unreadable>}"
say "  tracked modifications: $DIRTY   (untracked build artefacts are ignored on purpose)"
[ -n "$HEAD_NOW" ] || die "cannot read git HEAD in $REPO"
if [ "$HEAD_NOW" = "$BASE_SHA" ]; then
  release_state
  if [ -n "$MOD_OTHER$UNTR_OTHER" ]; then
    say "  changes that are NOT byte-identical to the 94ed70b release:"; list_paths "$MOD_OTHER$UNTR_OTHER"
    die "local changes at 04b332f that this kit did not write - someone changed prod by hand (or a file is half-written); investigate before deploying"
  fi
  if [ -n "$MOD_RELEASE$UNTR_RELEASE" ]; then
    say "  files already holding their 94ed70b content (left by an interrupted earlier fast-forward):"; list_paths "$MOD_RELEASE$UNTR_RELEASE"
    die "an earlier fast-forward was interrupted - run -Action Rollback (it removes exactly these files), then Deploy again"
  fi
elif [ "$DIRTY" != "0" ]; then
  $GIT status --porcelain --untracked-files=no | sed 's/^/    /'
  die "$REPO has $DIRTY tracked modification(s) - someone changed prod by hand; investigate before deploying"
fi
SVC_ACTIVE="$(systemctl is-active "$SERVICE" 2>/dev/null)"
TS_BEFORE="$(service_ts)"
say "  service:   $SERVICE $SVC_ACTIVE since $TS_BEFORE"
[ "$SVC_ACTIVE" = "active" ] || die "$SERVICE is not active before the deploy - investigate first"
AL_BEFORE="$(alembic_current)"
[ -n "$AL_BEFORE" ] || die "could not READ alembic current (sudo password/env/alembic error - see $OUT/alembic_current.err); nothing was changed"
say "  alembic:   $(echo "$AL_BEFORE" | tr '\n' ' ')"
case "$AL_BEFORE" in *"$ALEMBIC_HEAD"*) ;; *) die "alembic reads '$(echo "$AL_BEFORE" | tr '\n' ' ')', not $ALEMBIC_HEAD - investigate before deploying" ;; esac
echo "$HEAD_NOW" > "$OUT/ROLLBACK_ANCHOR"

if [ "$HEAD_NOW" = "$TARGET_SHA" ]; then
  say ""
  say "  Prod is ALREADY at 94ed70b - not fast-forwarding again."
  if [ "$RESTART" = "1" ]; then
    say ""
    say "PLAN: restart $SERVICE (prod already at 94ed70b; ~10-30 s of 502s while 4 workers boot)"
    confirm RESTART "Ready." || die "not confirmed - nothing was changed"
    rm -f "$RECORD"
    do_restart
  fi
  rm -f "$RECORD"
  run_checks target
  [ "$FAILS" = "0" ] || die "$FAILS check(s) failed with prod at 94ed70b - read the FAIL lines above"
  write_record "verified-at-target restart=$RESTART"
  RC=0; exit 0
fi
[ "$HEAD_NOW" = "$BASE_SHA" ] || die "prod HEAD is $HEAD_NOW, expected 04b332f (from the 14 Sep audit) - prod moved; re-baseline before deploying"
say "  served now (calculator.js?v=$V_BASE):"
for u in $SERVED_URLS; do say "    $u  $(served_sha "$u" "$V_BASE")"; done

# -- 2. fetch --------------------------------------------------------------------
step "2 FETCH origin (as icb) - progress below; can take ~10-30 s"
$AS_ICB git -c safe.directory="$REPO" -C "$REPO" fetch --progress origin
$GIT cat-file -e "$TARGET_SHA^{commit}" 2>/dev/null || die "94ed70b is not present after the fetch (network/credentials?) - nothing was changed"
$GIT merge-base --is-ancestor "$TARGET_SHA" "$DEPLOY_LINE" 2>/dev/null || die "94ed70b is not on $DEPLOY_LINE - refusing an unmerged commit; nothing was changed"
$GIT merge-base --is-ancestor "$BASE_SHA" "$TARGET_SHA" 2>/dev/null || die "04b332f is not an ancestor of 94ed70b - cannot fast-forward; nothing was changed"
ok "94ed70b fetched, on $DEPLOY_LINE, fast-forwardable from 04b332f"
$GIT log --oneline "$BASE_SHA..$TARGET_SHA"

# -- 3. change-set guard ------------------------------------------------------------
step "3 CHANGE-SET GUARD"
$GIT diff --name-only "$BASE_SHA" "$TARGET_SHA" | LC_ALL=C sort > "$OUT/actual_changes.txt"
tr -d '\r' < "$KIT/expected_changes.txt" | LC_ALL=C sort > "$OUT/expected_changes.txt"
if ! diff -u "$OUT/expected_changes.txt" "$OUT/actual_changes.txt"; then
  die "the 04b332f..94ed70b change set differs from the reviewed list - nothing was changed"
fi
RISKY="$(grep -E '^backend/app/.*\.py$|^backend/alembic/|^frontend/|requirements|^deploy/' "$OUT/actual_changes.txt")"
[ -z "$RISKY" ] || die "change set contains python/migration/frontend/deps paths: $RISKY"
ok "$(wc -l < "$OUT/actual_changes.txt" | tr -d ' ') paths, exactly as reviewed; app changes are calculator.js + 2 templates only"
grep -v '^docs/screenshots/' "$OUT/actual_changes.txt" | sed 's/^/    /'

# -- 4. confirm -----------------------------------------------------------------------
PLAN="PLAN: fast-forward $REPO  04b332f -> 94ed70b  (restart: $([ "$RESTART" = 1 ] && echo YES || echo no - not needed))"
say ""
say "$PLAN"
confirm DEPLOY "Ready." || die "not confirmed - nothing was changed"

# -- 5. fast-forward --------------------------------------------------------------------
step "5 FAST-FORWARD (as icb)"
rm -f "$RECORD"
trap '' INT HUP                       # a Ctrl-C or dropped VPN must not interrupt git mid-write
$AS_ICB git -c safe.directory="$REPO" -C "$REPO" merge --ff-only "$TARGET_SHA"
MERGE_RC=$?
trap 'RC=130; exit 130' INT
trap 'RC=143; exit 143' TERM HUP
HEAD_AFTER="$(head_sha)"
[ "$MERGE_RC" = "0" ] && [ "$HEAD_AFTER" = "$TARGET_SHA" ] \
  || die "fast-forward failed (git exit $MERGE_RC, HEAD now $HEAD_AFTER) - run Verify to see the state, then Rollback"
ok "HEAD = $HEAD_AFTER"

# -- 6. optional restart ------------------------------------------------------------------
if [ "$RESTART" = "1" ]; then
  do_restart
else
  step "6 RESTART - skipped (no python changed; calculator.js and templates are read from disk on every request)"
fi

# -- 7. verify ------------------------------------------------------------------------------
run_checks target
if [ "$RESTART" != "1" ]; then
  TS_NOW="$(service_ts)"
  if [ "$TS_NOW" = "$TS_BEFORE" ]; then ok "service not restarted (still since $TS_NOW)"; else say "  NOTE service start time changed: $TS_BEFORE -> $TS_NOW (something else restarted it)"; fi
fi
[ "$FAILS" = "0" ] || die "$FAILS verification check(s) failed after the fast-forward - prod has the NEW files on disk; read the FAIL lines, then run Verify again or Rollback"

# -- 8. record ---------------------------------------------------------------------------------
write_record "from=$HEAD_NOW restart=$RESTART"
step "8 DONE"
say "  prod is serving v1.53.1 (94ed70b). Record: $RECORD"
say "  NOW: purge the Cloudflare cache for mes.icecoldgrp.online (mandatory), then hard-reload and do the click-through (README section 6)."
say "  Rollback if ever needed: run the launcher with -Action Rollback (VM-local: bash $KIT/rollback.sh)"
RC=0
exit 0
