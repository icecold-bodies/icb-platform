#!/bin/bash
# The RT4 window kits (All + doors + the S data kit's staging) simulation, run as root in WSL:
#     bash run_window_sim.sh [kit-branch]
# The REAL mkstage_window.sh (and through it mkstage_data.sh), rt2_all.sh and rt2_doors.sh run in a private mount
# namespace (fake /opt, /etc, /tmp, /var/backups). The audit CLI, the page-vs-CLI compare and the door report are
# stubs (as in RT2's run_all_sim.sh: the real compare is proven page = CLI on the mirror); psql and the venv python
# are stubs; git is real. Covers: v1.60.0 before the tag/deploy, v1.60.1 after, and C11 against an RT4 journal.
set -u
KIT=${1:-rt4/build}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt4simW-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state,varbackups/icb-rt2-2026-10,varbackups/icb-rt4-2026-10}
export SIMSTATE=$SIM/state
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$WIN/icb-platform" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" || exit 1
$G -C "$SIM/origin.git" fetch -q "$WIN/icb-platform" "+refs/tags/v1.60.0:refs/tags/v1.60.0" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$WIN/icb-platform" "$KIT" && git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin
TARGET=$(git rev-parse HEAD); PREV=$(git rev-parse "v1.60.0^{commit}")

echo "== phase 1: staged BEFORE the tag (window steps 1 and the doors over v1.60.0)"
bash ops/prod-rt4/mkstage_window.sh "$SIM/stageout" "$TARGET" | grep -E '^note|^EXPECT|^KEEP' || exit 1
[ ! -e "$SIM/stageout/icb-rt4-data.tar" ] && echo "        no S data kit before the tag (as designed)"
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
  printf -- '- Cells: PASS 10, SKIP 2\n' > "$out/$stem.md"; echo '{"cells": []}' > "$out/$stem.json"; exit 0
fi
case "${1:-}" in
  */rt2_all_compare.py) [ -n "${5:-}" ] || { echo "stub: rt2_all.sh passed no not-before time"; exit 3; }
    echo "$5" > "$S/not_before_seen"
    if [ -f "$S/page_started" ] && [ "$(cat "$S/page_started")" -lt "$5" ]; then   # the real rule (C11), tested in pytest
      echo "PAGE_EQUALS_CLI: no — the newest page run started before the last data change: click All first, then run again"; exit 2; fi
    echo "page run #9: All, passed (stub)"; echo "PAGE_EQUALS_CLI: yes"; exit 0 ;;
  */rt1_door_report.py) [ -s "${3:-}" ] || { echo "no snapshot"; exit 1; }; echo "SUMMARY: 14 OK; no exceptions (stub)"; exit 0 ;;
esac
exec python3 "$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIMSTATE/alembic"
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
    mount --bind '$SIM/varbackups' /var/backups &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && $cmd" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local label=$1 want=$2; shift 2; local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label :: $got"; P=$((P+1)); else echo "FAIL  $label :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 14; fi; }

expect "1 · all pre over v1.60.0"         'DONE \(pre\): PAGE = CLI'                all pre
expect "doors over v1.60.0"               'DONE'                                    doors

echo "== phase 2: the deploy happened (code v1.60.1, alembic 0051) — the pre-tag kits refuse the new code"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
expect "pre-tag kit over v1.60.1"         'STOP \[CODE\]'                           all post

echo "== phase 3: tag v1.60.1, re-staged (now with the S data kit)"
cd "$SIM/work" && git -c user.email=sim@x -c user.name=sim tag -f -a v1.60.1 -m sim "$TARGET" > /dev/null && git push -q -f origin v1.60.1
rm -rf "$SIM/stageout2" && mkdir -p "$SIM/stageout2" && bash ops/prod-rt4/mkstage_window.sh "$SIM/stageout2" "$TARGET" | grep -E '^staged|^S_TODO|^S_DRAFTS|^KEEP' || exit 1
[ -f "$SIM/stageout2/icb-rt4-data.tar" ] && tar -tf "$SIM/stageout2/icb-rt4-data.tar" | grep -q manifest_s.yaml \
  && echo "PASS  the S data kit is staged with the manifest" && P=$((P+1)) || { echo "FAIL  no S data kit"; F=$((F+1)); }
rm -rf "$SIM/tmp/icb-rt2-all" "$SIM/tmp/icb-rt2-doors"
tar -xf "$SIM/stageout2/icb-rt2-all.tar" -C "$SIM/tmp" && tar -xf "$SIM/stageout2/icb-rt2-doors.tar" -C "$SIM/tmp" || exit 1
expect "3 · all post over v1.60.1"        'DONE \(post\): PAGE = CLI'               all post
expect "7 · doors over v1.60.1"           'DONE'                                    doors

echo "== C11 against the RT4 journal folder: a page run older than S's apply is refused"
touch "$SIM/varbackups/icb-rt4-2026-10/journal_S_pricing_corrections_journal_prod_sim.json"
J=$(stat -c %Y "$SIM/varbackups/icb-rt4-2026-10/journal_S_pricing_corrections_journal_prod_sim.json")
echo $(( J - 600 )) > "$SIMSTATE/page_started"
expect "5 · page run before S"            'STOP \[PAGE\]'                           all afterS
[ "$(cat "$SIMSTATE/not_before_seen")" = "$J" ] && echo "PASS  C11 used the RT4 journal's time" && P=$((P+1)) \
  || { echo "FAIL  C11 saw $(cat "$SIMSTATE/not_before_seen"), the RT4 journal is $J"; F=$((F+1)); }
echo $(( J + 5 )) > "$SIMSTATE/page_started"
expect "5 · page run after S"             'DONE \(afterS\): PAGE = CLI'             all afterS
rm -f "$SIMSTATE/page_started"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "all: code moved"                  'STOP \[CODE\]'                           all afterS
expect "doors: code moved"                'STOP \[CODE\]'                           doors
echo "== $P passed, $F failed · SIM=$SIM"
