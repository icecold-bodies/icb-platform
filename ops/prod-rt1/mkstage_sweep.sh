#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_sweep.sh from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt1/mkstage_sweep.sh <empty-out-dir> <commit>
#
# prod may run it before or after the v1.59.2 deploy: expected.env lists both codes (de74796 and the tag's commit).
set -u
OUTDIR=${1:?usage: mkstage_sweep.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "de74796^{commit}") || exit 1
TAGC=$(git rev-parse --verify "v1.59.2^{commit}") || { echo "STOP: no tag v1.59.2"; exit 1; }
S="$OUTDIR/icb-rt1-sweep"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
for f in rt1_sweep.sh rt1_sweep.py; do git cat-file blob "$SHA:ops/prod-rt1/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by mkstage_sweep.sh on $(date -Is)
EXPECT_HEADS="$PREV $TAGC"
EXPECT_ALEMBIC=0049
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt1_sweep.sh rt1_sweep.py expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_sweep.sh" || { echo "STOP: rt1_sweep.sh does not parse"; exit 1; }
echo "staged from $SHA"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt1-sweep.tar icb-rt1-sweep ) && ls -l "$OUTDIR/icb-rt1-sweep.tar"
