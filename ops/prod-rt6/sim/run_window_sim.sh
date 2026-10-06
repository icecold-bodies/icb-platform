#!/bin/bash
# The RT6 window kits, simulated (run as root in WSL):  bash run_window_sim.sh [kit-branch]
# Stages the whole window with the REAL ops/prod-rt6/mkstage_window.sh (and so the real release mkstage.sh) from a sim
# origin whose backport/v1.39-base carries the kit branch and an annotated v1.61.0 tag, unpacks the five kits into a
# fake prod /tmp and runs them inside private mount + UTS namespaces (hostname icb-mes-prod; /opt, /etc, /tmp,
# /var/tmp, /var/backups bind-mounted from the sim folder — nothing outside it is touched):
#   icb-rt6-rules   dry-run / apply / again / show / revert / re-apply, and every refusal before a write: wrong
#                   machine, wrong database, wrong code, wrong alembic, tampered kit, a different plan, a failed dump
#   icb-rt6-tidy    on REAL files (the 34 reviewed names, regenerated content; the sim's manifest is re-summed and
#                   committed before staging): dry-run, tamper / extra / missing refusals, apply (owners and modes
#                   kept, the stays stay), again, show, restore, the never-mixed-into archive
#   icb-rt2-doors / icb-rt2-all   the safe-paste first line, and the wrong-place refusal
# psql, pg_dump and the venv python are stubs: psql and the dry-run / show refuse a session that is not read-only, the
# rules stub refuses without DATABASE_URL. The sim folder is removed at the end (the RT4 disk lesson).
set -u
KIT=${1:-rt6/enforce}
REPO=/mnt/c/Users/micge/Documents/icb-platform
SIM=/root/rt6simW-$(date +%s)
G="git -c safe.directory=*"
P=0; F=0
[ -e "$SIM" ] && { echo "exists: $SIM"; exit 1; }
mkdir -p "$SIM"/{bin,opt,tmp,vartmp,varbackups,state,stageout}
trap 'rm -rf "$SIM"' EXIT
export SIMSTATE=$SIM/state
PREV=$($G -C "$REPO" rev-parse "v1.60.2^{commit}")
[ "${PREV:0:7}" = a429404 ] || { echo "SIM: v1.60.2 is ${PREV:0:7}, prod runs a429404"; exit 1; }

echo "== the sim origin: backport/v1.39-base + $KIT, the sim's tidy content, annotated tag v1.61.0"
$G clone -q --bare --single-branch --branch backport/v1.39-base "$REPO" "$SIM/origin.git" || exit 1
$G -C "$SIM/origin.git" fetch -q "$REPO" "+refs/remotes/origin/backport/v1.39-base:refs/heads/backport/v1.39-base" \
  "+refs/tags/v1.60.2:refs/tags/v1.60.2" || exit 1
git clone -q "$SIM/origin.git" "$SIM/work" && cd "$SIM/work" || exit 1
git -c advice.detachedHead=false checkout -q -B backport/v1.39-base origin/backport/v1.39-base
$G fetch -q "$REPO" "$KIT" || exit 1
git -c user.email=sim@x -c user.name=sim merge -q --no-edit FETCH_HEAD || exit 1
# the 34 reviewed names with made-up content (prod's bytes never leave prod); the manifest is re-summed over them
M=ops/prod-rt6/tmp_tidy_manifest.txt
while read -r _ _ path; do
  rel=${path#/tmp/}; mkdir -p "$SIM/tmp/$(dirname "$rel")"; printf 'sim %s %s\n' "$rel" "$RANDOM$RANDOM" > "$SIM/tmp/$rel"
done < <(grep '^FILE ' "$M")
{ grep -v '^FILE ' "$M"; grep '^FILE ' "$M" | while read -r _ _ path; do echo "FILE $(sha256sum "$SIM/tmp/${path#/tmp/}" | cut -d' ' -f1)  $path"; done; } > "$M.new" && mv "$M.new" "$M"
git -c user.email=sim@x -c user.name=sim commit -q -am "sim: the tidy manifest over the sim's own content" || exit 1
git push -q origin backport/v1.39-base && git fetch -q origin --tags
TARGET=$(git rev-parse HEAD); T7=${TARGET:0:7}
git -c user.email=sim@x -c user.name=sim tag -a v1.61.0 -m "sim v1.61.0" "$TARGET" && git push -q origin v1.61.0 || exit 1
echo "   prev ${PREV:0:7}  target $T7"

echo "== stage the window with the real mkstage_window.sh"
bash ops/prod-rt6/mkstage_window.sh "$SIM/stageout" "$TARGET" > "$SIM/stage.log" 2>&1; rc=$?
sed 's/^/   | /' "$SIM/stage.log" | grep -E 'staged|STOP|EXPECT_HEADS|PLAN_TODO|N_ITEMS|N_FILES' | head -n 12
row() { if [[ "$2" =~ $3 ]]; then echo "PASS  $1"; P=$((P+1)); else echo "FAIL  $1"; F=$((F+1)); echo "$2" | tail -n 40 | sed 's/^/      | /'; fi; }
row stage "rc=$rc $(cat "$SIM/stage.log")" "^rc=0 .*staged the RT6 window from $T7"
for ps in run_window_copy.ps1 run_window_fetch.ps1; do
  f="$SIM/stageout/$ps"
  row "$ps filled" "$(grep -c '__[A-Z_]*__' "$f" 2>&1) $(grep -m1 '^\$Kits' "$f") $(grep -m1 '^\$Heads' "$f")" \
    "^0 \\\$Kits   = 'icb-release-v1\.61\.0:[0-9a-f]{64} icb-rt6-rules:[0-9a-f]{64} icb-rt6-tidy:[0-9a-f]{64} icb-rt2-all:[0-9a-f]{64} icb-rt2-doors:[0-9a-f]{64}'\.Split.* \\\$Heads  = '$PREV $TARGET'\.Split"
  [ -n "${WINOUT:-}" ] && cp "$f" "$WINOUT/"
done
for d in icb-release-v1.61.0 icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do
  tar -xf "$SIM/stageout/$d.tar" -C "$SIM/tmp" || { echo "SIM: no $d.tar"; exit 1; }
done
row "kits verify" "$(for d in icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do ( cd "$SIM/tmp/$d" && sha256sum -c --quiet SHA256SUMS && echo "$d ok" ); done | tr '\n' ' ')" \
  "^icb-rt6-rules ok icb-rt6-tidy ok icb-rt2-all ok icb-rt2-doors ok $"

echo "== the fake prod at $T7 (after the deploy), alembic 0053"
git clone -q "$SIM/origin.git" "$SIM/opt/icb-platform" && git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET" || exit 1
mkdir -p "$SIM/opt/icb-platform/.venv/bin"
cp -a /etc "$SIM/etc" && mkdir -p "$SIM/etc/icb"
URL_OK='postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_platform'
printf '%s\n' "DATABASE_URL=$URL_OK" 'SESSION_SECRET=sim-not-real' 'MES_DEMO_AUTOLOGIN_USER=' 'ICB_ENVIRONMENT=prod' > "$SIM/etc/icb/backend.env"
chmod 600 "$SIM/etc/icb/backend.env"
echo icb_platform > "$SIMSTATE/dbname"; echo 0053 > "$SIMSTATE/alembic"; echo none > "$SIMSTATE/rules"
cat > "$SIM/bin/psql" <<'EOF'
#!/bin/bash
S=$SIMSTATE; sql=
case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ;; *) echo "psql stub: NOT a read-only session"; exit 3;; esac
while [ $# -gt 0 ]; do case "$1" in -c|-[A-Za-z]*c) sql=$2 ;; esac; shift; done
case "$sql" in
  *current_database*) cat "$S/dbname" ;;
  *alembic_version*) cat "$S/alembic" ;;
  *) echo "psql stub: unknown SQL: $sql"; exit 3 ;;
esac
EOF
cat > "$SIM/bin/pg_dump" <<'EOF'
#!/bin/bash
# data-only to stdout: one COPY block per -t table; with fail_pgdump: a partial dump, then exit 1 (the RT5 flaw's case)
t=(); while [ $# -gt 0 ]; do [ "$1" = -t ] && { t+=("$2"); shift; }; shift; done
for x in "${t[@]}"; do printf 'COPY %s (id, name, insulation_rule) FROM stdin;\n1\tCHILLER\t\\N\n\\.\n' "$x"; done
[ -f "$SIMSTATE/fail_pgdump" ] && { echo "pg_dump: error: query failed: server closed the connection" >&2; exit 1; }
echo "$(cat "$SIMSTATE/rules")" > "$SIMSTATE/dumped_rules"; exit 0
EOF
cat > "$SIM/opt/icb-platform/.venv/bin/python" <<'EOF'
#!/bin/bash
# rt6_rules.py's interface as the wrapper uses it; rt1_door_report.py, tools.costing_audit, rt2_all_compare.py
S=$SIMSTATE
ro=no; case "${PGOPTIONS:-}" in *default_transaction_read_only=on*) ro=yes;; esac
case "$1" in
  -c) [ "$2" = "import psycopg" ] && exit 0; exec python3 "$@" ;;
  -m) out=; stem=; while [ $# -gt 0 ]; do case "$1" in --out) out=$2;; --stem) stem=$2;; esac; shift; done
      [ $ro = yes ] || { echo "python stub: the packs ran in a session that is not read-only"; exit 3; }
      printf -- '- Cells: 120 · accepted 120\n' > "$out/$stem.md"; echo '{}' > "$out/$stem.json"; exit 0 ;;
  */rt2_all_compare.py) echo "   page run (stub) = CLI: 5 packs, every cell equal"; exit 0 ;;
  */rt1_door_report.py) [ $ro = yes ] || exit 3; echo "   14 OK, 0 FLAG (stub)"; exit 0 ;;
  */rt6_rules.py) shift ;;
  *) exec python3 "$@" ;;
esac
[ -n "${DATABASE_URL:-}" ] || { echo "REFUSED: DATABASE_URL is not set"; exit 1; }
case "$DATABASE_URL" in */icb_platform) ;; *) echo "REFUSED: --target prod expects database 'icb_platform'"; exit 1 ;; esac
mode=dry; out=; j=
while [ $# -gt 0 ]; do case "$1" in
  --apply) mode=apply;; --show) mode=show;; --revert) mode=revert; j=$2; shift;; --out-dir) out=$2; shift;;
  --target) [ "$2" = prod ] || { echo "stub: --target $2"; exit 3; }; shift;;
esac; shift; done
case $mode in
  dry|show) [ $ro = yes ] || { echo "python stub: the $mode ran in a session that is not read-only"; exit 3; } ;;
  *) [ $ro = no ] || { echo "ERROR: cannot execute UPDATE in a read-only transaction"; exit 1; }
     [ -n "$out" ] || { echo "error: --apply / --revert need --out-dir"; exit 2; } ;;
esac
r=$(cat "$S/rules"); ts=$(date -u +%Y%m%dT%H%M%SZ)
case $mode in
  dry) echo "database icb_platform (--target prod); RT6 insulation rules; plan sha256 (stub)"
       if [ -f "$S/plan_one" ]; then echo "   ALREADY #3 CHILLER"; echo "   TODO    #4 FREEZER"; echo "1 to apply, 1 already applied."
       elif [ "$r" = both ]; then echo "   ALREADY #3 CHILLER"; echo "   ALREADY #4 FREEZER"; echo "0 to apply, 2 already applied."
       else echo "   TODO    #3 CHILLER: None -> {...}"; echo "   TODO    #4 FREEZER: None -> {...}"; echo "2 to apply, 0 already applied."; fi ;;
  show) echo "database icb_platform (--target prod); every family's insulation rule (read only)"
        echo "   #3   CHILLER      insulation_rule = $([ "$r" = both ] && echo "'{...EPS...}'" || echo None)"
        echo "live breaching costings: 0"; echo "soft-deleted breaching costings: $([ "$r" = both ] && echo 1 || echo 0)" ;;
  apply) [ "$r" = both ] && { echo "0 to apply"; exit 0; }
         echo both > "$S/rules"; mkdir -p "$out"
         echo '{"tool": "rt6_rules", "database": "icb_platform", "target": "prod", "rows": [{"id": 3}, {"id": 4}]}' > "$out/rt6_rules_journal_prod_$ts.json"
         echo "APPLIED 2 rule(s): #3 CHILLER; #4 FREEZER"; echo "journal $out/rt6_rules_journal_prod_$ts.json" ;;
  revert) grep -q '"tool": "rt6_rules"' "$j" 2>/dev/null || { echo "REFUSED: $j is not an rt6_rules journal"; exit 2; }
          [ "$r" = both ] || { echo "REFUSED: #3 CHILLER reads None, not the journal's: moved since"; exit 2; }
          echo none > "$S/rules"; mkdir -p "$out"; echo '{"tool": "rt6_rules", "reverted": "x"}' > "$out/rt6_rules_revert_prod_$ts.json"
          echo "REVERTED 2 rule(s); record $out/rt6_rules_revert_prod_$ts.json" ;;
esac
EOF
chmod +x "$SIM/bin"/* "$SIM/opt/icb-platform/.venv/bin/python"
# what the tidy must leave: the OS items, node's cache, RT6's kits, and anything newer (the deploy's rollback note)
mkdir -p "$SIM/tmp/node-compile-cache/v22" "$SIM/tmp/systemd-private-abc-icb-backend.service-x" "$SIM/tmp/snap-private-tmp"
echo cache > "$SIM/tmp/node-compile-cache/v22/a"; echo note > "$SIM/tmp/icb-rollback-20261007-061500.txt"
chown 1001:1001 "$SIM/tmp/prod_quote93.py" && chmod 640 "$SIM/tmp/prod_quote93.py"; chmod 750 "$SIM/tmp/explosive-golden"
OWN_BEFORE=$(stat -c '%u:%g %a' "$SIM/tmp/prod_quote93.py" "$SIM/tmp/explosive-golden" | tr '\n' ' ')

HOST=icb-mes-prod
run() { # the staged kit inside private mount + UTS namespaces, as prod would (1 s apart: each run's folder is per-second)
  sleep 1
  unshare -m -u bash -c "
    hostname '$HOST' &&
    mount --bind '$SIM/opt' /opt && mount --bind '$SIM/etc' /etc && mount --bind '$SIM/vartmp' /var/tmp &&
    mount --bind '$SIM/varbackups' /var/backups && mount --bind '$SIM/tmp' /tmp &&
    export PATH='$SIM/bin':\$PATH SIMSTATE='$SIMSTATE' && bash $*" 2>&1
}
L1="^######## RT6 rules %s · machine icb-mes-prod · db icb_platform @ 127\\.0\\.0\\.1:5432 · head $T7 · "
first() { printf "$L1" "$1"; }
K=$SIM/varbackups/icb-rt6-2026-10

echo; echo "== icb-rt6-rules: the refusals before any write"
HOST=icb-mes-dev; log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply); HOST=icb-mes-prod
row "rules wrong machine" "$log" "machine icb-mes-dev .*STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev', this step runs on 'icb-mes-prod'; nothing was run"
sed -i "s#^DATABASE_URL=.*#DATABASE_URL=postgresql+psycopg://icb_app:sim-not-real@127.0.0.1:5432/icb_prodmirror#" "$SIM/etc/icb/backend.env"; echo icb_prodmirror > "$SIMSTATE/dbname"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply)
row "rules wrong database" "$log" "db icb_prodmirror @ 127\.0\.0\.1:5432 .*STOP \[WHERE\]: WRONG PLACE — database is 'icb_prodmirror', this step runs on 'icb_platform'; the URL names database 'icb_prodmirror'"
sed -i "s#^DATABASE_URL=.*#DATABASE_URL=$URL_OK#" "$SIM/etc/icb/backend.env"; echo icb_platform > "$SIMSTATE/dbname"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$PREV"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh dryrun)
row "rules over v1.60.2 code" "$log" "STOP \[WHERE\]: WRONG PLACE — code is at a429404, this step expects $T7; nothing was run"
git -C "$SIM/opt/icb-platform" -c advice.detachedHead=false checkout -q "$TARGET"
echo 0052 > "$SIMSTATE/alembic"; log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply); echo 0053 > "$SIMSTATE/alembic"
row "rules over alembic 0052" "$log" "STOP \[DB\]: alembic_version is '0052', expected 0053"
cp "$SIM/tmp/icb-rt6-rules/rt6_rules.py" "$SIMSTATE/tool.keep"; echo "# edited" >> "$SIM/tmp/icb-rt6-rules/rt6_rules.py"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply); cp "$SIMSTATE/tool.keep" "$SIM/tmp/icb-rt6-rules/rt6_rules.py"
row "rules tampered kit" "$log" "STOP \[KIT\]: staged files do not match SHA256SUMS"
touch "$SIMSTATE/plan_one"; log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply); rm -f "$SIMSTATE/plan_one"
row "rules a different plan" "$log" "STOP \[PLAN\]: the plan is '1 to apply, 1 already applied\.', the reviewed plan is '2 to apply, 0 already applied\.'"
touch "$SIMSTATE/fail_pgdump"; log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply); rm -f "$SIMSTATE/fail_pgdump"
row "rules failed dump" "$log rules=$(cat "$SIMSTATE/rules") failed=$(ls "$K"/*.FAILED 2>/dev/null | wc -l)" \
  "STOP \[BACKUP\]: backup [^ ]*pre_apply_rules_[^ ]*: pg_dump exited 1, gzip 0 — nothing applied.* rules=none failed=1$"
row "rules: nothing written so far" "rules=$(cat "$SIMSTATE/rules") journals=$(ls "$K"/journal_* 2>/dev/null | wc -l)" "^rules=none journals=0$"

echo; echo "== icb-rt6-rules: the window's path (dry-run, apply, again, show) and the undo"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh dryrun)
row "rules dryrun" "$log" "$(first dryrun).*\(the line above, as run: machine icb-mes-prod, db icb_platform @ 127\.0\.0\.1:5432, head $TARGET, mode dryrun\).*2 to apply, 0 already applied\..*######## DONE \(dryrun: 2 to apply, 0 already applied\.\)"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply)
row "rules apply" "$log" "$(first apply).*ok   backup /var/backups/icb-rt6-2026-10/pre_apply_rules_[0-9TZ]+\.sql\.gz .*holds: icb_costings\.trailer_groups.*APPLIED 2 rule.*ok   journal /var/backups/icb-rt6-2026-10/journal_rules_rt6_rules_journal_prod_.*0 to apply, 2 already applied\..*live breaching costings: 0.*soft-deleted breaching costings: 1.*######## DONE \(apply\).*undo: sudo bash /tmp/icb-rt6-rules/rt6_rules\.sh revert /var/backups/icb-rt6-2026-10/journal_rules_"
J=$(ls "$K"/journal_rules_*.json | head -n1)
row "rules kept" "$(ls "$K" | sed 's/[0-9TZ]\{16\}/<ts>/g' | sort | tr '\n' ' ') dumped=$(cat "$SIMSTATE/dumped_rules") $(grep -c . "${J%.json}.provenance.txt") $(stat -c %a "$K")" \
  "journal_rules_rt6_rules_journal_prod_<ts>\.json journal_rules_rt6_rules_journal_prod_<ts>\.provenance\.txt pre_apply_rules_<ts>\.sql\.gz pre_apply_rules_<ts>\.sql\.gz\.FAILED  ?dumped=none 7 700$"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply)
row "rules apply again" "$log" "0 to apply, 2 already applied\..*######## DONE \(apply: already applied\)"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh show)
row "rules show" "$log" "$(first show).*insulation_rule = '\{\.\.\.EPS\.\.\.\}'.*live breaching costings: 0.*soft-deleted breaching costings: 1.*######## DONE \(show\)"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh revert "$(echo "$J" | sed "s#^$SIM/varbackups#/var/backups#")")
row "rules revert" "$log rules=$(cat "$SIMSTATE/rules")" "$(first revert).*ok   backup /var/backups/icb-rt6-2026-10/pre_revert_rules_.*REVERTED 2 rule.*ok   record /var/backups/icb-rt6-2026-10/revert_rules_rt6_rules_revert_prod_.*insulation_rule = None.*######## DONE \(revert\).* rules=none$"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh revert "$(echo "$J" | sed "s#^$SIM/varbackups#/var/backups#")")
row "rules revert twice" "$log" "REFUSED: .*moved since.*STOP \[REVERT\]: revert refused or failed \(exit 2\): nothing changed"
log=$(run /tmp/icb-rt6-rules/rt6_rules.sh apply)
row "rules re-apply" "$log rules=$(cat "$SIMSTATE/rules")" "######## DONE \(apply\).* rules=both$"

echo; echo "== icb-rt6-tidy (real files)"
T=/tmp/icb-rt6-tidy/rt6_tmp_tidy.sh
DAY=$(date +%Y%m%d); A=$SIM/varbackups/icb-tmp-archive-$DAY
HOST=icb-mes-dev; log=$(run $T apply); HOST=icb-mes-prod
row "tidy wrong machine" "$log" "^######## RT6 tmp tidy apply · machine icb-mes-dev .*STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev'"
log=$(run $T dryrun)
row "tidy dryrun" "$log" "^######## RT6 tmp tidy dryrun · machine icb-mes-prod · db icb_platform @ 127\.0\.0\.1:5432 · head $T7 · .*34 of 34 present, 0 missing.*all 47 files match.*######## DONE \(dryrun: 34 to move, 47 files, as reviewed\)"
f=$(find "$SIM/tmp/sept-recheck" -type f | head -n1); cp -p "$f" "$SIMSTATE/one.keep"; echo changed >> "$f"
log=$(run $T apply); cp -p "$SIMSTATE/one.keep" "$f"
row "tidy changed file" "$log" "STOP \[STATE\]: the files under the reviewed items are not the reviewed ones \(above\) — nothing moved"
echo extra > "$SIM/tmp/explosive-golden/extra.txt"; log=$(run $T apply); rm -f "$SIM/tmp/explosive-golden/extra.txt"
row "tidy extra file" "$log" "STOP \[STATE\]: the files under the reviewed items are not the reviewed ones"
mv "$SIM/tmp/manni_inspect.sh" "$SIMSTATE/"; log=$(run $T apply); mv "$SIMSTATE/manni_inspect.sh" "$SIM/tmp/"
row "tidy missing item" "$log" "33 of 34 present, 1 missing.*STOP \[STATE\]: 1 reviewed item\(s\) are missing from /tmp — not the reviewed state; nothing moved"
row "tidy: nothing moved so far" "$(ls -d "$SIM"/varbackups/icb-tmp-archive-* 2>/dev/null | wc -l)" "^0$"
log=$(run $T apply)
row "tidy apply" "$log" "######## DONE \(apply: 34 items moved to /var/backups/icb-tmp-archive-$DAY, read back\)"
left=0; while read -r n; do [ -e "$SIM/tmp/$n" ] && left=$((left+1)); done < <(sed -n 's/^ITEM //p' "$SIM/tmp/icb-rt6-tidy/tmp_tidy_manifest.txt")
row "tidy result" "left=$left arch=$(stat -c '%U:%G %a' "$A") files=$(find "$A" -type f | wc -l) summed=$(wc -l < "$A/SHA256SUMS") sums=$( cd "$A" && sha256sum -c --quiet SHA256SUMS && echo ok) own=$(stat -c '%u:%g %a' "$A/prod_quote93.py" "$A/explosive-golden" | tr '\n' ' ')stays=$(ls "$SIM/tmp" | grep -cE '^(node-compile-cache|systemd-private-abc-icb-backend\.service-x|snap-private-tmp|icb-rollback-20261007-061500\.txt|icb-rt6-rules|icb-rt6-tidy|icb-release-v1\.61\.0|icb-rt2-all|icb-rt2-doors)$')" \
  "^left=0 arch=root:root 700 files=49 summed=47 sums=ok own=${OWN_BEFORE}stays=9$"
log=$(run $T apply)
row "tidy apply again" "$log" "0 of 34 present, 34 missing.*already tidied.*SHA256SUMS: all match.*######## DONE \(apply: already tidied\)"
log=$(run $T show)
row "tidy show" "$log" "in /tmp: 0 of 34 present.*archive /var/backups/icb-tmp-archive-$DAY: 49 files.*SHA256SUMS: all match.*node-compile-cache: present.*######## DONE \(show\)"
log=$(run $T restore "/var/backups/icb-tmp-archive-$DAY")
row "tidy restore" "$log" "######## DONE \(restore: 34 of 34 back in /tmp, sums as reviewed\)"
log=$(run $T apply)
row "tidy archive never mixed into" "$log" "STOP \[ARCHIVE\]: /var/backups/icb-tmp-archive-$DAY already exists — never mixed into"

echo; echo "== icb-rt2-doors / icb-rt2-all: the safe-paste first line"
log=$(run /tmp/icb-rt2-doors/rt2_doors.sh)
row "doors" "$log" "^######## RT6 door report \(read only\) · machine icb-mes-prod · db icb_platform @ 127\.0\.0\.1:5432 · head $T7 · .*14 OK, 0 FLAG.*######## DONE"
HOST=icb-mes-dev; log=$(run /tmp/icb-rt2-doors/rt2_doors.sh); HOST=icb-mes-prod
row "doors wrong machine" "$log" "machine icb-mes-dev .*STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev'"
log=$(run /tmp/icb-rt2-all/rt2_all.sh post)
row "all" "$log" "^######## RT6 All post \(read only\) · machine icb-mes-prod · db icb_platform @ 127\.0\.0\.1:5432 · head $T7 · .*smoke exit=0.*explosive exit=0.*######## DONE \(post\): PAGE = CLI"
HOST=icb-mes-dev; log=$(run /tmp/icb-rt2-all/rt2_all.sh post); HOST=icb-mes-prod
row "all wrong machine" "$log" "machine icb-mes-dev .*STOP \[WHERE\]: WRONG PLACE — machine is 'icb-mes-dev'"

echo; echo "== $P passed, $F failed"
cd / && rm -rf "$SIM"; trap - EXIT
echo "== /root after: $(ls -d /root/rt6simW-* 2>/dev/null | wc -l) sim folder(s) left"
