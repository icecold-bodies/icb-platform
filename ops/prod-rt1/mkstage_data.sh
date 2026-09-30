#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_data.sh (Manifests A, B, M) from COMMITTED blobs. Git Bash, AFTER the
# release PR has merged and the annotated tag v1.59.2 is on origin (A goes on only over the v1.59.2 code; the tag
# names that commit; M may go over v1.59.0 or v1.59.2):
#
#     bash ops/prod-rt1/mkstage_data.sh <empty-out-dir> <commit>        (a commit that contains the tagged release)
#
# Writes <out>/icb-rt1-data/{rt1_data.sh, expected.env, SHA256SUMS, stage/backend/tools/…, stage/docs/audit/…/manifest_*.yaml}
# and a tar of it. A is required; B and M are staged when committed (manifest_b.yaml only if a B was ruled in).
set -u
OUTDIR=${1:?usage: mkstage_data.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
TAG=v1.59.2
TAG_OBJ=$(git rev-parse -q --verify "refs/tags/$TAG") || { echo "STOP: no local tag $TAG — the data kit is staged after the tag"; exit 1; }
REMOTE_OBJ=$(git ls-remote --tags origin "refs/tags/$TAG" | cut -f1 | head -n1)
[ "$REMOTE_OBJ" = "$TAG_OBJ" ] || { echo "STOP: origin's $TAG is '${REMOTE_OBJ:-nothing}', local is $TAG_OBJ"; exit 1; }
EXPECT_HEAD=$(git rev-parse "$TAG^{commit}")
PREV_HEAD=$(git rev-parse --verify "v1.59.0^{commit}") || { echo "STOP: no tag v1.59.0 (prod's code before the window)"; exit 1; }
git merge-base --is-ancestor "$EXPECT_HEAD" "$SHA" || { echo "STOP: $SHA does not contain the release ${EXPECT_HEAD:0:7}"; exit 1; }
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$EXPECT_HEAD")
[ "$(last_rev "$PREV_HEAD")" = "$EXPECT_ALEMBIC" ] || { echo "STOP: v1.59.0 and v1.59.2 differ in alembic head"; exit 1; }
D=docs/audit/srd_rear_frame_2026-09
MA=$D/manifest_a.yaml; MB=$D/manifest_b.yaml; MM=docs/audit/rt1_2026-09/manifest_m.yaml
FILES="backend/tools/audit_pricing_corrections.py
$MA"
has() { git cat-file -e "$SHA:$1" 2>/dev/null; }
has "$MB" && FILES="$FILES
$MB"
has "$MM" && FILES="$FILES
$MM"

S="$OUTDIR/icb-rt1-data"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  mkdir -p "$S/stage/$(dirname "$f")" && git cat-file blob "$SHA:$f" > "$S/stage/$f" || exit 1
done
git cat-file blob "$SHA:ops/prod-rt1/rt1_data.sh" > "$S/rt1_data.sh" || exit 1
count() { grep -c '^- finding:' "$S/stage/$1"; }
sha() { sha256sum "$S/stage/$1" | cut -d' ' -f1; }
A_TODO=$(count "$MA"); A_SHA=$(sha "$MA")
[ "$A_TODO" = 120 ] || { echo "STOP: manifest A has $A_TODO entries, the reviewed plan is 120"; exit 1; }
if [ -f "$S/stage/$MB" ]; then B_TODO=$(count "$MB"); B_SHA=$(sha "$MB"); [ "$B_TODO" -gt 0 ] || { echo "STOP: manifest B has no entries"; exit 1; }
else B_TODO=0; B_SHA=none; echo "note: no manifest_b.yaml at ${SHA:0:7} — Manifest B is not part of this release"; fi
if [ -f "$S/stage/$MM" ]; then M_TODO=$(count "$MM"); M_SHA=$(sha "$MM"); [ "$M_TODO" -gt 0 ] || { echo "STOP: manifest M has no entries"; exit 1; }
else M_TODO=0; M_SHA=none; echo "note: no manifest_m.yaml at ${SHA:0:7} — Manifest M is not staged"; fi
cat > "$S/expected.env" <<EOF
# written by mkstage_data.sh on $(date -Is)
EXPECT_HEAD=$EXPECT_HEAD
PREV_HEAD=$PREV_HEAD
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
A_TODO=$A_TODO
B_TODO=$B_TODO
M_TODO=$M_TODO
A_SHA=$A_SHA
B_SHA=$B_SHA
M_SHA=$M_SHA
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_data.sh" || { echo "STOP: rt1_data.sh does not parse"; exit 1; }
echo "staged from $SHA: A $A_TODO, B $B_TODO, M $M_TODO entries; A needs prod at ${EXPECT_HEAD:0:7} ($TAG); M at ${PREV_HEAD:0:7} or ${EXPECT_HEAD:0:7}; alembic $EXPECT_ALEMBIC"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt1-data.tar icb-rt1-data ) && ls -l "$OUTDIR/icb-rt1-data.tar"
sha256sum "$OUTDIR/icb-rt1-data.tar"
