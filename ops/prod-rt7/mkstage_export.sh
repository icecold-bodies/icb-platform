#!/usr/bin/env bash
# RT7 build — the staging folder for the build export (the 15-body snapshot + All) from COMMITTED blobs (a Windows checkout is CRLF;
# `git cat-file` gives the committed bytes). Git Bash:
#
#     bash ops/prod-rt7/mkstage_export.sh <empty-out-dir> <commit>
#
# expected.env pins prod: machine icb-mes-prod, database icb_platform @ 127.0.0.1:5432 (learned by RT6's discovery),
# its code (the v1.61.0 tag's commit) and its alembic head (read from that commit).
# Writes <out>/icb-rt7-export/{rt7_export.sh, rt7_inventory.py, rt7_summary.py, test_mes_snapshot_no_people.py,
# lib/icb_where.sh, expected.env, SHA256SUMS} + the tar + run_export.ps1 (filled in) beside it.
set -u
OUTDIR=${1:?usage: mkstage_export.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PROD=$(git rev-parse --verify "v1.61.0^{commit}") || { echo "STOP: no tag v1.61.0"; exit 1; }
[ "${PROD:0:7}" = 5e37b0a ] || { echo "STOP: v1.61.0 is ${PROD:0:7}, prod runs 5e37b0a"; exit 1; }
git branch -r --contains "$SHA" | grep -q . \
  || echo "note: $SHA is on no origin branch yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PROD")
[ "$EXPECT_ALEMBIC" = 0053 ] || { echo "STOP: the alembic head at ${PROD:0:7} reads '$EXPECT_ALEMBIC', not 0053"; exit 1; }

S="$OUTDIR/icb-rt7-export"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/lib" || exit 1
for f in rt7_export.sh rt7_inventory.py rt7_summary.py; do git cat-file blob "$SHA:ops/prod-rt7/$f" > "$S/$f" || exit 1; done
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$S/lib/icb_where.sh" || exit 1
# the gate as DEPLOYED (prod's copy of the test), so the export is judged by the rules prod's code ships with
git cat-file blob "$PROD:backend/tests/costing_audit/test_mes_snapshot_no_people.py" > "$S/test_mes_snapshot_no_people.py" || exit 1
cat > "$S/expected.env" <<EOF
# written by mkstage_export.sh on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EXPECT_HEADS="$PROD"
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt7_export.sh" && bash -n "$S/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
( cd "$OUTDIR" && tar -cf "icb-rt7-export.tar" "icb-rt7-export" ) || exit 1
TSHA=$(sha256sum "$OUTDIR/icb-rt7-export.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt7/run_export.ps1" \
  | sed -e "s/__TAR_SHA256__/$TSHA/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$PROD/" > "$OUTDIR/run_export.ps1" || exit 1
grep -q '__[A-Z0-9_]*__' "$OUTDIR/run_export.ps1" && { echo "STOP: run_export.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_export.ps1" && { echo "STOP: run_export.ps1 is not ASCII"; exit 1; }
echo "staged the RT7 build-export kit from ${SHA:0:7} (prod expected at ${PROD:0:7}, alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
ls -l "$OUTDIR/icb-rt7-export.tar" "$OUTDIR/run_export.ps1"
echo "tar sha256 $TSHA"
