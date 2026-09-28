#!/usr/bin/env bash
# v1.59.0 — build the VM staging folder for release.sh from COMMITTED blobs, with every expected value
# derived from the target tree (never from memory). Run in Git Bash from the repo, after the release
# PR has merged, with the deploy line fetched:
#
#     bash ops/prod-release-v1.59.0/mkstage.sh <empty-out-dir> <target-sha> [prev-sha]   (prev = 6b77d52)
#
# Writes <out>/icb-release-v1.59.0/{release.sh, expected.env, requirements.txt, SHA256SUMS} + a tar.
# Then: scp the tar to icb@192.168.0.251:/tmp/ and `tar -xf` it there (as icb).
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> <target-sha> [prev-sha]}
TARGET=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "${3:-6b77d52}^{commit}") || exit 1
BRANCH=backport/v1.39-base
ORIGIN=$(git rev-parse --verify "origin/$BRANCH") || exit 1
[ "$ORIGIN" = "$TARGET" ] || { echo "STOP: origin/$BRANCH is ${ORIGIN:0:7}, not the target ${TARGET:0:7} — fetch, or re-check the target"; exit 1; }
git merge-base --is-ancestor "$PREV" "$TARGET" || { echo "STOP: $PREV is not an ancestor of $TARGET"; exit 1; }

S="$OUTDIR/icb-release-v1.59.0"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1

git cat-file blob "$TARGET:ops/prod-release-v1.59.0/release.sh" > "$S/release.sh" || exit 1
git cat-file blob "$TARGET:backend/requirements.txt" > "$S/requirements.txt" || exit 1

CHANGED_COUNT=$(git diff --name-only "$PREV" "$TARGET" | wc -l | tr -d ' ')
CHANGED_SHA=$(git diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
MIGRATION=$(git diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$(printf '%s\n' "$MIGRATION" | grep -c .)" = 1 ] || { echo "STOP: expected exactly one new migration, got: $MIGRATION"; exit 1; }
ALEMBIC_BEFORE=$(git cat-file blob "$PREV:backend/alembic/versions/$(git ls-tree --name-only "$PREV" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
  | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1)
ALEMBIC_AFTER=$(git cat-file blob "$TARGET:$MIGRATION" | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1)
DOWN=$(git cat-file blob "$TARGET:$MIGRATION" | sed -n 's/^down_revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1)
[ -n "$ALEMBIC_BEFORE" ] && [ -n "$ALEMBIC_AFTER" ] && [ "$DOWN" = "$ALEMBIC_BEFORE" ] \
  || { echo "STOP: migration chain unclear (before '$ALEMBIC_BEFORE', new '$ALEMBIC_AFTER' revises '$DOWN')"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- frontend | wc -l | tr -d ' ')" = 0 ] || { echo "STOP: frontend/ changed — this kit does not rebuild the SPA"; exit 1; }
CALC_V=$(git cat-file blob "$TARGET:backend/app/templates/calculator.html" | grep -o 'calculator\.js?v=[0-9]*' | head -n1 | cut -d= -f2)
CALC_SHA=$(git cat-file blob "$TARGET:backend/app/static/js/calculator.js" | sha256sum | cut -d' ' -f1)
NEW_PATHS=$(git cat-file blob "$TARGET:backend/app/routers/costing_audit.py" | grep -oE '@router\.(get|post)\("[^"]+"' | sed 's/.*("//;s/"$//' | LC_ALL=C sort -u | tr '\n' ' ' | sed 's/ $//')
PYYAML_VERSION=$(git cat-file blob "$TARGET:backend/requirements.txt" | sed -n 's/^PyYAML==\([0-9.]*\).*/\1/p' | head -n1)
PERM=$(git cat-file blob "$TARGET:backend/app/routers/costing_audit.py" | sed -n 's/^PERM *= *"\([^"]*\)".*/\1/p' | head -n1)
WORKERS=4
for v in CALC_V PYYAML_VERSION PERM NEW_PATHS; do [ -n "${!v}" ] || { echo "STOP: could not derive $v"; exit 1; }; done

cat > "$S/expected.env" <<EOF
# derived by mkstage.sh from $TARGET (prev $PREV) on $(date -Is)
PREV=$PREV
TARGET=$TARGET
BRANCH=$BRANCH
ALEMBIC_BEFORE=$ALEMBIC_BEFORE
ALEMBIC_AFTER=$ALEMBIC_AFTER
MIGRATION=$MIGRATION
CHANGED_COUNT=$CHANGED_COUNT
CHANGED_SHA=$CHANGED_SHA
CALC_V=$CALC_V
CALC_SHA=$CALC_SHA
NEW_PATHS="$NEW_PATHS"
PYYAML_VERSION=$PYYAML_VERSION
PERM=$PERM
WORKERS=$WORKERS
EOF
( cd "$S" && sha256sum release.sh expected.env requirements.txt > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/release.sh" || { echo "STOP: release.sh does not parse"; exit 1; }
echo "staged ${PREV:0:7} -> ${TARGET:0:7}"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-release-v1.59.0.tar icb-release-v1.59.0 ) && ls -l "$OUTDIR/icb-release-v1.59.0.tar"
