#!/bin/bash
# rt1_factor.sh (Manifest F or F2) simulation, run as root in WSL:  M=F2 bash run_factor_sim.sh   (M=F for F)
# The REAL rt1_factor.sh + mkstage_factor.sh (from the branch) run in a private mount namespace where /opt, /etc,
# /var/backups and /tmp are bind-mounted from $SIM. The tool is a stand-in (fake_factor_tool.py) that keeps the real
# tool's output contract — the real tool is proven on a real database, the local mirror; psql, pg_dump and the venv
# python are stubs; git is real.
set -u
WIN=/mnt/c/Users/micge/Documents
HERE=$(cd "$(dirname "$0")" && pwd)
M=${M:-F2}
case "$M" in F) DIR=icb-rt1-factor; BEFORE=1.3170731707317074 ;; F2) DIR=icb-rt1-factor2; BEFORE=1.362881562881563 ;; *) echo "M is F or F2"; exit 1 ;; esac
SIM=/root/relsimF-$M-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,varbackups,tmp,state,stageout}
export SIMSTATE=$SIM/state

echo "== sim origin + the branch carrying the F kit, and both release tags"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
$G fetch -q "$WIN/icb-platform" "${KIT_BRANCH:-docs/rt1-close}" "refs/tags/v1.59.0:refs/tags/v1.59.0" "refs/tags/v1.59.2:refs/tags/v1.59.2" || exit 1
git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
KIT=$(git rev-parse HEAD); PREV=$(git rev-parse "v1.59.0^{commit}"); TAGC=$(git rev-parse "v1.59.2^{commit}")
echo "   kit ${KIT:0:7} · v1.59.0 ${PREV:0:7} · v1.59.2 ${TAGC:0:7}"
 bash ops/prod-rt1/mkstage_factor.sh "$SIM/stageout" "$KIT" "$M" | sed -n '1,9p' || exit 1
tar -xf "$SIM/stageout/$DIR.tar" -C "$SIM/tmp" || exit 1

echo "== the fake prod at ${PREV:0:7} (v1.59.0, before the window)"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PREV"
git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.59.2:refs/tags/v1.59.2" || exit 1   # the window's code
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<EOF
#!/bin/bash
case "\$*" in
  *"import psycopg"*) exit 0 ;;
esac
case "\$1" in
  */rt1_factor.py) shift; exec python3 "$HERE/fake_factor_tool.py" "\$@" ;;
esac
exec python3 "\$@"
EOF
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
echo 'DATABASE_URL=postgresql+psycopg://icb_app:sim@localhost:5432/icb_platform' > "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only"; exit 3;; esac
sql=; while [ $# -gt 0 ]; do [ "$1" = -c ] && sql=$2; shift; done
case "$sql" in
  *current_database*) echo icb_platform ;;
  *alembic_version*) if [ -f "$SIMSTATE/alembic_moved" ]; then echo 0050; else echo 0049; fi ;;
  *"from icb_costings.admin_settings where key = 'costings.pu_foam_4g_factor'"*)
     if [ -f "$SIMSTATE/psql_lies" ]; then echo 9.99; else cat "$SIMSTATE/factor_value" 2>/dev/null || echo 1.3170731707317074; fi ;;
  *) echo "unknown SQL"; exit 3 ;;
esac
EOF
cat > "$SIM/bin/pg_dump" <<'EOF'
#!/bin/bash
case "$*" in *"-t icb_costings.admin_settings"*) ;; *) echo "pg_dump stub: unexpected table list: $*" >&2; exit 3 ;; esac
echo "-- stub data-only dump of admin_settings"; echo "COPY icb_costings.admin_settings FROM stdin;"
EOF
chmod +x "$SIM/bin/"*

run() { # run the staged kit as prod would; prints its first banner line
  unshare -m bash -c "
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/varbackups' /var/backups &&
    mount --bind '$SIM/tmp' /tmp && export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' &&
    bash /tmp/$DIR/rt1_factor.sh $*" > "$SIM/last.log" 2>&1
  grep -E '^######## ' "$SIM/last.log" | head -n 1
}
PASSES=0; FAILS=0
expect() { # $1 label, $2 regex the banner must match, rest = rt1_factor.sh args
  local label=$1 want=$2; shift 2
  local got; got=$(run "$@")
  if [[ "$got" =~ $want ]]; then echo "PASS  $label  :: $got"; PASSES=$((PASSES+1))
  else echo "FAIL  $label  :: $got  (wanted /$want/)"; FAILS=$((FAILS+1)); sed 's/^/        | /' "$SIM/last.log" | tail -n 25; fi
}
jr() { ls -t "$SIM/varbackups/icb-rt1-2026-09/"journal_"$M"_*.json 2>/dev/null | head -n1 | sed "s#$SIM/varbackups#/var/backups#"; }
reset_state() { echo "$BEFORE" > "$SIMSTATE/factor_value"; echo "2026-09-04 09:00:00.123456" > "$SIMSTATE/factor_updated"; }
reset_state

echo; echo "== the sequence over v1.59.0"
expect "dryrun (fresh)"                  "DONE \(dryrun $M: 1 to apply, 0 already applied\.\)"  dryrun
expect "apply"                           "DONE \(apply $M\) — journal /var/backups/icb-rt1-2026-09/journal_${M}_" apply
ls "$SIM/varbackups/icb-rt1-2026-09/" | sed 's/^/        kept: /'
expect "apply again = already applied"   "DONE \(apply $M: already applied\)"   apply
expect "dryrun after = already applied"  "DONE \(dryrun $M: already applied\)"  dryrun
expect "revert"                          "DONE \(revert $M\)"                   revert "$(jr)"
expect "revert again = nothing to do"    "DONE \(revert $M\)"                   revert "$(jr)"
echo '{"manifest_sha256": "59d37b082c4c35ac"}' > "$SIM/varbackups/icb-rt1-2026-09/journal_M_sim.json"
expect "an M journal is refused"         'STOP \[USAGE\]'                      revert /var/backups/icb-rt1-2026-09/journal_M_sim.json
OTHER=$([ "$M" = F2 ] && echo F || echo F2)
echo "{\"tool\": \"rt1_factor\", \"manifest\": \"$OTHER\"}" > "$SIM/varbackups/icb-rt1-2026-09/journal_${OTHER}_sim.json"
expect "the other manifest's journal"    'STOP \[USAGE\]'                      revert "/var/backups/icb-rt1-2026-09/journal_${OTHER}_sim.json"
expect "no such journal"                 'STOP \[USAGE\]'                      revert /var/backups/icb-rt1-2026-09/nope.json
echo 1.4 > "$SIMSTATE/factor_value"
expect "a third value: dryrun refused"   'STOP \[GUARD\]'                      dryrun
expect "a third value: apply refused"    'STOP \[GUARD\]'                      apply
[ "$(cat "$SIMSTATE/factor_value")" = 1.4 ] && echo "        value left at 1.4 (nothing written)"
reset_state; touch "$SIMSTATE/psql_lies"
expect "psql disagrees with the tool"    'STOP \[GUARD\]: psql reads'          dryrun
rm -f "$SIMSTATE/psql_lies"; touch "$SIMSTATE/no_journal"
expect "applied, but no journal"         'STOP \[JOURNAL\]'                    apply
rm -f "$SIMSTATE/no_journal"; reset_state; touch "$SIMSTATE/no_write"
expect "the write did not land"          'STOP \[AFTER\]'                      apply
rm -f "$SIMSTATE/no_write"; reset_state; touch "$SIMSTATE/alembic_moved"
expect "alembic moved"                   'STOP \[DB\]'                         dryrun
rm -f "$SIMSTATE/alembic_moved"
expect "bad usage"                       '^$'                                  apply extra
echo "# tampered" >> "$SIM/tmp/$DIR/rt1_factor.py"
expect "tampered tool"                   'STOP \[KIT\]'                        dryrun
tar -xf "$SIM/stageout/$DIR.tar" -C "$SIM/tmp" --overwrite   # restage the untampered kit

echo; echo "== after the window: prod on v1.59.2 (${TAGC:0:7})"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TAGC" || { echo "cannot check out v1.59.2 in the fake prod"; exit 1; }
reset_state
expect "v1.59.2: dryrun"                 "DONE \(dryrun $M: 1 to apply"         dryrun
expect "v1.59.2: apply"                  "DONE \(apply $M\)"                    apply
expect "v1.59.2: revert"                 "DONE \(revert $M\)"                   revert "$(jr)"
git -C "$SIM/opt/icb-platform" -c user.email=x@x -c user.name=x commit -q --allow-empty -m "hand edit"
expect "prod code moved"                 'STOP \[CODE\]'                       dryrun
echo; echo "== $PASSES passed, $FAILS failed · SIM=$SIM"
