#!/usr/bin/env bash
# v1.61.0 — build the VM staging folder for release.sh from COMMITTED blobs, with every expected value derived from
# the target tree (never from memory). Run in Git Bash from the repo, AFTER the release PR has merged AND the
# annotated tag v1.61.0 is pushed (tag first), with the deploy line fetched:
#
#     bash ops/prod-release-v1.61.0/mkstage.sh <empty-out-dir> <target-sha> [prev-sha]   (prev = a429404, v1.60.2)
#
# Writes <out>/icb-release-v1.61.0/{release.sh, probe_paths.txt, lib/icb_where.sh, lib/icb_backup.sh, expected.env,
# SHA256SUMS} + a tar.
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> <target-sha> [prev-sha]}
TARGET=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "${3:-a429404}^{commit}") || exit 1
BRANCH=backport/v1.39-base
TAG=v1.61.0
PREV_TAG=v1.60.2
MIGRATION=backend/alembic/versions/0053_trailer_group_insulation_rule.py
SPA_MARK="This costing cannot be accepted."
ORIGIN=$(git rev-parse --verify "origin/$BRANCH") || exit 1
git merge-base --is-ancestor "$TARGET" "$ORIGIN" || { echo "STOP: the target ${TARGET:0:7} is not on origin/$BRANCH — fetch, or re-check the target"; exit 1; }
git merge-base --is-ancestor "$PREV" "$TARGET" || { echo "STOP: $PREV is not an ancestor of $TARGET"; exit 1; }
[ "$(git rev-parse "$PREV_TAG^{commit}" 2>/dev/null)" = "$PREV" ] || { echo "STOP: $PREV_TAG does not peel to ${PREV:0:7} (prod's code)"; exit 1; }

TAG_OBJ=$(git rev-parse -q --verify "refs/tags/$TAG") || { echo "STOP: no local tag $TAG — tag the merge commit first"; exit 1; }
[ "$(git cat-file -t "$TAG_OBJ")" = tag ] || { echo "STOP: $TAG is not an annotated tag"; exit 1; }
[ "$(git rev-parse "$TAG^{commit}")" = "$TARGET" ] || { echo "STOP: $TAG does not peel to ${TARGET:0:7}"; exit 1; }
REMOTE_OBJ=$(git ls-remote --tags origin "refs/tags/$TAG" | cut -f1 | head -n1)
[ "$REMOTE_OBJ" = "$TAG_OBJ" ] || { echo "STOP: origin has $TAG as '${REMOTE_OBJ:-nothing}', local is $TAG_OBJ — push the tag"; exit 1; }
[ "$(git describe --tags --abbrev=0 "$TARGET")" = "$TAG" ] || { echo "STOP: git describe at the target is not $TAG"; exit 1; }

S="$OUTDIR/icb-release-v1.61.0"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/lib" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.61.0/release.sh" > "$S/release.sh" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.61.0/probe_paths.txt" > "$S/probe_paths.txt" || exit 1
git cat-file blob "$TARGET:ops/lib/icb_where.sh" > "$S/lib/icb_where.sh" || exit 1
git cat-file blob "$TARGET:ops/lib/icb_backup.sh" > "$S/lib/icb_backup.sh" || exit 1

CHANGED_COUNT=$(git diff --name-only "$PREV" "$TARGET" | wc -l | tr -d ' ')
CHANGED_SHA=$(git diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
NEW_MIG=$(git diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$NEW_MIG" = "$MIGRATION" ] || { echo "STOP: new migrations are '$NEW_MIG', expected exactly $MIGRATION"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' 'frontend/package.json' 'frontend/package-lock.json' | grep -c . || true)" = 0 ] \
  || { echo "STOP: a dependency manifest changed in the range — this kit installs nothing"; exit 1; }
FE=$(git diff --name-only "$PREV" "$TARGET" -- frontend | grep -c . || true)
[ "$FE" -gt 0 ] || { echo "STOP: frontend/ unchanged — this kit expects the SPA rebuild"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- deploy | grep -c . || true)" = 0 ] || { echo "STOP: deploy/ changed in the range"; exit 1; }
git grep -q "$SPA_MARK" "$TARGET" -- frontend/src || { echo "STOP: the target's SPA source has no '$SPA_MARK'"; exit 1; }
! git grep -q "$SPA_MARK" "$PREV" -- frontend/src || { echo "STOP: the $PREV_TAG SPA source already has '$SPA_MARK'"; exit 1; }
rev_of() { git cat-file blob "$1" | sed -n "s/^$2[^=]*= *\"\([0-9]*\)\".*/\1/p" | head -n1; }
last_mig() { git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1; }
ALEMBIC_BEFORE=$(rev_of "$PREV:backend/alembic/versions/$(last_mig "$PREV")" revision)
ALEMBIC_AFTER=$(rev_of "$TARGET:$MIGRATION" revision)
DOWN=$(rev_of "$TARGET:$MIGRATION" down_revision)
[ "$(last_mig "$TARGET")" = "$(basename "$MIGRATION")" ] || { echo "STOP: the new migration is not the target's newest"; exit 1; }
[ "$ALEMBIC_BEFORE" = 0052 ] && [ "$ALEMBIC_AFTER" = 0053 ] && [ "$DOWN" = "$ALEMBIC_BEFORE" ] \
  || { echo "STOP: migration chain unclear (before '$ALEMBIC_BEFORE', new '$ALEMBIC_AFTER' revises '$DOWN')"; exit 1; }
vtags() { git cat-file blob "$1:backend/app/templates/$2" 2>/dev/null | grep -o "$3?v=[0-9]*" | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
static_of() { # $1 template, $2 path under backend/app/static/
  local f=${2##*/} vb va sb sa
  vb=$(vtags "$PREV" "$1" "$f"); va=$(vtags "$TARGET" "$1" "$f")
  sb=$(git cat-file blob "$PREV:backend/app/static/$2" | sha256sum | cut -d' ' -f1)
  sa=$(git cat-file blob "$TARGET:backend/app/static/$2" | sha256sum | cut -d' ' -f1)
  case "$vb $va" in *" "*" "*|" "*|*" ") echo "STOP"; return 1 ;; esac      # exactly one tag each side
  [ "$vb" != "$va" ] && [ "$sb" != "$sa" ] || { echo "STOP"; return 1; }   # the cache-bust AND the blob moved
  echo "$1 $2 $vb $sb $va $sa"
}
STATIC_1=$(static_of calculator.html js/calculator.js) || { echo "STOP: calculator.js: $STATIC_1 (one ?v= each side, both moved)"; exit 1; }
STATIC_2=$(static_of admin_templates.html js/admin_templates.js) || { echo "STOP: admin_templates.js: $STATIC_2"; exit 1; }
STATIC_3=$(static_of base.html js/app.js) || { echo "STOP: app.js: $STATIC_3"; exit 1; }
OTHER=$(git diff --name-only "$PREV" "$TARGET" -- backend/app/static | grep -v -x -e backend/app/static/js/calculator.js \
        -e backend/app/static/js/admin_templates.js -e backend/app/static/js/app.js || true)
[ -z "$OTHER" ] || { echo "STOP: other static files changed (they would be served stale under their old ?v=): $OTHER"; exit 1; }
N_PROBES=$(grep -vc -E '^(#|$)' "$S/probe_paths.txt")
[ "$N_PROBES" -ge 46 ] || { echo "STOP: probe_paths.txt has only $N_PROBES paths"; exit 1; }
grep -qx '200 /health/version' "$S/probe_paths.txt" && grep -qx '401 /openapi.json' "$S/probe_paths.txt" \
  && grep -qx '401 /api/trailers/27/insulation-rule-check' "$S/probe_paths.txt" || { echo "STOP: probe_paths.txt lacks a key line"; exit 1; }
PYYAML_VERSION=$(git cat-file blob "$TARGET:backend/requirements.txt" | sed -n 's/^PyYAML==\([0-9.]*\).*/\1/p' | head -n1)
DEPLOY_SH_SHA=$(git cat-file blob "$TARGET:deploy/prod/icb-deploy.sh" | sha256sum | cut -d' ' -f1)
WORKERS=4
for v in ALEMBIC_BEFORE ALEMBIC_AFTER PYYAML_VERSION; do [ -n "${!v}" ] || { echo "STOP: could not derive $v"; exit 1; }; done

cat > "$S/expected.env" <<EOF
# derived by mkstage.sh from $TARGET (prev $PREV) on $(date -Is)
PREV=$PREV
PREV_TAG=$PREV_TAG
TARGET=$TARGET
BRANCH=$BRANCH
TAG=$TAG
TAG_OBJ=$TAG_OBJ
ALEMBIC_BEFORE=$ALEMBIC_BEFORE
ALEMBIC_AFTER=$ALEMBIC_AFTER
MIGRATION=$MIGRATION
CHANGED_COUNT=$CHANGED_COUNT
CHANGED_SHA=$CHANGED_SHA
STATIC_1="$STATIC_1"
STATIC_2="$STATIC_2"
STATIC_3="$STATIC_3"
SPA_MARK="$SPA_MARK"
N_PROBES=$N_PROBES
PYYAML_VERSION=$PYYAML_VERSION
DEPLOY_SH_SHA=$DEPLOY_SH_SHA
WORKERS=$WORKERS
# where every run must be (ops/lib/icb_where.sh; the database host as the RT6 discovery read it, 6 Oct)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EOF
( cd "$S" && sha256sum release.sh probe_paths.txt lib/icb_where.sh lib/icb_backup.sh expected.env > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/release.sh" && bash -n "$S/lib/icb_where.sh" && bash -n "$S/lib/icb_backup.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
echo "staged ${PREV:0:7} -> ${TARGET:0:7} ($TAG), alembic $ALEMBIC_BEFORE -> $ALEMBIC_AFTER, $FE frontend file(s), $N_PROBES no-session probes per door"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-release-v1.61.0.tar icb-release-v1.61.0 ) && ls -l "$OUTDIR/icb-release-v1.61.0.tar"
