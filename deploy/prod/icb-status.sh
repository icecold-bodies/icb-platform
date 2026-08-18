#!/usr/bin/env bash
#
# ICB MES — what is actually on production right now. Read-only, changes nothing.
#
#   ./icb-status.sh              no sudo needed
#   ./icb-status.sh --with-db    also reports the alembic revision (needs sudo:
#                                the DB URL lives in root-gated /etc/icb/backend.env)
#
set -uo pipefail

REPO=/opt/icb-platform
SERVICE=icb-backend
ENV_FILE=/etc/icb/backend.env
HEALTH_URL=https://127.0.0.1/health

BLD=$'\033[1m'; RST=$'\033[0m'
WITH_DB=0
[ "${1:-}" = "--with-db" ] && WITH_DB=1

printf '%s— code —%s\n' "$BLD" "$RST"
HEAD=$(git -C "$REPO" rev-parse HEAD 2>/dev/null)
printf '  HEAD        %s  %s\n' "${HEAD:0:8}" "$(git -C "$REPO" log -1 --format=%s "$HEAD" 2>/dev/null | cut -c1-60)"
printf '  committed   %s\n' "$(git -C "$REPO" log -1 --format=%cd --date=format:'%Y-%m-%d %H:%M' "$HEAD" 2>/dev/null)"
printf '  branch      %s\n' "$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"

# Every tag pointing exactly here. `git describe` shows only one, and this repo
# has commits carrying two tags (0dd4075 is both v1.47.2 and v1.48.0), so the
# single name describe picks can mislead about what was deployed.
TAGS=$(git -C "$REPO" tag --points-at HEAD 2>/dev/null | tr '\n' ' ')
printf '  tags here   %s\n' "${TAGS:-<none — this commit is untagged>}"
printf '  describe    %s\n' "$(git -C "$REPO" describe --tags 2>/dev/null || echo '-')"

# Only tracked modifications matter — untracked build droppings (.npm-cache/,
# __pycache__) are normal on prod and do not block a fast-forward.
DIRTY=$(git -C "$REPO" status --porcelain --untracked-files=no 2>/dev/null | wc -l)
if [ "$DIRTY" -gt 0 ]; then
  printf '  tree        %sDIRTY — %s modified tracked file(s); a deploy will refuse%s\n' "$BLD" "$DIRTY" "$RST"
  git -C "$REPO" status --short --untracked-files=no 2>/dev/null | head -10 | sed 's/^/                /'
else
  UNTRACKED=$(git -C "$REPO" ls-files --others --exclude-standard 2>/dev/null | wc -l)
  printf '  tree        clean (%s untracked path(s), ignored)\n' "$UNTRACKED"
fi

printf '\n%s— behind origin —%s\n' "$BLD" "$RST"
# ls-remote, not fetch: this script runs as mickeyger, who cannot write to
# icb-owned .git. ls-remote is read-only and needs no local write at all.
REMOTE_URL=$(git -C "$REPO" config --get remote.origin.url 2>/dev/null)
REFS=$(git -C "$REPO" ls-remote --heads --tags origin 2>/dev/null)
if [ -n "$REFS" ]; then
  HEAD_REF=$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)
  TIP=$(printf '%s\n' "$REFS" | awk -v b="refs/heads/$HEAD_REF" '$2==b {print $1}')
  if [ -n "$TIP" ]; then
    if [ "$TIP" = "$HEAD" ]; then
      printf '  origin/%s is at the deployed commit — nothing pending\n' "$HEAD_REF"
    else
      printf '  origin/%s is at %s — deployed is %s\n' "$HEAD_REF" "${TIP:0:8}" "${HEAD:0:8}"
      # The commits themselves may not be in prod's object store yet (no fetch),
      # so name the tip rather than pretending to list the range.
      printf '  %sthere is newer code on origin — run a --dry-run to see the plan%s\n' "$BLD" "$RST"
    fi
  fi
  NEWEST=$(printf '%s\n' "$REFS" | awk '$2 ~ /^refs\/tags\/v/ && $2 !~ /\^\{\}$/ {print $2}' \
           | sed 's|refs/tags/||' | sort -V | tail -1)
  printf '  newest tag on origin: %s\n' "${NEWEST:-<none>}"
  printf '  tag(s) on the deployed commit: %s\n' "${TAGS:-<none>}"
else
  printf '  (could not reach %s)\n' "${REMOTE_URL:-origin}"
fi

printf '\n%s— service —%s\n' "$BLD" "$RST"
printf '  %-12s %s\n' "$SERVICE" "$(systemctl is-active $SERVICE 2>/dev/null)"
printf '  active since %s\n' "$(systemctl show $SERVICE -p ActiveEnterTimestamp --value 2>/dev/null)"
printf '  health       %s -> %s\n' "$HEALTH_URL" "$(curl -k -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null)"
VER=$(curl -k -s "$HEALTH_URL" 2>/dev/null)
printf '  reports      %s\n' "${VER:-<no body>}"

printf '\n%s— SPA bundle —%s\n' "$BLD" "$RST"
BUNDLE=$(ls -t "$REPO"/frontend/dist/assets/index-*.js 2>/dev/null | head -1)
if [ -n "$BUNDLE" ]; then
  printf '  %s\n' "$(basename "$BUNDLE")"
  printf '  built       %s\n' "$(date -r "$BUNDLE" '+%Y-%m-%d %H:%M' 2>/dev/null)"
else
  printf '  <no built bundle found>\n'
fi

if [ "$WITH_DB" -eq 1 ]; then
  printf '\n%s— database —%s\n' "$BLD" "$RST"
  REV=$(sudo bash -c "set -a; . $ENV_FILE; set +a; cd $REPO/backend && $REPO/.venv/bin/alembic current" 2>/dev/null | tail -1)
  printf '  alembic     %s\n' "${REV:-<could not read — sudo declined?>}"
  printf '  last backup %s\n' "$(systemctl show icb-pg-backup -p ExecMainExitTimestamp --value 2>/dev/null)"
else
  printf '\n  (run with --with-db for the alembic revision — needs sudo)\n'
fi
printf '\n'
