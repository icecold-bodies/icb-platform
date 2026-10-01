#!/bin/bash
# rt2_export.sh simulation, run as root in WSL:  bash run_export_sim.sh <branch>
# The REAL rt2_export.sh + mkstage_export.sh run in a private mount namespace (fake /opt, /etc, /tmp). psql is a stub;
# the venv python is the real python3 except for the two steps that need prod's database (the id/name check and
# export_snapshot itself), which the stub answers — the export step copies the committed 12-body CI snapshot, so the
# REAL no-people gate and the REAL PU summary run on real data. The door report is a stub. git is real.
set -u
BR=${1:?usage: bash run_export_sim.sh <branch>}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt2simE-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.59.2:refs/tags/v1.59.2" || exit 1
git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
KIT=$(git rev-parse HEAD); TAGC=$(git rev-parse "v1.59.2^{commit}")
bash ops/prod-rt2/mkstage_export.sh "$SIM/stageout" "$KIT" "$TAGC" | sed -n '1,6p' || exit 1
tar -xf "$SIM/stageout/icb-rt2-export.tar" -C "$SIM/tmp" || exit 1
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.59.2:refs/tags/v1.59.2" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TAGC" || exit 1
git show "$KIT:backend/tests/costing_audit/mes_snapshot/all.json" > "$SIM/state/fake_all.json" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
S=$SIMSTATE
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT a read-only session"; exit 3;; esac
if [ "${1:-}" = - ]; then
  script=$(cat)
  case "$script" in
    *'WANT = {12: "MEAT HANGER LARGE"'*)
      [ -f "$S/bad_body" ] && { echo "15: expected 'RHINORANGE TRAILER', prod has ('RHINORANGE OLD', True)"; exit 1; }
      echo "   session read-only: on"; echo "    15 RHINORANGE TRAILER          active=True   (stub)"; exit 0 ;;
    *'export_snapshot([12, 15'*)
      cp "$S/fake_all.json" "$2" && echo "[snapshot] all.json: (stub — the committed 12-body file)"; exit $? ;;
    *) printf '%s' "$script" | python3 - "${@:2}"; exit $? ;;
  esac
fi
case "${1:-}" in */rt1_door_report.py) echo "SUMMARY: 14 OK; no exceptions (stub)"; exit 0 ;; esac
exec python3 "$@"
EOF
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session"; exit 3;; esac
while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
case "$sql" in
  *current_database*) echo icb_platform ;;
  *alembic_version*) echo 0049 ;;
  *"where b.id = 5284"*) cat "$S/r7" ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF
chmod +x "$SIM/bin/"* "$SIM/opt/icb-platform/.venv/bin/python"
run() { rm -rf "$SIM/tmp/icb-rt2-export"/out-*
        unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' && bash /tmp/icb-rt2-export/rt2_export.sh" > "$SIM/last.log" 2>&1
        grep -E '^######## ' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run); if [[ "$got" =~ $2 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 14; fi; }

echo "34|DRD PU|0.06" > "$SIM/state/r7"
expect "R7 not yet set (0.06)"  'STOP \[R7\]'
echo "34|DRD PU|0.041" > "$SIM/state/r7"
expect "happy path"             'DONE'
grep -q "gate ok: test_snapshot_has_no_personal_columns" "$SIM/last.log" && echo "        the REAL no-people gate ran on the file"
grep -E "^   active PU foam cost lines" "$SIM/last.log" | sed 's/^/        summary: /'
grep -q "^r7_bom_5284  34|DRD PU|0.041" "$SIM/last.log" && echo "        MANIFEST records R7"
touch "$SIM/state/bad_body"
expect "a body renamed"         'STOP \[BODIES\]'
rm -f "$SIM/state/bad_body"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"        'STOP \[CODE\]'
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TAGC"
expect "back on v1.59.2"        'DONE'
echo x >> "$SIM/tmp/icb-rt2-export/rt2_export.sh"
expect "tampered kit"           'STOP \[KIT\]'
echo "== $P passed, $F failed · SIM=$SIM"
