#!/usr/bin/env bash
# RT11 §3.0 prod check — stage Michael's ONE line from COMMITTED blobs (Git Bash, from a commit that is on origin):
#
#     bash ops/prod-rt11/mkstage_check.sh <empty-out-dir> <commit>
#
#   icb-rt11-check.tar   rt11_check.sh + lib/icb_where.sh + expected.env + requirements-rt11.txt + SHA256SUMS
#   rt11_vm.sh           the VM helper the line copies first (where / unpack / readback)
#   run_check.ps1        the line itself, its placeholders filled (stage commit, prod's HEAD, both sha256s)
# requirements-rt11.txt = the commit's backend/requirements.txt + the WeasyPrint pin (unless it already names one).
# Prod must run v1.62.0, or v1.63.0 once that tag exists (RT11_RULING_0A: RT12 takes prod to v1.63.0 first): the only
# HEADs the line accepts. LF bytes, no CR, ASCII .ps1, scripts parse.
set -u
OUTDIR=${1:?usage: mkstage_check.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
REL=$(git rev-parse --verify "v1.62.0^{commit}") || { echo "STOP: no tag v1.62.0"; exit 1; }
REL63=$(git rev-parse --verify -q "v1.63.0^{commit}") && REL="$REL $REL63"
WEASY_PIN=weasyprint==70.0
APT_PKGS="libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0"
[ -n "$(git branch -r --contains "$SHA" 2>/dev/null)" ] || { echo "STOP: ${SHA:0:7} is on no origin branch: push it first"; exit 1; }
[ -e "$OUTDIR" ] && [ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ] && { echo "STOP: $OUTDIR is not empty"; exit 1; }
mkdir -p "$OUTDIR" || exit 1
K="$OUTDIR/icb-rt11-check"
mkdir -p "$K/lib" || exit 1
git cat-file blob "$SHA:ops/prod-rt11/rt11_check.sh" > "$K/rt11_check.sh" || exit 1
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$K/lib/icb_where.sh" || exit 1
git cat-file blob "$SHA:backend/requirements.txt" > "$K/requirements-rt11.txt" || exit 1
grep -qiE '^weasyprint==' "$K/requirements-rt11.txt" || printf '\n# RT11 section 3.0 prod check: the pin under test\n%s\n' "$WEASY_PIN" >> "$K/requirements-rt11.txt"
[ "$(grep -ciE '^weasyprint==' "$K/requirements-rt11.txt")" = 1 ] || { echo "STOP: requirements-rt11.txt must name weasyprint exactly once"; exit 1; }
cat > "$K/expected.env" <<EOF
# written by ops/prod-rt11/mkstage_check.sh from $SHA on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_DBHOST=127.0.0.1:5432
EXPECT_HEADS="$REL"
EXPECT_ALEMBIC=0053
STAGED_FROM=$SHA
WEASY_PIN=$(grep -iE '^weasyprint==' "$K/requirements-rt11.txt")
APT_PKGS="$APT_PKGS"
EOF
( cd "$K" && sha256sum rt11_check.sh lib/icb_where.sh expected.env requirements-rt11.txt > SHA256SUMS ) || exit 1
CR=$(find "$K" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged kit"; exit 1; }
bash -n "$K/rt11_check.sh" && bash -n "$K/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
( cd "$OUTDIR" && tar -cf icb-rt11-check.tar icb-rt11-check && rm -rf icb-rt11-check ) || exit 1
KIT_SHA=$(sha256sum "$OUTDIR/icb-rt11-check.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt11/rt11_vm.sh" > "$OUTDIR/rt11_vm.sh" || exit 1
bash -n "$OUTDIR/rt11_vm.sh" && [ "$(tr -cd '\r' < "$OUTDIR/rt11_vm.sh" | wc -c | tr -d ' ')" = 0 ] || { echo "STOP: rt11_vm.sh"; exit 1; }
VM_SHA=$(sha256sum "$OUTDIR/rt11_vm.sh" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt11/run_check.ps1" | sed -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$REL/" \
  -e "s/__VM_SHA__/$VM_SHA/" -e "s/__KIT_SHA__/$KIT_SHA/" > "$OUTDIR/run_check.ps1" || exit 1
grep -q '__[A-Z_]*__' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_check.ps1" && { echo "STOP: run_check.ps1 is not ASCII"; exit 1; }
( cd "$OUTDIR" && sha256sum icb-rt11-check.tar rt11_vm.sh run_check.ps1 > STAGE_SHA256SUMS && echo "STAGED_FROM=$SHA" > STAGED_FROM.txt )
echo "staged the RT11 prod check from ${SHA:0:7} (prod must run: $(for h in $REL; do printf '%s ' "${h:0:7}"; done); pin $WEASY_PIN; apt $APT_PKGS)"
cat "$OUTDIR/STAGE_SHA256SUMS"
