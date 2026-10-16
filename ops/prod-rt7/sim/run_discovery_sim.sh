#!/bin/bash
# rt7_discovery.sh simulation, run as root in WSL:  bash run_discovery_sim.sh <branch> <reports-dir>
# The REAL rt7_discovery.sh + mkstage_discovery.sh + ops/lib/icb_where.sh + rt7_inventory.py + rt7_summary.py in
# private mount + UTS namespaces (fake /opt, /etc, /tmp; the hostname set per scenario). psql and the venv python are
# stubs that refuse a session that is not read-only; `audit run` copies saved prod reports (<reports-dir>, the RT6
# window's), `audit snapshot` copies the committed snapshot; git is real.
# What it proves: the FIRST line names machine, database, HEAD and the BOOT TIME; a wrong place, a kit staged before
# the last boot, an unstamped kit and an export carrying an email are each refused; the happy path tars its output
# with no env value in it. Cleans its own folder at the end (the WSL disk lesson).
set -u
BR=${1:-rt7/audit-truth}
REPORTS=${2:?reports dir}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt7simD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
trap 'rm -rf "$SIM"' EXIT
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
# the worktree's branch lives in the main clone's repository (WSL git cannot read a Windows worktree's .git file)
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.61.0:refs/tags/v1.61.0" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt7/mkstage_discovery.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
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
if [ "$1" = -c ]; then exit 0; fi
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
echo icb_platform > "$SIM/state/db"; echo 0053 > "$SIM/state/alembic"
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
tar -xf "$SIM/stageout/icb-rt7-discovery.tar" -C "$SIM/tmp" || exit 1
BOOT=$(awk '/^btime/{print $2}' /proc/stat)
cp -a "$SIM/tmp/icb-rt7-discovery" "$SIM/pristine"

run() {  # run [hostname] [as-user]
  local hn=${1:-icb-mes-prod} user=${2:-root}
  sleep 1
  rm -rf "$SIM/tmp/icb-rt7-discovery"; cp -a "$SIM/pristine" "$SIM/tmp/icb-rt7-discovery"
  date +%s > "$SIM/tmp/icb-rt7-discovery/.staged_at"           # what the copy line writes after unpacking
  ${MUTATE:-true}
  unshare -m -u bash -c "hostname '$hn' && mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
      export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' &&
      if [ '$user' = root ]; then bash /tmp/icb-rt7-discovery/rt7_discovery.sh; else chmod -R a+rX /tmp/icb-rt7-discovery; runuser -u '$user' -- bash /tmp/icb-rt7-discovery/rt7_discovery.sh; fi" > "$SIM/last.log" 2>&1
}
first() { head -n 1 "$SIM/last.log"; }
verdict() { grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1"; tail -n 8 "$SIM/last.log" | sed 's/^/       | /'; }
row() {  # row <name> <regex for the verdict> [<regex for the first line>]
  local v f; v=$(verdict); f=$(first)
  if [[ "$v" =~ $2 ]] && [[ "$f" =~ ${3:-^######## RT7 discovery } ]]; then ok "$1: $v"
  else bad "$1"; echo "       first:   $f"; echo "       verdict: $v"; fi
}

echo "== scenarios (boot epoch $BOOT)"
BOOTTXT=$(date -d "@$BOOT" '+%Y-%m-%d %H:%M:%S %Z')
run; row "happy" '^######## DONE' "^######## RT7 discovery \(read only\) · machine icb-mes-prod · db icb_platform @ 127.0.0.1:5432 · head ${PROD:0:7} · boot $BOOTTXT · "
L="$SIM/tmp/icb-rt7-discovery"; O=$(ls -d "$L"/out-*/ 2>/dev/null | tail -n1); O=${O%/}
[ -n "$O" ] && [ -s "$O/all.json" ] && [ -s "$L/$(basename "$O").tar" ] && ok "out folder, all.json and the tar exist" || bad "no output"
grep -rq 'not-real\|s3cret' "$O" && bad "a secret value reached the output" || ok "no env value in any output file"
grep -q 'gate ok: test_snapshot_has_no_email_addresses' "$O/inventory.txt" && grep -q '^   bill_of_materials ' "$O/inventory.txt" \
  && ok "inventory: the four gates + every table" || bad "inventory"
grep -q 'FLAG  .*FLOOR .*2\*300 INT LAMINATION' "$O/summary.txt" && grep -q '^All (chillers + freezers + icecream + explosive): 2702 cells' "$O/summary.txt" \
  && ok "summary groups the FLAG cells; All = 2702 cells" || { bad "summary"; head -n 20 "$O/summary.txt"; }
run dev-laptop; row "wrong machine" "STOP \[WHERE\]: WRONG PLACE — machine is 'dev-laptop'" "^######## RT7 discovery \(read only\) · machine dev-laptop "
echo icb > "$SIM/state/db"; run; row "wrong database" "STOP \[WHERE\]: WRONG PLACE — database is 'icb'"; echo icb_platform > "$SIM/state/db"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD~1"; run; row "wrong HEAD" "STOP \[WHERE\]: WRONG PLACE — code is at"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
MUTATE="eval echo $((BOOT - 60)) > $SIM/tmp/icb-rt7-discovery/.staged_at" run
row "kit staged before the last boot" "STOP \[WHERE\]: WRONG PLACE — the kit was staged .*, before this machine's last boot"
MUTATE="rm -f $SIM/tmp/icb-rt7-discovery/.staged_at" run; row "unstamped kit" 'STOP \[WHERE\]: WRONG PLACE — the kit has no staging stamp'
run icb-mes-prod nobody; row "not root" 'STOP \[KIT\]: run with sudo'
echo 0052 > "$SIM/state/alembic"; run; row "wrong alembic" 'STOP \[DB\]: alembic_version is .0052.'; echo 0053 > "$SIM/state/alembic"
MUTATE="truncate -s 100 $SIM/tmp/icb-rt7-discovery/rt7_summary.py" run; row "tampered stage" 'STOP \[KIT\]: staged files do not match'
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
