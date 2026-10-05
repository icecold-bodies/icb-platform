#!/bin/bash
# rt4_prewindow.sh simulation, run as root in WSL:  bash run_prewindow_sim.sh [branch]
# The REAL rt4_prewindow.sh + mkstage_prewindow.sh in a private mount namespace (fake /opt at v1.60.0, /etc, /tmp);
# psql and the prod-only python steps are stubs (rt4_prewindow.py's logic is proven by backend/tests/
# test_rt4_prewindow.py on the database); the no-people gate runs for real on the stub's export; git is real.
# Cleans its own /root folder at the end (the C: lesson).
set -u
BR=${1:-rt4/prewindow}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt4simP-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.60.0:refs/tags/v1.60.0" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt4/mkstage_prewindow.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
grep '^staged' "$SIM/stage.log"
tar -xf "$SIM/stageout/icb-rt4-prewindow.tar" -C "$SIM/tmp" || exit 1
grep -q '^BASE_RUN=33$' "$SIM/tmp/icb-rt4-prewindow/expected.env" && echo "PASS  the stager read the baseline run #33 from RT3's committed compare" \
  || echo "FAIL  BASE_RUN: $(grep BASE_RUN "$SIM/tmp/icb-rt4-prewindow/expected.env")"
PROD=$(git rev-parse "v1.60.0^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.60.0:refs/tags/v1.60.0" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
echo "$*" >> "$SIMSTATE/python.log"
case "$1" in
  */rt4_prewindow.py)
    case "$2" in
      facts)
        [ -f "$SIMSTATE/facts_crash" ] && { echo "Traceback (stub): boom"; exit 1; }
        echo '{"generated_at": "x", "trailer_ids": [26], "tables": {"trailer_types": [{"id": 26, "name": "CHILLER MEDIUM"}]}}' > "$3/now_snapshot.json"
        echo "== (a1) stub" > "$3/facts.txt"; cat "$SIMSTATE/facts_extra" >> "$3/facts.txt" 2>/dev/null
        echo '{"verdict": {}}' > "$3/facts.json"; echo '{}' > "$3/snapshot_diff.json"
        printf 'a: DRAFT NODES ONLY · stub\nb: #25 OK; #26 OK\n' > "$3/verdicts.txt"; exit 0 ;;
      cells)
        echo "baseline: page run #$5 (stub)" > "$3/cells.txt"; cat "$3/cells.txt"
        echo "d: no cell moved since page run #$5 (stub)" >> "$3/verdicts.txt"; exit 0 ;;
    esac ;;
  */rt1_door_report.py) cat "$SIMSTATE/door_report"; exit "$(cat "$SIMSTATE/door_rc")" ;;
  -m) if [ "$2" = tools.costing_audit ]; then
        p=$5; d=$9; s=${11}
        [ -f "$SIMSTATE/crash_$p" ] && { echo "Traceback (stub)"; exit 2; }
        echo "- Cells: 10 (stub $p)" > "$d/$s.md"; echo '{"cells": []}' > "$d/$s.json"; exit 0
      fi ;;
esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
echo 0051 > "$SIM/state/alembic"
printf 'read_only session: on\nSUMMARY: 14 OK; no exceptions\n' > "$SIM/state/door_report"; echo 0 > "$SIM/state/door_rc"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) exit 3 ;; esac
PS
chmod +x "$SIM/bin/psql"
run() { sleep 1; : > "$SIM/state/python.log"
        unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' && bash /tmp/icb-rt4-prewindow/rt4_prewindow.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 14; fi; }
check() { if eval "$2"; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); fi; }

expect "over v1.60.0, every check clean"        '^######## DONE — copy back'
T=$(ls -t "$SIM/tmp/icb-rt4-prewindow/"out-*.tar | head -n1)
check "the no-people gate ran for real on the export" "grep -q 'gate ok: test_snapshot_has_no_email_addresses' '$SIM/last.log'"
check "four answers a, b, c, d in order" "[ \"\$(sed -n '/the four answers/,\$p' '$SIM/last.log' | grep -oE '^   [abcd]:' | tr -d ' :\n')\" = abcd ]"
check "c reads 14 OK" "grep -q 'c: runs (exit 0) and reads SUMMARY: 14 OK' '$SIM/last.log'"
check "the five packs ran, --env prod, then the compare against #33" \
  "[ \"\$(grep -c 'tools.costing_audit run --pack .* --env prod' '$SIM/state/python.log')\" = 5 ] && grep -q 'cells .* 33\$' '$SIM/state/python.log'"
check "the tar carries the answers" "tar -tf '$T' | grep -q verdicts.txt && tar -tf '$T' | grep -q door_report.txt && tar -tf '$T' | grep -q now_snapshot.json"

printf 'read_only session: on\nSUMMARY: 13 OK; 26 CHILLER MEDIUM: NO THICKNESS\n' > "$SIM/state/door_report"
expect "door report not 14 OK -> a finding, the rest still runs" 'DONE, WITH FINDINGS'
check "  ... and it says so" "grep -q 'c: !! runs (exit 0) but does NOT read 14 OK: SUMMARY: 13 OK' '$SIM/last.log'"
echo 1 > "$SIM/state/door_rc"; printf 'Traceback: KeyError\n' > "$SIM/state/door_report"
expect "door report crashes -> a finding" 'DONE, WITH FINDINGS'
check "  ... named as FAILED" "grep -q 'c: !! the door report FAILED (exit 1)' '$SIM/last.log'"
echo 0 > "$SIM/state/door_rc"; printf 'read_only session: on\nSUMMARY: 14 OK; no exceptions\n' > "$SIM/state/door_report"

touch "$SIM/state/facts_crash"
expect "facts crash -> (c) and (d) still run" 'DONE, WITH FINDINGS'
check "  ... a and b DID NOT RUN, c and d answered" "grep -q 'a: !! DID NOT RUN' '$SIM/last.log' && grep -q 'c: runs' '$SIM/last.log' && grep -q '   d: no cell moved' '$SIM/last.log'"
rm -f "$SIM/state/facts_crash"
touch "$SIM/state/crash_freezers"
expect "an audit pack crashes -> (d) is a finding" 'DONE, WITH FINDINGS'
check "  ... naming the pack" "grep -q 'd: !! the audit crashed on: freezers(exit 2)' '$SIM/last.log'"
rm -f "$SIM/state/crash_freezers"
echo "backup label: ask jan.smit@example.co.za" > "$SIM/state/facts_extra"
expect "email-shaped value in the facts" 'STOP \[GATE\]'
check "  ... the facts were deleted" "! ls '$SIM'/tmp/icb-rt4-prewindow/out-*/facts.txt 2>/dev/null | xargs -r grep -l 'jan.smit' | grep -q ."
rm -f "$SIM/state/facts_extra"
echo 0050 > "$SIM/state/alembic"
expect "alembic not 0051"          'STOP \[DB\]'
echo 0051 > "$SIM/state/alembic"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"           'STOP \[CODE\]'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
echo x >> "$SIM/tmp/icb-rt4-prewindow/rt4_prewindow.py"
expect "tampered kit"              'STOP \[KIT\]'
check "no __pycache__ in the fake repo" "[ -z \"\$(find '$SIM/opt/icb-platform' -name __pycache__ | head -n1)\" ]"
echo "== $P passed, $F failed · SIM=$SIM (removed)"
rm -rf "$SIM"
