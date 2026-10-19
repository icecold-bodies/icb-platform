#!/bin/bash
# rt8_frozen_check.sh simulation, run as root in WSL:  bash run_check_sim.sh <branch-or-commit>
# The REAL rt8_frozen_check.sh + mkstage_check.sh + ops/lib/icb_where.sh in a private folder: a fake /opt, /etc and
# /tmp (the ICB_* overrides the script offers for exactly this), the hostname taken as the kit expects it per
# scenario. psql and the venv python are STUBS that refuse a session that is not read-only, and the python stub
# refuses when DATABASE_URL and SESSION_SECRET are not in its environment (RT7's 16 Oct lesson); the happy-path stub
# writes the three outputs the real check writes. git is real.
# What it proves: the FIRST line names machine, database and HEAD; a wrong machine, a wrong database, a tampered
# kit and a python that is not given a read-only session are each refused (STOP, nothing written); the happy path
# tars its output with no env value in it. The real check's python is proven separately, against icb_test, by
# backend/tests/test_rt8_prod_kit_allowlist.py and a direct run. Cleans its own folder at the end (the WSL disk
# lesson: every sim folder removed on exit).
set -u
REF=${1:-rt8/frozen-quote-edit}
WIN=/mnt/c/Users/micge/Documents
SIM=/root/rt8sim-$(date +%s)
G="git -c safe.directory=*"
mkdir -p "$SIM"/{bin,opt,tmp,stageout,etc/icb}
trap 'rm -rf "$SIM"' EXIT
fail() { echo "SIM FAIL: $*"; exit 1; }
$G clone -q --bare --single-branch --branch backport/v1.39-base "$WIN/icb-platform" "$SIM/origin.git" || fail clone
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || fail work
$G fetch -q "$WIN/icb-platform" "$REF" "refs/tags/v1.61.0:refs/tags/v1.61.0" && git -c advice.detachedHead=false checkout -q FETCH_HEAD || fail "fetch $REF"
bash ops/prod-rt8/mkstage_check.sh "$SIM/stageout" HEAD > "$SIM/stage.log" 2>&1 || { cat "$SIM/stage.log"; fail stage; }
grep -m1 '^staged' "$SIM/stage.log"
PROD=$(git rev-parse "v1.61.0^{commit}")
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" fetch -q "$SIM/work" "refs/tags/v1.61.0:refs/tags/v1.61.0" \
  && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PROD" || fail "fake /opt"
printf 'DATABASE_URL=postgresql+psycopg://icb_app:s3cret-not-real@127.0.0.1:5432/icb_platform\nSESSION_SECRET=zzz-not-real\n' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
cat > "$SIM/bin/psql" <<'PS'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT read-only" >&2; exit 3;; esac
case "$*" in
  *current_database*) echo "${SIM_DB:-icb_platform}" ;;
  *alembic_version*)  echo 0053 ;;
  *transaction_read_only*) echo on ;;
  *) echo "psql stub: unexpected query: $*" >&2; exit 4 ;;
esac
PS
cat > "$SIM/bin/python" <<'PY'
#!/bin/bash
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "python stub: NOT read-only"; exit 3;; esac
[ -n "${DATABASE_URL:-}" ] && [ -n "${SESSION_SECRET:-}" ] || { echo "pydantic ValidationError: 2 validation errors for Settings (stub)"; exit 1; }
[ "$1" = -c ] && exit 0
out=$2; mkdir -p "$out"
printf 'RT8 frozen-quote check (stub) · pending costings 3\nN10022/10/2026: MEAT HANGER LARGE · replay PASS (stub)\n' > "$out/summary.txt"
echo '[]' > "$out/details.json"
printf 'columns read: (stub)\n' > "$out/inventory.txt"
cat "$out/summary.txt"
PY
chmod +x "$SIM/bin/psql" "$SIM/bin/python"
export PATH="$SIM/bin:$PATH"
KIT="$SIM/tmp/icb-rt8-check"
( cd "$SIM/tmp" && tar -xf "$SIM/stageout/icb-rt8-check.tar" ) || fail untar

run() {   # run <label> <expected-exit> <expected-text> [SIM_DB]
  local label=$1 want=$2 text=$3; export SIM_DB=${4:-icb_platform}
  local log="$SIM/$label.log"
  ICB_KIT_BASE="$KIT" ICB_REPO="$SIM/opt/icb-platform" ICB_ENV_FILE="$SIM/etc/icb/backend.env" ICB_PY="$SIM/bin/python" \
    bash "$KIT/rt8_frozen_check.sh" > "$log" 2>&1
  local rc=$?
  if [ "$rc" != "$want" ] || ! grep -q -- "$text" "$log"; then echo "--- $label: exit $rc (wanted $want), looked for '$text'"; cat "$log"; fail "$label"; fi
  grep -q 's3cret-not-real\|zzz-not-real' "$log" && fail "$label leaked an env value"
  echo "ok  $label: exit $rc · $(head -n1 "$log" | cut -c1-110)"
}
# the kit's expected.env pins icb-mes-prod; this machine is not it → the WHERE stop is the first thing proven
run wrong-machine 1 'STOP \[WHERE\]'
# now pretend we are prod (the kit reads hostname -s): patch the expectation to this host for the rest
sed -i "s/^EXPECT_MACHINE=.*/EXPECT_MACHINE=$(hostname -s)/" "$KIT/expected.env"
( cd "$KIT" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS )
run wrong-db 1 'STOP \[WHERE\]' icb_test
run happy 0 'DONE (read only)'
ls "$KIT"/out-*/summary.txt >/dev/null || fail "happy path wrote no summary"
tar -tf "$KIT"/out-*.tar | grep -q summary.txt || fail "happy path tar has no summary"
# a tampered kit (one byte changed after staging) is refused before anything runs
echo "# tampered" >> "$KIT/rt8_frozen_check.py"
run tampered 1 'STOP \[KIT\]'
sed -i '$ d' "$KIT/rt8_frozen_check.py"
# the python given a session that is not read-only refuses (the stub models the real check's assert)
PGOPTIONS= ICB_KIT_BASE="$KIT" ICB_REPO="$SIM/opt/icb-platform" ICB_ENV_FILE="$SIM/etc/icb/backend.env" ICB_PY="$SIM/bin/python" \
  bash -c 'export PGOPTIONS=""; "$0"/bin/python -c x; echo "exit $?"' "$SIM" > "$SIM/ro.log" 2>&1
grep -q 'NOT read-only' "$SIM/ro.log" || fail "the python stub accepted a non-read-only session"
echo "ok  not-read-only python refused (stub)"
echo "SIM PASS: 5 scenarios (wrong machine, wrong db, happy, tampered kit, not read-only)"
