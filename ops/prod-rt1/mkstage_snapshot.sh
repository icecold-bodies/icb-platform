#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_snapshot.sh from COMMITTED blobs (a Windows checkout is
# CRLF; `git archive` is run with core.autocrlf=false so every file is the committed bytes). Git Bash:
#
#     bash ops/prod-rt1/mkstage_snapshot.sh <empty-out-dir> <commit> <reference|baseline> <expected-prod-head>
#
#   1b (before the release):     ... <out> <this branch's pushed commit> reference de74796
#   Stage 3 (after A + B + prune): ... <out> <the OUTCOME commit>          baseline  <the v1.59.2 target>
#
# Writes <out>/icb-rt1-snapshot/{rt1_snapshot.sh, rt1_door_report.py, expected.env,
# stage/backend/{tools/costing_audit, tests/costing_audit}, SHA256SUMS} and a tar of it.
set -u
OUTDIR=${1:?usage: mkstage_snapshot.sh <empty-out-dir> <commit> <reference|baseline> <expected-prod-head>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
MODE=${3:?reference|baseline}
case "$MODE" in reference|baseline) ;; *) echo "STOP: mode must be reference or baseline"; exit 1 ;; esac
EXPECT_HEAD=$(git rev-parse --verify "${4:?expected prod head}^{commit}") || exit 1
git merge-base --is-ancestor "$SHA" "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null \
  || echo "note: $SHA is not on this branch's origin copy yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$EXPECT_HEAD")
[ -n "$EXPECT_ALEMBIC" ] || { echo "STOP: cannot read the alembic head at ${EXPECT_HEAD:0:7}"; exit 1; }

S="$OUTDIR/icb-rt1-snapshot"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
git -c core.autocrlf=false archive "$SHA" backend/tools/costing_audit backend/tests/costing_audit | tar -x -C "$S/stage" || exit 1
for f in rt1_snapshot.sh rt1_door_report.py; do
  git cat-file blob "$SHA:ops/prod-rt1/$f" > "$S/$f" || exit 1
done
cat > "$S/expected.env" <<EOF
# written by mkstage_snapshot.sh on $(date -Is)
MODE=$MODE
EXPECT_HEAD=$EXPECT_HEAD
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.yaml' -o -name '*.env' -o -name '*.json' \) -print0 \
     | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged text files"; exit 1; }
bash -n "$S/rt1_snapshot.sh" || { echo "STOP: rt1_snapshot.sh does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
echo "staged $MODE from $SHA (prod expected at ${EXPECT_HEAD:0:7}, alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
( cd "$OUTDIR" && tar -cf icb-rt1-snapshot.tar icb-rt1-snapshot ) && ls -l "$OUTDIR/icb-rt1-snapshot.tar"
sha256sum "$OUTDIR/icb-rt1-snapshot.tar"
