#!/usr/bin/env bash
# RT4 §3.0 — build the VM staging folder for rt4_discovery.sh from COMMITTED blobs (a Windows checkout is CRLF;
# `git archive` / `git cat-file` give the committed bytes). Git Bash:
#
#     bash ops/prod-rt4/mkstage_discovery.sh <empty-out-dir> <commit> [discovery|export41]
#
# discovery (default): the §3.0 kit. export41 (RT4_RULING_1 Q3): deleted id 41's lines + draft for Manifest S.
# expected.env pins prod's code (the v1.60.0 tag's commit) and its alembic head (read from that commit).
# Writes <out>/icb-rt4-<kit>/{the kit's files, expected.env,
# stage/backend/{tools/costing_audit, tests/costing_audit/test_mes_snapshot_no_people.py}, SHA256SUMS} + a tar.
set -u
OUTDIR=${1:?usage: mkstage_discovery.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
KIT=${3:-discovery}
case "$KIT" in
  discovery) FILES="rt4_discovery.sh rt4_discovery.py noauth_probe_paths.txt" ;;
  export41)  FILES="rt4_export41.sh rt4_export41.py" ;;
  *) echo "STOP: unknown kit $KIT"; exit 1 ;;
esac
PROD=$(git rev-parse --verify "v1.60.0^{commit}") || { echo "STOP: no tag v1.60.0"; exit 1; }
git merge-base --is-ancestor "$SHA" "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null \
  || echo "note: $SHA is not on this branch's origin copy yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PROD")
[ -n "$EXPECT_ALEMBIC" ] || { echo "STOP: cannot read the alembic head at ${PROD:0:7}"; exit 1; }

S="$OUTDIR/icb-rt4-$KIT"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  git cat-file blob "$SHA:ops/prod-rt4/$f" > "$S/$f" || exit 1
done
git -c core.autocrlf=false archive "$SHA" backend/tools/costing_audit \
    backend/tests/costing_audit/test_mes_snapshot_no_people.py | tar -x -C "$S/stage" || exit 1
cat > "$S/expected.env" <<EOF
# written by mkstage_discovery.sh on $(date -Is)
EXPECT_HEADS="$PROD"
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f \( -name '*.sh' -o -name '*.py' -o -name '*.txt' -o -name '*.env' -o -name '*.yaml' -o -name '*.json' \) -print0 \
     | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged text files"; exit 1; }
bash -n "$S/rt4_$KIT.sh" || { echo "STOP: rt4_$KIT.sh does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
echo "staged the RT4 $KIT kit from ${SHA:0:7} (prod expected at ${PROD:0:7}, alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
( cd "$OUTDIR" && tar -cf "icb-rt4-$KIT.tar" "icb-rt4-$KIT" ) && ls -l "$OUTDIR/icb-rt4-$KIT.tar"
sha256sum "$OUTDIR/icb-rt4-$KIT.tar"
