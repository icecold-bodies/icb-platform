"""RT8 §3.0 — timing harness for the Edit race (READ ONLY: opens saved costings for edit, never saves).

For each run: a FRESH browser context (empty localStorage), demo autologin, open
/mes/calculator?edit=<id>, then watch until the page is quiet. Instrumentation (init script, before any page
script): every /api/calculate request/response is timestamped, and a MutationObserver timestamps each change of
#edit-banner-balance (the moment verifyEditBalance ran). After the page settles we read the page's own `lastResult`
and the saved result from GET /api/calculations/<id>.

Verdicts per run:
  gate_ran       verifyEditBalance wrote the banner
  late_calcs     /api/calculate responses that arrived AFTER the banner was written (the race firing)
  drift_banner   the banner says the saved figures are shown (re-cost drifted)
  shown_is_saved lastResult.grand_total == saved grand_total (to the cent)
  WRONG          drift_banner and not shown_is_saved  -> Michael's screenshot state

Usage: python -I rt8_race.py <base> <out.json> <runs> <id> [<id> ...]
"""
import json
import os
import sys
import time

PATCH = os.environ.get("RT8_PATCH") == "cancel"

from playwright.sync_api import sync_playwright

INIT = r"""
(() => {
  window.__rt8 = { t0: performance.now(), calcs: [], banner: [] };
  const _f = window.fetch;
  window.fetch = function (input, init) {
    const url = (typeof input === 'string') ? input : (input && input.url) || '';
    if (url.indexOf('/api/calculate') >= 0) {
      const rec = { start: performance.now(), end: null };
      window.__rt8.calcs.push(rec);
      return _f.apply(this, arguments).then(r => { rec.end = performance.now(); return r; },
                                            e => { rec.end = performance.now(); rec.err = true; throw e; });
    }
    return _f.apply(this, arguments);
  };
  document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('edit-banner-balance');
    if (!b) return;
    new MutationObserver(() => {
      window.__rt8.banner.push({ t: performance.now(), text: b.textContent.slice(0, 200) });
    }).observe(b, { childList: true, subtree: true, characterData: true });
  });
})();
"""


def one_run(browser, base, rid):
    ctx = browser.new_context(base_url=base)
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    if PATCH:
        def _patch(route):
            resp = route.fetch()
            body = resp.text()
            import re as _re
            pat = _re.compile(r"(    await runCalc\(\);)(\r?\n)(    verifyEditBalance\(saved\);)")
            body, n = pat.subn(r"    clearTimeout(calcTimer);\2\1\2    clearTimeout(calcTimer);\2\3", body)
            if n != 1:
                print("PATCH ANCHOR NOT FOUND", n, flush=True)
            route.fulfill(response=resp, body=body)
        page.route("**/static/js/calculator.js*", _patch)
    r = page.request.post(f"{base}/api/mes/autologin", headers={"Origin": base})
    assert r.ok, f"autologin HTTP {r.status}"
    saved = page.request.get(f"{base}/api/calculations/{rid}").json()
    t = time.monotonic()
    page.goto(f"/mes/calculator?edit={rid}")
    # quiet = no /api/calculate in flight, banner written, and 2.5 s (> the 700 ms debounce) with nothing new
    last_n, quiet_since = -1, time.monotonic()
    while time.monotonic() - t < 40:
        st = page.evaluate("() => ({n: window.__rt8.calcs.length, open: window.__rt8.calcs.filter(c => c.end === null).length,"
                           " b: window.__rt8.banner.length})")
        if st["n"] != last_n or st["open"]:
            last_n, quiet_since = st["n"], time.monotonic()
        elif st["b"] and time.monotonic() - quiet_since > 2.5:
            break
        page.wait_for_timeout(100)
    probe = page.evaluate("""() => ({
        calcs: window.__rt8.calcs, banner: window.__rt8.banner,
        shown_gt: (typeof lastResult !== 'undefined' && lastResult) ? lastResult.grand_total : null,
        shown_items: (typeof lastResult !== 'undefined' && lastResult && lastResult.items) ? lastResult.items.length : null,
        banner_now: (document.getElementById('edit-banner-balance') || {}).textContent || '' })""")
    ctx.close()
    sr = saved.get("saved_result") or {}
    gate_t = probe["banner"][-1]["t"] if probe["banner"] else None
    first_gate_t = probe["banner"][0]["t"] if probe["banner"] else None
    late = [c for c in probe["calcs"] if first_gate_t is not None and c["end"] and c["end"] > first_gate_t]
    drift = "Showing the saved figures" in probe["banner_now"]
    shown_is_saved = (probe["shown_gt"] is not None and sr.get("grand_total") is not None
                      and abs(float(probe["shown_gt"]) - float(sr["grand_total"])) < 0.005)
    return {
        "id": rid, "qno": saved.get("quote_number"), "n_calcs": len(probe["calcs"]),
        "calc_ms": [[round(c["start"]), round(c["end"] or -1)] for c in probe["calcs"]],
        "gate_ms": round(first_gate_t) if first_gate_t else None,
        "late_calcs": len(late), "drift_banner": drift, "banner": probe["banner_now"][:160],
        "saved_gt": sr.get("grand_total"), "shown_gt": probe["shown_gt"], "shown_is_saved": shown_is_saved,
        "WRONG": bool(drift and not shown_is_saved),
    }


def main():
    base, out, runs, ids = sys.argv[1], sys.argv[2], int(sys.argv[3]), [int(x) for x in sys.argv[4:]]
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for rid in ids:
            for i in range(runs):
                res = one_run(browser, base, rid)
                res["run"] = i + 1
                results.append(res)
                print(json.dumps({k: res[k] for k in ("id", "qno", "run", "n_calcs", "gate_ms", "late_calcs",
                                                      "drift_banner", "shown_is_saved", "WRONG")}), flush=True)
        browser.close()
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
