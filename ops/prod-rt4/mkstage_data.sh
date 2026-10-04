#!/usr/bin/env bash
# RT4 — build the VM staging folder for rt4_data.sh (Manifest S) from COMMITTED blobs. Git Bash, AFTER the release PR
# has merged and the annotated tag v1.60.1 is on origin (S goes only over the v1.60.1 code, which the tag names):
#
#     bash ops/prod-rt4/mkstage_data.sh <empty-out-dir> <commit>        (a commit that contains the tagged release)
#
# Writes <out>/icb-rt4-data/{rt4_data.sh, expected.env, SHA256SUMS, stage/backend/tools/audit_pricing_corrections.py,
# stage/docs/audit/rt4_2026-10/manifest_s/manifest_s.yaml} and a tar of it.
set -u
OUTDIR=${1:?usage: mkstage_data.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
TAG=v1.60.1
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
[ "$EXPECT_ALEMBIC" = 0051 ] || { echo "STOP: the release's alembic head is '$EXPECT_ALEMBIC', v1.60.1 has no migration (0051)"; exit 1; }
git cat-file -e "$EXPECT_HEAD:backend/app/services/sections.py" 2>/dev/null \
  || { echo "STOP: the tagged release has no app/services/sections.py — S needs the v1.60.1 code"; exit 1; }
MS=docs/audit/rt4_2026-10/manifest_s/manifest_s.yaml
FILES="backend/tools/audit_pricing_corrections.py
$MS"
# the staged tool must be the RELEASED tool (prod runs the tagged code's app; the tool is its sibling)
[ "$(git rev-parse "$SHA:backend/tools/audit_pricing_corrections.py")" = "$(git rev-parse "$EXPECT_HEAD:backend/tools/audit_pricing_corrections.py")" ] \
  || { echo "STOP: the tool at $SHA differs from the tagged release's"; exit 1; }

S="$OUTDIR/icb-rt4-data"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  mkdir -p "$S/stage/$(dirname "$f")" && git cat-file blob "$SHA:$f" > "$S/stage/$f" || exit 1
done
git cat-file blob "$SHA:ops/prod-rt4/rt4_data.sh" > "$S/rt4_data.sh" || exit 1
S_TODO=$(grep -c '^    field: section$' "$S/stage/$MS")
S_DRAFTS=$(grep -c '^    old_key: ' "$S/stage/$MS")
S_SHA=$(sha256sum "$S/stage/$MS" | cut -d' ' -f1)
[ "$S_TODO" = 46 ] && [ "$S_DRAFTS" = 2 ] || { echo "STOP: manifest S has $S_TODO line moves and $S_DRAFTS draft keys; RT4_RULING_1 says 46 + id 41's two"; exit 1; }
grep -qx 'expect_unused_after: \[83, 84, 85\]' "$S/stage/$MS" || { echo "STOP: manifest S does not expect 83/84/85 unused"; exit 1; }
cat > "$S/expected.env" <<EOF
# written by mkstage_data.sh on $(date -Is)
EXPECT_HEAD=$EXPECT_HEAD
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
S_TODO=$S_TODO
S_DRAFTS=$S_DRAFTS
S_SHA=$S_SHA
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt4_data.sh" || { echo "STOP: rt4_data.sh does not parse"; exit 1; }
echo "staged from $SHA: S $S_TODO line moves + $S_DRAFTS draft keys; needs prod at ${EXPECT_HEAD:0:7} ($TAG), alembic $EXPECT_ALEMBIC"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt4-data.tar icb-rt4-data ) && ls -l "$OUTDIR/icb-rt4-data.tar"
sha256sum "$OUTDIR/icb-rt4-data.tar"
