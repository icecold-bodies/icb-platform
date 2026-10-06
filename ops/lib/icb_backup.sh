# shellcheck shell=bash
# RT6 (RT6_DISPATCH default 7, RT6_RULING_1 Q7) — the ONE checked backup every ops kit uses before it writes.
#
# The flaw it replaces (found by RT5): `pg_dump … | gzip > f || stop` tests gzip's exit status only. A failed dump
# leaves a valid, non-empty gzip that also passes `[ -s f ] && gzip -t f` — the kit then writes with no backup.
# A CI guard (backend/tests/test_ops_backup_guard.py) fails on any pg_dump pipe in ops/ outside this file.
#
# Sourced, never run:
#     . "$KIT_DIR/lib/icb_backup.sh"
#     icb_backup <out-file> data-gz <database-url> <schema.table>...   # data-only, gzip; each table must be in it
#     icb_backup <out-file> custom  <database-url> <schema.table>...   # pg_dump -Fc (the whole database); each named
#                                                                      # table's DATA must be listed by pg_restore -l
#     ... || stop BACKUP "$ICB_BACKUP_WHY — nothing applied"
# On success: prints one "ok" line and sets ICB_BACKUP_BYTES and ICB_BACKUP_SHA. On failure: returns 1 with the reason
# in ICB_BACKUP_WHY and leaves the bad file renamed <out-file>.FAILED, so nothing can mistake it for a backup.

icb_backup() {
  local out=$1 fmt=$2 url=$3 t schema table listing rc
  shift 3
  ICB_BACKUP_WHY=''; ICB_BACKUP_BYTES=''; ICB_BACKUP_SHA=''
  _icb_backup_fail() { ICB_BACKUP_WHY="backup $out: $1"; [ -e "$out" ] && mv -f "$out" "$out.FAILED"; return 1; }
  [ -n "$out" ] && [ -n "$url" ] || { ICB_BACKUP_WHY="usage: icb_backup <out> data-gz|custom <url> <schema.table>..."; return 1; }
  [ $# -gt 0 ] || { ICB_BACKUP_WHY="backup $out: name at least one table it must hold"; return 1; }
  [ -e "$out" ] && { ICB_BACKUP_WHY="backup $out: already exists — never overwritten"; return 1; }
  case "$fmt" in
    data-gz)
      local args=() ps
      for t in "$@"; do args+=(-t "$t"); done
      pg_dump "$url" --data-only "${args[@]}" | gzip > "$out"; ps=("${PIPESTATUS[@]}")
      [ "${ps[0]}" = 0 ] && [ "${ps[1]}" = 0 ] || { _icb_backup_fail "pg_dump exited ${ps[0]}, gzip ${ps[1]}"; return 1; }
      [ -s "$out" ] && gzip -t "$out" 2>/dev/null || { _icb_backup_fail "empty or not a valid gzip"; return 1; }
      for t in "$@"; do
        zcat "$out" | grep -q "^COPY $t " || { _icb_backup_fail "holds no $t data"; return 1; }
      done
      ;;
    custom)
      pg_dump "$url" -Fc -f "$out"; rc=$?
      [ "$rc" = 0 ] || { _icb_backup_fail "pg_dump exited $rc"; return 1; }
      [ -s "$out" ] || { _icb_backup_fail "empty"; return 1; }
      listing=$(pg_restore -l "$out" 2>/dev/null) || { _icb_backup_fail "pg_restore -l cannot read it"; return 1; }
      for t in "$@"; do
        schema=${t%%.*}; table=${t#*.}
        grep -q "TABLE DATA $schema $table " <<<"$listing" || { _icb_backup_fail "holds no $t data"; return 1; }
      done
      ;;
    *) ICB_BACKUP_WHY="backup $out: unknown format '$fmt' (data-gz | custom)"; return 1 ;;
  esac
  ICB_BACKUP_BYTES=$(stat -c %s "$out")
  ICB_BACKUP_SHA=$(sha256sum "$out" | cut -d' ' -f1)
  echo "   ok   backup $out  $ICB_BACKUP_BYTES bytes  sha256 $ICB_BACKUP_SHA  (holds: $*)"
}
