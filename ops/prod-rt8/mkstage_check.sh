#!/usr/bin/env bash
# RT8 — build the staging folder for the prod frozen-quote check from COMMITTED blobs (a Windows checkout is CRLF;
# `git cat-file` gives the committed bytes). Git Bash:
#
#     bash ops/prod-rt8/mkstage_check.sh <empty-out-dir> <commit>
#
# expected.env pins prod: machine icb-mes-prod, database icb_platform @ 127.0.0.1:5432, its code (the v1.61.0 tag's
# commit — or v1.61.1's once RT7 has deployed: both are accepted) and its alembic head.
# Writes <out>/icb-rt8-check/{rt8_frozen_check.sh, rt8_frozen_check.py, lib/icb_where.sh, expected.env, SHA256SUMS}
# + the tar + run_check.ps1 (filled in) beside it.
set -u
OUTDIR=${1:?usage: mkstage_check.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PROD=$(git rev-parse --verify "v1.61.0^{commit}") || { echo "STOP: no tag v1.61.0"; exit 1; }
[ "${PROD:0:7}" = 5e37b0a ] || { echo "STOP: v1.61.0 is ${PROD:0:7}, prod runs 5e37b0a"; exit 1; }
HEADS="$PROD"
if NEXT=$(git rev-parse --verify "v1.61.1^{commit}" 2>/dev/null); then HEADS="$HEADS $NEXT"; fi
git branch -r --contains "$SHA" | grep -q . \
  || echo "note: $SHA is on no origin branch yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PROD")
[ "$EXPECT_ALEMBIC" = 0053 ] || { echo "STOP: the alembic head at ${PROD:0:7} reads '$EXPECT_ALEMBIC', not 0053"; exit 1; }

S="$OUTDIR/icb-rt8-check"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/lib" || exit 1
for f in rt8_frozen_check.sh rt8_frozen_check.py; do git cat-file blob "$SHA:ops/prod-rt8/$f" > "$S/$f" || exit 1; done
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$S/lib/icb_where.sh" || exit 1
cat > "$S/expected.env" <<EOF
# written by mkstage_check.sh on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EXPECT_HEADS="$HEADS"
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt8_frozen_check.sh" && bash -n "$S/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
python3 -m py_compile "$S/rt8_frozen_check.py" 2>/dev/null || python -m py_compile "$S/rt8_frozen_check.py" || { echo "STOP: rt8_frozen_check.py does not compile"; exit 1; }
rm -rf "$S/__pycache__"
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
( cd "$OUTDIR" && tar -cf "icb-rt8-check.tar" "icb-rt8-check" ) || exit 1
TSHA=$(sha256sum "$OUTDIR/icb-rt8-check.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt8/run_check.ps1" \
  | sed -e "s/__TAR_SHA256__/$TSHA/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$HEADS/" > "$OUTDIR/run_check.ps1" || exit 1
grep -q '__[A-Z0-9_]*__' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 is not ASCII"; exit 1; }
echo "staged the RT8 check kit from ${SHA:0:7} (prod expected at $(for h in $HEADS; do printf '%s ' "${h:0:7}"; done), alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
ls -l "$OUTDIR/icb-rt8-check.tar" "$OUTDIR/run_check.ps1"
echo "tar sha256 $TSHA"
