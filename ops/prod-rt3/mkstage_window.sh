#!/usr/bin/env bash
# RT3 — build the VM staging folders for the v1.60.0 window from COMMITTED blobs. Git Bash, from the repo:
#
#     bash ops/prod-rt3/mkstage_window.sh <empty-out-dir> <commit>
#
#   icb-rt3-families   rt3_families.sh + rt3_families.py (the data step; over v1.60.0 / alembic 0051 only)
#   icb-rt2-all        RT2's CLI "All" beside the page's All, unchanged (window steps a: "pre" before the deploy,
#                      "post" after the families) — over v1.59.3 or v1.60.0, alembic 0050 or 0051
#   icb-rt2-doors      RT2's door report, unchanged (window step g: 14 OK) — same codes
#
# The families kit pins prod's code to the v1.60.0 tag's commit, so it can only be staged once the annotated tag is
# on origin (tag first). The two RT2 kits are staged for v1.59.3 alone until then.
set -u
OUTDIR=${1:?usage: mkstage_window.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.59.3^{commit}") || { echo "STOP: no tag v1.59.3"; exit 1; }
[ "${PREV:0:7}" = 0926193 ] || { echo "STOP: v1.59.3 is ${PREV:0:7}, prod runs 0926193"; exit 1; }
HEADS=$PREV; ALEMBICS=0050; NEXT=
if TAG_OBJ=$(git rev-parse -q --verify "refs/tags/v1.60.0"); then
  [ "$(git ls-remote --tags origin refs/tags/v1.60.0 | cut -f1 | head -n1)" = "$TAG_OBJ" ] \
    || { echo "STOP: v1.60.0 is not on origin as the local object — push the tag"; exit 1; }
  NEXT=$(git rev-parse "v1.60.0^{commit}"); HEADS="$PREV $NEXT"; ALEMBICS="0050 0051"
else
  echo "note: no tag v1.60.0 yet — the All and door kits are staged for v1.59.3 only, and the families kit is NOT staged"
fi
for d in icb-rt3-families icb-rt2-all icb-rt2-doors; do [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }; done
mkdir -p "$OUTDIR" || exit 1

if [ -n "$NEXT" ]; then
  F="$OUTDIR/icb-rt3-families"; mkdir -p "$F" || exit 1
  for f in rt3_families.sh rt3_families.py; do git cat-file blob "$SHA:ops/prod-rt3/$f" > "$F/$f" || exit 1; done
  [ "$(git cat-file blob "$NEXT:ops/prod-rt3/rt3_families.py" | sha256sum | cut -d' ' -f1)" = "$(sha256sum < "$F/rt3_families.py" | cut -d' ' -f1)" ] \
    || { echo "STOP: rt3_families.py at $SHA differs from the one v1.60.0 ships"; exit 1; }
  cat > "$F/expected.env" <<EOF
# written by mkstage_window.sh on $(date -Is)
EXPECT_HEAD=$NEXT
EXPECT_ALEMBIC=0051
PLAN_TODO=40
TOOL_SHA=$(sha256sum < "$F/rt3_families.py" | cut -d' ' -f1)
STAGED_FROM=$SHA
EOF
  ( cd "$F" && sha256sum rt3_families.sh rt3_families.py expected.env > SHA256SUMS ) || exit 1
fi

S="$OUTDIR/icb-rt2-all"; mkdir -p "$S" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by ops/prod-rt3/mkstage_window.sh on $(date -Is) — the RT3 window's All, before (pre) and after (post)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="$ALEMBICS"
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt2_all.sh rt2_all_compare.py expected.env > SHA256SUMS ) || exit 1

T="$OUTDIR/icb-rt2-doors"; mkdir -p "$T" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$T/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$T/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$T/all.json" || exit 1
cat > "$T/expected.env" <<EOF
# written by ops/prod-rt3/mkstage_window.sh on $(date -Is) — the RT3 window's door report (step g)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="$ALEMBICS"
STAGED_FROM=$SHA
EOF
( cd "$T" && sha256sum rt2_doors.sh rt1_door_report.py all.json expected.env > SHA256SUMS ) || exit 1

CR=$(cat "$OUTDIR"/icb-*/*.sh "$OUTDIR"/icb-*/*.py "$OUTDIR"/icb-*/expected.env "$OUTDIR"/icb-*/SHA256SUMS | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
for s in "$OUTDIR"/icb-*/*.sh; do bash -n "$s" || { echo "STOP: $s does not parse"; exit 1; }; done
echo "staged from $SHA (heads: $HEADS; alembic: $ALEMBICS)"
for d in "$OUTDIR"/icb-*/; do echo "-- $(basename "$d")"; cat "$d/expected.env"; done
( cd "$OUTDIR" && for d in icb-*/; do d=${d%/}; tar -cf "$d.tar" "$d" || exit 1; done ) || exit 1
ls -l "$OUTDIR"/icb-*.tar && sha256sum "$OUTDIR"/icb-*.tar
