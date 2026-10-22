#!/usr/bin/env bash
# RT9 — stage EVERY kit and every laptop line of the v1.62.0 window from COMMITTED blobs (Git Bash, after the release
# PR merged and the annotated tag v1.62.0 is pushed):
#
#     bash ops/prod-release-v1.62.0/mkstage_window.sh <empty-out-dir> <target-sha>
#
#   icb-release-v1.62.0  the release (mkstage.sh): preflight / deploy / verify (its checked backup is in the deploy)
#   icb-rt2-all          RT2's All (before on v1.61.1, after on v1.62.0): the CLI beside the page's, cell for cell
#   icb-rt2-doors        RT2's door report (14 OK)
# Every kit carries lib/icb_where.sh and the place it must run (machine, database @ host, HEAD) and the reboot guard:
# its FIRST output line names the machine, the database, the HEAD and the BOOT TIME, and it refuses a wrong place or a
# kit staged before prod's last boot (the copy line stamps .staged_at).
# Beside the tars, Michael's laptop lines (ASCII; each run by its full path from PowerShell or Command Prompt):
#   run_window_copy.ps1     step 1: copy + unpack + verify + stamp on prod
#   run_window_step.ps1     steps 2-6 and 8: ssh to the VM, then the staged kit BY PATH under sudo
#   run_window_fetch.ps1    step 9: every out-* folder this window wrote, back to Downloads
#   run_window_cleanup.ps1  the close: the window's /tmp names removed and read back
# with window_common.ps1 (dot-sourced) and rt9_vm.sh (copied to prod and run by path by every line).
# The paste blocks for Michael are in docs/runbooks/prod-deploy-v1.62.0.md, byte for byte as the CA sends them.
set -u
OUTDIR=${1:?usage: mkstage_window.sh <empty-out-dir> <target-sha>}
SHA=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.61.1^{commit}") || { echo "STOP: no tag v1.61.1"; exit 1; }
[ "${PREV:0:7}" = 5511355 ] || { echo "STOP: v1.61.1 is ${PREV:0:7}, prod runs 5511355"; exit 1; }
HEADS="$PREV $SHA"
WHERE="EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
REBOOT_GUARD=1"
KITS="icb-release-v1.62.0 icb-rt2-all icb-rt2-doors"
mkdir -p "$OUTDIR" || exit 1
for d in $KITS; do [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }; done
lib() { mkdir -p "$1/lib" && git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$1/lib/icb_where.sh" \
        && git cat-file blob "$SHA:ops/lib/icb_backup.sh" > "$1/lib/icb_backup.sh"; }
sums() { ( cd "$1" && find . -type f ! -name SHA256SUMS | sed 's#^\./##' | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ); }

bash ops/prod-release-v1.62.0/mkstage.sh "$OUTDIR" "$SHA" "$PREV" > "$OUTDIR/mkstage_release.log" 2>&1 \
  || { cat "$OUTDIR/mkstage_release.log"; echo "STOP: the release kit did not stage"; exit 1; }
rm -f "$OUTDIR/icb-release-v1.62.0.tar"      # re-tarred with the others below
grep -m2 -E '^(staged|calculator)' "$OUTDIR/mkstage_release.log"

A="$OUTDIR/icb-rt2-all"; mkdir -p "$A" && lib "$A" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$A/$f" || exit 1; done
cat > "$A/expected.env" <<EOF
# written by ops/prod-release-v1.62.0/mkstage_window.sh on $(date -Is) — the RT9 window's All: before (v1.61.1), after (v1.62.0)
$WHERE
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0053"
KEEP_DIRS="/var/backups/icb-rt2-2026-10 /var/backups/icb-rt4-2026-10 /var/backups/icb-rt5-2026-10 /var/backups/icb-rt6-2026-10"
STAGED_FROM=$SHA
EOF
sums "$A" || exit 1

D="$OUTDIR/icb-rt2-doors"; mkdir -p "$D" && lib "$D" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$D/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$D/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$D/all.json" || exit 1
cat > "$D/expected.env" <<EOF
# written by ops/prod-release-v1.62.0/mkstage_window.sh on $(date -Is) — the RT9 window's door report (14 OK)
$WHERE
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0053"
STAGED_FROM=$SHA
EOF
sums "$D" || exit 1

grep -q '^KIT_DIR=\$BASE' "$OUTDIR/icb-release-v1.62.0/release.sh" || { echo "STOP: release.sh does not set KIT_DIR"; exit 1; }
CR=$(find "$OUTDIR"/icb-* -type f \( -name '*.sh' -o -name '*.py' -o -name '*.env' -o -name '*.txt' -o -name SHA256SUMS \) -print0 \
     | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
for s in "$OUTDIR"/icb-*/*.sh "$OUTDIR"/icb-*/lib/*.sh; do bash -n "$s" || { echo "STOP: $s does not parse"; exit 1; }; done
( cd "$OUTDIR" && for d in $KITS; do tar -cf "$d.tar" "$d" || exit 1; done ) || exit 1
LIST=$(cd "$OUTDIR" && for d in $KITS; do printf '%s:%s ' "$d" "$(sha256sum "$d.tar" | cut -d' ' -f1)"; done)

# the laptop side: rt9_vm.sh (LF, as committed) and the .ps1 lines with every placeholder filled
W=ops/prod-release-v1.62.0/window
git cat-file blob "$SHA:$W/rt9_vm.sh" > "$OUTDIR/rt9_vm.sh" || exit 1
bash -n "$OUTDIR/rt9_vm.sh" || { echo "STOP: rt9_vm.sh does not parse"; exit 1; }
[ "$(tr -cd '\r' < "$OUTDIR/rt9_vm.sh" | wc -c | tr -d ' ')" = 0 ] || { echo "STOP: rt9_vm.sh has CR bytes"; exit 1; }
VM_SHA=$(sha256sum "$OUTDIR/rt9_vm.sh" | cut -d' ' -f1)
for ps in window_common.ps1 run_window_copy.ps1 run_window_step.ps1 run_window_fetch.ps1 run_window_cleanup.ps1; do
  git cat-file blob "$SHA:$W/$ps" | sed -e "s/__KITS__/${LIST% }/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$HEADS/" \
    -e "s/__VM_SHA__/$VM_SHA/" > "$OUTDIR/$ps" || exit 1
  grep -q '__[A-Z_]*__' "$OUTDIR/$ps" && { echo "STOP: $ps still has a placeholder"; exit 1; }
  LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/$ps" && { echo "STOP: $ps is not ASCII"; exit 1; }
done
( cd "$OUTDIR" && sha256sum ./*.tar rt9_vm.sh ./*.ps1 > STAGE_SHA256SUMS && { echo "STAGED_FROM=$SHA"; echo "EXPECT_HEADS=$HEADS"; } > STAGED_FROM.txt )
echo "staged the RT9 window from ${SHA:0:7} (prod today ${PREV:0:7}; heads: $HEADS)"
for d in icb-rt2-all icb-rt2-doors; do echo "-- $d"; grep -v '^#' "$OUTDIR/$d/expected.env"; done
ls -l "$OUTDIR"/*.tar "$OUTDIR"/*.ps1 "$OUTDIR"/rt9_vm.sh && cat "$OUTDIR/STAGE_SHA256SUMS"
