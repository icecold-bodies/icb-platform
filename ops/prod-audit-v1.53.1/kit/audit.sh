#!/usr/bin/env bash
# v1.53.1 PROD AUDIT - master-bound draft-flag shadowing. READ-ONLY.
#
# Runs ON the prod VM (192.168.0.251) from the kit folder:
#     bash ~/icb-prod-audit-v1531/audit.sh [RUN_ID]
# RUN_ID is the launcher's timestamp (so the fetch can prove the results are
# from this run); when omitted, the VM's own timestamp is used.
#
# sudo is used only to read /etc/icb/backend.env (root-only) for the read-only
# Python audit, and to chown that step's output back to you.
#
# Writes ONLY inside this kit folder (out-<RUN_ID>/, out-latest/, LAST_RUN).
# Deliberately no `set -e` / pipefail: every step reports its own exit code and
# a failed probe never hides the rest. Results are published on EVERY exit path,
# and the previous out-latest is removed first, so a failed run can never be
# mistaken for an old successful one.

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${ICB_REPO:-/opt/icb-platform}"
ENV_FILE="${ICB_ENV_FILE:-/etc/icb/backend.env}"
PY="${ICB_PY:-$REPO/.venv/bin/python}"
SUDO="${ICB_SUDO-sudo}"
RUN_ID="${1:-$(date +%Y%m%d-%H%M%S)}"
case "$RUN_ID" in *[!0-9-]*) echo "FATAL: RUN_ID must be digits/dashes"; exit 2;; esac
OUT="$KIT/out-$RUN_ID"
rc=0

if [ -e "$OUT" ]; then echo "FATAL: $OUT already exists (RUN_ID reused) - rerun with a new RUN_ID"; exit 2; fi
rm -rf "$KIT/out-latest" "$KIT/LAST_RUN"
mkdir -p "$OUT" || { echo "FATAL: cannot create $OUT"; exit 2; }
echo "$RUN_ID" > "$OUT/RUN_ID"
CODE="$OUT/00_code_state.txt"

publish() {
  rm -rf "$KIT/out-latest" && cp -r "$OUT" "$KIT/out-latest"
  echo "$OUT" > "$KIT/LAST_RUN"
  echo ""
  echo "================================ SUMMARY ================================"
  sed -n '1,14p' "$CODE" 2>/dev/null
  echo "..."
  if [ -f "$OUT/SUMMARY.txt" ]; then cat "$OUT/SUMMARY.txt"; else echo "(no database summary - see $OUT)"; fi
  echo "========================================================================="
  echo "Full results: $OUT  (copied to $KIT/out-latest)"
  if [ "$rc" = "0" ]; then
    echo "=== AUDIT COMPLETE (read-only) run=$RUN_ID exit=0 ==="
  else
    echo "=== AUDIT INCOMPLETE (read-only, nothing written) run=$RUN_ID exit=$rc - results are NOT usable ==="
  fi
}
trap publish EXIT
trap 'rc=130; exit 130' INT
trap 'rc=143; exit 143' TERM HUP

say() { printf '%s\n' "$*" | tee -a "$CODE"; }
step() { say ""; say "-- $* --"; }

say "v1.53.1 prod audit (read-only) run=$RUN_ID - $(date '+%Y-%m-%d %H:%M:%S %Z')"
say "host=$(hostname) user=$(id -un) kit=$KIT repo=$REPO"

# -- 0. code state: what is prod actually serving? ----------------------------
GIT="git --no-optional-locks -c safe.directory=$REPO -C $REPO"   # no index refresh writes
step "git checkout"
$GIT rev-parse HEAD 2>&1 | tee -a "$CODE"
$GIT log -1 --format='%h %ad %s' --date=iso 2>&1 | tee -a "$CODE"
say "branch/detached: $($GIT symbolic-ref -q --short HEAD 2>/dev/null || echo DETACHED)"
say "tracked changes: $($GIT status --porcelain --untracked-files=no 2>/dev/null | wc -l)"
for sha in e9dd6da e5c7837 04b332f 197863f 41d5986 94ed70b; do
  if $GIT cat-file -e "$sha^{commit}" 2>/dev/null; then
    if $GIT merge-base --is-ancestor "$sha" HEAD 2>/dev/null; then r="ancestor-of-HEAD"; else r="NOT in HEAD"; fi
  else
    r="not fetched on this VM"
  fi
  say "  $sha: $r"
done

JS="$REPO/backend/app/static/js/calculator.js"
TPL="$REPO/backend/app/templates/calculator.html"
markers() {   # $1 = file
  printf '_draftFlagVariables=%s _masterBodyVarNameSet=%s flagVarDefault=%s' \
    "$(grep -c _draftFlagVariables "$1" 2>/dev/null)" "$(grep -c _masterBodyVarNameSet "$1" 2>/dev/null)" \
    "$(grep -c flagVarDefault "$1" 2>/dev/null)"
}
fhash() { tr -d '\r' < "$1" | sha256sum | cut -c1-16; }   # $1 = file; CR-stripped so a CRLF checkout compares equal

step "calculator.js on disk"
say "  bytes=$(wc -c < "$JS" 2>/dev/null) $(markers "$JS") sha256=$(fhash "$JS")"
say "  template tag(s): $(grep -o 'calculator\.js?v=[0-9]*' "$TPL" 2>/dev/null | tr '\n' ' ')"

step "calculator.js as SERVED (what browsers get)"
TMPJS="$OUT/.served.js"
for url in "https://127.0.0.1/static/js/calculator.js" "https://192.168.0.251/static/js/calculator.js" "http://127.0.0.1:8000/static/js/calculator.js"; do
  code="$(curl -sk --max-time 30 -o "$TMPJS" -w '%{http_code}' "$url" 2>/dev/null)"
  cerr=$?
  if [ "$cerr" = "0" ] && [ "$code" = "200" ] && [ -s "$TMPJS" ]; then
    say "  $url: http=200 bytes=$(wc -c < "$TMPJS") $(markers "$TMPJS") sha256=$(fhash "$TMPJS")"
  else
    say "  $url: http=${code:-none} curl_exit=$cerr (no complete bundle - not comparable)"
  fi
  rm -f "$TMPJS"
done
say "  openapi.json: http=$(curl -sk -o /dev/null -w '%{http_code}' --max-time 10 https://127.0.0.1/openapi.json 2>/dev/null)"

step "service"
systemctl show icb-backend -p ActiveEnterTimestamp -p MainPID -p ActiveState 2>&1 | tee -a "$CODE"

# -- 1. database audit (read-only python, app's own DATABASE_URL) -------------
step "database audit (read-only)"
if [ ! -x "$PY" ]; then say "FATAL: python not found at $PY"; rc=2; exit $rc; fi
if [ -n "$SUDO" ]; then
  $SUDO bash -c 'set -a; . "$1"; set +a; cd "$2/backend" && PGOPTIONS="-c default_transaction_read_only=on" PYTHONDONTWRITEBYTECODE=1 "$3" -B "$4/prod_audit.py" --out "$5"' \
    _ "$ENV_FILE" "$REPO" "$PY" "$KIT" "$OUT"
  rc=$?
  $SUDO chown -R "$(id -u):$(id -g)" "$OUT" 2>/dev/null
else
  ( set -a; . "$ENV_FILE"; set +a; cd "$REPO/backend" && PGOPTIONS="-c default_transaction_read_only=on" PYTHONDONTWRITEBYTECODE=1 "$PY" -B "$KIT/prod_audit.py" --out "$OUT" )
  rc=$?
fi
say "database audit exit=$rc"
exit $rc
