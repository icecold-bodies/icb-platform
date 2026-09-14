#!/usr/bin/env bash
# v1.53.1 prod deploy kit - shared constants + helpers. Sourced, never run.
# Everything that identifies the release is PINNED here; nothing is inferred.

TARGET_SHA="94ed70b17ed69d0000ddf7cd4c6c44759e4a192e"   # #186 v1.53.1 (includes #184, #185)
BASE_SHA="04b332f8c9ad6a4bc5d4c3cd2bea428d3589eea5"     # prod checkout found by the 14 Sep audit
DEPLOY_LINE="origin/backport/v1.39-base"
JS_SHA_TARGET="23f2471931502a40d0f49dab93dfd0e70b648b7db54ac4335448f39eba4e1bd0"   # sha256(calculator.js, CR-stripped) @ 94ed70b
JS_SHA_BASE="5e466646789db3486b1ddb85756525790cfc12e87c881445f899f75c969dedb4"     # @ 04b332f (== e5c7837, what prod serves today)
V_TARGET="180"
V_BASE="178"
ALEMBIC_HEAD="0047"

REPO="${ICB_REPO:-/opt/icb-platform}"
ENV_FILE="${ICB_ENV_FILE:-/etc/icb/backend.env}"
PY="${ICB_PY:-$REPO/.venv/bin/python}"
ALEMBIC="${ICB_ALEMBIC:-$REPO/.venv/bin/alembic}"
SERVICE="${ICB_SERVICE:-icb-backend}"
SUDO="${ICB_SUDO-sudo}"                 # "" in a local simulation
AS_ICB="${ICB_AS_ICB-sudo -u icb}"      # the repo is icb-owned; "" in a local simulation
SERVED_URLS="${ICB_SERVED_URLS:-https://127.0.0.1 https://192.168.0.251 http://127.0.0.1:8000}"
CF_URL="${ICB_CF_URL:-https://mes.icecoldgrp.online}"
HEALTH_URL="${ICB_HEALTH_URL:-https://127.0.0.1/health}"

GIT="git --no-optional-locks -c safe.directory=$REPO -C $REPO"
JS="$REPO/backend/app/static/js/calculator.js"
TPL="$REPO/backend/app/templates/calculator.html"
SETTINGS_TPL="$REPO/backend/app/templates/admin_visual_configurator_settings.html"

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s ==\n' "$*"; }
ok()   { printf '  OK   %s\n' "$*"; }
bad()  { printf '  FAIL %s\n' "$*"; FAILS=$((FAILS + 1)); }
FAILS=0

sha_file() { tr -d '\r' < "$1" | sha256sum | cut -d' ' -f1; }   # CR-stripped so any checkout style compares equal

head_sha()      { $GIT rev-parse HEAD 2>/dev/null; }
tracked_dirty() { $GIT status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' '; }
service_ts()    { systemctl show "$SERVICE" -p ActiveEnterTimestamp --value 2>/dev/null; }

alembic_current() {   # read-only: prints the alembic current line(s); stderr kept in $OUT/alembic_current.err
  if [ -n "${ICB_ALEMBIC_FAKE:-}" ]; then echo "$ICB_ALEMBIC_FAKE"; return 0; fi
  $SUDO bash -c 'set -a; . "$1"; set +a; cd "$2/backend" && PYTHONDONTWRITEBYTECODE=1 "$3" current' \
    _ "$ENV_FILE" "$REPO" "$ALEMBIC" 2>>"${OUT:-/tmp}/alembic_current.err"
}

# served_sha URL -> prints "http=<code> curl=<exit> sha=<sha256|->" for /static/js/calculator.js?v=<tag>
served_sha() {
  local base="$1" tag="$2" tmp code cerr
  tmp="$(mktemp)"
  code="$(curl -sk --max-time 30 -o "$tmp" -w '%{http_code}' "$base/static/js/calculator.js?v=$tag" 2>/dev/null)"
  cerr=$?
  if [ "$cerr" = "0" ] && [ "$code" = "200" ] && [ -s "$tmp" ]; then
    printf 'http=%s curl=%s bytes=%s sha=%s' "$code" "$cerr" "$(wc -c < "$tmp" | tr -d ' ')" "$(sha_file "$tmp")"
  else
    printf 'http=%s curl=%s bytes=0 sha=-' "${code:-none}" "$cerr"
  fi
  rm -f "$tmp"
}

# release_state: classify local changes by CONTENT, not by name. Sets four newline lists:
#   MOD_RELEASE   tracked files modified to exactly their 94ed70b content (a half-written fast-forward)
#   MOD_OTHER     any other tracked modification (a hand edit - never destroyed by this kit)
#   UNTR_RELEASE  untracked files at paths 94ed70b ADDS, with exactly their 94ed70b content
#   UNTR_OTHER    untracked files at those paths with different content
release_state() {
  MOD_RELEASE=""; MOD_OTHER=""; UNTR_RELEASE=""; UNTR_OTHER=""
  local p want have
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    want="$($GIT rev-parse -q --verify "$TARGET_SHA:$p" 2>/dev/null)"
    have="$($GIT hash-object -- "$p" 2>/dev/null)"
    if [ -n "$want" ] && [ "$want" = "$have" ]; then MOD_RELEASE="$MOD_RELEASE$p"$'\n'; else MOD_OTHER="$MOD_OTHER$p"$'\n'; fi
  done < <($GIT diff --name-only HEAD 2>/dev/null)
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    [ -e "$REPO/$p" ] || continue
    $GIT ls-files --error-unmatch -- "$p" >/dev/null 2>&1 && continue      # tracked at HEAD: not untracked
    want="$($GIT rev-parse -q --verify "$TARGET_SHA:$p" 2>/dev/null)"
    have="$($GIT hash-object -- "$p" 2>/dev/null)"
    if [ -n "$want" ] && [ "$want" = "$have" ]; then UNTR_RELEASE="$UNTR_RELEASE$p"$'\n'; else UNTR_OTHER="$UNTR_OTHER$p"$'\n'; fi
  done < <(tr -d '\r' < "$KIT/expected_added.txt")
}
list_paths() { printf '%s' "$1" | sed '/^$/d; s/^/    /'; }

RECORD="$KIT/DEPLOYED_94ed70b"
write_record() { printf '%s run=%s head=%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$RUN_ID" "$(head_sha)" "$1" > "$RECORD"; }
record_matches_head() { [ -f "$RECORD" ] && grep -q "head=$(head_sha) " "$RECORD"; }

confirm() {   # confirm WORD "prompt"
  if [ "${ICB_ASSUME_YES:-}" = "$1" ]; then say "(confirmed by ICB_ASSUME_YES=$1)"; return 0; fi
  printf '\n%s\nType %s to continue (anything else aborts): ' "$2" "$1"
  local answer
  read -r answer
  [ "$answer" = "$1" ]
}

# Results folder + publish-on-every-exit (same proven pattern as the audit kit).
init_run() {   # init_run ACTION RUN_ID
  ACTION="$1"
  RUN_ID="${2:-$(date +%Y%m%d-%H%M%S)}"
  case "$RUN_ID" in *[!0-9-]*|"") echo "FATAL: RUN_ID must be digits/dashes"; exit 2;; esac
  OUT="$KIT/out-$RUN_ID"
  if [ -e "$OUT" ]; then echo "FATAL: $OUT already exists (RUN_ID reused) - rerun with a new RUN_ID"; exit 2; fi
  rm -rf "$KIT/out-latest"
  mkdir -p "$OUT" || { echo "FATAL: cannot create $OUT"; exit 2; }
  echo "$RUN_ID" > "$OUT/RUN_ID"
  echo "$ACTION" > "$OUT/ACTION"
  LOG="$OUT/$ACTION.log"
  RC=0
  exec 3>&1 4>&2
  exec > >(tee -a "$LOG") 2>&1
  TEE_PID=$!
  trap 'publish_run' EXIT
  trap 'RC=130; exit 130' INT
  trap 'RC=143; exit 143' TERM HUP
  say "v1.53.1 prod $ACTION run=$RUN_ID - $(date '+%Y-%m-%d %H:%M:%S %Z') host=$(hostname) user=$(id -un)"
}

publish_run() {
  echo "$RC" > "$OUT/EXIT_CODE"
  if [ "$RC" = "0" ]; then
    echo "=== $ACTION COMPLETE run=$RUN_ID exit=0 ==="
  else
    echo "=== $ACTION DID NOT COMPLETE run=$RUN_ID exit=$RC - read the log above before doing anything else ==="
  fi
  # flush: close our end of the tee pipe, wait for tee to finish writing the log, THEN publish
  exec 1>&3 2>&4
  wait "$TEE_PID" 2>/dev/null
  rm -rf "$KIT/out-latest" && cp -r "$OUT" "$KIT/out-latest"
}

die() { say ""; say "STOP: $1"; RC="${2:-1}"; exit "$RC"; }
