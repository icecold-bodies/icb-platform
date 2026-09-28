#!/usr/bin/env bash
# v1.58 — build the VM staging folder for pc_prod.sh from COMMITTED blobs (never the working
# copy: a Windows checkout is CRLF). Run in Git Bash from the repo:
#
#     bash ops/prod-pricing-corrections/mkstage.sh <empty-out-dir> [commit]      (default HEAD)
#
# Writes <out>/icb-audit-pc/{pc_prod.sh, stage/…, stage/STAGED_FROM, stage/SHA256SUMS} and a tar
# of it. STAGED_FROM (the full commit sha) is covered by SHA256SUMS, and pc_prod.sh prints it in
# every run header and writes it into the provenance note beside the prod journal. Then:
#     scp <out>/icb-audit-pc.tar icb@192.168.0.251:/tmp/ && ssh icb@… 'cd /tmp && tar -xf icb-audit-pc.tar'
set -u
OUTDIR=${1:?usage: mkstage.sh <empty-out-dir> [commit]}
REF=${2:-HEAD}
SHA=$(git rev-parse --verify "$REF^{commit}") || exit 1
S="$OUTDIR/icb-audit-pc"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
FILES="backend/tools/audit_pricing_corrections.py
docs/audit/pricing_corrections_2026-09/manifest.yaml
docs/audit/pricing_corrections_2026-09/impact/impact_refresh.sql"
mkdir -p "$S/stage" || exit 1
for f in $FILES; do
  mkdir -p "$S/stage/$(dirname "$f")" && git cat-file blob "$SHA:$f" > "$S/stage/$f" || exit 1
done
git cat-file blob "$SHA:ops/prod-pricing-corrections/pc_prod.sh" > "$S/pc_prod.sh" || exit 1
echo "$SHA" > "$S/stage/STAGED_FROM"
( cd "$S/stage" && sha256sum $FILES STAGED_FROM > SHA256SUMS ) || exit 1
CR=$(cat "$S/pc_prod.sh" "$S/stage/STAGED_FROM" $(for f in $FILES; do echo "$S/stage/$f"; done) | tr -cd '\r' | wc -c)
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/pc_prod.sh" || { echo "STOP: pc_prod.sh does not parse"; exit 1; }
echo "staged from $SHA"; cat "$S/stage/SHA256SUMS"
( cd "$OUTDIR" && tar -cf icb-audit-pc.tar icb-audit-pc ) && ls -l "$OUTDIR/icb-audit-pc.tar"
