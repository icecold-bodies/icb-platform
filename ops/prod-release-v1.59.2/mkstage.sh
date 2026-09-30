#!/usr/bin/env bash
# v1.59.2 — build the VM staging folder for release.sh from COMMITTED blobs, with every expected value
# derived from the target tree (never from memory). Run in Git Bash from the repo, AFTER the release
# PR has merged AND the annotated tag v1.59.2 is pushed (tag first), with the deploy line fetched:
#
#     bash ops/prod-release-v1.59.2/mkstage.sh <empty-out-dir> <target-sha> [prev-sha]   (prev = de74796)
#
# Writes <out>/icb-release-v1.59.2/{release.sh, expected.env, SHA256SUMS} + a tar.
# Then Michael: scp the tar to the VM's /tmp and `tar -xf` it there (the runbook has the lines).
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> <target-sha> [prev-sha]}
TARGET=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "${3:-de74796}^{commit}") || exit 1
BRANCH=backport/v1.39-base
TAG=v1.59.2
ORIGIN=$(git rev-parse --verify "origin/$BRANCH") || exit 1
[ "$ORIGIN" = "$TARGET" ] || { echo "STOP: origin/$BRANCH is ${ORIGIN:0:7}, not the target ${TARGET:0:7} — fetch, or re-check the target"; exit 1; }
git merge-base --is-ancestor "$PREV" "$TARGET" || { echo "STOP: $PREV is not an ancestor of $TARGET"; exit 1; }

# tag first: the annotated tag must exist locally AND on origin, as the same object, peeling to the target
TAG_OBJ=$(git rev-parse -q --verify "refs/tags/$TAG") || { echo "STOP: no local tag $TAG — tag the merge commit first"; exit 1; }
[ "$(git cat-file -t "$TAG_OBJ")" = tag ] || { echo "STOP: $TAG is not an annotated tag"; exit 1; }
[ "$(git rev-parse "$TAG^{commit}")" = "$TARGET" ] || { echo "STOP: $TAG does not peel to ${TARGET:0:7}"; exit 1; }
REMOTE_OBJ=$(git ls-remote --tags origin "refs/tags/$TAG" | cut -f1 | head -n1)
[ "$REMOTE_OBJ" = "$TAG_OBJ" ] || { echo "STOP: origin has $TAG as '${REMOTE_OBJ:-nothing}', local is $TAG_OBJ — push the tag"; exit 1; }
[ "$(git describe --tags --abbrev=0 "$TARGET")" = "$TAG" ] || { echo "STOP: git describe at the target is not $TAG"; exit 1; }

S="$OUTDIR/icb-release-v1.59.2"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.59.2/release.sh" > "$S/release.sh" || exit 1

CHANGED_COUNT=$(git diff --name-only "$PREV" "$TARGET" | wc -l | tr -d ' ')
CHANGED_SHA=$(git diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
N_MIG=$(git diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*' | grep -c . || true)
[ "$N_MIG" = 0 ] || { echo "STOP: $N_MIG new migration(s) in the range — this kit deploys none"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' | grep -c . || true)" = 0 ] \
  || { echo "STOP: requirements changed in the range — this kit installs nothing"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- frontend | grep -c . || true)" = 0 ] || { echo "STOP: frontend/ changed — this kit does not rebuild the SPA"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- deploy | grep -c . || true)" = 0 ] || { echo "STOP: deploy/ changed in the range"; exit 1; }
last_rev() { # the newest migration revision in a tree
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
ALEMBIC=$(last_rev "$TARGET"); [ -n "$ALEMBIC" ] && [ "$ALEMBIC" = "$(last_rev "$PREV")" ] || { echo "STOP: alembic head unclear ('$ALEMBIC')"; exit 1; }
calc_v() { git cat-file blob "$1:backend/app/templates/calculator.html" | grep -o 'calculator\.js?v=[0-9]*' | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
CALC_V_BEFORE=$(calc_v "$PREV"); CALC_V=$(calc_v "$TARGET")
CALC_SHA_BEFORE=$(git cat-file blob "$PREV:backend/app/static/js/calculator.js" | sha256sum | cut -d' ' -f1)
CALC_SHA=$(git cat-file blob "$TARGET:backend/app/static/js/calculator.js" | sha256sum | cut -d' ' -f1)
case "$CALC_V_BEFORE $CALC_V" in *" "*" "*) echo "STOP: calculator.html loads more than one calculator.js ($CALC_V_BEFORE / $CALC_V)"; exit 1 ;; esac
[ "$CALC_V" != "$CALC_V_BEFORE" ] && [ "$CALC_SHA" != "$CALC_SHA_BEFORE" ] || { echo "STOP: the calculator cache-bust or blob did not move"; exit 1; }
PYYAML_VERSION=$(git cat-file blob "$TARGET:backend/requirements.txt" | sed -n 's/^PyYAML==\([0-9.]*\).*/\1/p' | head -n1)
DEPLOY_SH_SHA=$(git cat-file blob "$TARGET:deploy/prod/icb-deploy.sh" | sha256sum | cut -d' ' -f1)
WORKERS=4
for v in CALC_V CALC_V_BEFORE PYYAML_VERSION; do [ -n "${!v}" ] || { echo "STOP: could not derive $v"; exit 1; }; done

cat > "$S/expected.env" <<EOF
# derived by mkstage.sh from $TARGET (prev $PREV) on $(date -Is)
PREV=$PREV
TARGET=$TARGET
BRANCH=$BRANCH
TAG=$TAG
TAG_OBJ=$TAG_OBJ
ALEMBIC=$ALEMBIC
CHANGED_COUNT=$CHANGED_COUNT
CHANGED_SHA=$CHANGED_SHA
CALC_V_BEFORE=$CALC_V_BEFORE
CALC_SHA_BEFORE=$CALC_SHA_BEFORE
CALC_V=$CALC_V
CALC_SHA=$CALC_SHA
PYYAML_VERSION=$PYYAML_VERSION
DEPLOY_SH_SHA=$DEPLOY_SH_SHA
WORKERS=$WORKERS
EOF
( cd "$S" && sha256sum release.sh expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/release.sh" || { echo "STOP: release.sh does not parse"; exit 1; }
echo "staged ${PREV:0:7} -> ${TARGET:0:7} ($TAG)"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-release-v1.59.2.tar icb-release-v1.59.2 ) && ls -l "$OUTDIR/icb-release-v1.59.2.tar"
