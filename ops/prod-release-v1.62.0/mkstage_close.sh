#!/usr/bin/env bash
# RT9 close — stage the close's two laptop lines from COMMITTED blobs (Git Bash, from a commit that is on origin):
#
#     bash ops/prod-release-v1.62.0/mkstage_close.sh <empty-out-dir> <commit> <deploy-count> <deploy-digest> \
#                                                   <backup-path-on-prod> <backup-bytes> <backup-sha256>
#
#   icb-rt9-quotes          the read-only quotes check (close/rt9_quotes.sh + rt9_quotes_filter.py + lib/icb_where.sh
#                           + expected.env: the deploy's checked backup by path, size and sha256, and its quotes digest)
#   run_quotes_check.ps1    its laptop line (copy + unpack + stamp, then the check BY PATH under sudo)
#   run_window_fetch.ps1    step 9 again, re-staged: its rt9_vm.sh now also fetches /tmp/icb-rt9-quotes/out-*
#   run_window_cleanup.ps1  block 10, re-staged: its rt9_vm.sh now also names /tmp/icb-rt9-quotes{,.tar}
# with window_common.ps1 and rt9_vm.sh beside them. <deploy-count> <deploy-digest> = the "quotes" line of the
# deploy's OUTCOME.txt (release.sh, 22 Oct 12:35:35: "92 92163e05..."); when that OUTCOME is committed in <commit>,
# the stager checks the two agree. Prod must run the release (v1.62.0^{commit}): that is the one HEAD the lines accept.
set -u
OUTDIR=${1:?usage: mkstage_close.sh <empty-out-dir> <commit> <deploy-count> <deploy-digest> <backup> <bytes> <sha256>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
DCOUNT=${3:?deploy count}; DDIGEST=${4:?deploy digest}
BACKUP=${5:?the backup path on prod}; BBYTES=${6:?the backup size}; BSHA=${7:?the backup sha256}   # no apostrophe here: bash reads it as a quote
[[ "$DCOUNT" =~ ^[0-9]+$ ]] && [[ "$DDIGEST" =~ ^[0-9a-f]{32}$ ]] || { echo "STOP: the deploy's count and md5 look wrong: '$DCOUNT' '$DDIGEST'"; exit 1; }
[[ "$BACKUP" =~ ^/var/backups/postgres/icb_platform_pre-v1\.62\.0_[0-9]{8}-[0-9]{6}\.dump$ ]] && [[ "$BBYTES" =~ ^[0-9]+$ ]] && [[ "$BSHA" =~ ^[0-9a-f]{64}$ ]] \
  || { echo "STOP: the backup's path, size or sha256 look wrong: '$BACKUP' '$BBYTES' '$BSHA'"; exit 1; }
REL=$(git rev-parse --verify "v1.62.0^{commit}") || { echo "STOP: no tag v1.62.0"; exit 1; }
[ -n "$(git branch -r --contains "$SHA" 2>/dev/null)" ] || { echo "STOP: ${SHA:0:7} is on no origin branch — push it first"; exit 1; }
git merge-base --is-ancestor "$REL" "$SHA" || { echo "STOP: ${SHA:0:7} does not contain the release ${REL:0:7}"; exit 1; }
EVID=docs/audit/rt9_2026-10/prod/window_20261022/icb-release-v1.62.0/out-deploy-20261022-123535/OUTCOME.txt
if git cat-file -e "$SHA:$EVID" 2>/dev/null; then
  LINE=$(git cat-file blob "$SHA:$EVID" | sed -n 's/^quotes *\([0-9]*\) \([0-9a-f]\{32\}\) at the deploy.*/\1 \2/p')
  [ "$LINE" = "$DCOUNT $DDIGEST" ] || { echo "STOP: the committed deploy OUTCOME says '$LINE', not '$DCOUNT $DDIGEST'"; exit 1; }
  BLINE=$(git cat-file blob "$SHA:$EVID" | sed -n 's/^backup *\([^ ]*\) *\([0-9]*\) bytes *sha256 \([0-9a-f]*\).*/\1 \2 \3/p')
  [ "$BLINE" = "$BACKUP $BBYTES $BSHA" ] || { echo "STOP: the committed deploy OUTCOME's backup line is '$BLINE', not '$BACKUP $BBYTES $BSHA'"; exit 1; }
  echo "deploy digest and backup = the committed OUTCOME ($EVID)"
fi
mkdir -p "$OUTDIR" || exit 1
K="$OUTDIR/icb-rt9-quotes"
[ -e "$K" ] && { echo "exists: $K"; exit 1; }
mkdir -p "$K/lib" || exit 1
git cat-file blob "$SHA:ops/prod-release-v1.62.0/close/rt9_quotes.sh" > "$K/rt9_quotes.sh" || exit 1
git cat-file blob "$SHA:ops/prod-release-v1.62.0/close/rt9_quotes_filter.py" > "$K/rt9_quotes_filter.py" || exit 1
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$K/lib/icb_where.sh" || exit 1
cat > "$K/expected.env" <<EOF
# written by ops/prod-release-v1.62.0/mkstage_close.sh from $SHA on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EXPECT_HEADS="$REL"
DEPLOY_COUNT=$DCOUNT
DEPLOY_DIGEST=$DDIGEST
DEPLOY_AT="2026-10-22 12:35:35 SAST"
BACKUP=$BACKUP
BACKUP_BYTES=$BBYTES
BACKUP_SHA=$BSHA
STAGED_FROM=$SHA
EOF
( cd "$K" && sha256sum rt9_quotes.sh rt9_quotes_filter.py lib/icb_where.sh expected.env > SHA256SUMS ) || exit 1
CR=$(find "$K" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged kit"; exit 1; }
bash -n "$K/rt9_quotes.sh" && bash -n "$K/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
python -I -m py_compile "$K/rt9_quotes_filter.py" 2>/dev/null || python3 -I -m py_compile "$K/rt9_quotes_filter.py" || { echo "STOP: the filter does not compile"; exit 1; }
find "$K" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
( cd "$OUTDIR" && tar -cf icb-rt9-quotes.tar icb-rt9-quotes ) || exit 1
QKIT="icb-rt9-quotes:$(sha256sum "$OUTDIR/icb-rt9-quotes.tar" | cut -d' ' -f1)"

W=ops/prod-release-v1.62.0/window
git cat-file blob "$SHA:$W/rt9_vm.sh" > "$OUTDIR/rt9_vm.sh" || exit 1
bash -n "$OUTDIR/rt9_vm.sh" && [ "$(tr -cd '\r' < "$OUTDIR/rt9_vm.sh" | wc -c | tr -d ' ')" = 0 ] || { echo "STOP: rt9_vm.sh"; exit 1; }
grep -q 'icb-rt9-quotes' "$OUTDIR/rt9_vm.sh" || { echo "STOP: this rt9_vm.sh does not know the quotes kit"; exit 1; }
VM_SHA=$(sha256sum "$OUTDIR/rt9_vm.sh" | cut -d' ' -f1)
for src in "$W/window_common.ps1" "$W/run_window_fetch.ps1" "$W/run_window_cleanup.ps1" ops/prod-release-v1.62.0/close/run_quotes_check.ps1; do
  ps=${src##*/}
  git cat-file blob "$SHA:$src" | sed -e "s/__QKIT__/$QKIT/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$REL/" \
    -e "s/__VM_SHA__/$VM_SHA/" > "$OUTDIR/$ps" || exit 1
  grep -q '__[A-Z_]*__' "$OUTDIR/$ps" && { echo "STOP: $ps still has a placeholder"; exit 1; }
  LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/$ps" && { echo "STOP: $ps is not ASCII"; exit 1; }
done
( cd "$OUTDIR" && sha256sum icb-rt9-quotes.tar rt9_vm.sh ./*.ps1 > STAGE_SHA256SUMS && echo "STAGED_FROM=$SHA" > STAGED_FROM.txt )
echo "staged the RT9 close from ${SHA:0:7} (prod must run the release ${REL:0:7}); the deploy's quotes: $DCOUNT $DDIGEST; its backup: $BACKUP $BBYTES ${BSHA:0:16}"
grep -v '^#' "$K/expected.env"
ls -l "$OUTDIR"/*.tar "$OUTDIR"/*.ps1 "$OUTDIR"/rt9_vm.sh && cat "$OUTDIR/STAGE_SHA256SUMS"
