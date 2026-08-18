#!/usr/bin/env bash
#
# ICB MES — production rollback (code only).
#
#   ./icb-rollback.sh 0dd4075          go back to that commit
#   ./icb-rollback.sh 0dd4075 --yes    no confirmation prompt
#
# Deliberately does NOT touch the database. Every migration in this project so
# far has been additive, so old code simply ignores the new columns — whereas
# `alembic downgrade` destroys data (0042's downgrade, for one, deletes the
# repair-document counter series and any numbers already issued from it).
#
# If a rollback ever genuinely needs a schema change, that is a decision for
# Michael and the BA, not for a script.
#
set -euo pipefail

REPO=/opt/icb-platform
SERVICE=icb-backend
EXPECTED_WORKERS=4
HEALTH_URL=https://127.0.0.1/health

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLD=$'\033[1m'; RST=$'\033[0m'
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s== %s%s\n' "$BLD" "$*" "$RST"; }
ok()   { printf '%s  ok%s  %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s  !!%s  %s\n' "$YEL" "$RST" "$*"; }
die()  { printf '\n%sFAILED:%s %s\n' "$RED" "$RST" "$*" >&2; exit 1; }

TARGET_REF=""; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)  ASSUME_YES=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    -*)        die "unknown option: $1" ;;
    *)         [ -n "$TARGET_REF" ] && die "give exactly one ref"; TARGET_REF="$1" ;;
  esac
  shift
done
[ -n "$TARGET_REF" ] || die "usage: $0 <tag-or-sha> [--yes]"
[ -d "$REPO/.git" ]  || die "$REPO is not a git repo — are you on the prod VM?"

CURRENT=$(git -C "$REPO" rev-parse HEAD)
# Only fetch if the target is genuinely missing. A rollback target is nearly
# always a commit prod was running minutes ago, so it is already on disk — and
# an unconditional fetch would make rollback impossible whenever origin is
# unreachable, and would demand a sudo password before printing so much as the
# plan. Neither is acceptable in the one script you reach for during an incident.
if ! git -C "$REPO" cat-file -e "${TARGET_REF}^{commit}" 2>/dev/null; then
  say "  $TARGET_REF is not in prod's object store — fetching (needs sudo)."
  sudo -v || die "sudo declined — nothing has changed"
  sudo -u icb git -C "$REPO" fetch origin --tags --progress 2>&1 | sed 's/^/    /'
fi
TARGET=$(git -C "$REPO" rev-parse "${TARGET_REF}^{commit}" 2>/dev/null) || die "ref '$TARGET_REF' not found"

step "rollback plan"
say "  from  ${CURRENT:0:8}  $(git -C "$REPO" log -1 --format=%s "$CURRENT" | cut -c1-60)"
say "  to    ${TARGET:0:8}  $(git -C "$REPO" log -1 --format=%s "$TARGET"  | cut -c1-60)"

# Was this a forward move? If so we are genuinely going backwards, which is the
# normal case. If the target is AHEAD, the operator has the direction wrong.
if git -C "$REPO" merge-base --is-ancestor "$CURRENT" "$TARGET"; then
  warn "$TARGET_REF is AHEAD of what is deployed — that is a deploy, not a rollback. Use icb-deploy.sh."
  die "refusing to 'roll back' forwards"
fi

CHANGED=$(git -C "$REPO" diff --name-only "$TARGET".."$CURRENT")
n_frontend=$(printf '%s\n' "$CHANGED" | grep -c '^frontend/' || true)
LOST_MIGRATIONS=$(git -C "$REPO" diff --name-only --diff-filter=A "$TARGET".."$CURRENT" -- 'backend/alembic/versions/*' || true)

say ""
say "  SPA rebuild      $([ "$n_frontend" -gt 0 ] && echo "YES — $n_frontend file(s) under frontend/" || echo 'no')"

# `reset --hard` discards tracked modifications without a word. During an
# incident those are exactly the hot-fixes someone just made by hand on the box,
# so name them and make the operator consent — a hard refusal would be wrong
# here (rolling back is the emergency), but silently destroying the work is worse.
DIRTY=$(git -C "$REPO" status --porcelain --untracked-files=no | wc -l)
if [ "$DIRTY" -gt 0 ]; then
  say ""
  warn "the working tree has $DIRTY modified TRACKED file(s). reset --hard WILL DISCARD them:"
  git -C "$REPO" status --short --untracked-files=no | head -20 | sed 's/^/      /'
  warn "if any of that is a hot-fix worth keeping, stop now and save it:"
  say  "      sudo -u icb git -C $REPO stash push -m rollback-$(date +%H%M)"
fi
if [ -n "$LOST_MIGRATIONS" ]; then
  warn "this range introduced migration(s): $(printf '%s\n' "$LOST_MIGRATIONS" | xargs -n1 basename | tr '\n' ' ')"
  warn "they STAY APPLIED. The old code ignores them. Do not downgrade to undo this."
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  say ""
  printf 'Roll back to %s? [y/N] ' "${TARGET:0:8}"
  read -r reply </dev/tty || die "no terminal to confirm on"
  case "$reply" in y|Y|yes|YES) ;; *) die "aborted (nothing has changed)" ;; esac
fi

step "reset the working tree"
# reset --hard, not merge --ff-only: going backwards is not a fast-forward.
sudo -u icb git -C "$REPO" reset --hard "$TARGET"
# The deploy script's completion record described the commit we are leaving, so
# it is now false. Clearing it means a later re-deploy of that same target can
# never mistake the old record for proof it already ran.
rm -f /var/tmp/icb-deploy-state 2>/dev/null || true
NOW=$(git -C "$REPO" rev-parse HEAD)
[ "$NOW" = "$TARGET" ] || die "HEAD is ${NOW:0:8}, expected ${TARGET:0:8}"
ok "at ${TARGET:0:8}"

if [ "$n_frontend" -gt 0 ]; then
  step "rebuild the SPA for the older code"
  sudo -u icb bash -lc "cd $REPO/frontend && npm run build"
  ok "bundle rebuilt"
fi

step "restart $SERVICE"
STAMP_BEFORE=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
sudo systemctl restart "$SERVICE"
sleep 6
STAMP_AFTER=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
[ "$STAMP_AFTER" != "$STAMP_BEFORE" ] || die "the service did not actually restart"
[ "$(systemctl is-active "$SERVICE")" = "active" ] || die "$SERVICE is not active"
ok "restarted at $STAMP_AFTER"

step "verify"
FAILED=$(sudo journalctl -u "$SERVICE" --since '-2 min' --no-pager | grep -c 'BOOTSTRAP FAILED' || true)
STARTED=$(sudo journalctl -u "$SERVICE" --since '-2 min' --no-pager | grep -c 'Application startup complete' || true)
say "  workers started   $STARTED (expected $EXPECTED_WORKERS)"
say "  BOOTSTRAP FAILED  $FAILED (expected 0)"
# Printing "expected 0" and then declaring success in green regardless is worse
# than not checking at all — it looks like it was checked. Assert, as the deploy
# script does: a worker that logged BOOTSTRAP FAILED has silently lost its role
# grants, and a rollback that ends green on top of that is a lie.
[ "$FAILED" -eq 0 ] || die "$FAILED worker(s) logged BOOTSTRAP FAILED — the rollback is NOT healthy"
[ "$STARTED" -ge "$EXPECTED_WORKERS" ] || warn "fewer workers than expected — check: sudo journalctl -u $SERVICE -n 100"
CODE=$(curl -k -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)
say "  $HEALTH_URL -> $CODE"
[ "$CODE" = "200" ] || die "health check returned $CODE"

say ""
say "${GRN}${BLD}ROLLED BACK${RST}  ${CURRENT:0:8} -> ${TARGET:0:8}"
say ""
