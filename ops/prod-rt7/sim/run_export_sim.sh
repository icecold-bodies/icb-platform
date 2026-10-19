#!/bin/bash
# rt7_export.sh simulation, run as root in WSL:  bash run_export_sim.sh <branch> <reports-dir>
# The REAL rt7_export.sh + mkstage_export.sh + ops/lib/icb_where.sh + rt7_inventory.py + rt7_summary.py in
# private mount + UTS namespaces (fake /opt, /etc, /tmp; the hostname set per scenario). psql and the venv python are
# stubs that refuse a session that is not read-only or an app import without the env file's values; `audit run`
# copies saved prod reports (<reports-dir>); the stdin precheck answers from the sim's factor; the 15-body export
# copies the committed snapshot; git is real.
# What it proves: the FIRST line names machine, database, HEAD and the BOOT TIME; a wrong place, a kit staged before
# the last boot, an unstamped kit, a 4G factor that is not EXACTLY '1.3170731707317074' (rounded, or F2's old value),
# and an export carrying an email are each refused; the happy path tars its output with no env value in it. Cleans its
# own folder at the end (the WSL disk lesson).
set -u
BR=${1:-rt7/audit-truth}
REPORTS=${2:?reports dir}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt7simE-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
trap 'rm -rf "$SIM"' EXIT
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
# the worktree's branch lives in the main clone's repository (WSL git cannot read a Windows worktree's .git file)
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.61.0:refs/tags/v1.61.0" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
# KITREF stages another commit's kit with this commit's sim — the negative control (KITREF=e1e6d37: the kit that
# stopped on prod on 16 Oct must stop here too)
bash ops/prod-rt7/mkstage_export.sh "$SIM/stageout" "${KITREF:-HEAD}" > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
grep -m1 '^staged' "$SIM/stage.log"
PROD=$(git rev-parse "v1.61.0^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.61.0:refs/tags/v1.61.0" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
cp "$SIM/opt/icb-platform/backend/tests/costing_audit/mes_snapshot/all.json" "$SIM/state/snapshot.json"
mkdir -p "$SIM/state/reports" && cp "$REPORTS"/prod_*.json "$SIM/state/reports/" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in -c|-m|-)    # the real app's Settings: both values must be in the ENVIRONMENT (16 Oct, the first prod paste)
  [ -n "${DATABASE_URL:-}" ] && [ -n "${SESSION_SECRET:-}" ] \
    || { echo "pydantic_core._pydantic_core.ValidationError: 2 validation errors for Settings (stub)"; exit 1; } ;;
esac
if [ "$1" = -c ]; then exit 0; fi
if [ "$1" = - ]; then                  # a heredoc program on stdin: the precheck, or the 15-body export
  prog=$(cat)
  case "$prog" in
    *pu_foam_4g_factor*)
      f=$(cat "$SIMSTATE/factor")
      echo "   session read-only: on"
      echo "   costings.pu_foam_4g_factor = '$f'  updated_at 2026-10-19 09:31:07  (expected '$WANT_FACTOR' = 5400/4100)"
      [ "$f" = "$WANT_FACTOR" ] || { echo "FACTOR: the 4G factor reads '$f', not exactly '$WANT_FACTOR' (stub)"; exit 1; }
      exit 0 ;;
    *export_snapshot*)
      case "$prog" in *"[12, 15, 16, 17, 18, 19, 20, 21, 24, 25, 26, 27, 34, 36, 37]"*) ;; *) echo "stub: not the 15 bodies"; exit 5;; esac
      cp "$SIMSTATE/snapshot.json" "$2"; echo "[snapshot] all.json: (stub copy, 15 bodies)"; exit 0 ;;
  esac
  echo "stub: unknown stdin program"; exit 4
fi
if [ "$1" = -m ] && [ "$2" = tools.costing_audit ]; then
  cmd=$3; shift 3; out=; stem=; pack=
  while [ $# -gt 0 ]; do case "$1" in --out) out=$2; shift;; --stem) stem=$2; shift;; --pack) pack=$2; shift;; esac; shift; done
  case "$cmd" in
    run) cp "$SIMSTATE/reports/prod_$pack.json" "$out/$stem.json"; echo "- Cells: (stub copy of $pack)" > "$out/$stem.md"; exit 1 ;;
    snapshot) cp "$SIMSTATE/snapshot.json" "$out"; echo "[snapshot] $(basename "$out"): (stub copy)"; exit 0 ;;
  esac
  exit 4
fi
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
printf 'DATABASE_URL=postgresql+psycopg://icb_app:s3cret-not-real@127.0.0.1:5432/icb_platform\nSESSION_SECRET=zzz-not-real\n' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
echo icb_platform > "$SIM/state/db"; echo 0053 > "$SIM/state/alembic"; echo 1.3170731707317074 > "$SIM/state/factor"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only" >&2; exit 3;; esac
case "$*" in
  *current_database*) cat "$SIMSTATE/db" ;;
  *alembic_version*) cat "$SIMSTATE/alembic" ;;
  *transaction_read_only*) echo on ;;
  *) exit 3 ;;
esac
PS
chmod +x "$SIM/bin/psql"
tar -xf "$SIM/stageout/icb-rt7-export.tar" -C "$SIM/tmp" || exit 1
BOOT=$(awk '/^btime/{print $2}' /proc/stat)
cp -a "$SIM/tmp/icb-rt7-export" "$SIM/pristine"

run() {  # run [hostname] [as-user]
  local hn=${1:-icb-mes-prod} user=${2:-root}
  sleep 1
  rm -rf "$SIM/tmp/icb-rt7-export"; cp -a "$SIM/pristine" "$SIM/tmp/icb-rt7-export"
  date +%s > "$SIM/tmp/icb-rt7-export/.staged_at"           # what the copy line writes after unpacking
  ${MUTATE:-true}
  unshare -m -u bash -c "hostname '$hn' && mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
      export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' &&
      if [ '$user' = root ]; then bash /tmp/icb-rt7-export/rt7_export.sh; else chmod -R a+rX /tmp/icb-rt7-export; runuser -u '$user' -- bash /tmp/icb-rt7-export/rt7_export.sh; fi" > "$SIM/last.log" 2>&1
}
first() { head -n 1 "$SIM/last.log"; }
verdict() { grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; tail -n 8 "$SIM/last.log" | sed 's/^/       | /'; }
row() {  # row <name> <regex for the verdict> [<regex for the first line>]
  local v f; v=$(verdict); f=$(first)
  if [[ "$v" =~ $2 ]] && [[ "$f" =~ ${3:-^######## RT7 build export } ]]; then ok "$1: $v"
  else bad "$1"; echo "       first:   $f"; echo "       verdict: $v"; fi
}

echo "== scenarios (boot epoch $BOOT)"
BOOTTXT=$(date -d "@$BOOT" '+%Y-%m-%d %H:%M:%S %Z')
run; row "happy" '^######## DONE' "^######## RT7 build export \(read only\) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head ${PROD:0:7} · boot $BOOTTXT · "
L="$SIM/tmp/icb-rt7-export"; O=$(ls -d "$L"/out-*/ 2>/dev/null | tail -n1); O=${O%/}
[ -n "$O" ] && [ -s "$O/all.json" ] && [ -s "$L/$(basename "$O").tar" ] && ok "out folder, all.json and the tar exist" || bad "no output"
grep -rq 'not-real\|s3cret' "$O" && bad "a secret value reached the output" || ok "no env value in any output file"
grep -q 'gate ok: test_snapshot_has_no_email_addresses' "$O/inventory.txt" && grep -q '^   bill_of_materials ' "$O/inventory.txt" \
  && ok "inventory: the four gates + every table" || bad "inventory"
grep -q 'FLAG  .*FREEZER MEDIUM .*DRD DOOR FITTINGS .*CSLB HINGES' "$O/summary.txt" && grep -q '^All (chillers + freezers + icecream + explosive): 2702 cells' "$O/summary.txt" \
  && ok "summary groups the FLAG cells; All = 2702 cells" || { bad "summary"; head -n 20 "$O/summary.txt"; }
grep -q "costings.pu_foam_4g_factor = '1.3170731707317074'  updated_at " "$O/precheck.txt" \
  && ok "precheck prints the factor's exact text and its updated_at" || { bad "precheck"; cat "$O/precheck.txt"; }
for f in 1.317073170731707 1.361219512195122 1.3170731707317073; do
  echo "$f" > "$SIM/state/factor"; run; row "factor '$f' refused" "STOP \[FACTOR\]: the 4G factor reads '$f', not exactly '1.3170731707317074'"
done
echo 1.3170731707317074 > "$SIM/state/factor"
run dev-laptop; row "wrong machine" "STOP \[WHERE\]: WRONG PLACE — machine is 'dev-laptop'" "^######## RT7 build export \(read only\) · machine dev-laptop "
echo icb > "$SIM/state/db"; run; row "wrong database" "STOP \[WHERE\]: WRONG PLACE — database is 'icb'"; echo icb_platform > "$SIM/state/db"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD~1"; run; row "wrong HEAD" "STOP \[WHERE\]: WRONG PLACE — code is at"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
MUTATE="eval echo $((BOOT - 60)) > $SIM/tmp/icb-rt7-export/.staged_at" run
row "kit staged before the last boot" "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*, before this machine's last boot"
MUTATE="rm -f $SIM/tmp/icb-rt7-export/.staged_at" run; row "unstamped kit" 'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp'
run icb-mes-prod nobody; row "not root" 'STOP \[KIT\]: run with sudo'
echo 0052 > "$SIM/state/alembic"; run; row "wrong alembic" 'STOP \[DB\]: alembic_version is .0052.'; echo 0053 > "$SIM/state/alembic"
MUTATE="truncate -s 100 $SIM/tmp/icb-rt7-export/rt7_summary.py" run; row "tampered stage" 'STOP \[KIT\]: staged files do not match'
cp "$SIM/etc/icb/backend.env" "$SIM/state/env.good"; grep -v '^SESSION_SECRET=' "$SIM/state/env.good" > "$SIM/etc/icb/backend.env"
run; row "env file without SESSION_SECRET" 'STOP \[KIT\]: /etc/icb/backend.env did not provide DATABASE_URL and SESSION_SECRET'
cp "$SIM/state/env.good" "$SIM/etc/icb/backend.env"
cp "$SIM/state/snapshot.json" "$SIM/state/snapshot.good"
python3 - "$SIM/state/snapshot.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1])); d["tables"]["materials"][0]["notes_x"] = "ask someone@example.com"
json.dump(d, open(sys.argv[1], "w"))
EOF
run; row "email in the export" 'STOP \[GATE\]: the no-people gate FAILED'
O=$(ls -d "$L"/out-*/ | tail -n1); [ ! -e "${O%/}/all.json" ] && ok "the refused export was removed" || bad "the refused export is still on disk"
cp "$SIM/state/snapshot.good" "$SIM/state/snapshot.json"
echo
echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
