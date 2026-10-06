#!/bin/bash
# rt6_discovery.sh simulation, run as root in WSL:  bash run_discovery_sim.sh [branch]
# The REAL rt6_discovery.sh + mkstage_discovery.sh + ops/lib/icb_where.sh in private mount + UTS namespaces (fake
# /opt, /etc, /tmp; the hostname set per scenario). psql, systemctl and the venv python are stubs that refuse a
# session that is not read-only (the real rt6_discovery.py ran read-only against the prod mirror); git is real.
# What it proves: the FIRST line names machine, database (name @ host) and HEAD, and a wrong machine, database or
# HEAD is refused before anything runs. Cleans its own folder at the end (the RT4 disk lesson).
set -u
BR=${1:-rt6/enforce}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt6simD-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,state}
trap 'rm -rf "$SIM"' EXIT
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
# the worktree's branch lives in the main clone's repository (WSL git cannot read a Windows worktree's .git file)
$G fetch -q "$WIN/icb-platform" "$BR" "refs/tags/v1.60.2:refs/tags/v1.60.2" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || exit 1
bash ops/prod-rt6/mkstage_discovery.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; exit 1; }
grep -m1 '^staged' "$SIM/stage.log"
PROD=$(git rev-parse "v1.60.2^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.60.2:refs/tags/v1.60.2" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin" "$SIM/opt/icb-platform/backend"
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
case "$1" in
  */rt6_discovery.py)
    echo "== 1 · classification (stub)"; echo "   LIVE BREACHES: 1"
    cat "$SIMSTATE/discovery.json" > "$3/discovery.json"; echo "== 1 · classification (stub)" > "$3/discovery.txt"; exit 0 ;;
esac
exec python3 "$@"
PY
chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
printf 'DATABASE_URL=postgresql+psycopg://icb_app:s3cret-not-real@localhost:5432/icb_platform\nSESSION_SECRET=zzz-not-real\nexport SMTP_URL=smtp://u:p@x\n' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
printf 'SESSION_SECRET=also-not-real\nDEPLOYMENT_MODE=on_prem\n' > "$SIM/opt/icb-platform/backend/.env"
echo icb_platform > "$SIM/state/db"; echo 0052 > "$SIM/state/alembic"
echo '{"database": "icb_platform", "costings": [{"quote_number": "A1/10/2026"}]}' > "$SIM/state/discovery.json"
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
cat > "$SIM/bin/systemctl" <<'SC'
#!/bin/bash
case "$*" in
  *EnvironmentFiles*) echo "/etc/icb/backend.env (ignore_errors=no)" ;;
  *"-p Environment "*) echo "PYTHONUNBUFFERED=1 LANG=C.UTF-8" ;;
  *) exit 1 ;;
esac
SC
chmod +x "$SIM/bin/psql" "$SIM/bin/systemctl"
mkdir -p "$SIM/tmp/icb-srd-discovery" "$SIM/tmp/node-compile-cache" "$SIM/tmp/systemd-private-abc"
echo x > "$SIM/tmp/icb-rollback-20260915.txt"; echo y > "$SIM/tmp/icb-srd-discovery/a.txt"
tar -xf "$SIM/stageout/icb-rt6-discovery.tar" -C "$SIM/tmp" || exit 1
cp -a "$SIM/tmp/icb-rt6-discovery" "$SIM/pristine"

run() {  # run [hostname] [as-user]
  local hn=${1:-icb-mes-prod} user=${2:-root}
  sleep 1
  rm -rf "$SIM/tmp/icb-rt6-discovery"; cp -a "$SIM/pristine" "$SIM/tmp/icb-rt6-discovery"; ${MUTATE:-true}
  unshare -m -u bash -c "hostname '$hn' && mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/tmp' /tmp &&
      export PATH='$SIM/bin':\$PATH SIMSTATE='$SIM/state' &&
      if [ '$user' = root ]; then bash /tmp/icb-rt6-discovery/rt6_discovery.sh; else chmod -R a+rX /tmp/icb-rt6-discovery; runuser -u '$user' -- bash /tmp/icb-rt6-discovery/rt6_discovery.sh; fi" > "$SIM/last.log" 2>&1
}
first() { head -n 1 "$SIM/last.log"; }
verdict() { grep -E '^######## (STOP|DONE)' "$SIM/last.log" | head -n 1; }
PASS=0; FAIL=0
row() {  # row <name> <regex for the verdict> [<regex for the first line>]
  local v f; v=$(verdict); f=$(first)
  if [[ "$v" =~ $2 ]] && [[ "$f" =~ ${3:-^######## RT6 discovery } ]]; then PASS=$((PASS+1)); echo "  ok   $1: $v"
  else FAIL=$((FAIL+1)); echo "  FAIL $1"; echo "       first:   $f"; echo "       verdict: $v"; tail -n 5 "$SIM/last.log" | sed 's/^/       | /'; fi
}

echo "== scenarios"
run; row "happy" '^######## DONE' "^######## RT6 discovery \(read only\) · machine icb-mes-prod · db icb_platform @ localhost:5432 · head ${PROD:0:7} "
L="$SIM/tmp/icb-rt6-discovery"; O=$(ls -d "$L"/out-*/ | tail -n1); O=${O%/}
grep -q 'not-real\|s3cret\|smtp://' "$O"/* && { FAIL=$((FAIL+1)); echo "  FAIL happy: a secret value reached the output"; } || { PASS=$((PASS+1)); echo "  ok   no env value in any output file"; }
grep -q '^/etc/icb/backend.env (root:root 600): DATABASE_URL SESSION_SECRET SMTP_URL $' "$O/env_keys.txt" \
  && { PASS=$((PASS+1)); echo "  ok   env_keys.txt lists key names only (incl. an 'export' line)"; } || { FAIL=$((FAIL+1)); echo "  FAIL env_keys.txt:"; cat "$O/env_keys.txt"; }
grep -qE '^MOVE\? .* icb-rollback-20260915.txt$' "$O/tmp_listing.txt" && grep -qE '^STAYS .* node-compile-cache$' "$O/tmp_listing.txt" \
  && grep -qE '^OS-STAYS .* systemd-private-abc$' "$O/tmp_listing.txt" && grep -qE '^RT6-KIT .* icb-rt6-discovery$' "$O/tmp_listing.txt" \
  && { PASS=$((PASS+1)); echo "  ok   /tmp listing classes (MOVE? / STAYS / OS-STAYS / RT6-KIT)"; } || { FAIL=$((FAIL+1)); echo "  FAIL /tmp listing"; cat "$O/tmp_listing.txt"; }
run dev-laptop; row "wrong machine" "STOP \[WHERE\]: WRONG PLACE — machine is 'dev-laptop'" "^######## RT6 discovery \(read only\) · machine dev-laptop "
echo icb > "$SIM/state/db"; run; row "wrong database" "STOP \[WHERE\]: WRONG PLACE — database is 'icb'" "· db icb @ localhost:5432 "; echo icb_platform > "$SIM/state/db"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD~1"; run; row "wrong HEAD" "STOP \[WHERE\]: WRONG PLACE — code is at"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD"
run icb-mes-prod nobody; row "not root" 'STOP \[KIT\]: run with sudo' "· db \? @ \? "
echo 0051 > "$SIM/state/alembic"; run; row "wrong alembic" 'STOP \[DB\]: alembic_version is .0051.'; echo 0052 > "$SIM/state/alembic"
MUTATE="truncate -s 100 $SIM/tmp/icb-rt6-discovery/rt6_discovery.py" run; row "tampered stage" 'STOP \[KIT\]: staged files do not match'
echo '{"x": "someone@example.com"}' > "$SIM/state/discovery.json"; run; row "email gate" 'STOP \[GATE\]: an email-shaped value'
echo
echo "== $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
