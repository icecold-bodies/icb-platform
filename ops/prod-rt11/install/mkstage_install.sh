#!/usr/bin/env bash
# RT11 install kit — stage Michael's lines from COMMITTED blobs (Git Bash, from a commit that is on origin):
#
#     bash ops/prod-rt11/install/mkstage_install.sh <empty-out-dir> <commit> [<prod head> ...]
#
#   icb-rt11-install.tar   rt11_install.sh + rt11_verify.py + weasyprint-lock.txt + lib/icb_where.sh + expected.env
#                          + SHA256SUMS
#   rt11_install_vm.sh     the VM helper each line copies first (where / unpack / readback)
#   run_install.ps1        the line itself (one per step), its placeholders filled
# The prod HEAD(s) the lines accept default to <commit> itself: the release deploys the RT11 code first, and the pip
# step refuses any code without the shipped fonts. The release CA passes the release tag's commit. FONT_SHAS are the
# commit's own font blobs, so the VM checks the deployed faces byte for byte. LF bytes, no CR, ASCII .ps1, all parse.
set -u
OUTDIR=${1:?usage: mkstage_install.sh <empty-out-dir> <commit> [<prod head> ...]}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
shift 2
HEADS=""
for h in "${@:-$SHA}"; do HEADS="$HEADS $(git rev-parse --verify "$h^{commit}")" || exit 1; done
HEADS=${HEADS# }
APT_PKG=libharfbuzz-subset0
APT_VER=8.3.0-2build2
[ -n "$(git branch -r --contains "$SHA" 2>/dev/null)" ] || { echo "STOP: ${SHA:0:7} is on no origin branch: push it first"; exit 1; }
[ -e "$OUTDIR" ] && [ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ] && { echo "STOP: $OUTDIR is not empty"; exit 1; }
mkdir -p "$OUTDIR" || exit 1
K="$OUTDIR/icb-rt11-install"
mkdir -p "$K/lib" || exit 1
for f in rt11_install.sh rt11_verify.py weasyprint-lock.txt; do
  git cat-file blob "$SHA:ops/prod-rt11/install/$f" > "$K/$f" || exit 1
done
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$K/lib/icb_where.sh" || exit 1
FONT_SHAS=""
for f in LiberationSans-Regular LiberationSans-Bold LiberationSans-Italic LiberationSans-BoldItalic LiberationMono-Regular; do
  s=$(git cat-file blob "$SHA:backend/app/static/fonts/$f.ttf" | sha256sum | cut -d' ' -f1) || exit 1
  FONT_SHAS="$FONT_SHAS $s:$f.ttf"
done
cat > "$K/expected.env" <<EOF
# written by ops/prod-rt11/install/mkstage_install.sh from $SHA on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_HEADS="$HEADS"
STAGED_FROM=$SHA
APT_PKG=$APT_PKG
APT_VER=$APT_VER
FONT_SHAS="${FONT_SHAS# }"
EOF
( cd "$K" && sha256sum rt11_install.sh rt11_verify.py weasyprint-lock.txt lib/icb_where.sh expected.env > SHA256SUMS ) || exit 1
CR=$(find "$K" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged kit"; exit 1; }
bash -n "$K/rt11_install.sh" && bash -n "$K/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
( cd "$OUTDIR" && tar -cf icb-rt11-install.tar icb-rt11-install && rm -rf icb-rt11-install ) || exit 1
KIT_SHA=$(sha256sum "$OUTDIR/icb-rt11-install.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt11/install/rt11_install_vm.sh" > "$OUTDIR/rt11_install_vm.sh" || exit 1
bash -n "$OUTDIR/rt11_install_vm.sh" && [ "$(tr -cd '\r' < "$OUTDIR/rt11_install_vm.sh" | wc -c | tr -d ' ')" = 0 ] || { echo "STOP: rt11_install_vm.sh"; exit 1; }
VM_SHA=$(sha256sum "$OUTDIR/rt11_install_vm.sh" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt11/install/run_install.ps1" | sed -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$HEADS/" \
  -e "s/__VM_SHA__/$VM_SHA/" -e "s/__KIT_SHA__/$KIT_SHA/" > "$OUTDIR/run_install.ps1" || exit 1
grep -q '__[A-Z_]*__' "$OUTDIR/run_install.ps1" && { echo "STOP: run_install.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_install.ps1" && { echo "STOP: run_install.ps1 is not ASCII"; exit 1; }
( cd "$OUTDIR" && sha256sum icb-rt11-install.tar rt11_install_vm.sh run_install.ps1 > STAGE_SHA256SUMS && echo "STAGED_FROM=$SHA" > STAGED_FROM.txt )
echo "staged the RT11 install kit from ${SHA:0:7} (prod must run: $(for h in $HEADS; do printf '%s ' "${h:0:7}"; done); apt $APT_PKG=$APT_VER; lock $(git cat-file blob "$SHA:ops/prod-rt11/install/weasyprint-lock.txt" | grep -c .) packages)"
cat "$OUTDIR/STAGE_SHA256SUMS"
