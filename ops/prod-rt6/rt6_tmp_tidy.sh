#!/usr/bin/env bash
# RT6 — the prod /tmp tidy (RT6_RULING_1 "the /tmp tidy: ratified as proposed"), one step of the v1.61.0 window.
# The operator runs ONE line at a time, on the VM:
#
#     sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh dryrun    read only: each of the 34 reviewed items is there and holds
#                                                          exactly the reviewed files (sha256), nothing else is named
#     sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh apply     MOVES (never deletes) exactly those 34 into
#                                                          /var/backups/icb-tmp-archive-<date>/ (root:root 700) with
#                                                          LISTING.txt and SHA256SUMS, then reads it back
#     sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh show      read only: the archive and what is left in /tmp
#     sudo bash /tmp/icb-rt6-tidy/rt6_tmp_tidy.sh restore /var/backups/icb-tmp-archive-<date>   puts them back
#
# Its FIRST output line names the machine, the database (name and host) and the git HEAD, and it refuses unless they
# are prod's (ops/lib/icb_where.sh). The list is tmp_tidy_manifest.txt — the read-only RT6 discovery's listing of
# 6 Oct — never a glob: node-compile-cache/, the OS items, RT6's own kits and anything newer (the v1.61.0 deploy's own
# rollback note) stay. Moving keeps owners, modes and dates (mv on one filesystem). Touches no database, no service.
# Each check is a loud STOP; deliberately no bare `set -e`.
set -u

MODE=${1:-}; ARG=${2:-}
BASE=/tmp/icb-rt6-tidy
MANIFEST=$BASE/tmp_tidy_manifest.txt
DAY=$(date +%Y%m%d)
ARCH=/var/backups/icb-tmp-archive-$DAY
TS=$(date -u +%Y%m%dT%H%M%SZ)
USAGE="usage: sudo bash $0 dryrun | apply | show | restore <archive-dir>"
case "$MODE" in
  dryrun|apply|show) [ -z "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  restore) [ -n "$ARG" ] || { echo "$USAGE"; exit 1; } ;;
  *) echo "$USAGE"; exit 1 ;;
esac
OUT=''
stop() { echo; echo "######## STOP [$1]: $2"; [ -n "$OUT" ] && [ -d "$OUT" ] && chmod -R a+rX "$OUT"; echo "######## tell the CA${OUT:+: $OUT}"; exit 1; }
say()  { echo "== $*"; }

# ---- where am I? (the first line) ------------------------------------------------------------------------------
URL=''
if [ "$(id -u)" = 0 ] && [ -r /etc/icb/backend.env ]; then
  URL=$( set -a; . /etc/icb/backend.env >/dev/null 2>&1; printf '%s' "${DATABASE_URL:-}" )
  URL=${URL/postgresql+psycopg:/postgresql:}
fi
# shellcheck disable=SC1091
. "$BASE/lib/icb_where.sh" 2>/dev/null || { echo "######## RT6 tmp tidy $MODE · machine $(hostname -s) · db ? · head ?"; stop KIT "lib/icb_where.sh missing: re-stage"; }
# shellcheck disable=SC1091
. "$BASE/expected.env" 2>/dev/null || true
export PGOPTIONS='-c default_transaction_read_only=on'
icb_where "tmp tidy $MODE" /opt/icb-platform "$URL"
unset PGOPTIONS
[ "$(id -u)" = 0 ] || stop KIT "run with sudo (items belong to icb, root and mickeyger)"
for v in EXPECT_MACHINE EXPECT_DB EXPECT_DBHOST EXPECT_HEADS N_ITEMS N_FILES; do [ -n "${!v:-}" ] || stop KIT "expected.env has no $v"; done
icb_where_check || stop WHERE "$WHERE_WHY"
( cd "$BASE" && sha256sum -c --quiet SHA256SUMS ) || stop KIT "staged files do not match SHA256SUMS: re-stage"
OUT=$BASE/out-$MODE-$TS
[ -e "$OUT" ] && { OUT=''; stop KIT "two runs in one second: run again"; }
mkdir -p "$OUT" && chmod 700 "$OUT" || { OUT=''; stop KIT "cannot create the run folder"; }
exec > >(tee -a "$OUT/run.txt") 2>&1

mapfile -t ITEMS < <(sed -n 's/^ITEM //p' "$MANIFEST")
[ "${#ITEMS[@]}" = "$N_ITEMS" ] || stop KIT "the manifest names ${#ITEMS[@]} items, expected $N_ITEMS"
sed -n 's/^FILE //p' "$MANIFEST" | LC_ALL=C sort -k2 > "$OUT/reviewed.sha256"
[ "$(wc -l < "$OUT/reviewed.sha256")" = "$N_FILES" ] || stop KIT "the manifest lists $(wc -l < "$OUT/reviewed.sha256") files, expected $N_FILES"
for n in "${ITEMS[@]}"; do case "$n" in */*|.*|''|node-compile-cache|systemd-private-*|snap-private-tmp|icb-rt6-*)
  stop KIT "the manifest names '$n' — never moved" ;; esac; done

state_of() { # $1 root (/tmp or the archive): "present missing changed" for the reviewed items, and the current sums
  local root=$1 present=0 missing=0 n
  for n in "${ITEMS[@]}"; do [ -e "$root/$n" ] && present=$((present+1)) || missing=$((missing+1)); done
  { for n in "${ITEMS[@]}"; do [ -e "$root/$n" ] && find "$root/$n" -type f -print0; done | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum; } | sed "s#  $root/#  /tmp/#" | LC_ALL=C sort -k2 > "$OUT/current_$(basename "$root").sha256"
  echo "$present $missing"
}

if [ "$MODE" = show ]; then
  say "what is left in /tmp of the reviewed 34 (read only)"
  set -- $(state_of /tmp); echo "   in /tmp: $1 of $N_ITEMS present"
  for a in /var/backups/icb-tmp-archive-*; do [ -d "$a" ] && { echo "   archive $a: $(find "$a" -type f | wc -l) files"; ( cd "$a" && sha256sum -c --quiet SHA256SUMS 2>/dev/null && echo "      SHA256SUMS: all match" || echo "      SHA256SUMS: MISMATCH or missing" ); }; done
  echo "   node-compile-cache: $([ -d /tmp/node-compile-cache ] && echo present || echo MISSING)"
  chmod -R a+rX "$OUT"; echo; echo "######## DONE (show) — tell the CA: $OUT"; exit 0
fi

if [ "$MODE" = restore ]; then
  A=$ARG; [ -d "$A" ] && [ -f "$A/SHA256SUMS" ] || stop RESTORE "no archive with SHA256SUMS at $A"
  ( cd "$A" && sha256sum -c --quiet SHA256SUMS ) || stop RESTORE "the archive does not match its own SHA256SUMS"
  for n in "${ITEMS[@]}"; do [ -e "/tmp/$n" ] && stop RESTORE "/tmp/$n exists again — not overwritten"; done
  for n in "${ITEMS[@]}"; do [ -e "$A/$n" ] && { mv "$A/$n" "/tmp/$n" || stop RESTORE "mv back of $n failed"; }; done
  set -- $(state_of /tmp)
  cmp -s "$OUT/reviewed.sha256" "$OUT/current_tmp.sha256" || stop RESTORE "restored, but the sums differ from the reviewed list — tell the CA"
  chmod -R a+rX "$OUT"; echo; echo "######## DONE (restore: $1 of $N_ITEMS back in /tmp, sums as reviewed) — tell the CA: $OUT"; exit 0
fi

say "the reviewed items in /tmp: present and holding exactly the reviewed files"
set -- $(state_of /tmp)
PRESENT=$1; MISSING=$2
echo "   $PRESENT of $N_ITEMS present, $MISSING missing"
if [ "$PRESENT" = 0 ] && [ -f "$ARCH/SHA256SUMS" ]; then
  say "already tidied: none of the 34 is in /tmp and $ARCH exists"
  ( cd "$ARCH" && sha256sum -c --quiet SHA256SUMS ) && echo "   $ARCH SHA256SUMS: all match" || stop ARCHIVE "$ARCH does not match its SHA256SUMS"
  chmod -R a+rX "$OUT"; echo; echo "######## DONE ($MODE: already tidied) — tell the CA: $OUT"; exit 0
fi
[ "$MISSING" = 0 ] || stop STATE "$MISSING reviewed item(s) are missing from /tmp — not the reviewed state; nothing moved"
if ! cmp -s "$OUT/reviewed.sha256" "$OUT/current_tmp.sha256"; then
  diff "$OUT/reviewed.sha256" "$OUT/current_tmp.sha256" | head -n 20 | sed 's/^/   | /'
  stop STATE "the files under the reviewed items are not the reviewed ones (above) — nothing moved"
fi
echo "   all $N_FILES files match the reviewed sha256s"
echo "   stays: node-compile-cache ($([ -d /tmp/node-compile-cache ] && echo present || echo absent)), the OS items, RT6's kits, anything newer"
if [ "$MODE" = dryrun ]; then
  chmod -R a+rX "$OUT"; echo; echo "######## DONE (dryrun: $N_ITEMS to move, $N_FILES files, as reviewed) — tell the CA: $OUT"; exit 0
fi

say "apply: move the $N_ITEMS items into $ARCH (root:root 700)"
[ -e "$ARCH" ] && stop ARCHIVE "$ARCH already exists — never mixed into"
mkdir -p "$ARCH" && chown root:root "$ARCH" && chmod 700 "$ARCH" || stop ARCHIVE "cannot create $ARCH"
for n in "${ITEMS[@]}"; do mv "/tmp/$n" "$ARCH/$n" || stop MOVE "mv of $n failed — tell the CA (already moved items are in $ARCH)"; done
( cd "$ARCH" && find . -type f ! -name SHA256SUMS ! -name LISTING.txt -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS ) \
  || stop ARCHIVE "SHA256SUMS not written"
{ echo "# moved from /tmp by ops/prod-rt6/rt6_tmp_tidy.sh on $(date -Is) (RT6_RULING_1); owners, modes and dates kept"
  ( cd "$ARCH" && find . -mindepth 1 ! -name SHA256SUMS ! -name LISTING.txt -printf '%M %u:%g %10s %TY-%Tm-%Td %TH:%TM %p\n' | LC_ALL=C sort -k6 ); } > "$ARCH/LISTING.txt"
chmod 600 "$ARCH/SHA256SUMS" "$ARCH/LISTING.txt"

say "read back"
set -- $(state_of "$ARCH")
sed "s#  \./#  /tmp/#" "$ARCH/SHA256SUMS" | LC_ALL=C sort -k2 > "$OUT/archive.sha256"
cmp -s "$OUT/reviewed.sha256" "$OUT/archive.sha256" || stop READBACK "the archive's sums are not the reviewed ones — tell the CA"
echo "   the archive's SHA256SUMS = the reviewed list ($N_FILES files)"
LEFT=0; for n in "${ITEMS[@]}"; do [ -e "/tmp/$n" ] && LEFT=$((LEFT+1)); done
[ "$LEFT" = 0 ] || stop READBACK "$LEFT of the items are still in /tmp"
echo "   none of the $N_ITEMS is left in /tmp"
[ -d /tmp/node-compile-cache ] && echo "   node-compile-cache/ is still there" || echo "   (node-compile-cache/ was not there before either)"
echo "   $ARCH: $(stat -c '%U:%G %a' "$ARCH"), $(find "$ARCH" -type f | wc -l) files incl. SHA256SUMS and LISTING.txt"
cp "$ARCH/LISTING.txt" "$OUT/LISTING.txt" && cp "$ARCH/SHA256SUMS" "$OUT/SHA256SUMS.archive"
chmod -R a+rX "$OUT"
echo; echo "######## DONE (apply: $N_ITEMS items moved to $ARCH, read back) — tell the CA: $OUT  (undo: sudo bash $0 restore $ARCH)"
