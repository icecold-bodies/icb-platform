#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_doors.sh (the rear-door thickness report) from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt1/mkstage_doors.sh <empty-out-dir> <commit>
#
# expected.env lists both codes (v1.59.0 de74796 and the v1.59.2 tag's commit); all.json is the commit's CI snapshot
# (the report's "then" column).
set -u
OUTDIR=${1:?usage: mkstage_doors.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.59.0^{commit}") || { echo "STOP: no tag v1.59.0"; exit 1; }
TAGC=$(git rev-parse --verify "v1.59.2^{commit}") || { echo "STOP: no tag v1.59.2"; exit 1; }
[ "${PREV:0:7}" = de74796 ] || { echo "STOP: v1.59.0 is ${PREV:0:7}, prod ran de74796"; exit 1; }
S="$OUTDIR/icb-rt1-doors"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
for f in rt1_doors.sh rt1_door_report.py; do git cat-file blob "$SHA:ops/prod-rt1/$f" > "$S/$f" || exit 1; done
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$S/all.json" || exit 1
cat > "$S/expected.env" <<EOF
# written by mkstage_doors.sh on $(date -Is)
EXPECT_HEADS="$PREV $TAGC"
EXPECT_ALEMBIC=0049
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt1_doors.sh rt1_door_report.py all.json expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/*.sh "$S"/*.py "$S"/expected.env "$S"/SHA256SUMS | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_doors.sh" || { echo "STOP: rt1_doors.sh does not parse"; exit 1; }
echo "staged from $SHA"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-rt1-doors.tar icb-rt1-doors ) && ls -l "$OUTDIR/icb-rt1-doors.tar"
