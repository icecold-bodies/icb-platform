#!/usr/bin/env bash
# RT1 — build the VM staging folder for rt1_factor.sh (Manifest F or F2) from COMMITTED blobs. Git Bash:
#
#     bash ops/prod-rt1/mkstage_factor.sh <empty-out-dir> <commit> [F|F2]        (default F)
#
# F  -> icb-rt1-factor/   1.3170731707317074 -> 1.362881562881563  (5581/4095)
# F2 -> icb-rt1-factor2/  1.362881562881563  -> 1.361219512195122  (5581/4100)
# Either may go before or after the v1.59.2 deploy: expected.env lists both codes (v1.59.0 de74796 and the tag's commit).
set -u
OUTDIR=${1:?usage: mkstage_factor.sh <empty-out-dir> <commit> [F|F2]}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
M=${3:-F}
case "$M" in
  F)  DIR=icb-rt1-factor;  BEFORE=1.3170731707317074; AFTER=1.362881562881563 ;;
  F2) DIR=icb-rt1-factor2; BEFORE=1.362881562881563;  AFTER=1.361219512195122 ;;
  *) echo "STOP: the manifest is F or F2"; exit 1 ;;
esac
PREV=$(git rev-parse --verify "v1.59.0^{commit}") || { echo "STOP: no tag v1.59.0"; exit 1; }
TAGC=$(git rev-parse --verify "v1.59.2^{commit}") || { echo "STOP: no tag v1.59.2"; exit 1; }
[ "${PREV:0:7}" = de74796 ] || { echo "STOP: v1.59.0 is ${PREV:0:7}, prod ran de74796"; exit 1; }
S="$OUTDIR/$DIR"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S" || exit 1
for f in rt1_factor.sh rt1_factor.py; do git cat-file blob "$SHA:ops/prod-rt1/$f" > "$S/$f" || exit 1; done
cat > "$S/expected.env" <<EOF
# written by mkstage_factor.sh on $(date -Is)
F_MANIFEST=$M
EXPECT_HEADS="$PREV $TAGC"
EXPECT_ALEMBIC=0049
F_BEFORE=$BEFORE
F_AFTER=$AFTER
TOOL_SHA=$(sha256sum "$S/rt1_factor.py" | cut -d' ' -f1)
STAGED_FROM=$SHA
EOF
grep -qF "\"$M\": (\"$BEFORE\", \"$AFTER\"," "$S/rt1_factor.py" \
  || { echo "STOP: the tool's $M is not $BEFORE -> $AFTER"; exit 1; }
( cd "$S" && sha256sum rt1_factor.sh rt1_factor.py expected.env > SHA256SUMS ) || exit 1
CR=$(cat "$S"/* | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt1_factor.sh" || { echo "STOP: rt1_factor.sh does not parse"; exit 1; }
echo "staged $M from $SHA"; cat "$S/expected.env"; cat "$S/SHA256SUMS"
( cd "$OUTDIR" && tar -cf "$DIR.tar" "$DIR" ) && ls -l "$OUTDIR/$DIR.tar"
