#!/usr/bin/env bash
# RT6 §3.0 — build the staging folder for the prod discovery from COMMITTED blobs (a Windows checkout is CRLF;
# `git cat-file` gives the committed bytes). Git Bash:
#
#     bash ops/prod-rt6/mkstage_discovery.sh <empty-out-dir> <commit>
#
# expected.env pins prod: machine icb-mes-prod, database icb_platform, its code (the v1.60.2 tag's commit) and its
# alembic head (read from that commit). EXPECT_DBHOST is left unset on purpose: the discovery LEARNS prod's database
# host (printed on its first line) and every later RT6 kit pins it.
# Writes <out>/icb-rt6-discovery/{rt6_discovery.sh, rt6_discovery.py, insulation_rules.py, lib/icb_where.sh,
# expected.env, SHA256SUMS} + the tar + run_discovery.ps1 (filled in) beside it.
set -u
OUTDIR=${1:?usage: mkstage_discovery.sh <empty-out-dir> <commit>}
SHA=$(git rev-parse --verify "${2:?commit}^{commit}") || exit 1
PROD=$(git rev-parse --verify "v1.60.2^{commit}") || { echo "STOP: no tag v1.60.2"; exit 1; }
git merge-base --is-ancestor "$SHA" "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null \
  || echo "note: $SHA is not on this branch's origin copy yet — push before staging, so STAGED_FROM is reachable"
last_rev() {
  git cat-file blob "$1:backend/alembic/versions/$(git ls-tree --name-only "$1" backend/alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{4}_' | LC_ALL=C sort | tail -n1)" \
    | sed -n 's/^revision[^=]*= *"\([0-9]*\)".*/\1/p' | head -n1
}
EXPECT_ALEMBIC=$(last_rev "$PROD")
[ -n "$EXPECT_ALEMBIC" ] || { echo "STOP: cannot read the alembic head at ${PROD:0:7}"; exit 1; }

S="$OUTDIR/icb-rt6-discovery"
[ -e "$S" ] && { echo "exists: $S"; exit 1; }
mkdir -p "$S/lib" || exit 1
for f in rt6_discovery.sh rt6_discovery.py; do git cat-file blob "$SHA:ops/prod-rt6/$f" > "$S/$f" || exit 1; done
git cat-file blob "$SHA:ops/lib/icb_where.sh" > "$S/lib/icb_where.sh" || exit 1
git cat-file blob "$SHA:backend/app/services/insulation_rules.py" > "$S/insulation_rules.py" || exit 1
cat > "$S/expected.env" <<EOF
# written by mkstage_discovery.sh on $(date -Is)
EXPECT_MACHINE=icb-mes-prod
EXPECT_DB=icb_platform
EXPECT_HEADS="$PROD"
EXPECT_ALEMBIC=$EXPECT_ALEMBIC
STAGED_FROM=$SHA
EOF
( cd "$S" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum > SHA256SUMS ) || exit 1
CR=$(find "$S" -type f -print0 | xargs -0 cat | tr -cd '\r' | wc -c | tr -d ' ')
[ "$CR" = 0 ] || { echo "STOP: $CR CR byte(s) in the staged files"; exit 1; }
bash -n "$S/rt6_discovery.sh" && bash -n "$S/lib/icb_where.sh" || { echo "STOP: a staged script does not parse"; exit 1; }
N=$(wc -l < "$S/SHA256SUMS" | tr -d ' ')
( cd "$OUTDIR" && tar -cf "icb-rt6-discovery.tar" "icb-rt6-discovery" ) || exit 1
TSHA=$(sha256sum "$OUTDIR/icb-rt6-discovery.tar" | cut -d' ' -f1)
git cat-file blob "$SHA:ops/prod-rt6/run_discovery.ps1" \
  | sed -e "s/__TAR_SHA256__/$TSHA/" -e "s/__STAGED_FROM__/$SHA/" -e "s/__EXPECT_HEADS__/$PROD/" > "$OUTDIR/run_discovery.ps1" || exit 1
grep -q '__[A-Z0-9_]*__' "$OUTDIR/run_discovery.ps1" && { echo "STOP: run_discovery.ps1 still has a placeholder"; exit 1; }
LC_ALL=C grep -q $'[\x80-\xff]' "$OUTDIR/run_discovery.ps1" && { echo "STOP: run_discovery.ps1 is not ASCII"; exit 1; }
echo "staged the RT6 discovery kit from ${SHA:0:7} (prod expected at ${PROD:0:7}, alembic $EXPECT_ALEMBIC): $N files"
cat "$S/expected.env"
ls -l "$OUTDIR/icb-rt6-discovery.tar" "$OUTDIR/run_discovery.ps1"
echo "tar sha256 $TSHA"
