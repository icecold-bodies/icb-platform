#!/usr/bin/env bash
# v1.53.1 PROD ROLLBACK - back to 04b332f (code only; no network, no restart).
#     bash ~/icb-deploy-v1531/rollback.sh [RUN_ID]
# Handles:
#   - prod at 94ed70b, clean                       -> normal rollback
#   - prod at 04b332f with files left by an interrupted fast-forward (tracked files holding
#     their exact 94ed70b content and/or untracked copies of files 94ed70b adds, byte-identical)
#                                                  -> restores/removes exactly those files
#   - prod clean at 04b332f                        -> verify only
# Anything whose content is NOT the release (a hand edit) is refused and never destroyed.
# The deploy changed no schema and no data.
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$KIT/lib.sh"
. "$KIT/checks.sh"
init_run rollback "${1:-}"

step "1 PREFLIGHT (read-only)"
HEAD_NOW="$(head_sha)"
DIRTY="$(tracked_dirty)"
say "  HEAD: ${HEAD_NOW:-<unreadable>}   tracked modifications: $DIRTY"
[ -n "$HEAD_NOW" ] || die "cannot read git HEAD in $REPO"
if ls "$KIT"/manni_draft_before_*.json >/dev/null 2>&1; then
  say "  NOTE: if you seeded the Manni defaults and have not restored them, this code rollback does NOT undo them;"
  say "        -Action SeedRestore works before or after this rollback (the defaults are inert on 04b332f)."
fi

FORCE=""; REMOVE=""
case "$HEAD_NOW" in
  "$TARGET_SHA")
    if [ "$DIRTY" != "0" ]; then
      $GIT status --porcelain --untracked-files=no | sed 's/^/    /'
      $GIT diff HEAD > "$OUT/modified_before_rollback.patch" 2>/dev/null
      die "tracked modifications at 94ed70b (a hand edit - saved to $OUT/modified_before_rollback.patch); a rollback would destroy them - investigate first"
    fi
    ;;
  "$BASE_SHA")
    release_state
    if [ -n "$MOD_OTHER$UNTR_OTHER" ]; then
      $GIT diff HEAD > "$OUT/modified_before_rollback.patch" 2>/dev/null
      say "  changes that are NOT byte-identical to the 94ed70b release:"; list_paths "$MOD_OTHER$UNTR_OTHER"
      die "local changes this kit did not write (tracked edits saved to $OUT/modified_before_rollback.patch; untracked files are left in place) - refusing to destroy them; investigate first"
    fi
    if [ -z "$MOD_RELEASE$UNTR_RELEASE" ]; then
      say "  already at 04b332f and clean - verifying only"
      rm -f "$RECORD"
      run_checks baseline
      [ "$FAILS" = "0" ] || die "$FAILS check(s) failed at 04b332f - read the FAIL lines"
      RC=0; exit 0
    fi
    $GIT diff HEAD > "$OUT/modified_before_rollback.patch" 2>/dev/null
    say "  left by an interrupted fast-forward (each byte-identical to 94ed70b):"
    [ -n "$MOD_RELEASE" ] && { say "   tracked, will be restored to 04b332f:"; list_paths "$MOD_RELEASE"; }
    [ -n "$UNTR_RELEASE" ] && { say "   untracked copies of files 94ed70b adds, will be removed:"; list_paths "$UNTR_RELEASE"; }
    FORCE="-f"; REMOVE="$UNTR_RELEASE"
    ;;
  *) die "HEAD is $HEAD_NOW - neither 94ed70b nor 04b332f; this rollback is only for the v1.53.1 deploy" ;;
esac
$GIT cat-file -e "$BASE_SHA^{commit}" 2>/dev/null || die "04b332f is not in the local repo (unexpected) - nothing was changed"

say ""
say "PLAN: put $REPO back to 04b332f (the pre-deploy checkout)${FORCE:+ - restoring/removing ONLY the release files listed above}"
confirm ROLLBACK "Ready." || die "not confirmed - nothing was changed"

step "2 CHECKOUT 04b332f (as icb)"
rm -f "$RECORD"
trap '' INT HUP
$AS_ICB git -c safe.directory="$REPO" -C "$REPO" checkout --detach $FORCE "$BASE_SHA"
CO_RC=$?
if [ "$CO_RC" = "0" ] && [ -n "$REMOVE" ]; then
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    $AS_ICB rm -f -- "$REPO/$p" && say "    removed $p"
  done < <(printf '%s' "$REMOVE")
fi
trap 'RC=130; exit 130' INT
trap 'RC=143; exit 143' TERM HUP
[ "$CO_RC" = "0" ] && [ "$(head_sha)" = "$BASE_SHA" ] || die "checkout failed (git exit $CO_RC) - investigate"
ok "HEAD = $BASE_SHA"
release_state
[ -z "$MOD_RELEASE$MOD_OTHER$UNTR_RELEASE$UNTR_OTHER" ] || { list_paths "$MOD_RELEASE$MOD_OTHER$UNTR_RELEASE$UNTR_OTHER"; die "files above still differ from 04b332f after the rollback - investigate"; }
ok "no release files left behind"

run_checks baseline
[ "$FAILS" = "0" ] || die "$FAILS check(s) failed after rollback - read the FAIL lines"
say ""
say "  Rolled back. Browsers need a hard reload; purge the Cloudflare cache for mes.icecoldgrp.online."
RC=0
exit 0
