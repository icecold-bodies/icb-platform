#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_check.sh from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt1/mkstage_check.sh <empty-out-dir> <commit>
set -u
OUTDIR=${1:?usage: mkstage_check.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.59.0^{commit}") || { echo "STOP: no tag v1.59.0"; exit 1; }
TAGC=$(git rev-parse --verify "v1.59.2^{commit}") || { echo "STOP: no tag v1.59.2"; exit 1; }
S="$OUTDIR/icb-rt1-check"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
for f in rt1_check.sh rt1_check.py; do git cat-file blob "$SHA:ops/prod-rt1/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by mkstage_check.sh on $(date -Is)
EXPECT_HEADS="$PREV $TAGC"
EXPECT_ALEMBIC=0049
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt1_check.sh rt1_check.py expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_check.sh" || { echo "STOP: rt1_check.sh does not parse"; exit 1; }
echo "staged from $SHA"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt1-check.tar icb-rt1-check ) && ls -l "$OUTDIR/icb-rt1-check.tar"
