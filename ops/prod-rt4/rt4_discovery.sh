#!/usr/bin/env bash
# RT4 §3.0 — the Manni sections (Part B) + the unauthenticated answers (Part C). READ ONLY on prod. The operator runs,
# on the VM:
#
#     sudo bash /tmp/icb-rt4-discovery/rt4_discovery.sh
#
#   1. rt4_discovery.py (psycopg only, one read-only session): the five Mannis — v2, every section with its line
#      count, door / insulation masters, the draft's section keys, saved-costing counts — the E3 sweep of every
#      Manni section name against the 14 standard bodies, who else uses each non-standard section, and what deleted
#      id 41 left behind.
#   2. the five Mannis' pricing rows, exported for the CA's mirror (the audit tool's own exporter, read-only session)
#      + the no-people gate on the written file.
#   3. GET-only probe, NO session, of the routes in noauth_probe_paths.txt on the three doors (127.0.0.1, LAN,
#      Cloudflare): status, bytes, type, CF cache status, Location. No response body is kept.
#
# Against icb_platform it only SELECTs (every session read-only). Writes only under /tmp/icb-rt4-discovery/.
# No service is touched and nothing under /opt/icb-platform changes: not a deploy.
# Selects no customer, contact, end-user, user or person column (calculations are counted only).
#
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u
BASE=/tmp/icb-rt4-discovery
STAGE=$BASE/stage/backend
TS=$(date +%Y%m%d-%H%M%S)
OUT=$BASE/out-$TS
PY=/opt/icb-platform/.venv/bin/python
DOORS="https://127.0.0.1 https://192.168.0.251 https://mes.icecoldgrp.online"
stop() { echo; echo "######## STOP [$1]: $2"; [ -d "$OUT" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA: $OUT"; exit 1; }
say()  { echo "== $*"; }

[ "$(id -u)" = 0 ] || stop KIT "run with sudo (the env file is root-readable only)"
[ -z "${RT4_DISCOVERY_TEST_IDS:-}" ] || stop KIT "RT4_DISCOVERY_TEST_IDS is set (tests only) — unset it"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
# shellcheck disable=SC1091
. "$BASE/expected.env" || stop KIT "expected.env unreadable"
for v in EXPECT_HEADS EXPECT_ALEMBIC STAGED_FROM; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
[ -e "$OUT" ] && stop KIT "$OUT already exists (two runs in one second?): run again"
mkdir -p "$OUT" && chmod 700 "$OUT" || stop KIT "cannot create $OUT"
exec > >(tee -a "$OUT/run.txt") 2>&1
[ -r /etc/icb/backend.env ] || stop KIT "/etc/icb/backend.env not readable"
set -a; . /etc/icb/backend.env; set +a
[ -n "${DATABASE_URL:-}" ] || stop KIT "DATABASE_URL not set"
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
# every session below is read-only (libpq reads PGOPTIONS; the app sets no `options`)
export PGOPTIONS='-c default_transaction_read_only=on'
export PYTHONDONTWRITEBYTECODE=1
DBNAME=$(psql "$URL" -XAtc "select current_database()") || stop DB "cannot reach the database"
[ "$DBNAME" = icb_platform ] || stop DB "database is '$DBNAME', expected icb_platform"
ALEMBIC=$(psql "$URL" -XAtc "select string_agg(version_num, ',') from alembic_version") || stop DB "cannot read alembic_version"
[ "$ALEMBIC" = "$EXPECT_ALEMBIC" ] || stop DB "alembic_version is '$ALEMBIC', expected $EXPECT_ALEMBIC"
# Under sudo git refuses the icb-owned repo as "dubious ownership" unless the path is trusted (read-only).
HEAD=$(git -c safe.directory=/opt/icb-platform -C /opt/icb-platform rev-parse HEAD 2>/dev/null || echo '?')
case " $EXPECT_HEADS " in *" $HEAD "*) ;; *) stop CODE "prod's code is ${HEAD:0:7}, expected one of: $EXPECT_HEADS" ;; esac
say "prod: db=$DBNAME alembic=$ALEMBIC code=${HEAD:0:7} staged=${STAGED_FROM:0:7} $(date -Is)"

# ---- 1. the Manni facts + the E3 section sweep + id 41 --------------------------------------------------------
say "1. discovery (read-only session)"
"$PY" "$BASE/rt4_discovery.py" "$URL" "$OUT" > "$OUT/discovery.log" 2>&1; rc=$?
grep -E '^== |^   #|^   (ok|NON) |⚠|rows left|standard 14' "$OUT/discovery.log" | head -n 80
[ $rc = 0 ] || { tail -n 20 "$OUT/discovery.log"; stop DISCOVERY "the discovery failed (exit $rc)"; }
# discovery.json carries the Mannis' draft trees (configuration text): no email-shaped value may leave the VM
EM=$(grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' "$OUT/discovery.json" || true)
[ "$EM" = 0 ] || { rm -f "$OUT/discovery.json" "$OUT/discovery.txt" "$OUT/discovery.log"; stop GATE "an email-shaped value in discovery.json — files deleted"; }
echo "   gate ok: no email-shaped value in discovery.json"

# ---- 2. the five Mannis' pricing rows, for the CA's mirror -----------------------------------------------------
say "2. export of the five Mannis' pricing rows (read-only session)"
cd "$STAGE" || stop KIT "cd $STAGE"
export PYTHONPATH=/opt/icb-platform/backend
WHERE=$("$PY" -c "import tools.costing_audit as t; print(t.__file__)" 2>&1 | tail -n1)
case "$WHERE" in "$STAGE"/*) ;; *) stop IMPORT "the audit tool does not import from the staged copy: $WHERE" ;; esac
IDS=$("$PY" - "$OUT/discovery.json" <<'PY'
import json, sys
WANT = {"MANNI BAKKI RIGIDS", "MANNI DF", "MANNI RIGIDS CB", "MANNI RIGIDS FB", "MANNI TRAILERS"}
d = json.load(open(sys.argv[1], encoding="utf-8"))
five = {b["name"]: b["id"] for b in d["bodies"] if b["name"] in WANT}
print(",".join(str(five[n]) for n in sorted(five)) if set(five) == WANT else "")
PY
)
if [ -z "$IDS" ]; then
  echo "   SKIPPED: the five Manni names are not exactly present (see discovery.txt §1) — nothing exported"
else
  echo "   ids: $IDS"
  "$PY" - "$OUT/manni_snapshot.json" "$IDS" <<'PY' || { rm -f "$OUT/manni_snapshot.json"; stop SNAPSHOT "the export failed or was refused"; }
import sys
from pathlib import Path
from tools.costing_audit.mes_snapshot import export_snapshot
export_snapshot([int(x) for x in sys.argv[2].split(",")], Path(sys.argv[1]))
PY
  "$PY" - "$OUT/manni_snapshot.json" <<'PY' || { rm -f "$OUT/manni_snapshot.json"; stop GATE "no-people gate FAILED — file deleted"; }
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("gate", "tests/costing_audit/test_mes_snapshot_no_people.py")
gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
gate.SNAPSHOT = Path(sys.argv[1])
for name in ("test_the_gates_catch_a_known_hit", "test_snapshot_tables_are_pricing_definitions_only",
             "test_snapshot_has_no_personal_columns", "test_snapshot_has_no_email_addresses"):
    getattr(gate, name)()
    print(f"   gate ok: {name}")
PY
fi
cd "$BASE" || stop KIT "cd $BASE"

# ---- 3. what answers with NO session, on the three doors (GET only; no body kept) ------------------------------
say "3. GET with no session — door · local answer · status · bytes · type · cf-cache · location"
probe() { # $1 door, $2 path -> "status bytes type cfcache location" (each field '-' when absent)
  local w cf loc
  rm -f "$OUT/.h"
  w=$(curl -ks -o /dev/null --max-time 20 -D "$OUT/.h" -w '%{http_code} %{size_download} %{content_type}' "$1$2" 2>/dev/null)
  set -- $w
  cf=$(grep -i '^cf-cache-status:' "$OUT/.h" 2>/dev/null | tr -d '\r' | awk '{print $2}' | head -n1)
  loc=$(grep -i '^location:' "$OUT/.h" 2>/dev/null | tr -d '\r' | awk '{print $2}' | head -n1)
  echo "${1:-000} ${2:-0} ${3:--} ${cf:--} ${loc:--}"
}
{
  printf '%-30s %-5s %s\n' door local "status bytes type cf-cache location   path"
  grep -v '^#' "$BASE/noauth_probe_paths.txt" | while read -r want path; do
    [ -n "${path:-}" ] || continue
    for d in $DOORS; do printf '%-30s %-5s %s   %s\n' "$d" "$want" "$(probe "$d" "$path")" "$path"; done
  done
} > "$OUT/noauth_probe.txt"
rm -f "$OUT/.h"
# per door: how many paths answered exactly as the local code did
awk 'NR > 1 { k = $1 " " (($2 == $3) ? "same-as-local" : "DIFFERS"); n[k]++ } END { for (k in n) print "   " k ": " n[k] }' \
    "$OUT/noauth_probe.txt" | sort
awk 'NR > 1 && $2 != $3 { print "   differs: " $0 }' "$OUT/noauth_probe.txt" | head -n 40

( cd "$OUT" && sha256sum discovery.json discovery.txt noauth_probe.txt $( [ -f manni_snapshot.json ] && echo manni_snapshot.json ) > SHA256SUMS.out )
cat > "$OUT/MANIFEST.txt" <<EOF
database     $DBNAME
alembic      $ALEMBIC
prod_code    $HEAD
staged_from  $STAGED_FROM
manni_ids    ${IDS:-none (export skipped)}
finished     $(date -Is)
EOF
chmod -R a+rX "$OUT"
( cd "$BASE" && tar -cf "out-$TS.tar" "out-$TS" && chmod a+r "out-$TS.tar" ) || stop TAR "cannot tar $OUT"
echo; cat "$OUT/MANIFEST.txt"; echo
echo "######## DONE — copy back: $BASE/out-$TS.tar"
