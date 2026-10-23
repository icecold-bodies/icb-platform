#!/bin/bash
# RT10 prod check sims — the throw-away prod, shared by run_sim.sh (WSL scenarios) and ps51/ (the paste block from
# Windows PowerShell 5.1). SOURCED, as root in WSL, with SIM = an empty folder under /root (removed by the caller).
#
# fp_prod   the fake prod: /opt/icb-platform at v1.62.0 (a depth-1 fetch of the tag from Michael's clone: a READ —
#           nothing is written there), a venv python stand-in that runs the REAL rt10_revisions.py on a fake psycopg
#           (sim/fakepy) over the fixture rows in $SIMSTATE/fixture.json, the env file, a psql stand-in, sudo
# fp_run    one command line run as prod would: private mount + UTS namespaces (hostname from $SIMSTATE/hostname),
#           /opt, /etc and /tmp bind-mounted from $SIM — nothing outside $SIM is touched
REPO_WIN=${REPO_WIN:-/mnt/c/Users/micge/Documents/icb-platform}
SIMKIT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

fp_prod() {
  export SIMSTATE=$SIM/state
  mkdir -p "$SIM"/{bin,opt/icb-platform,tmp,state,fakepy} || return 1
  cp -a "$SIMKIT/fakepy/." "$SIM/fakepy/" || return 1
  ( cd "$SIM/opt/icb-platform" && git init -q && git -c protocol.file.allow=always fetch -q --depth 1 "file://$REPO_WIN" refs/tags/v1.62.0 \
      && git -c advice.detachedHead=false checkout -q --detach 'FETCH_HEAD^{commit}' ) || { echo "SIM: could not fetch v1.62.0"; return 1; }
  git -C "$SIM/opt/icb-platform" rev-parse HEAD > "$SIMSTATE/head"
  mkdir -p "$SIM/opt/icb-platform/.venv/bin"
  cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
# the deployed venv's python, as the check calls it: `python -I <kit>/rt10_revisions.py` runs the REAL script on the
# fake psycopg; anything else is a loud failure
for a in "$@"; do case "$a" in */rt10_revisions.py)
  [ -f "$SIMSTATE/py_fail" ] && { echo "Traceback (most recent call last):"; echo "psycopg.OperationalError: (sim) connection refused"; exit 1; }
  exec python3 -c 'import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; runpy.run_path(sys.argv[0], run_name="__main__")' \
    "$SIMFAKEPY" "$a" ;;
esac; done
echo "python stub: unknown call: $*"; exit 4
EOF
  chmod +x "$SIM/opt/icb-platform/.venv/bin/python"
  cp -a /etc "$SIM/etc" 2>/dev/null; mkdir -p "$SIM/etc/icb"
  printf '%s\n' 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform' \
    'SESSION_SECRET=sim-not-real' 'MES_DEMO_AUTOLOGIN_USER=' 'ICB_ENVIRONMENT=prod' > "$SIM/etc/icb/backend.env"
  chmod 600 "$SIM/etc/icb/backend.env"
  echo icb-mes-prod > "$SIMSTATE/hostname"; echo icb_platform > "$SIMSTATE/dbname"; echo 0053 > "$SIMSTATE/alembic"
  cp "$SIMKIT/fixture.json" "$SIMSTATE/fixture.json"
  cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
# Answers exactly the read-only SQL the check sends; anything else is a loud failure.
S=$SIMSTATE; sql=
while [ $# -gt 0 ]; do case "$1" in -c|-[A-Za-z]*c) sql=$2 ;; esac; shift; done
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ro=on ;; *) ro=off ;; esac
[ -f "$S/not_read_only" ] && ro=off
case "$sql" in
  *current_database*) cat "$S/dbname" ;;
  *transaction_read_only*) echo "$ro" ;;
  *alembic_version*) [ "$ro" = on ] || { echo "psql stub: NOT a read-only session"; exit 3; }; cat "$S/alembic" ;;
  "show timezone") echo Africa/Johannesburg ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF
  cat > "$SIM/bin/sudo" <<'EOF'
#!/bin/bash
while [ $# -gt 0 ]; do case "$1" in -u) shift 2;; -n|-E|-H) shift;; -*) shift;; *) break;; esac; done
export SUDO_USER=root
exec "$@"
EOF
  chmod +x "$SIM/bin/"*
  printf 'SIM=%s\nSIMSTATE=%s\n' "$SIM" "$SIMSTATE" > "$SIM/fp.env"
}

fp_run() { # $1 = one command line, run as prod runs it
  FP_CMD=$1 FP_SIM=$SIM SIMSTATE=$SIMSTATE SIMFAKEPY=$SIM/fakepy unshare -m -u bash -c '
    hostname "$(cat "$SIMSTATE/hostname")" &&
    mount --bind "$FP_SIM/opt" /opt && mount --bind "$FP_SIM/etc" /etc && mount --bind "$FP_SIM/tmp" /tmp &&
    export PATH="$FP_SIM/bin:$PATH" && cd /tmp && bash -c "$FP_CMD"'
}
