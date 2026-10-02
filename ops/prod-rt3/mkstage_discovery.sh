#!/usr/bin/env bash
# RT3 — build the VM staging folder for rt3_discovery.sh from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt3/mkstage_discovery.sh <empty-out-dir> <commit>
#
# expected.env pins prod's code (the v1.59.3 tag's commit) and its alembic head (0050).
set -u
OUTDIR=${1:?usage: mkstage_discovery.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PROD=$(git rev-parse --verify "v1.59.3^{commit}") || { echo "STOP: no tag v1.59.3"; exit 1; }
S="$OUTDIR/icb-rt3-discovery"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
for f in rt3_discovery.sh rt3_discovery.py; do git cat-file blob "$SHA:ops/prod-rt3/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by mkstage_discovery.sh on $(date -Is)
EXPECT_HEADS="$PROD"
EXPECT_ALEMBIC=0050
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt3_discovery.sh rt3_discovery.py expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt3_discovery.sh" || { echo "STOP: rt3_discovery.sh does not parse"; exit 1; }
echo "staged from $SHA (prod expected at ${PROD:0:7}, alembic 0050)"; cat "$S/expected.env"
( cd "$OUTDIR" && tar -cf icb-rt3-discovery.tar icb-rt3-discovery ) && ls -l "$OUTDIR/icb-rt3-discovery.tar" && sha256sum "$OUTDIR/icb-rt3-discovery.tar"
