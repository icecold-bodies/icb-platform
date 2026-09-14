#!/usr/bin/env bash
# Read-only verification used by deploy.sh, rollback.sh and verify.sh. Sourced after lib.sh.
#   run_checks target|baseline  -> sets FAILS (0 = everything matched)

run_checks() {
  local expect="$1" want_head want_js want_v want_master want_settings
  if [ "$expect" = "target" ]; then
    want_head="$TARGET_SHA"; want_js="$JS_SHA_TARGET"; want_v="$V_TARGET"; want_master="5"; want_settings="1"
  else
    want_head="$BASE_SHA"; want_js="$JS_SHA_BASE"; want_v="$V_BASE"; want_master="0"; want_settings="0"
  fi
  FAILS=0

  step "VERIFY ($expect): checkout"
  local h d
  h="$(head_sha)"; d="$(tracked_dirty)"
  [ "$h" = "$want_head" ] && ok "HEAD = $h" || bad "HEAD = $h (want $want_head)"
  [ "$d" = "0" ] && ok "no tracked modifications" || bad "$d tracked modification(s) in $REPO"

  step "VERIFY ($expect): files on disk"
  local js_sha tags ntags master settings
  js_sha="$(sha_file "$JS")"
  [ "$js_sha" = "$want_js" ] && ok "calculator.js sha256 ${js_sha:0:16}" || bad "calculator.js sha256 ${js_sha:0:16} (want ${want_js:0:16})"
  tags="$(grep -o 'calculator\.js?v=[0-9]*' "$TPL" 2>/dev/null | tr '\n' ' ')"
  ntags="$(grep -o 'calculator\.js?v=[0-9]*' "$TPL" 2>/dev/null | wc -l | tr -d ' ')"
  [ "$ntags" = "1" ] && [ "$tags" = "calculator.js?v=$want_v " ] && ok "calculator.html has exactly one tag: ${tags% }" \
    || bad "calculator.html tags: '${tags% }' (want exactly calculator.js?v=$want_v)"
  master="$(grep -c _masterBodyVarNameSet "$JS" 2>/dev/null)"
  [ "$master" = "$want_master" ] && ok "_masterBodyVarNameSet markers = $master" || bad "_masterBodyVarNameSet markers = $master (want $want_master)"
  settings="$(grep -c 'Default thickness (m)' "$SETTINGS_TPL" 2>/dev/null)"
  [ "$settings" = "$want_settings" ] && ok "Explorer 'Default thickness (m)' field markers = $settings" || bad "Explorer default-thickness markers = $settings (want $want_settings)"

  step "VERIFY ($expect): what browsers are SERVED"
  local u r
  for u in $SERVED_URLS; do
    r="$(served_sha "$u" "$want_v")"
    case "$r" in
      *"sha=$want_js") ok "$u/static/js/calculator.js?v=$want_v  ${r%sha=*}sha=${want_js:0:16}" ;;
      *) bad "$u/static/js/calculator.js?v=$want_v  $r" ;;
    esac
  done
  # Cloudflare caches .js by FULL URL (query included). Asking it for ?v=$want_v while the
  # disk still holds the other bundle would store the WRONG bytes under that URL for hours,
  # so the real URL is probed only once the disk already matches.
  if [ "$js_sha" = "$want_js" ]; then
    r="$(served_sha "$CF_URL" "$want_v")"
    case "$r" in
      *"sha=$want_js") ok "(Cloudflare door) $CF_URL/static/js/calculator.js?v=$want_v matches" ;;
      "http=200"*) bad "(Cloudflare door) $CF_URL/static/js/calculator.js?v=$want_v serves OTHER bytes ($r) - PURGE the Cloudflare cache for mes.icecoldgrp.online now, then re-run this same verification ($expect)" ;;
      *) say "  WARN (Cloudflare door unreachable from the VM: $r) - check it from a browser on the domain after the purge" ;;
    esac
  else
    say "  SKIP Cloudflare probe - the files on disk are not this version yet (probing would cache the wrong bundle at the edge)"
  fi
  local health
  health="$(curl -sk --max-time 15 "$HEALTH_URL" 2>/dev/null)"
  case "$health" in *'"ok"'*) ok "health $health" ;; *) bad "health: '${health:-no response}'" ;; esac

  step "VERIFY ($expect): database schema + service"
  local al
  al="$(alembic_current)"
  if [ -z "$al" ]; then
    bad "could not READ alembic current (sudo/env/alembic error - see $OUT/alembic_current.err); this is NOT evidence of a schema change"
  else
    case "$al" in *"$ALEMBIC_HEAD"*) ok "alembic current: $(echo "$al" | tr '\n' ' ')" ;; *) bad "alembic current: '$(echo "$al" | tr '\n' ' ')' (want $ALEMBIC_HEAD)" ;; esac
  fi
  local active ts
  active="$(systemctl is-active "$SERVICE" 2>/dev/null)"
  ts="$(service_ts)"
  [ "$active" = "active" ] && ok "$SERVICE active (since $ts)" || bad "$SERVICE is '$active'"

  step "VERIFY ($expect): result"
  if [ "$FAILS" = "0" ]; then say "  ALL CHECKS PASSED"; else say "  $FAILS CHECK(S) FAILED"; fi
}
