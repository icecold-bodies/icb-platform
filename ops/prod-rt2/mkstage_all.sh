#!/usr/bin/env bash
# RT2 — build the VM staging folders for rt2_all.sh (the CLI "All" beside the page's) and rt2_doors.sh (the door
# report: ops/prod-rt1/rt1_door_report.py, unchanged) from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt2/mkstage_all.sh <empty-out-dir> <commit>
#
# expected.env lists the codes they may run over: v1.59.2 (1d9cb47, window step 1) and, once the annotated tag is on
# origin, v1.59.3 (steps 3, 5, 6 and the close); alembic 0049 or 0050. The door kit's all.json is the commit's CI
# snapshot (the report's "then" column).
set -u
OUTDIR=${1:?usage: mkstage_all.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PREV=$(git rev-parse --verify "v1.59.2^{commit}") || { echo "STOP: no tag v1.59.2"; exit 1; }
[ "${PREV:0:7}" = 1d9cb47 ] || { echo "STOP: v1.59.2 is ${PREV:0:7}, prod runs 1d9cb47"; exit 1; }
HEADS=$PREV; ALEMBICS=0049
if TAG_OBJ=$(git rev-parse -q --verify "refs/tags/v1.59.3"); then
  [ "$(git ls-remote --tags origin refs/tags/v1.59.3 | cut -f1 | head -n1)" = "$TAG_OBJ" ] || { echo "STOP: v1.59.3 is not on origin as the local object"; exit 1; }
  HEADS="$PREV $(git rev-parse "v1.59.3^{commit}")"; ALEMBICS="0049 0050"
else
  echo "note: no tag v1.59.3 yet — staged for v1.59.2 only (window step 1); re-stage after the tag"
fi
for d in icb-rt2-all icb-rt2-doors; do [ -e "$OUTDIR/$d" ] && { echo "exists: $OUTDIR/$d"; exit 1; }; done

S="$OUTDIR/icb-rt2-all"; mkdir -p "$S" || exit 1
for f in rt2_all.sh rt2_all_compare.py; do git cat-file blob "$SHA:ops/prod-rt2/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by mkstage_all.sh on $(date -Is)
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="$ALEMBICS"
STAGED_FROM=$SHA
EOF
( cd "$S" && sha256sum rt2_all.sh rt2_all_compare.py expected.env > SHA256SUMS ) || exit 1

T="$OUTDIR/icb-rt2-doors"; mkdir -p "$T" || exit 1
git cat-file blob "$SHA:ops/prod-rt2/rt2_doors.sh" > "$T/rt2_doors.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt1/rt1_door_report.py" > "$T/rt1_door_report.py" || exit 1
git cat-file blob "$SHA:backend/tests/costing_audit/mes_snapshot/all.json" > "$T/all.json" || exit 1
cat > "$T/expected.env" <<EOF
# written by mkstage_all.sh on $(date -Is) — the RT2 door test (window step 6) and the close
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBICS="$ALEMBICS"
STAGED_FROM=$SHA
EOF
( cd "$T" && sha256sum rt2_doors.sh rt1_door_report.py all.json expected.env > SHA256SUMS ) || exit 1

CR=$(cat "$S"/* "$T"/*.sh "$T"/*.py "$T"/expected.env "$T"/SHA256SUMS | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt2_all.sh" && bash -n "$T/rt2_doors.sh" || { echo "STOP: a script does not parse"; exit 1; }
echo "staged from $SHA"; cat "$S/expected.env"; cat "$T/expected.env"
( cd "$OUTDIR" && tar -cf icb-rt2-all.tar icb-rt2-all && tar -cf icb-rt2-doors.tar icb-rt2-doors ) \
  && ls -l "$OUTDIR"/icb-rt2-*.tar && sha256sum "$OUTDIR"/icb-rt2-*.tar
