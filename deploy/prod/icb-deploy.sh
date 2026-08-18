#!/usr/bin/env bash
#
# ICB MES — production deploy.
#
#   ./icb-deploy.sh v1.48.1              deploy that tag (asks before doing anything)
#   ./icb-deploy.sh v1.48.1 --yes        no confirmation prompt
#   ./icb-deploy.sh v1.48.1 --dry-run    print the plan and stop
#
# Run this ON the prod VM. It uses sudo, which is password-required for
# mickeyger, so it cannot be driven non-interactively over ssh — use
# Push-ToProd.ps1 from Windows, which allocates a TTY so sudo can prompt.
#
# What it decides for you, by diffing the deployed commit against the target
# (these were hand-decided in every previous runbook, and they are mechanical):
#
#   * DB migration   — only if a new file appears in backend/alembic/versions/
#   * SPA rebuild    — only if anything under frontend/ changed
#   * service restart— only if backend Python changed, or a migration ran.
#                      Templates and static assets reload from disk, so a
#                      template/CSS-only deploy genuinely needs no restart
#                      (this is how v1.46.4 went out).
#
# It never runs `alembic downgrade`. Rollback is code-only — see icb-rollback.sh.
#
set -euo pipefail

REPO=/opt/icb-platform
SERVICE=icb-backend
ENV_FILE=/etc/icb/backend.env
EXPECTED_WORKERS=4
HEALTH_URL=https://127.0.0.1/health

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLD=$'\033[1m'; RST=$'\033[0m'
say()  { printf '%s\n' "$*"; }
step() { printf '\n%s== %s%s\n' "$BLD" "$*" "$RST"; }
ok()   { printf '%s  ok%s  %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s  !!%s  %s\n' "$YEL" "$RST" "$*"; }
die()  { printf '\n%sFAILED:%s %s\n' "$RED" "$RST" "$*" >&2; exit 1; }

# ── arguments ────────────────────────────────────────────────────────────────
TARGET_REF=""; ASSUME_YES=0; DRY_RUN=0; FORCE_RESTART=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)        ASSUME_YES=1 ;;
    --dry-run|-n)    DRY_RUN=1 ;;
    --force-restart) FORCE_RESTART=1 ;;
    -h|--help)       sed -n '2,30p' "$0"; exit 0 ;;
    -*)              die "unknown option: $1" ;;
    *)               [ -n "$TARGET_REF" ] && die "give exactly one ref"; TARGET_REF="$1" ;;
  esac
  shift
done
[ -n "$TARGET_REF" ] || die "usage: $0 <tag-or-sha> [--yes] [--dry-run]"
[ -d "$REPO/.git" ]  || die "$REPO is not a git repo — are you on the prod VM?"

# ── 0. preflight ─────────────────────────────────────────────────────────────
step "0. preflight"
CURRENT=$(git -C "$REPO" rev-parse HEAD)
BRANCH=$(git -C "$REPO" rev-parse --abbrev-ref HEAD)
say "  repo      $REPO (branch $BRANCH)"
say "  deployed  ${CURRENT:0:8}  $(git -C "$REPO" log -1 --format=%s "$CURRENT" | cut -c1-64)"

# Only TRACKED modifications can block a fast-forward. Prod accumulates
# untracked build droppings (.npm-cache/, __pycache__), and refusing to deploy
# over those would be a false alarm.
DIRTY=$(git -C "$REPO" status --porcelain --untracked-files=no | wc -l)
[ "$DIRTY" -eq 0 ] || {
  git -C "$REPO" status --short --untracked-files=no | head -20
  die "the prod working tree has $DIRTY modified TRACKED file(s) — a fast-forward will not apply cleanly. Resolve by hand first."
}
UNTRACKED=$(git -C "$REPO" ls-files --others --exclude-standard "$REPO" | wc -l)
if [ "$UNTRACKED" -gt 0 ]; then
  ok "no tracked modifications ($UNTRACKED untracked path(s) present — harmless, ignored)"
else
  ok "working tree clean"
fi

step "1. fetch"
# PLANREPO is whichever repo has the objects needed to work out the plan. It is
# the prod repo in the normal case, and a scratch clone during a --dry-run that
# would otherwise have to fetch.
PLANREPO="$REPO"
if git -C "$REPO" cat-file -e "${TARGET_REF}^{commit}" 2>/dev/null; then
  ok "$TARGET_REF already present — no fetch needed"
elif [ "$DRY_RUN" -eq 1 ]; then
  # A dry run changes nothing, so it must not demand a password. Fetching into
  # the prod repo would (it is icb-owned), so clone into /tmp instead — which
  # mickeyger CAN write — using the prod repo as a --reference so only the new
  # objects come over the wire. Read-only as far as $REPO is concerned.
  say "  $TARGET_REF is not in prod's object store yet."
  say "  dry run: resolving it in a scratch clone instead of fetching (no sudo)."
  SCRATCH=$(mktemp -d /tmp/icb-plan-XXXXXX)
  trap 'rm -rf "$SCRATCH"' EXIT
  REMOTE_URL=$(git -C "$REPO" config --get remote.origin.url)
  if git clone -q --bare --reference "$REPO" "$REMOTE_URL" "$SCRATCH/r" 2>/dev/null \
     || git clone -q --bare "$REMOTE_URL" "$SCRATCH/r" 2>/dev/null; then
    PLANREPO="$SCRATCH/r"
    ok "scratch clone ready (nothing in $REPO was touched)"
  else
    die "could not reach $REMOTE_URL to resolve $TARGET_REF for the dry run"
  fi
else
  # Fetching writes into an icb-owned .git, so it needs sudo — and mickeyger's
  # sudo is password-required. Ask for the password ONCE here, with a message
  # saying why, rather than letting a bare prompt appear mid-script and look
  # like a hang. The credential is then cached for the rest of the run.
  say "  $TARGET_REF is not in prod's object store yet — fetching (needs sudo)."
  say "  ${BLD}sudo will ask for your password now.${RST}"
  sudo -v || die "sudo declined — nothing has changed"
  # NOT --quiet. A silent multi-second network fetch immediately after a
  # password prompt looks exactly like a hang, and the operator's instinct at
  # that moment is Ctrl-C — which is what happened on the first real run. The
  # fetch itself is harmless either way, but an interrupt here leaves the
  # operator unsure whether anything was applied. Show that work is happening.
  say "  fetching from origin (a few seconds)…"
  sudo -u icb git -C "$REPO" fetch origin --tags --progress 2>&1 | sed 's/^/    /'
  ok "fetched — nothing has been applied yet, the plan comes next"
fi
TARGET=$(git -C "$PLANREPO" rev-parse "${TARGET_REF}^{commit}" 2>/dev/null) \
  || die "ref '$TARGET_REF' not found even after fetch"
ok "$TARGET_REF = ${TARGET:0:8}"

if [ "$CURRENT" = "$TARGET" ]; then
  say ""; ok "already at ${TARGET:0:8} — nothing to deploy."
  exit 0
fi
git -C "$PLANREPO" merge-base --is-ancestor "$CURRENT" "$TARGET" \
  || die "$TARGET_REF is NOT ahead of the deployed commit — this would not be a fast-forward. Use icb-rollback.sh to go backwards."

# ── 2. work out what this deploy actually needs ──────────────────────────────
step "2. plan"
CHANGED=$(git -C "$PLANREPO" diff --name-only "$CURRENT".."$TARGET")
NEW_MIGRATIONS=$(git -C "$PLANREPO" diff --name-only --diff-filter=A "$CURRENT".."$TARGET" -- 'backend/alembic/versions/*' || true)
N_COMMITS=$(git -C "$PLANREPO" rev-list --count "$CURRENT".."$TARGET")

n_frontend=$(printf '%s\n' "$CHANGED" | grep -c '^frontend/'          || true)
n_pycode=$(printf  '%s\n' "$CHANGED" | grep -c '^backend/.*\.py$'     || true)
n_deps=$(printf    '%s\n' "$CHANGED" | grep -cE 'requirements.*\.txt$|(^|/)package(-lock)?\.json$' || true)
n_env=$(printf     '%s\n' "$CHANGED" | grep -c '\.env\.example$'      || true)

NEED_MIGRATE=0; [ -n "$NEW_MIGRATIONS" ] && NEED_MIGRATE=1
NEED_BUILD=0;   [ "$n_frontend" -gt 0 ] && NEED_BUILD=1
NEED_RESTART=0; { [ "$n_pycode" -gt 0 ] || [ "$NEED_MIGRATE" -eq 1 ]; } && NEED_RESTART=1
[ "$FORCE_RESTART" -eq 1 ] && NEED_RESTART=1

say "  ${CURRENT:0:8} -> ${TARGET:0:8}   ($N_COMMITS commit(s), $(printf '%s\n' "$CHANGED" | grep -c . || true) file(s))"
git -C "$PLANREPO" log --oneline "$CURRENT".."$TARGET" | sed 's/^/    /'
say ""
say "  DB migration     $([ "$NEED_MIGRATE" -eq 1 ] && echo "YES — $(printf '%s\n' "$NEW_MIGRATIONS" | xargs -n1 basename | tr '\n' ' ')" || echo 'no  (no new files in backend/alembic/versions/)')"
say "  SPA rebuild      $([ "$NEED_BUILD"   -eq 1 ] && echo "YES — $n_frontend file(s) under frontend/" || echo 'no  (frontend/ untouched)')"
if [ "$NEED_RESTART" -eq 1 ]; then
  say "  Service restart  YES — $([ "$FORCE_RESTART" -eq 1 ] && echo 'forced' || { [ "$n_pycode" -gt 0 ] && echo "$n_pycode Python file(s) changed" || echo 'a migration runs'; })"
else
  say "  Service restart  no  (no Python changed; templates + static reload from disk)"
fi
[ "$n_deps" -gt 0 ] && warn "dependency manifests changed ($n_deps) — check whether pip/npm install is needed BEFORE continuing"
[ "$n_env"  -gt 0 ] && warn ".env.example changed — prod .env is Marnus-owned: APPEND missing keys only, never overwrite"

if [ "$DRY_RUN" -eq 1 ]; then say ""; ok "dry run — nothing changed."; exit 0; fi

if [ "$ASSUME_YES" -eq 0 ]; then
  say ""
  printf 'Proceed with this deploy? [y/N] '
  read -r reply </dev/tty || die "no terminal to confirm on — re-run with --yes if you are sure"
  case "$reply" in y|Y|yes|YES) ;; *) die "aborted by operator (nothing has changed)" ;; esac
fi

# Get the sudo credential NOW, in one clearly-labelled place, before anything
# mutates. Otherwise the first prompt lands mid-deploy — at the npm build or the
# restart — where a surprise password request is easy to mistake for a failure,
# and where declining leaves prod half-updated. Skipped when the fetch above
# already validated sudo in this run.
if ! sudo -n true 2>/dev/null; then
  say ""
  say "  ${BLD}sudo will ask for your password now${RST} (build + restart need it)."
  sudo -v || die "sudo declined — nothing has changed"
fi

ROLLBACK_FILE=/tmp/icb-rollback-$(date +%Y%m%d-%H%M%S).txt
printf '%s\n' "$CURRENT" > "$ROLLBACK_FILE"
say ""; say "  rollback anchor ${CURRENT:0:8} saved to $ROLLBACK_FILE"

# ── 3. backup before touching the DB ─────────────────────────────────────────
if [ "$NEED_MIGRATE" -eq 1 ]; then
  step "3. database backup (a migration is about to run)"
  sudo systemctl start icb-pg-backup.service
  sleep 5
  sudo systemctl status icb-pg-backup.service --no-pager | tail -4 || true
  BEFORE_REV=$(sudo bash -c "set -a; . $ENV_FILE; set +a; cd $REPO/backend && $REPO/.venv/bin/alembic current" 2>/dev/null | tail -1)
  ok "schema before: ${BEFORE_REV:-unknown}"
else
  step "3. database backup — skipped (no migration in this range)"
fi

# ── 4. code ──────────────────────────────────────────────────────────────────
step "4. fast-forward the code"
sudo -u icb git -C "$REPO" merge --ff-only "$TARGET"
NOW=$(git -C "$REPO" rev-parse HEAD)
# Verify by SHA. `git describe` names the newest tag reachable, which is not
# necessarily the one being deployed (0dd4075 carries both v1.47.2 and v1.48.0).
[ "$NOW" = "$TARGET" ] || die "HEAD is ${NOW:0:8}, expected ${TARGET:0:8}"
ok "at ${TARGET:0:8} (verified by SHA, not by git describe)"

# ── 5. migrations ────────────────────────────────────────────────────────────
if [ "$NEED_MIGRATE" -eq 1 ]; then
  step "5. alembic upgrade head"
  sudo bash -c "set -a; . $ENV_FILE; set +a; cd $REPO/backend && $REPO/.venv/bin/alembic upgrade head"
  AFTER_REV=$(sudo bash -c "set -a; . $ENV_FILE; set +a; cd $REPO/backend && $REPO/.venv/bin/alembic current" 2>/dev/null | tail -1)
  ok "schema after: ${AFTER_REV:-unknown}"
else
  step "5. migrations — skipped"
fi

# ── 6. SPA build ─────────────────────────────────────────────────────────────
if [ "$NEED_BUILD" -eq 1 ]; then
  step "6. npm run build"
  sudo -u icb bash -lc "cd $REPO/frontend && npm run build"
  ok "bundle rebuilt: $(ls -t "$REPO"/frontend/dist/assets/index-*.js 2>/dev/null | head -1 | xargs -r basename)"
else
  step "6. SPA build — skipped (frontend/ untouched in this range)"
fi

# ── 7. restart ───────────────────────────────────────────────────────────────
if [ "$NEED_RESTART" -eq 1 ]; then
  step "7. restart $SERVICE"
  STAMP_BEFORE=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
  say "  active since (before): ${STAMP_BEFORE:-unknown}"
  sudo systemctl restart "$SERVICE"
  sleep 6
  STAMP_AFTER=$(systemctl show "$SERVICE" -p ActiveEnterTimestamp --value)
  say "  active since (after):  ${STAMP_AFTER:-unknown}"
  # `is-active` alone reports the OLD process as healthy if the restart failed
  # to take, so compare the start timestamps.
  [ "$STAMP_AFTER" != "$STAMP_BEFORE" ] || die "the service did not actually restart — ActiveEnterTimestamp is unchanged"
  [ "$(systemctl is-active "$SERVICE")" = "active" ] || die "$SERVICE is not active after restart"
  ok "restarted"
else
  step "7. restart — skipped (nothing loaded at import time changed)"
fi

# ── 8. verify ────────────────────────────────────────────────────────────────
step "8. verify"
if [ "$NEED_RESTART" -eq 1 ]; then
  # `icb` is not in `adm`, so journalctl needs sudo to see the unit's log.
  STARTED=$(sudo journalctl -u "$SERVICE" --since '-2 min' --no-pager | grep -c 'Application startup complete' || true)
  FAILED=$(sudo journalctl  -u "$SERVICE" --since '-2 min' --no-pager | grep -c 'BOOTSTRAP FAILED'          || true)
  say "  workers started      $STARTED (expected $EXPECTED_WORKERS)"
  say "  BOOTSTRAP FAILED     $FAILED (expected 0)"
  [ "$STARTED" -ge "$EXPECTED_WORKERS" ] || warn "fewer workers than expected — check: sudo journalctl -u $SERVICE -n 100"
  [ "$FAILED" -eq 0 ] || die "$FAILED worker(s) logged BOOTSTRAP FAILED — permission seeding raced; see the bootstrap advisory-lock fix"
fi
CODE=$(curl -k -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)
say "  $HEALTH_URL -> $CODE"
[ "$CODE" = "200" ] || die "health check returned $CODE"
ok "healthy"

# ── done ─────────────────────────────────────────────────────────────────────
say ""
say "${GRN}${BLD}DEPLOYED${RST}  ${CURRENT:0:8} -> ${TARGET:0:8}  ($TARGET_REF)"
say ""
say "Rollback (code-only — additive migrations are left in place deliberately):"
# $0 may be anywhere — the script is often run from ~ before it exists in the
# repo (deploy/prod/ is not on prod until the commit adding it is deployed), and
# its sibling icb-rollback.sh may simply not be there. Naming a path that does
# not exist is worst at exactly this moment, so only offer the script if it is
# really present, and always print a fallback that needs no script at all.
_rb=""
for _c in "$(dirname "$0")/icb-rollback.sh" "$REPO/deploy/prod/icb-rollback.sh"; do
  [ -x "$_c" ] && { _rb="$_c"; break; }
done
if [ -n "$_rb" ]; then
  say "    $_rb ${CURRENT:0:8}"
  say ""
  say "  or, without the script:"
else
  say "  (icb-rollback.sh is not on this box yet — use the commands directly:)"
fi
say "    sudo -u icb git -C $REPO reset --hard ${CURRENT:0:8}"
[ "$NEED_BUILD" -eq 1 ] && \
  say "    sudo -u icb bash -lc 'cd $REPO/frontend && npm run build'   # this range touched frontend/"
say "    sudo systemctl restart $SERVICE"
say ""
