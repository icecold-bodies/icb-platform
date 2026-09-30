#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_data.sh (Manifests A and B) from COMMITTED blobs. Git Bash,
# AFTER the release PR has merged and the annotated tag v1.59.2 is on origin (the data goes on only
# over the v1.59.2 code; the tag names that commit):
#
#     bash ops/prod-rt1/mkstage_data.sh <empty-out-dir> <commit>        (commit = the tagged merge commit)
#
# Writes <out>/icb-rt1-data/{rt1_data.sh, expected.env, SHA256SUMS, stage/backend/tools/…,
# stage/docs/audit/srd_rear_frame_2026-09/manifest_{a,b}.yaml} and a tar of it.
set -u
OUTDIR=${1:?usage: mkstage_data.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
TAG=v1.59.2
TAG_OBJ=$(git rev-parse -q --verify "refs/tags/$TAG") || { echo "STOP: no local tag $TAG — the data kit is staged after the tag"; exit 1; }
REMOTE_OBJ=$(git ls-remote --tags origin "refs/tags/$TAG" | cut -f1 | head -n1)
[ "$REMOTE_OBJ" = "$TAG_OBJ" ] || { echo "STOP: origin's $TAG is '${REMOTE_OBJ:-nothing}', local is $TAG_OBJ"; exit 1; }
EXPECT_HEAD=$(git rev-parse "$TAG^{commit}")
git merge-base --is-ancestor "$EXPECT_HEAD" "$SHA" || { echo "STOP: $SHA does not contain the release ${EXPECT_HEAD:0:7}"; exit 1; }
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$EXPECT_HEAD")
D=docs/audit/srd_rear_frame_2026-09
FILES="backend/tools/audit_pricing_corrections.py
$D/manifest_a.yaml"
# Manifest B is the one RT1_RULING_1 kept (it is committed as manifest_b.yaml); absent = B stops, A goes alone
HAS_B=0; git cat-file -e "$SHA:$D/manifest_b.yaml" 2>/dev/null && { HAS_B=1; FILES="$FILES
$D/manifest_b.yaml"; }

S="$OUTDIR/icb-rt1-data"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  mkdir -p "$S/stage/$(dirname "$f")" && git cat-file blob "$SHA:$f" > "$S/stage/$f" || exit 1
done
git cat-file blob "$SHA:ops/prod-rt1/rt1_data.sh" > "$S/rt1_data.sh" || exit 1
count() { grep -c '^- finding:' "$S/stage/$D/manifest_$1.yaml"; }
A_TODO=$(count a)
A_SHA=$(sha256sum "$S/stage/$D/manifest_a.yaml" | cut -d' ' -f1)
if [ "$HAS_B" = 1 ]; then
  B_TODO=$(count b); B_SHA=$(sha256sum "$S/stage/$D/manifest_b.yaml" | cut -d' ' -f1)
  [ "$B_TODO" -gt 0 ] || { echo "STOP: manifest B has no entries"; exit 1; }
else
  B_TODO=0; B_SHA=none; echo "note: no manifest_b.yaml at ${SHA:0:7} — Manifest B is not part of this release; A goes alone"
fi
[ "$A_TODO" = 120 ] || { echo "STOP: manifest A has $A_TODO entries, the reviewed plan is 120"; exit 1; }
cat > "$S/expected.env" <<EOF
# written by mkstage_data.sh on $(date -Is)
EXPECT_HEAD=$EXPECT_HEAD
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
A_TODO=$A_TODO
B_TODO=$B_TODO
A_SHA=$A_SHA
B_SHA=$B_SHA
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_data.sh" || { echo "STOP: rt1_data.sh does not parse"; exit 1; }
echo "staged from $SHA: A $A_TODO entries, B $B_TODO entries; prod must be at ${EXPECT_HEAD:0:7} ($TAG), alembic $EXPECT_ALEMBIC"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt1-data.tar icb-rt1-data ) && ls -l "$OUTDIR/icb-rt1-data.tar"
sha256sum "$OUTDIR/icb-rt1-data.tar"
