#!/bin/bash
# rt5_notes.sh simulation, run as root in WSL:  bash run_notes_sim.sh [branch]
# The REAL rt5_notes.sh in a private mount namespace (fake /opt, /etc, /tmp, /var/backups). psql, pg_dump and the
# python tool are stubs: the stub tool keeps the two notes in a state file ("none" / "applied" / "other") and answers
# exactly as rt5_notes.py does (the real tool is proven against the _test database by backend/tests/
# test_rt5_notes_tool.py and rehearsed on the prod mirror). Cleans its own folder at the end (the RT4 disk lesson).
set -u
BR=${1:-rt5/build}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt5simN-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,backups,state}
trap 'rm -rf "$SIM"' EXIT
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "$BR" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
STAGED=$(git rev-parse HEAD)
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "$STAGED" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
PRODHEAD=$(git -C "$SIM/opt/icb-platform" rev-parse HEAD)

K="$SIM/tmp/icb-rt5-notes"; mkdir -p "$K"
for f in rt5_notes.sh rt5_notes.py; do git cat-file blob "$STAGED:ops/prod-rt5/$f" > "$K/$f"; done
mkdir -p "$K/lib" && git cat-file blob "$STAGED:ops/lib/icb_backup.sh" > "$K/lib/icb_backup.sh"   # RT6
cat > "$K/expected.env" <<EOF
EXPECT_HEAD=$PRODHEAD
EXPECT_ALEMBIC=0052
PLAN_TODO=2
TOOL_SHA=$(sha256sum "$K/rt5_notes.py" | cut -d' ' -f1)
STAGED_FROM=$STAGED
EOF
( cd "$K" && sha256sum rt5_notes.sh rt5_notes.py lib/icb_backup.sh expected.env > SHA256SUMS )

mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
# the rt5_notes.py stub: state in $SIMSTATE/notes = none | applied | other
S=$SIMSTATE
[ "$1" = -c ] && exit 0                                    # `python -c "import psycopg"`
shift                                                      # the tool path
st=$(cat "$S/notes"); mode=dry; out=; j=
while [ $# -gt 0 ]; do case "$1" in --apply) mode=apply;; --show) mode=show;; --revert) mode=revert; j=$2; shift;; --out-dir) out=$2; shift;; esac; shift; done
case "${PGOPTIONS:-}/$mode" in */apply|*/revert) ;; *default_transaction_read_only=on*) ;; *) [ "$mode" = dry ] || [ "$mode" = show ] && { echo "stub: dry/show must be read-only"; exit 3; } ;; esac
C="No PU insulation for Chillers"; F="Freezers: EPS insulation in the ROOF and FLOOR only, never in the SIDES, FRONT or doors"
echo "database icb_platform (--target prod); RT5 rule notes; plan sha256 stub"
[ "$st" = other ] && { echo "REFUSED: family 'CHILLER' (#5) already carries ANOTHER note 'typed': not overwritten"; exit 2; }
case "$mode" in
  dry)  if [ "$st" = applied ]; then echo "   ALREADY #5 CHILLER"; echo "   ALREADY #4 FREEZER"; echo "0 to apply, 2 already applied."
        else echo "   TODO    #5 CHILLER: None -> '$C'"; echo "   TODO    #4 FREEZER: None -> '$F'"; echo "2 to apply, 0 already applied."; fi ;;
  apply) [ "$st" = applied ] && { echo "APPLIED 0 note(s): "; exit 0; }
         echo applied > "$S/notes"; echo '{"tool": "rt5_notes", "rows": []}' > "$out/rt5_notes_journal_prod_20261006T060000Z.json"
         echo "APPLIED 2 note(s): #5 CHILLER; #4 FREEZER" ;;
  show) if [ "$st" = applied ]; then echo "   #5   CHILLER       3 active bodies · rule_note = '$C'"; else echo "   #5   CHILLER       3 active bodies · rule_note = None"; fi ;;
  revert) [ "$st" = applied ] || { echo "REFUSED: moved since"; exit 2; }; echo none > "$S/notes"; echo "REVERTED 2 note(s)"; echo '{}' > "$out/rt5_notes_revert_prod_x.json" ;;
esac
exit 0
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb" && echo 'DATABASE_URL=postgresql+psycopg://x:y@localhost/icb_platform' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
case "$*" in *current_database*) echo icb_platform ;; *alembic_version*) cat "$SIMSTATE/alembic" ;; *) exit 3 ;; esac
PS
cat > "$SIM/bin/pg_dump" <<'PD'
#!/bin/bash
[ -f "$SIMSTATE/fail_pgdump" ] && exit 1
echo "-- data-only dump (stub)"; echo "COPY icb_costings.trailer_groups (id, name, rule_note) FROM stdin;"; echo '\.'
PD
chmod +x "$SIM/bin/psql" "$SIM/bin/pg_dump"
echo 0052 > "$SIM/state/alembic"; echo none > "$SIM/state/notes"

run() { sleep 1
        unshare -m bash -c "mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
          mkdir -p /var/backups && mount --bind '$SIM/backups' /var/backups &&
          export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' && bash /tmp/icb-rt5-notes/rt5_notes.sh $*" > "$SIM/last.log" 2>&1
        grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
P=0; F=0
expect() { local got; got=$(run $2); if [[ "$got" =~ $3 ]]; then echo "PASS  $1 :: $got"; P=$((P+1)); else echo "FAIL  $1 :: $got"; F=$((F+1)); sed 's/^/   | /' "$SIM/last.log" | tail -n 14; fi; }
check() { if eval "$2"; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); fi; }

expect "dryrun before"                 dryrun 'DONE \(dryrun: 2 to apply, 0 already applied\.\)'
echo 1 > "$SIM/state/fail_pgdump"
expect "the backup fails"              apply  'STOP \[BACKUP\]'
check  "... and nothing was applied"   '[ "$(cat "$SIM/state/notes")" = none ]'
rm -f "$SIM/state/fail_pgdump"
expect "apply"                         apply  'DONE \(apply\)'
J=$(ls "$SIM"/backups/icb-rt5-2026-10/journal_notes_*.json 2>/dev/null | head -n1)
check  "journal + provenance + backup kept in /var/backups/icb-rt5-2026-10" \
       '[ -n "$J" ] && ls "$SIM"/backups/icb-rt5-2026-10/*.provenance.txt >/dev/null 2>&1 && ls "$SIM"/backups/icb-rt5-2026-10/pre_apply_notes_*.sql.gz >/dev/null 2>&1'
check  "the apply's second dry-run read '0 to apply, 2 already applied.'" 'grep -q "0 to apply, 2 already applied." "$SIM/last.log"'
expect "dryrun after = already applied" dryrun 'DONE \(dryrun: already applied\)'
expect "apply again = already applied"  apply  'DONE \(apply: already applied\)'
expect "show (the read-back)"           show   'DONE \(show\)'
check  "... carries the chiller note"   'grep -q "No PU insulation for Chillers" "$SIM/last.log"'
expect "revert"                         "revert /var/backups/icb-rt5-2026-10/$(basename "$J")" 'DONE \(revert\)'
check  "... notes back to none"         '[ "$(cat "$SIM/state/notes")" = none ]'
echo other > "$SIM/state/notes"
expect "another note on a family"       dryrun 'STOP \[GUARD\]'
echo none > "$SIM/state/notes"
echo 0051 > "$SIM/state/alembic"
expect "alembic still 0051 (v1.60.2 not deployed)" dryrun 'STOP \[DB\]'
echo 0052 > "$SIM/state/alembic"
echo "# tampered" >> "$SIM/tmp/icb-rt5-notes/rt5_notes.py"
expect "a staged file was edited"       dryrun 'STOP \[KIT\]'
sed -i '$ d' "$SIM/tmp/icb-rt5-notes/rt5_notes.py"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"                dryrun 'STOP \[CODE\]'
echo "RESULT: $P passed, $F failed"
