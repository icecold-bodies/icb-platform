#!/bin/bash
# RT11 §3.0 prod check sims — the throw-away prod, shared by run_sim.sh (WSL scenarios) and ps51/ (the paste block from
# Windows PowerShell 5.1). SOURCED, as root, in the Ubuntu 24.04 clone of prod (the WSL distro icb-noble-rt11: the
# same release, Python 3.12.3, Pango 1.52.1 and HarfBuzz 8.3.0 as prod), with SIM = an empty folder under /root
# (removed by the caller). apt-get -s, dpkg-query, fontconfig, runuser and pip are the clone's REAL ones; only psql
# and sudo are stand-ins.
#
# fp_prod   the fake prod: /opt/icb-platform at v1.62.0 (a depth-1 fetch of the tag from Michael's clone: a READ —
#           nothing is written there), a REAL venv like prod's (a copy of $FP_VENV_BASE: python3.12 + the base
#           requirements, built once by `fp_venv_base`), the env file, a psql stand-in answering the check's fixed
#           SELECTs from $SIMSTATE, sudo
# fp_run    one command line run as prod would: private mount + UTS namespaces (hostname from $SIMSTATE/hostname),
#           /opt, /etc and /tmp bind-mounted from $SIM — nothing outside $SIM is touched
REPO_WIN=${REPO_WIN:-/mnt/c/Users/micge/Documents/icb-platform}
FP_VENV_BASE=${FP_VENV_BASE:-/var/lib/rt11sim/venv-base}
SIMKIT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

fp_venv_base() { # $1 = a requirements file (the base, dcba297's): build the prod-like venv once
  [ -x "$FP_VENV_BASE/bin/python" ] && return 0
  python3.12 -m venv "$FP_VENV_BASE" && "$FP_VENV_BASE/bin/python" -m pip install -q -r "${1:?requirements}" \
    && chmod -R a+rX "$FP_VENV_BASE"
}

fp_prod() {
  export SIMSTATE=$SIM/state
  mkdir -p "$SIM"/{bin,opt/icb-platform,tmp,state} || return 1
  . /etc/os-release; [ "$VERSION_ID" = 24.04 ] || { echo "SIM: run me in the Ubuntu 24.04 clone (this is $PRETTY_NAME)"; return 1; }
  # prod's /tmp rule (RT11_RULING_0A): a sticky, root-owned 1777 /tmp under fs.protected_regular=2, and a NON-root sudo
  # user the report is handed to — so a root append after the hand-over fails here exactly as it did on prod (23 Oct)
  [ "$(sysctl -n fs.protected_regular 2>/dev/null)" = 2 ] || { echo "SIM: fs.protected_regular is not 2 here: the sim cannot prove the /tmp rule"; return 1; }
  chown root:root "$SIM/tmp" && chmod 1777 "$SIM/tmp" || return 1
  [ -x "$FP_VENV_BASE/bin/python" ] || { echo "SIM: no base venv at $FP_VENV_BASE (fp_venv_base first)"; return 1; }
  ( cd "$SIM/opt/icb-platform" && git init -q && git -c protocol.file.allow=always fetch -q --depth 1 "file://$REPO_WIN" refs/tags/v1.62.0 \
      && git -c advice.detachedHead=false checkout -q --detach 'FETCH_HEAD^{commit}' ) || { echo "SIM: could not fetch v1.62.0"; return 1; }
  git -C "$SIM/opt/icb-platform" rev-parse HEAD > "$SIMSTATE/head"
  cp -a "$FP_VENV_BASE" "$SIM/opt/icb-platform/.venv" || return 1
  cp -a /etc "$SIM/etc" 2>/dev/null; mkdir -p "$SIM/etc/icb"
  grep -q '^mickeyger:' "$SIM/etc/passwd" || { echo 'mickeyger:x:1500:1500:sim ssh user:/nonexistent:/usr/sbin/nologin' >> "$SIM/etc/passwd"
    echo 'mickeyger:x:1500:' >> "$SIM/etc/group"; }
  printf '%s\n' 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform' \
    'SESSION_SECRET=sim-not-real' 'MES_DEMO_AUTOLOGIN_USER=' 'ICB_ENVIRONMENT=prod' > "$SIM/etc/icb/backend.env"
  chmod 600 "$SIM/etc/icb/backend.env"
  echo icb-mes-prod > "$SIMSTATE/hostname"; echo icb_platform > "$SIMSTATE/dbname"; echo 0053 > "$SIMSTATE/alembic"
  cp "$SIMKIT/fixture/"*.txt "$SIMSTATE/" || return 1
  cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
# Answers exactly the read-only SQL the check sends (the fixture's rows for each fixed SELECT); anything else, or a
# data read in a session that is not read-only, is a loud failure.
S=$SIMSTATE; sql=
while [ $# -gt 0 ]; do case "$1" in -c|-[A-Za-z]*c) sql=$2 ;; esac; shift; done
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ro=on ;; *) ro=off ;; esac
[ -f "$S/not_read_only" ] && ro=off
data() { [ "$ro" = on ] || { echo "psql stub: NOT a read-only session"; exit 3; }; cat "$S/$1"; }
case "$sql" in
  *current_database*) cat "$S/dbname" ;;
  *transaction_read_only*) echo "$ro" ;;
  *alembic_version*) data alembic ;;
  "SELECT rp.role FROM icb_costings.role_permissions rp "*) data qg_roles.txt ;;
  "SELECT u.role, count(*) FROM icb_costings.users u "*) data users_by_role.txt ;;
  "SELECT u.role, up.effect, count(*) FROM icb_costings.user_permissions up "*) data qg_overrides.txt ;;
  "SELECT t.id, t.slug, t.kind, t.is_active FROM icb_costings.report_templates t "*) data templates.txt ;;
  "SELECT g.id, g.name, "*) data groups.txt ;;
  "SELECT tt.id, tt.name, "*) data bodies.txt ;;
  "SELECT coalesce(CASE WHEN ot.is_active "*"FROM icb_costings.calculations c "*) data costings.txt ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF
  cat > "$SIM/bin/sudo" <<'EOF'
#!/bin/bash
while [ $# -gt 0 ]; do case "$1" in -u) shift 2;; -n|-E|-H) shift;; -*) shift;; *) break;; esac; done
export SUDO_USER=mickeyger          # as on prod: the ssh user, not root (the check hands its report to this user)
exec "$@"
EOF
  chmod +x "$SIM/bin/"*
  printf 'SIM=%s\nSIMSTATE=%s\n' "$SIM" "$SIMSTATE" > "$SIM/fp.env"
}

fp_pip_offline() { # on|off: the venv's own pip.conf points pip at a dead index (the check runs pip under env -i)
  if [ "$1" = on ]; then printf '[global]\nindex-url = http://127.0.0.1:9/simple\ntimeout = 3\nretries = 0\n' > "$SIM/opt/icb-platform/.venv/pip.conf"
  else rm -f "$SIM/opt/icb-platform/.venv/pip.conf"; fi
}

fp_run() { # $1 = one command line, run as prod runs it
  FP_CMD=$1 FP_SIM=$SIM SIMSTATE=$SIMSTATE unshare -m -u bash -c '
    hostname "$(cat "$SIMSTATE/hostname")" &&
    mount --bind "$FP_SIM/opt" /opt && mount --bind "$FP_SIM/etc" /etc && mount --bind "$FP_SIM/tmp" /tmp &&
    export PATH="$FP_SIM/bin:$PATH" && cd /tmp && bash -c "$FP_CMD"'
}
