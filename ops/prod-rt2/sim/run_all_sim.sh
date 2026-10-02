#!/bin/bash
# rt2_all.sh + rt2_doors.sh simulation, run as root in WSL:  bash run_all_sim.sh [part-branch] [kit-branch]
# The REAL rt2_all.sh, rt2_doors.sh and mkstage_all.sh run in a private mount namespace (fake /opt, /etc, /tmp).
# The audit CLI, the page-vs-CLI compare and the door report are stubs (they need psycopg and prod's data; the real
# compare is proven page = CLI on the mirror, 2 702 of 2 702 cells, with a one-cell negative control); psql and the
# venv python are stubs; git is real. Covers both codes (v1.59.2 before the deploy, v1.59.3 after) and the stops.
set -u
PART=${1:-rt2/part2-reland}
KIT=${2:-rt2/release-v1.59.3}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt2simA-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
export SIMSTATE=$SIM/state
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$WIN/icb-platform" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" "$PART" && git merge -q --ff-only FETCH_HEAD || exit 1
$G fetch -q "$WIN/icb-platform" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD); PREV=$(git rev-parse "v1.59.2^{commit}")

echo "== phase 1: staged BEFORE the tag (window step 1 only)"
bash ops/prod-rt2/mkstage_all.sh "$SIM/stageout" "$TARGET" | grep -E '^note|^EXPECT' || exit 1
tar -xf "$SIM/stageout/icb-rt2-all.tar" -C "$SIM/tmp" && tar -xf "$SIM/stageout/icb-rt2-doors.tar" -C "$SIM/tmp" || exit 1

git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PREV" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
S=$SIMSTATE
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT a read-only session"; exit 3;; esac
if [ "${1:-}" = -m ] && [ "${2:-}" = tools.costing_audit ] && [ "${3:-}" = run ]; then
  pack=; out=; stem=; env=
  while [ $# -gt 0 ]; do case "$1" in --pack) pack=$2;; --out) out=$2;; --stem) stem=$2;; --env) env=$2;; esac; shift; done
  [ "$env" = prod ] || { echo "stub: --env prod expected"; exit 3; }
  [ "$(pwd)" = /opt/icb-platform/backend ] || { echo "stub: run from the deployed backend, not $(pwd)"; exit 3; }
  [ -f "$S/run_fail_$pack" ] && { echo "stub: $pack crashed"; exit 2; }
  printf -- '- Cells: PASS 10, SKIP 2\n' > "$out/$stem.md"; echo '{"cells": []}' > "$out/$stem.json"
  [ -f "$S/red_$pack" ] && exit 1; exit 0
fi
case "${1:-}" in
  */rt2_all_compare.py) echo "page run #7: All, passed (stub)"; echo "PAGE_EQUALS_CLI: $(cat "$S/cmp_word")"; exit "$(cat "$S/cmp_rc")" ;;
  */rt1_door_report.py) [ -s "${3:-}" ] || { echo "no snapshot"; exit 1; }; echo "SUMMARY: 14 OK; no exceptions (stub)"; exit 0 ;;
esac
exec python3 "$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0049 > "$SIMSTATE/alembic"; echo yes > "$SIMSTATE/cmp_word"; echo 0 > "$SIMSTATE/cmp_rc"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) echo "unknown SQL"; exit 3 ;; esac
EOF
chmod +x "$SIM/bin/"*
run() { # $1 = all|doors, rest = args
  sleep 1; local k=$1; shift
  local cmd="bash /tmp/icb-rt2-all/rt2_all.sh $*"; [ "$k" = doors ] && cmd="bash /tmp/icb-rt2-doors/rt2_doors.sh"
  unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && $cmd" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local label=$1 want=$2; shift 2; local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label :: $got"; P=$((P+1)); else echo "FAIL  $label :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 14; fi; }

expect "all pre over v1.59.2"            'DONE \(pre\): PAGE = CLI'                all pre
grep -c '^   [a-z]* exit=0' "$SIM/last.log" | sed 's/^/        packs run: /'
expect "a bad label"                     '^$'                                      all bogus
expect "doors over v1.59.2"              'DONE'                                    doors
echo 1 > "$SIMSTATE/cmp_rc"; echo no > "$SIMSTATE/cmp_word"
expect "the page and the CLI differ"     'DONE \(pre\): the page and the CLI DIFFER' all pre
echo 2 > "$SIMSTATE/cmp_rc"; echo "no — no finished 'All' run" > "$SIMSTATE/cmp_word"
expect "no page run"                     'STOP \[PAGE\]'                           all pre
echo 0 > "$SIMSTATE/cmp_rc"; echo yes > "$SIMSTATE/cmp_word"
touch "$SIMSTATE/red_explosive"
expect "unaccepted cells are reported"   'DONE \(pre\): PAGE = CLI'                all pre
grep -q 'NOTE: unaccepted cells in: explosive' "$SIM/last.log" && echo "        the NOTE names explosive"
rm -f "$SIMSTATE/red_explosive"; touch "$SIMSTATE/run_fail_icecream"
expect "a pack crashes"                  'STOP \[RUN\]: icecream exited 2'         all pre
rm -f "$SIMSTATE/run_fail_icecream"

echo "== phase 2: the deploy happened (code v1.59.3, alembic 0050) — the phase-1 kit refuses it"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"; echo 0050 > "$SIMSTATE/alembic"
expect "pre-tag kit over v1.59.3"        'STOP \[DB\]'                             all post
echo "== phase 3: re-staged after the tag"
cd "$SIM/work" && git -c user.email=sim@x -c user.name=sim tag -f -a v1.59.3 -m sim "$TARGET" > /dev/null && git push -q -f origin v1.59.3
rm -rf "$SIM/stageout2" && mkdir -p "$SIM/stageout2" && bash ops/prod-rt2/mkstage_all.sh "$SIM/stageout2" "$TARGET" | grep -E '^EXPECT' || exit 1
rm -rf "$SIM/tmp/icb-rt2-all" "$SIM/tmp/icb-rt2-doors"
tar -xf "$SIM/stageout2/icb-rt2-all.tar" -C "$SIM/tmp" && tar -xf "$SIM/stageout2/icb-rt2-doors.tar" -C "$SIM/tmp" || exit 1
expect "all post over v1.59.3"           'DONE \(post\): PAGE = CLI'               all post
expect "doors over v1.59.3"              'DONE'                                    doors
grep -q "SUMMARY: 14 OK" "$SIM/last.log" && echo "        the report's summary is printed"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "all: code moved"                 'STOP \[CODE\]'                           all afterP
expect "doors: code moved"               'STOP \[CODE\]'                           doors
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
echo x >> "$SIM/tmp/icb-rt2-doors/all.json"
expect "doors: tampered kit"             'STOP \[KIT\]'                            doors
echo x >> "$SIM/tmp/icb-rt2-all/rt2_all_compare.py"
expect "all: tampered kit"               'STOP \[KIT\]'                            all afterD
echo "== $P passed, $F failed · SIM=$SIM"
