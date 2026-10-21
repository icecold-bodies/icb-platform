#!/bin/bash
# RT9 sims — the throw-away prod, shared by run_sim.sh (the release kit's scenarios) and ps51/fakeprod_up.sh (the
# window lines from Windows PowerShell 5.1). SOURCED, as root in WSL, with:
#     SIM   an empty folder under /root (removed by the caller)      KIT   the kit branch      REPO  the Windows repo
#
# fp_origin   the sim origin: backport/v1.39-base + the kit branch, tags v1.61.1 and an annotated v1.62.0 on its head
#             (built once per kit commit under /root/rt9sim-cache/<sha>, then copied: the clone off /mnt/c is slow)
# fp_stage    the REAL ops/prod-release-v1.62.0/mkstage_window.sh -> $SIM/stageout
# fp_prod     the fake prod at v1.61.1 (5511355): repo, venv / dist stubs, env file, a database at 0053 with the 4G
#             factor and 72 saved costings, a running service whose journal holds an OLD traceback (19 Oct's kind:
#             a ClientDisconnect — listed as pre-existing, never counted), the stub commands
# fp_run      one command line run as prod would: private mount + UTS namespaces (hostname icb-mes-prod) where /opt,
#             /etc, /var/tmp, /var/backups and /tmp are bind-mounted from $SIM — nothing outside $SIM is touched
G="git -c safe.directory=*"
HOSTNAME_SIM=${HOSTNAME_SIM:-icb-mes-prod}

fp_origin() {
  local ksha cache w
  ksha=$($G -C "$REPO" rev-parse "$KIT^{commit}") || { echo "SIM: no branch $KIT in $REPO"; return 1; }
  PREV=$($G -C "$REPO" rev-parse "v1.61.1^{commit}") || return 1
  [ "${PREV:0:7}" = 5511355 ] || { echo "SIM: v1.61.1 is ${PREV:0:7}, prod runs 5511355"; return 1; }
  cache=${RT9SIM_CACHE:-/root/rt9sim-cache}/$ksha
  if [ ! -d "$cache/origin.git" ]; then
    rm -rf "$cache"; mkdir -p "$cache"
    $G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$cache/origin.git" || return 1
    $G -C "$cache/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" \
      "+refs/tags/v1.61.1:refs/tags/v1.61.1" || return 1
    w=$cache/work; git clone -q "$cache/origin.git" "$w" || return 1
    git -C "$w" -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
    $G -C "$w" fetch -q "$REPO" "$KIT" || return 1
    git -C "$w" -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || return 1
    git -C "$w" push -q origin backport/v1.39-base || return 1
    git -C "$w" -c user.email=sim@x -c user.name=sim tag -a v1.62.0 -m "sim v1.62.0" HEAD && git -C "$w" push -q origin v1.62.0 || return 1
    rm -rf "$w"
  fi
  cp -a "$cache/origin.git" "$SIM/origin.git" || return 1
  git clone -q "$SIM/origin.git" "$SIM/work" || return 1
  git -C "$SIM/work" -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
  git -C "$SIM/work" fetch -q origin --tags
  TARGET=$(git -C "$SIM/work" rev-parse HEAD)
  echo "   prev ${PREV:0:7}  target ${TARGET:0:7}  tag $(git -C "$SIM/work" rev-parse v1.62.0 | cut -c1-12)"
}

fp_stage() {
  ( cd "$SIM/work" && bash ops/prod-release-v1.62.0/mkstage_window.sh "$SIM/stageout" "$TARGET" ) > "$SIM/stage.log" 2>&1 \
    || { cat "$SIM/stage.log"; echo "SIM: the window did not stage"; return 1; }
  grep -E '^(staged|calculator)' "$SIM/stage.log"
}

fp_prod() {
  export SIMSTATE=$SIM/state
  mkdir -p "$SIM"/{bin,opt,vartmp,varbackups/postgres,tmp,state}
  git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" || return 1
  ( cd "$SIM/opt/icb-platform" || exit 1
    git -c advice.detachedHead=false checkout -q -B backport/v1.39-base "$PREV" && git branch -q -u origin/backport/v1.39-base
    git tag -d v1.62.0 > /dev/null 2>&1      # as the real VM: the tag arrives with the deploy's fetch
    mkdir -p frontend/dist/assets frontend/node_modules .venv/bin
    echo 'console.log("spa v1.61.1")' > frontend/dist/assets/index-BBI2d9Oo.js
    echo '<script type="module" src="/mes-app/assets/index-BBI2d9Oo.js"></script>' > frontend/dist/index.html
  ) || return 1
  cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
# the deployed tools, as the kits call them: the audit list (stdin program), the All packs, the page-vs-CLI compare,
# the door report. Anything else is a loud failure.
if [ "${1:-}" = - ]; then
  prog=$(cat)
  case "$prog" in *load_accepted_doc*)
    R=/opt/icb-platform/backend
    grep -q 'def load_accepted_doc' "$R/tools/costing_audit/accepted.py" \
      || { echo "ImportError: cannot import name 'load_accepted_doc' from 'tools.costing_audit.accepted'"; exit 1; }
    L=$R/tests/costing_audit/accepted_differences.prod.yaml
    n=$(grep -c '^- body:' "$L"); pair=$(sed -n 's/^ *snapshot_sha256: *\([0-9a-f]*\).*/\1/p' "$L" | head -n1)
    have=$(tr -d '\r' < "$R/tests/costing_audit/mes_snapshot/all.json" | sha256sum | cut -d' ' -f1)
    [ "$pair" = "$have" ] && echo "$n $pair pair=snapshot" || echo "$n $pair pair!=snapshot"
    exit 0 ;;
  esac
  echo "python stub: unknown stdin program"; exit 4
fi
case "$*" in
  *"import yaml"*) echo 6.0.2 ;;
  --version) echo "Python 3.12.3" ;;
  "-m tools.costing_audit run "*)
    p=; out=; stem=; while [ $# -gt 0 ]; do case "$1" in --pack) p=$2;; --out) out=$2;; --stem) stem=$2;; esac; shift; done
    printf '# %s\n- Cells: FLAG 0 · ACCEPTED (sim) · PASS (sim)\n' "$p" > "$out/$stem.md"; echo '{"sim": true}' > "$out/$stem.json" ;;
  *rt2_all_compare.py*) echo "   (sim) All page run #50 vs CLI: 2702 / 2702 cells equal"; echo "PAGE_EQUALS_CLI yes" ;;
  *rt1_door_report.py*) echo "   (sim) 14 bodies"; echo "SUMMARY: 14 OK" ;;
  *) echo "python stub: unknown call: $*"; exit 4 ;;
esac
EOF
  cat > "$SIM/opt/icb-platform/.venv/bin/alembic" <<'EOF'
#!/bin/bash
# v1.62.0 migrates nothing: icb-deploy.sh's RESUME path still runs `alembic upgrade head` (a no-op at head)
case "$1" in
  upgrade) echo "INFO  [alembic] (stub) already at head $(cat "$SIMSTATE/alembic")" ;;
  current) echo "$(cat "$SIMSTATE/alembic") (head)" ;;
esac
EOF
  chmod +x "$SIM/opt/icb-platform/.venv/bin/"*
  cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
  # prod's env file since RT6: ICB_ENVIRONMENT=prod; MES_DEMO_AUTOLOGIN_USER present and EMPTY; a duplicate key
  printf '%s\n' 'DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform' \
    'SESSION_SECRET=sim-not-real' 'SMTP_URL=' 'SMTP_URL=smtp://x' 'MES_DEMO_AUTOLOGIN_USER=' 'ICB_ENVIRONMENT=prod' > "$SIM/etc/icb/backend.env"
  chmod 600 "$SIM/etc/icb/backend.env"
  echo "completed $PREV" > "$SIM/vartmp/icb-deploy-state"
  echo x > "$SIM/varbackups/postgres/icb_platform_20261021-0230.dump.gz"
  echo 0053 > "$SIMSTATE/alembic"; echo 1.3170731707317074 > "$SIMSTATE/factor"; echo icb_platform > "$SIMSTATE/dbname"
  echo "72 0f1e2d3c4b5a69788796a5b4c3d2e1f0" > "$SIMSTATE/quotes"
  echo "$TARGET" > "$SIMSTATE/target"; echo "POST /api/calculations/1/reprice-preview" > "$SIMSTATE/absent_prev"
  echo 76017 > "$SIMSTATE/pid"; echo "Mon 2026-10-20 13:12:40 SAST" > "$SIMSTATE/aet"
  echo "$PREV" > "$SIMSTATE/live_code"; echo prod > "$SIMSTATE/live_env"
  local now old; now=$(date +%s); old=$(( now - 3 * 86400 ))
  : > "$SIMSTATE/journal"
  # 19 Oct's kind of pre-existing traceback, BEFORE the running service started: RT7's lesson — listed, never counted
  printf '%s %s\n' "$old" "Traceback (most recent call last):" "$old" '  File "/opt/icb-platform/.venv/lib/starlette/requests.py", line 210, in receive' \
    "$old" "starlette.requests.ClientDisconnect" >> "$SIMSTATE/journal"
  sleep 2
  awk '{ printf "%d\n", $1 * 1000000 }' /proc/uptime > "$SIMSTATE/mono"
  now=$(date +%s); for i in 1 2 3 4; do echo "$now INFO:     Application startup complete." >> "$SIMSTATE/journal"; done
  # and one UNDER the running v1.61.1, after its start (RT7's 8th verify-before failure, 19 Oct): listed, not counted
  printf '%s %s\n' "$((now + 1))" "Traceback (most recent call last):" "$((now + 1))" "starlette.requests.ClientDisconnect" >> "$SIMSTATE/journal"
  sleep 2
  bash "$SIM/work/ops/prod-release-v1.62.0/sim/stubs.sh" "$SIM/bin"
  printf 'SIM=%s\nSIMSTATE=%s\nHOSTNAME_SIM=%s\n' "$SIM" "$SIMSTATE" "$HOSTNAME_SIM" > "$SIM/fp.env"
}

fp_run() { # $1 = one command line, run as prod runs it (each run 1 s apart: the kits' out folders are per second)
  sleep 1
  FP_CMD=$1 FP_SIM=$SIM FP_HOST=$HOSTNAME_SIM SIMSTATE=$SIMSTATE unshare -m -u bash -c '
    hostname "$FP_HOST" &&
    mount --bind "$FP_SIM/opt" /opt && mount --bind "$FP_SIM/etc" /etc && mount --bind "$FP_SIM/vartmp" /var/tmp &&
    mount --bind "$FP_SIM/varbackups" /var/backups && mount --bind "$FP_SIM/tmp" /tmp &&
    export PATH="$FP_SIM/bin:$PATH" && cd /tmp && bash -c "$FP_CMD"'
}
