#!/usr/bin/env bash
# v1.60.0 — build the VM staging folder for release.sh from COMMITTED blobs, with every expected value derived from
# the target tree (never from memory). Run in Git Bash from the repo, AFTER the release PR has merged AND the
# annotated tag v1.60.0 is pushed (tag first), with the deploy line fetched:
#
#     bash ops/prod-release-v1.60.0/mkstage.sh <empty-out-dir> <target-sha> [prev-sha]   (prev = 0926193, v1.59.3)
#
# Writes <out>/icb-release-v1.60.0/{release.sh, expected.env, SHA256SUMS} + a tar.
# Then Michael: scp the tar to the VM's /tmp and `tar -xf` it there (the runbook has the lines).
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> <target-sha> [prev-sha]}
TARGET=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "${3:-0926193}^{commit}") || exit 1
BRANCH=backport/v1.39-base
TAG=v1.60.0
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

S="$OUTDIR/icb-release-v1.60.0"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.60.0/release.sh" > "$S/release.sh" || exit 1

CHANGED_COUNT=$(git diff --name-only "$PREV" "$TARGET" | wc -l | tr -d ' ')
CHANGED_SHA=$(git diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
MIGRATION=$(git diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*')
[ "$(printf '%s\n' "$MIGRATION" | grep -c .)" = 1 ] || { echo "STOP: expected exactly one new migration, got: $MIGRATION"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' frontend/package.json frontend/package-lock.json | grep -c . || true)" = 0 ] \
  || { echo "STOP: a dependency manifest changed in the range — this kit installs nothing"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- frontend | grep -c . || true)" -gt 0 ] || { echo "STOP: frontend/ unchanged — this kit expects the SPA rebuild"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- deploy | grep -c . || true)" = 0 ] || { echo "STOP: deploy/ changed in the range"; exit 1; }
rev_of() { git cat-file blob "$1" | sed -n "s/^$2[^=]*= *\"\([0-9]*\)\".*/\1/p" | head -n1; }
last_mig() { git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1; }
ALEMBIC_BEFORE=$(rev_of "$PREV:backend/alembic/versions/$(last_mig "$PREV")" revision)
ALEMBIC_AFTER=$(rev_of "$TARGET:$MIGRATION" revision)
DOWN=$(rev_of "$TARGET:$MIGRATION" down_revision)
[ "$(last_mig "$TARGET")" = "$(basename "$MIGRATION")" ] || { echo "STOP: the new migration is not the target's newest"; exit 1; }
[ -n "$ALEMBIC_BEFORE" ] && [ -n "$ALEMBIC_AFTER" ] && [ "$DOWN" = "$ALEMBIC_BEFORE" ] \
  || { echo "STOP: migration chain unclear (before '$ALEMBIC_BEFORE', new '$ALEMBIC_AFTER' revises '$DOWN')"; exit 1; }
# the five static files: "<template> <path under static/> <v before|-> <sha before|-> <v after> <sha after>"; each must move
vtags() { git cat-file blob "$1:backend/app/templates/$2" 2>/dev/null | grep -o "$3?v=[0-9]*" | cut -d= -f2 | tr '\n' ' ' | sed 's/ $//'; }
static_of() { # $1 template, $2 path under backend/app/static/
  local f=${2##*/} vb va sb sa
  vb=$(vtags "$PREV" "$1" "$f"); va=$(vtags "$TARGET" "$1" "$f")
  sa=$(git cat-file blob "$TARGET:backend/app/static/$2" | sha256sum | cut -d' ' -f1)
  if git cat-file -e "$PREV:backend/app/static/$2" 2>/dev/null; then
    sb=$(git cat-file blob "$PREV:backend/app/static/$2" | sha256sum | cut -d' ' -f1)
  else sb=-; [ -z "$vb" ] || { echo "STOP"; return 1; }; vb=-; fi   # NEW: no tag before, no blob before
  case "$vb $va" in *" "*" "*|" "*|*" ") echo "STOP"; return 1 ;; esac      # exactly one tag each side
  [ "$vb" != "$va" ] && [ "$sb" != "$sa" ] || { echo "STOP"; return 1; }   # the cache-bust AND the blob moved
  echo "$1 $2 $vb $sb $va $sa"
}
STATIC_1=$(static_of calculator.html js/calculator.js) || { echo "STOP: calculator.js: $STATIC_1 (one ?v= each side, both moved)"; exit 1; }
STATIC_2=$(static_of calculator2.html js/calculator2.js) || { echo "STOP: calculator2.js: $STATIC_2"; exit 1; }
STATIC_3=$(static_of admin_templates.html js/admin_templates.js) || { echo "STOP: admin_templates.js: $STATIC_3"; exit 1; }
STATIC_4=$(static_of base.html js/body_family.js) || { echo "STOP: body_family.js: $STATIC_4 (new in this release)"; exit 1; }
STATIC_5=$(static_of base.html css/theme-mes.css) || { echo "STOP: theme-mes.css: $STATIC_5"; exit 1; }
# theme-mes.css is also linked by dashboard_mes.html and results_mes.html: every link must carry the same ?v=
TMES=$(echo "$STATIC_5" | cut -d' ' -f5)
for t in dashboard_mes.html results_mes.html; do
  [ "$(vtags "$TARGET" "$t" theme-mes.css)" = "$TMES" ] || { echo "STOP: $t links theme-mes.css at another ?v= than base.html ($TMES)"; exit 1; }
done
# every changed static file is one of the five: a sixth would be served stale-cached under its old ?v=
OTHER=$(git diff --name-only "$PREV" "$TARGET" -- backend/app/static | grep -v -x -E 'backend/app/static/(js/(calculator|calculator2|admin_templates|body_family)\.js|css/theme-mes\.css)' || true)
[ -z "$OTHER" ] || { echo "STOP: other static files changed: $OTHER"; exit 1; }
# the SPA's family chip: a field the rebuilt bundle must carry, and the v1.59.3 bundle must not
SPA_MARK=trailer_family
git grep -q "$SPA_MARK" "$TARGET" -- frontend/src || { echo "STOP: the target's SPA source has no $SPA_MARK"; exit 1; }
! git grep -q "$SPA_MARK" "$PREV" -- frontend/src || { echo "STOP: the v1.59.3 SPA source already has $SPA_MARK"; exit 1; }
PYYAML_VERSION=$(git cat-file blob "$TARGET:backend/requirements.txt" | sed -n 's/^PyYAML==\([0-9.]*\).*/\1/p' | head -n1)
DEPLOY_SH_SHA=$(git cat-file blob "$TARGET:deploy/prod/icb-deploy.sh" | sha256sum | cut -d' ' -f1)
WORKERS=4
for v in PYYAML_VERSION ALEMBIC_BEFORE ALEMBIC_AFTER; do [ -n "${!v}" ] || { echo "STOP: could not derive $v"; exit 1; }; done

cat > "$S/expected.env" <<EOF
# derived by mkstage.sh from $TARGET (prev $PREV) on $(date -Is)
PREV=$PREV
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
STATIC_4="$STATIC_4"
STATIC_5="$STATIC_5"
SPA_MARK=$SPA_MARK
PYYAML_VERSION=$PYYAML_VERSION
DEPLOY_SH_SHA=$DEPLOY_SH_SHA
WORKERS=$WORKERS
EOF
( cd "$S" && sha256sum release.sh expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/release.sh" || { echo "STOP: release.sh does not parse"; exit 1; }
echo "staged ${PREV:0:7} -> ${TARGET:0:7} ($TAG), alembic $ALEMBIC_BEFORE -> $ALEMBIC_AFTER"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-release-v1.60.0.tar icb-release-v1.60.0 ) && ls -l "$OUTDIR/icb-release-v1.60.0.tar"
