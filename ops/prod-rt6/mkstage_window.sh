#!/usr/bin/env bash
# RT6 — stage EVERY kit of the v1.61.0 window from COMMITTED blobs (Git Bash, after the release PR merged and the
# annotated tag v1.61.0 is pushed):
#
#     bash ops/prod-rt6/mkstage_window.sh <empty-out-dir> <target-sha>
#
#   icb-release-v1.61.0  the release (ops/prod-release-v1.61.0/mkstage.sh, unchanged): preflight / verify / env / deploy
#   icb-rt6-rules        rt6_rules.{sh,py} + the staged pure check: Burt's two rules (over v1.61.0 / 0053; PLAN_TODO 2)
#                        and `show` = the window's read-only breach count
#   icb-rt6-tidy         rt6_tmp_tidy.sh + tmp_tidy_manifest.txt: the 34 reviewed /tmp items (47 files)
#   icb-rt2-all          RT2's All (pre on v1.60.2 / 0052, post on v1.61.0 / 0053 + the rules)
#   icb-rt2-doors        RT2's door report (14 OK)
# Every kit carries lib/icb_where.sh and the place it must run (machine, database @ host, HEAD): its FIRST output line
# names them and it refuses a wrong place (RT6 safe pastes). Beside the tars: run_window_copy.ps1 (one line on Windows:
# copy + unpack + verify on prod) and run_window_fetch.ps1 (one line: bring every out-* folder back to Downloads).
set -u
OUTDIR=${1:?usage: mkstage_window.sh <empty-out-dir> <target-sha>}
SHA=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.60.2^{commit}") || { echo "STOP: no tag v1.60.2"; exit 1; }
HEADS="$PREV $SHA"
WHERE="EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432"
mkdir -p "$OUTDIR" || exit 1
for d in icb-release-v1.61.0 icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do
  [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }
done
lib() { mkdir -p "$1/lib" && git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$1/lib/icb_where.sh" \
        && git cat-file blob "$SHA:ops/lib/icb_backup.sh" > "$1/lib/icb_backup.sh"; }
sums() { ( cd "$1" && find . -type f ! -name SHA256SUMS | sed 's#^\./##' | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ); }

bash ops/prod-release-v1.61.0/mkstage.sh "$OUTDIR" "$SHA" "$PREV" > "$OUTDIR/mkstage_release.log" 2>&1 \
  || { cat "$OUTDIR/mkstage_release.log"; echo "STOP: the release kit did not stage"; exit 1; }
rm -f "$OUTDIR/icb-release-v1.61.0.tar"      # re-tarred with the others below
grep -m1 '^staged' "$OUTDIR/mkstage_release.log"

R="$OUTDIR/icb-rt6-rules"; mkdir -p "$R" && lib "$R" || exit 1
for f in rt6_rules.sh rt6_rules.py; do git cat-file blob "$SHA:ops/prod-rt6/$f" > "$R/$f" || exit 1; done
git cat-file blob "$SHA:backend/app/services/insulation_rules.py" > "$R/insulation_rules.py" || exit 1
cat > "$R/expected.env" <<EOF
# written by ops/prod-rt6/mkstage_window.sh on $(date -Is) — Burt's two insulation rules, over v1.61.0 only
$WHERE
EXPECT_HEADS="$SHA"
EXPECT_ALEMBIC=0053
PLAN_TODO=2
TOOL_SHA=$(sha256sum "$R/rt6_rules.py" | cut -d' ' -f1)
STAGED_FROM=$SHA
EOF
sums "$R" || exit 1

T="$OUTDIR/icb-rt6-tidy"; mkdir -p "$T" && lib "$T" || exit 1
for f in rt6_tmp_tidy.sh tmp_tidy_manifest.txt; do git cat-file blob "$SHA:ops/prod-rt6/$f" > "$T/$f" || exit 1; done
NI=$(grep -c '^ITEM ' "$T/tmp_tidy_manifest.txt"); NF=$(grep -c '^FILE ' "$T/tmp_tidy_manifest.txt")
[ "$NI" = 34 ] && [ "$NF" = 47 ] || { echo "STOP: the tidy manifest has $NI items / $NF files, the reviewed list is 34 / 47"; exit 1; }
cat > "$T/expected.env" <<EOF
# written by ops/prod-rt6/mkstage_window.sh on $(date -Is) — the /tmp tidy (RT6_RULING_1): exactly the reviewed list
$WHERE
EXPECT_HEADS="$HEADS"
N_ITEMS=$NI
N_FILES=$NF
STAGED_FROM=$SHA
EOF
sums "$T" || exit 1

A="$OUTDIR/icb-rt2-all"; mkdir -p "$A" && lib "$A" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$A/$f" || exit 1; done
cat > "$A/expected.env" <<EOF
# written by ops/prod-rt6/mkstage_window.sh on $(date -Is) — the RT6 window's All: pre (v1.60.2), post (v1.61.0 + rules)
$WHERE
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0052 0053"
KEEP_DIRS="/var/backups/icb-rt2-2026-10 /var/backups/icb-rt4-2026-10 /var/backups/icb-rt5-2026-10 /var/backups/icb-rt6-2026-10"
STAGED_FROM=$SHA
EOF
sums "$A" || exit 1

D="$OUTDIR/icb-rt2-doors"; mkdir -p "$D" && lib "$D" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$D/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$D/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$D/all.json" || exit 1
cat > "$D/expected.env" <<EOF
# written by ops/prod-rt6/mkstage_window.sh on $(date -Is) — the RT6 window's door report (14 OK)
$WHERE
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0052 0053"
STAGED_FROM=$SHA
EOF
sums "$D" || exit 1

CR=$(find "$OUTDIR"/icb-* -type f \( -name '*.sh' -o -name '*.py' -o -name '*.env' -o -name '*.txt' -o -name SHA256SUMS \) -print0 \
     | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
for s in "$OUTDIR"/icb-*/*.sh "$OUTDIR"/icb-*/lib/*.sh; do bash -n "$s" || { echo "STOP: $s does not parse"; exit 1; }; done
( cd "$OUTDIR" && for d in icb-release-v1.61.0 icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do
    tar -cf "$d.tar" "$d" || exit 1; done ) || exit 1
LIST=$(cd "$OUTDIR" && for d in icb-release-v1.61.0 icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do
         printf '%s:%s ' "$d" "$(sha256sum "$d.tar" | cut -d' ' -f1)"; done)
for ps in run_window_copy.ps1 run_window_fetch.ps1; do
  git cat-file blob "$SHA:ops/prod-rt6/$ps" | sed -e "s/__KITS__/${LIST% }/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$HEADS/" \
    > "$OUTDIR/$ps" || exit 1
  grep -q '__[A-Z_]*__' "$OUTDIR/$ps" && { echo "STOP: $ps still has a placeholder"; exit 1; }
  LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/$ps" && { echo "STOP: $ps is not ASCII"; exit 1; }
done
echo "staged the RT6 window from ${SHA:0:7} (prod today ${PREV:0:7}; heads: $HEADS)"
for d in icb-rt6-rules icb-rt6-tidy icb-rt2-all icb-rt2-doors; do echo "-- $d"; grep -v '^#' "$OUTDIR/$d/expected.env"; done
ls -l "$OUTDIR"/*.tar "$OUTDIR"/*.ps1 && sha256sum "$OUTDIR"/*.tar
