#!/usr/bin/env bash
# RT5 — build the VM staging folders for the v1.60.2 window from COMMITTED blobs. Git Bash, from the repo, AFTER the
# release PR has merged and the annotated tag v1.60.2 is on origin (tag first):
#
#     bash ops/prod-rt5/mkstage_window.sh <empty-out-dir> <merge-sha>
#
#   icb-release-v1.60.2  the release kit (ops/prod-release-v1.60.2/mkstage.sh)
#   icb-rt5-notes        rt5_notes.sh + rt5_notes.py: the two rule notes (over v1.60.2 / 0052 only; PLAN_TODO 2)
#   icb-rt2-all          RT2's CLI "All" beside the page's All (window step 1 "pre" over v1.60.1 / 0051, step 4 "post"
#                        over v1.60.2 / 0052); C11 reads the RT2, RT4 AND RT5 journal folders, so "post" must be a page
#                        run that started after the notes were applied
#   icb-rt2-doors        RT2's door report, unchanged (window step 7: 14 OK) — over either code
set -u
OUTDIR=${1:?usage: mkstage_window.sh <empty-out-dir> <merge-sha>}
SHA=$(git rev-parse --verify "${2:?merge sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.60.1^{commit}") || { echo "STOP: no tag v1.60.1"; exit 1; }
[ "${PREV:0:7}" = 01751fa ] || { echo "STOP: v1.60.1 is ${PREV:0:7}, prod runs 01751fa"; exit 1; }
TAG_OBJ=$(git rev-parse -q --verify "refs/tags/v1.60.2") || { echo "STOP: no tag v1.60.2 — tag the merge commit first"; exit 1; }
[ "$(git ls-remote --tags origin refs/tags/v1.60.2 | cut -f1 | head -n1)" = "$TAG_OBJ" ] \
  || { echo "STOP: v1.60.2 is not on origin as the local object — push the tag"; exit 1; }
NEXT=$(git rev-parse "v1.60.2^{commit}")
[ "$NEXT" = "$SHA" ] || { echo "STOP: v1.60.2 peels to ${NEXT:0:7}, not the given ${SHA:0:7}"; exit 1; }
HEADS="$PREV $NEXT"
for d in icb-release-v1.60.2 icb-rt5-notes icb-rt2-all icb-rt2-doors; do [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }; done
mkdir -p "$OUTDIR" || exit 1

bash "$(dirname "$0")/../prod-release-v1.60.2/mkstage.sh" "$OUTDIR" "$SHA" "$PREV" > "$OUTDIR/mkstage_release.log" 2>&1 \
  || { cat "$OUTDIR/mkstage_release.log"; echo "STOP: the release kit did not stage"; exit 1; }
rm -f "$OUTDIR/icb-release-v1.60.2.tar"      # re-tarred with the others below
grep -m1 '^staged' "$OUTDIR/mkstage_release.log"

N="$OUTDIR/icb-rt5-notes"; mkdir -p "$N" || exit 1
for f in rt5_notes.sh rt5_notes.py; do git cat-file blob "$SHA:ops/prod-rt5/$f" > "$N/$f" || exit 1; done
mkdir -p "$N/lib" && git cat-file blob "$SHA:ops/lib/icb_backup.sh" > "$N/lib/icb_backup.sh" || exit 1   # RT6
cat > "$N/expected.env" <<EOF
# written by ops/prod-rt5/mkstage_window.sh on $(date -Is) — the two rule notes, over v1.60.2 only
EXPECT_HEAD=$NEXT
EXPECT_ALEMBIC=0052
PLAN_TODO=2
TOOL_SHA=$(sha256sum "$N/rt5_notes.py" | cut -d' ' -f1)
STAGED_FROM=$SHA
EOF
( cd "$N" && sha256sum rt5_notes.sh rt5_notes.py lib/icb_backup.sh expected.env > SHA256SUMS ) || exit 1

S="$OUTDIR/icb-rt2-all"; mkdir -p "$S" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by ops/prod-rt5/mkstage_window.sh on $(date -Is) — the RT5 window's All: pre (v1.60.1), post (v1.60.2 + notes)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0051 0052"
KEEP_DIRS="/var/backups/icb-rt2-2026-10 /var/backups/icb-rt4-2026-10 /var/backups/icb-rt5-2026-10"
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt2_all.sh rt2_all_compare.py expected.env > SHA256SUMS ) || exit 1

T="$OUTDIR/icb-rt2-doors"; mkdir -p "$T" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$T/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$T/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$T/all.json" || exit 1
cat > "$T/expected.env" <<EOF
# written by ops/prod-rt5/mkstage_window.sh on $(date -Is) — the RT5 window's door report (step 7: 14 OK)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0051 0052"
STAGED_FROM=$SHA
EOF
( cd "$T" && sha256sum rt2_doors.sh rt1_door_report.py all.json expected.env > SHA256SUMS ) || exit 1

CR=$(cat "$OUTDIR"/icb-rt5-notes/* "$OUTDIR"/icb-rt2-*/*.sh "$OUTDIR"/icb-rt2-*/*.py "$OUTDIR"/icb-rt2-*/expected.env \
     "$OUTDIR"/icb-rt2-*/SHA256SUMS | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
for s in "$OUTDIR"/icb-*/*.sh; do bash -n "$s" || { echo "STOP: $s does not parse"; exit 1; }; done
echo "staged from $SHA (heads: $HEADS; alembic: 0051 -> 0052)"
for d in icb-rt5-notes icb-rt2-all icb-rt2-doors; do echo "-- $d"; cat "$OUTDIR/$d/expected.env"; done
( cd "$OUTDIR" && for d in icb-*/; do d=${d%/}; tar -cf "$d.tar" "$d" || exit 1; done ) || exit 1
ls -l "$OUTDIR"/icb-*.tar && sha256sum "$OUTDIR"/icb-*.tar
