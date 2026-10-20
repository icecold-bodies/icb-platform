#!/usr/bin/env bash
# v1.61.1 — build the VM staging folder for release.sh from COMMITTED blobs, with every expected value derived from
# the target tree (never from memory). Run in Git Bash from the repo, AFTER the release PR has merged AND the
# annotated tag v1.61.1 is pushed (tag first):
#
#     bash ops/prod-release-v1.61.1/mkstage.sh <empty-out-dir> <target-sha> [prev-sha]   (prev = 5e37b0a, v1.61.0)
#
# Writes <out>/icb-release-v1.61.1/{release.sh, probe_paths.txt, lib/icb_where.sh, lib/icb_backup.sh, expected.env,
# SHA256SUMS} + a tar. The Windows copy line stamps the kit (.staged_at) on prod — release.sh refuses an unstamped
# kit or one staged before prod's last boot (the RT7 reboot guard).
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> <target-sha> [prev-sha]}
TARGET=$(git rev-parse --verify "${2:?target sha}^{commit}") || exit 1
PREV=$(git rev-parse --verify "${3:-5e37b0a}^{commit}") || exit 1
BRANCH=backport/v1.39-base
TAG=v1.61.1
PREV_TAG=v1.61.0
FACTOR=1.3170731707317074           # RT7_RULING_1A: 5400/4100, set on prod by Michael on 19 Oct (data; not deployed)
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

S="$OUTDIR/icb-release-v1.61.1"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/lib" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.61.1/release.sh" > "$S/release.sh" || exit 1
git cat-file blob "$TARGET:ops/prod-release-v1.61.1/probe_paths.txt" > "$S/probe_paths.txt" || exit 1
git cat-file blob "$TARGET:ops/lib/icb_where.sh" > "$S/lib/icb_where.sh" || exit 1
git cat-file blob "$TARGET:ops/lib/icb_backup.sh" > "$S/lib/icb_backup.sh" || exit 1

CHANGED_COUNT=$(git diff --name-only "$PREV" "$TARGET" | wc -l | tr -d ' ')
CHANGED_SHA=$(git diff --name-only "$PREV" "$TARGET" | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
[ "$(git diff --name-only --diff-filter=A "$PREV" "$TARGET" -- 'backend/alembic/versions/*' | grep -c . || true)" = 0 ] \
  || { echo "STOP: a migration was added in the range — this kit migrates nothing"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- 'backend/requirements*.txt' 'frontend/package.json' 'frontend/package-lock.json' | grep -c . || true)" = 0 ] \
  || { echo "STOP: a dependency manifest changed in the range — this kit installs nothing"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- frontend backend/app/static | grep -c . || true)" = 0 ] \
  || { echo "STOP: frontend/ or backend/app/static changed — this kit expects the browser's files untouched (no ?v=)"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- deploy | grep -c . || true)" = 0 ] || { echo "STOP: deploy/ changed in the range"; exit 1; }
[ "$(git diff --name-only "$PREV" "$TARGET" -- 'backend/**/*.py' | grep -c . || true)" -gt 0 ] \
  || { echo "STOP: no Python changed — icb-deploy.sh would not restart, and the page would keep the old list"; exit 1; }
last_mig() { git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1; }
ALEMBIC=$(git cat-file blob "$TARGET:backend/alembic/versions/$(last_mig "$TARGET")" | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1)
[ "$ALEMBIC" = 0053 ] && [ "$(last_mig "$PREV")" = "$(last_mig "$TARGET")" ] || { echo "STOP: alembic head is '$ALEMBIC', expected 0053 unchanged"; exit 1; }
N_PROBES=$(grep -vc -E '^(#|$)' "$S/probe_paths.txt")
[ "$N_PROBES" -ge 46 ] || { echo "STOP: probe_paths.txt has only $N_PROBES paths"; exit 1; }
# RT6_RULING_3: a probe whose ROUTE is new in the range answers 404 before the deploy. v1.61.1 must add none.
route_re() { printf '%s' "${1%%\?*}" | sed -e 's/[.*^$+()|]/[&]/g' -e 's#/[0-9][0-9]*#/[{][^}/]+[}]#g'; }
NEW_PROBES=""
while read -r want path; do
  case "$want" in ''|\#*) continue ;; esac
  re="\"$(route_re "$path")\""
  git grep -qE "$re" "$TARGET" -- backend/app || continue
  git grep -qE "$re" "$PREV" -- backend/app && continue
  NEW_PROBES="$NEW_PROBES $path"
done < "$S/probe_paths.txt"
[ -z "$NEW_PROBES" ] || { echo "STOP: routes new in the range:$NEW_PROBES — this kit expects none"; exit 1; }
# the audit the deployed code will carry: the prod list (every entry pinned), its pair = the snapshot's blob, the golden
LISTF=backend/tests/costing_audit/accepted_differences.prod.yaml
LIST_ENTRIES=$(git cat-file blob "$TARGET:$LISTF" | grep -c '^- body:' || true)
PAIR_SHA=$(git cat-file blob "$TARGET:backend/tests/costing_audit/mes_snapshot/all.json" | sha256sum | cut -d' ' -f1)
LISTED=$(git cat-file blob "$TARGET:$LISTF" | sed -n 's/^ *snapshot_sha256: *\([0-9a-f]\{64\}\).*/\1/p' | head -n1)
[ "$LISTED" = "$PAIR_SHA" ] || { echo "STOP: the prod list's pair ($LISTED) is not the target snapshot ($PAIR_SHA)"; exit 1; }
[ "$LIST_ENTRIES" -ge 1 ] || { echo "STOP: no entries in $LISTF"; exit 1; }
GOLDEN_MONTH=$(for p in smoke chillers freezers icecream explosive; do git cat-file blob "$TARGET:backend/tests/costing_audit/golden/$p/_manifest.json" | sed -n 's/.*"workbook_month": *"\([^"]*\)".*/\1/p'; done | sort -u | tr '\n' ' ' | sed 's/ $//')
case "$GOLDEN_MONTH" in *" "*|"") echo "STOP: the packs' golden months differ or are missing: '$GOLDEN_MONTH'"; exit 1 ;; esac
PYYAML_VERSION=$(git cat-file blob "$TARGET:backend/requirements.txt" | sed -n 's/^PyYAML==\([0-9.]*\).*/\1/p' | head -n1)
DEPLOY_SH_SHA=$(git cat-file blob "$TARGET:deploy/prod/icb-deploy.sh" | sha256sum | cut -d' ' -f1)
WORKERS=4
for v in PYYAML_VERSION; do [ -n "${!v}" ] || { echo "STOP: could not derive $v"; exit 1; }; done

cat > "$S/expected.env" <<EOF
# derived by mkstage.sh from $TARGET (prev $PREV) on $(date -Is)
PREV=$PREV
PREV_TAG=$PREV_TAG
TARGET=$TARGET
BRANCH=$BRANCH
TAG=$TAG
TAG_OBJ=$TAG_OBJ
ALEMBIC=$ALEMBIC
CHANGED_COUNT=$CHANGED_COUNT
CHANGED_SHA=$CHANGED_SHA
N_PROBES=$N_PROBES
PYYAML_VERSION=$PYYAML_VERSION
DEPLOY_SH_SHA=$DEPLOY_SH_SHA
WORKERS=$WORKERS
FACTOR=$FACTOR
LIST_ENTRIES=$LIST_ENTRIES
PAIR_SHA=$PAIR_SHA
GOLDEN_MONTH=$GOLDEN_MONTH
# where every run must be (ops/lib/icb_where.sh; the database host as the RT6 discovery read it, 6 Oct)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EOF
( cd "$S" && sha256sum release.sh probe_paths.txt lib/icb_where.sh lib/icb_backup.sh expected.env > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/release.sh" && bash -n "$S/lib/icb_where.sh" && bash -n "$S/lib/icb_backup.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
echo "staged ${PREV:0:7} -> ${TARGET:0:7} ($TAG), alembic $ALEMBIC unchanged, $CHANGED_COUNT files, $N_PROBES no-session probes per door"
echo "audit: $LIST_ENTRIES pinned entries, pair ${PAIR_SHA:0:16}, golden month $GOLDEN_MONTH"
cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-release-v1.61.1.tar icb-release-v1.61.1 ) && ls -l "$OUTDIR/icb-release-v1.61.1.tar"
