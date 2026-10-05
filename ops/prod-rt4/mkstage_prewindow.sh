#!/usr/bin/env bash
# RT4_RULING_2 — build the VM staging folder for rt4_prewindow.sh from COMMITTED blobs (a Windows checkout is CRLF;
# `git cat-file` gives the committed bytes). Git Bash, from the repo:
#
#     bash ops/prod-rt4/mkstage_prewindow.sh <empty-out-dir> <commit>
#
# Writes <out>/icb-rt4-prewindow/{rt4_prewindow.sh, rt4_prewindow.py, rt1_door_report.py, all.json, manifest_a.yaml,
# door_report_20261003.txt, expected.env, SHA256SUMS} + a tar. Every expected value is read from the commit:
#   EXPECT_HEADS   v1.60.0's commit (prod today) and, once the annotated tag is on origin, v1.60.1's
#   EXPECT_ALEMBIC the alembic head at v1.60.0 (v1.60.1 has no migration)
#   BASE_RUN       the 3 Oct page run RT3's window compared with (its committed compare.txt)
set -u
OUTDIR=${1:?usage: mkstage_prewindow.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.60.0^{commit}") || { echo "STOP: no tag v1.60.0"; exit 1; }
[ "${PREV:0:7}" = 682a6cc ] || { echo "STOP: v1.60.0 is ${PREV:0:7}, prod runs 682a6cc"; exit 1; }
HEADS=$PREV
if TAG_OBJ=$(git rev-parse -q --verify "refs/tags/v1.60.1"); then
  [ "$(git ls-remote --tags origin refs/tags/v1.60.1 | cut -f1 | head -n1)" = "$TAG_OBJ" ] \
    || { echo "STOP: v1.60.1 is not on origin as the local object — push the tag"; exit 1; }
  HEADS="$PREV $(git rev-parse "v1.60.1^{commit}")"
fi
git merge-base --is-ancestor "$SHA" "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null \
  || echo "note: $SHA is not on this branch's origin copy yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PREV")
[ -n "$EXPECT_ALEMBIC" ] || { echo "STOP: cannot read the alembic head at ${PREV:0:7}"; exit 1; }
RT3=docs/audit/rt3_2026-10/prod/window_20261003
BASE_RUN=$(git cat-file blob "$SHA:$RT3/icb-rt2-all/out-post-20261003-061605/compare.txt" | sed -n 's/^page run #\([0-9]*\): All.*/\1/p' | head -n1)
[ -n "$BASE_RUN" ] || { echo "STOP: cannot read the 3 Oct page run from RT3's committed compare.txt"; exit 1; }

S="$OUTDIR/icb-rt4-prewindow"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
blob() { git cat-file blob "$SHA:$1" > "$S/$2" || { echo "STOP: $1 missing at ${SHA:0:7}"; exit 1; }; }
blob ops/prod-rt4/rt4_prewindow.sh rt4_prewindow.sh
blob ops/prod-rt4/rt4_prewindow.py rt4_prewindow.py
blob ops/prod-rt1/rt1_door_report.py rt1_door_report.py
blob backend/tests/costing_audit/mes_snapshot/all.json all.json
blob docs/audit/srd_rear_frame_2026-09/manifest_a.yaml manifest_a.yaml
blob "$RT3/icb-rt2-doors/out-20261003-061457/door_report.txt" door_report_20261003.txt
cat > "$S/expected.env" <<EOF
# written by ops/prod-rt4/mkstage_prewindow.sh on $(date -Is) — RT4_RULING_2's pre-window check (read only)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
BASE_RUN=$BASE_RUN
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(cat "$S"/*.sh "$S"/*.py "$S"/*.yaml "$S"/*.txt "$S"/*.env | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged text files"; exit 1; }
bash -n "$S/rt4_prewindow.sh" || { echo "STOP: rt4_prewindow.sh does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
echo "staged the RT4 pre-window kit from ${SHA:0:7} (heads ${HEADS//$'\n'/ }, alembic $EXPECT_ALEMBIC, baseline run #$BASE_RUN): $N files"
cat "$S/expected.env"
( cd "$OUTDIR" && tar -cf "icb-rt4-prewindow.tar" "icb-rt4-prewindow" ) && ls -l "$OUTDIR/icb-rt4-prewindow.tar"
sha256sum "$OUTDIR/icb-rt4-prewindow.tar"
