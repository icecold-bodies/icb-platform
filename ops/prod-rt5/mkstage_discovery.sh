#!/usr/bin/env bash
# RT5 §3.0 — build the VM staging folder for rt5_discovery.sh from COMMITTED blobs (a Windows checkout is CRLF;
# `git archive` / `git cat-file` give the committed bytes). Git Bash:
#
#     bash ops/prod-rt5/mkstage_discovery.sh <empty-out-dir> <commit>
#
# expected.env pins prod's code (the v1.60.1 tag's commit) and its alembic head (read from that commit).
# Writes <out>/icb-rt5-discovery/{rt5_discovery.sh, rt5_discovery.py, expected.env,
# stage/backend/{tools/costing_audit, tests/costing_audit/{packs, golden/{freezers,smoke}, sheet_maps,
# accepted_differences*.yaml}}, SHA256SUMS} + a tar.
set -u
OUTDIR=${1:?usage: mkstage_discovery.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PROD=$(git rev-parse --verify "v1.60.1^{commit}") || { echo "STOP: no tag v1.60.1"; exit 1; }
git merge-base --is-ancestor "$SHA" "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null \
  || echo "note: $SHA is not on this branch's origin copy yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PROD")
[ -n "$EXPECT_ALEMBIC" ] || { echo "STOP: cannot read the alembic head at ${PROD:0:7}"; exit 1; }

S="$OUTDIR/icb-rt5-discovery"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/stage" || exit 1
for f in rt5_discovery.sh rt5_discovery.py; do
  git cat-file blob "$SHA:ops/prod-rt5/$f" > "$S/$f" || exit 1
done
T=backend/tests/costing_audit
git -c core.autocrlf=false archive "$SHA" backend/tools/costing_audit "$T/packs" "$T/golden/freezers" "$T/golden/smoke" \
    "$T/sheet_maps" "$T/accepted_differences.yaml" "$T/accepted_differences.prod.yaml" | tar -x -C "$S/stage" || exit 1
grep -q roof_floor_eps "$S/stage/$T/packs/freezers.yaml" || { echo "STOP: the staged freezers pack has no roof_floor_eps"; exit 1; }
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
bash -n "$S/rt5_discovery.sh" || { echo "STOP: rt5_discovery.sh does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
echo "staged the RT5 discovery kit from ${SHA:0:7} (prod expected at ${PROD:0:7}, alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
( cd "$OUTDIR" && tar -cf "icb-rt5-discovery.tar" "icb-rt5-discovery" ) && ls -l "$OUTDIR/icb-rt5-discovery.tar"
sha256sum "$OUTDIR/icb-rt5-discovery.tar"
