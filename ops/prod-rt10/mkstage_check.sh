#!/usr/bin/env bash
# RT10 prod check — stage Michael's ONE line from COMMITTED blobs (Git Bash, from a commit that is on origin):
#
#     bash ops/prod-rt10/mkstage_check.sh <empty-out-dir> <commit>
#
#   icb-rt10-check.tar   rt10_check.sh + rt10_revisions.py + lib/icb_where.sh + expected.env + SHA256SUMS
#   rt10_vm.sh           the VM helper the line copies first (where / unpack / readback)
#   run_check.ps1        the line itself, its placeholders filled (stage commit, prod's HEAD, both sha256s)
# Prod must run v1.62.0 (v1.62.0^{commit}): the one HEAD the line accepts. LF bytes, no CR, ASCII .ps1, scripts parse.
set -u
OUTDIR=${1:?usage: mkstage_check.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
REL=$(git rev-parse --verify "v1.62.0^{commit}") || { echo "STOP: no tag v1.62.0"; exit 1; }
[ -n "$(git branch -r --contains "$SHA" 2>/dev/null)" ] || { echo "STOP: ${SHA:0:7} is on no origin branch: push it first"; exit 1; }
[ -e "$OUTDIR" ] && [ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ] && { echo "STOP: $OUTDIR is not empty"; exit 1; }
mkdir -p "$OUTDIR" || exit 1
K="$OUTDIR/icb-rt10-check"
mkdir -p "$K/lib" || exit 1
git cat-file blob "$SHA:ops/prod-rt10/rt10_check.sh" > "$K/rt10_check.sh" || exit 1
git cat-file blob "$SHA:ops/prod-rt10/rt10_revisions.py" > "$K/rt10_revisions.py" || exit 1
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$K/lib/icb_where.sh" || exit 1
cat > "$K/expected.env" <<EOF
# written by ops/prod-rt10/mkstage_check.sh from $SHA on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EXPECT_HEADS="$REL"
EXPECT_ALEMBIC=0053
STAGED_FROM=$SHA
EOF
( cd "$K" && sha256sum rt10_check.sh rt10_revisions.py lib/icb_where.sh expected.env > SHA256SUMS ) || exit 1
CR=$(find "$K" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged kit"; exit 1; }
bash -n "$K/rt10_check.sh" && bash -n "$K/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
python -I -m py_compile "$K/rt10_revisions.py" 2>/dev/null || python3 -I -m py_compile "$K/rt10_revisions.py" || { echo "STOP: the report does not compile"; exit 1; }
find "$K" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
( cd "$OUTDIR" && tar -cf icb-rt10-check.tar icb-rt10-check && rm -rf icb-rt10-check ) || exit 1
KIT_SHA=$(sha256sum "$OUTDIR/icb-rt10-check.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt10/rt10_vm.sh" > "$OUTDIR/rt10_vm.sh" || exit 1
bash -n "$OUTDIR/rt10_vm.sh" && [ "$(tr -cd '\r' < "$OUTDIR/rt10_vm.sh" | wc -c | tr -d ' ')" = 0 ] || { echo "STOP: rt10_vm.sh"; exit 1; }
VM_SHA=$(sha256sum "$OUTDIR/rt10_vm.sh" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt10/run_check.ps1" | sed -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$REL/" \
  -e "s/__VM_SHA__/$VM_SHA/" -e "s/__KIT_SHA__/$KIT_SHA/" > "$OUTDIR/run_check.ps1" || exit 1
grep -q '__[A-Z_]*__' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 is not ASCII"; exit 1; }
( cd "$OUTDIR" && sha256sum icb-rt10-check.tar rt10_vm.sh run_check.ps1 > STAGE_SHA256SUMS && echo "STAGED_FROM=$SHA" > STAGED_FROM.txt )
echo "staged the RT10 prod check from ${SHA:0:7} (prod must run v1.62.0 ${REL:0:7})"
cat "$OUTDIR/STAGE_SHA256SUMS"
