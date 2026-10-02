#!/usr/bin/env bash
# RT2 — build the VM staging folder for rt2_data.sh (Manifests P and D) from COMMITTED blobs. Git Bash, AFTER the
# release PRs have merged and the annotated tag v1.59.3 is on origin (P and D go only over the v1.59.3 code, which
# the tag names):
#
#     bash ops/prod-rt2/mkstage_data.sh <empty-out-dir> <commit>        (a commit that contains the tagged release)
#
# Writes <out>/icb-rt2-data/{rt2_data.sh, expected.env, SHA256SUMS, stage/backend/tools/audit_pricing_corrections.py,
# stage/docs/audit/rt2_2026-10/manifest_p/manifest_p.yaml, stage/ops/prod-rt2/rt2_defaults.py} and a tar of it.
set -u
OUTDIR=${1:?usage: mkstage_data.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
TAG=v1.59.3
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
[ "$EXPECT_ALEMBIC" = 0050 ] || { echo "STOP: the release's alembic head is '$EXPECT_ALEMBIC', D needs 0050"; exit 1; }
MP=docs/audit/rt2_2026-10/manifest_p/manifest_p.yaml
FILES="backend/tools/audit_pricing_corrections.py
$MP
ops/prod-rt2/rt2_defaults.py"

S="$OUTDIR/icb-rt2-data"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  mkdir -p "$S/stage/$(dirname "$f")" && git cat-file blob "$SHA:$f" > "$S/stage/$f" || exit 1
done
git cat-file blob "$SHA:ops/prod-rt2/rt2_data.sh" > "$S/rt2_data.sh" || exit 1
P_TODO=$(grep -c '^- finding:' "$S/stage/$MP")
P_SHA=$(sha256sum "$S/stage/$MP" | cut -d' ' -f1)
[ "$P_TODO" -gt 0 ] || { echo "STOP: manifest P has no entries"; exit 1; }
D_TODO=$(sed -n 's/^BODIES = {\(.*\)}$/\1/p' "$S/stage/ops/prod-rt2/rt2_defaults.py" | grep -o '[0-9]*: "' | wc -l | tr -d ' ')
[ "$D_TODO" = 4 ] || { echo "STOP: rt2_defaults.py names $D_TODO bodies, R6 names 4"; exit 1; }
D_SHA=$(sha256sum "$S/stage/ops/prod-rt2/rt2_defaults.py" | cut -d' ' -f1)
cat > "$S/expected.env" <<EOF
# written by mkstage_data.sh on $(date -Is)
EXPECT_HEAD=$EXPECT_HEAD
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
P_TODO=$P_TODO
D_TODO=$D_TODO
P_SHA=$P_SHA
D_SHA=$D_SHA
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt2_data.sh" || { echo "STOP: rt2_data.sh does not parse"; exit 1; }
echo "staged from $SHA: P $P_TODO entries, D $D_TODO bodies; both need prod at ${EXPECT_HEAD:0:7} ($TAG), alembic $EXPECT_ALEMBIC"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt2-data.tar icb-rt2-data ) && ls -l "$OUTDIR/icb-rt2-data.tar"
sha256sum "$OUTDIR/icb-rt2-data.tar"
