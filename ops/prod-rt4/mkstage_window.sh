#!/usr/bin/env bash
# RT4 — build the VM staging folders for the v1.60.1 window from COMMITTED blobs. Git Bash, from the repo:
#
#     bash ops/prod-rt4/mkstage_window.sh <empty-out-dir> <commit>
#
#   icb-rt4-data    rt4_data.sh + the tool + Manifest S (ops/prod-rt4/mkstage_data.sh; over v1.60.1 / 0051 only)
#   icb-rt2-all     RT2's CLI "All" beside the page's All (window steps 1 "pre", 3 "post", 5 "afterS") — over v1.60.0
#                   or v1.60.1, alembic 0051; C11 reads the RT2 AND the RT4 journal folders (KEEP_DIRS)
#   icb-rt2-doors   RT2's door report, unchanged (window step 7: 14 OK) — same codes
#
# The data kit pins prod's code to the v1.60.1 tag's commit, so it can only be staged once the annotated tag is on
# origin (tag first). The two RT2 kits are staged for v1.60.0 alone until then.
set -u
OUTDIR=${1:?usage: mkstage_window.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.60.0^{commit}") || { echo "STOP: no tag v1.60.0"; exit 1; }
[ "${PREV:0:7}" = 682a6cc ] || { echo "STOP: v1.60.0 is ${PREV:0:7}, prod runs 682a6cc"; exit 1; }
HEADS=$PREV; NEXT=
if TAG_OBJ=$(git rev-parse -q --verify "refs/tags/v1.60.1"); then
  [ "$(git ls-remote --tags origin refs/tags/v1.60.1 | cut -f1 | head -n1)" = "$TAG_OBJ" ] \
    || { echo "STOP: v1.60.1 is not on origin as the local object — push the tag"; exit 1; }
  NEXT=$(git rev-parse "v1.60.1^{commit}"); HEADS="$PREV $NEXT"
else
  echo "note: no tag v1.60.1 yet — the All and door kits are staged for v1.60.0 only, and the S data kit is NOT staged"
fi
for d in icb-rt4-data icb-rt2-all icb-rt2-doors; do [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }; done
mkdir -p "$OUTDIR" || exit 1

if [ -n "$NEXT" ]; then
  bash "$(dirname "$0")/mkstage_data.sh" "$OUTDIR" "$SHA" > "$OUTDIR/mkstage_data.log" 2>&1 \
    || { cat "$OUTDIR/mkstage_data.log"; echo "STOP: the S data kit did not stage"; exit 1; }
  rm -f "$OUTDIR/icb-rt4-data.tar"      # re-tarred with the others below
  head -n 1 "$OUTDIR/mkstage_data.log"
fi

S="$OUTDIR/icb-rt2-all"; mkdir -p "$S" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by ops/prod-rt4/mkstage_window.sh on $(date -Is) — the RT4 window's All: pre, post (deploy), afterS (S)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0051"
KEEP_DIRS="/var/backups/icb-rt2-2026-10 /var/backups/icb-rt4-2026-10"
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt2_all.sh rt2_all_compare.py expected.env > SHA256SUMS ) || exit 1

T="$OUTDIR/icb-rt2-doors"; mkdir -p "$T" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$T/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$T/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$T/all.json" || exit 1
cat > "$T/expected.env" <<EOF
# written by ops/prod-rt4/mkstage_window.sh on $(date -Is) — the RT4 window's door report (step 7: 14 OK)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="0051"
STAGED_FROM=$SHA
EOF
( cd "$T" && sha256sum rt2_doors.sh rt1_door_report.py all.json expected.env > SHA256SUMS ) || exit 1

CR=$(cat "$OUTDIR"/icb-rt2-*/*.sh "$OUTDIR"/icb-rt2-*/*.py "$OUTDIR"/icb-rt2-*/expected.env "$OUTDIR"/icb-rt2-*/SHA256SUMS | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
for s in "$OUTDIR"/icb-*/*.sh; do bash -n "$s" || { echo "STOP: $s does not parse"; exit 1; }; done
echo "staged from $SHA (heads: $HEADS; alembic: 0051)"
for d in "$OUTDIR"/icb-*/; do echo "-- $(basename "$d")"; cat "$d/expected.env"; done
( cd "$OUTDIR" && for d in icb-*/; do d=${d%/}; tar -cf "$d.tar" "$d" || exit 1; done ) || exit 1
ls -l "$OUTDIR"/icb-*.tar && sha256sum "$OUTDIR"/icb-*.tar
