"""v1.46 — the help-assistant panels must stay READABLE on every page skin.

Regression cover for the "assistant replies are invisible" defect and its twin
in the Excel-audit panel. Both panels paint their own dark surface but took
their *text* colours from page-level theme variables (``--text-head``,
``--text``, ``--text-dim``, ``--border``, ``--accent`` …). Those resolve DARK on
the light MES/admin skins introduced in v1.40.1, so:

* ``.help-msg-assistant`` rendered near-black on the near-black chat panel —
  present in the DOM, legible only by drag-selecting it;
* the audit panel had it worse, because its root sets ``color``, so every
  element declaring no colour of its own inherited near-black too.

Written against the *mechanism*, not the reported symptom: each case opens a
panel, renders the full set of node shapes its JS can produce, then sweeps
EVERY visible text-bearing element and asserts a sane WCAG contrast ratio
between the computed text colour and the **composited** background behind it.
Any future page-theme change that leaks into either panel goes red here,
whichever element it lands on.

Thresholds
----------
``FLOOR`` (3.0) applies to everything. It is set just under the panels' own
long-standing white-on-brand-blue chrome (#fff on #388bfd = 3.34:1, the user
bubble and the Send button), which is accepted design and not in scope. A real
theme leak lands around 1.1:1, so the floor separates the two with wide margin.
``BODY_FLOOR`` (4.5) — full WCAG AA — applies to the reading surfaces.

Elements painted with a ``background-image`` (the gradient chrome) are reported
as *indeterminate* rather than guessed at: a gradient has no single computed
colour to measure against. They are excluded from the assertions and listed in
the failure output, and ``MIN_SWEPT`` guards against a future change quietly
turning the whole sweep indeterminate.

Selector policy: journeys normally select on ``data-testid`` only. This test is
the exception, and deliberately so — the CSS class names ARE the contract under
test here, so they are the correct handle.
"""
from __future__ import annotations

import json

import pytest

# (path, expects_light_page_theme). The light entries are the ones that
# regressed; the dark standalone app is kept in the sweep so a fix can't be
# "make it work on light, break it on dark".
PAGES = [
    ("/calculator?skin=mes", True),        # Michael's report: the costing calculator
    ("/?skin=mes", True),                  # dashboard under the MES light skin
    ("/admin/customers?skin=mes", True),   # an admin page, per the WO click-through
    ("/calculator", False),                # standalone dark app — must be unchanged
]

FLOOR = 3.0
BODY_FLOOR = 4.5
MIN_SWEPT = 12

# Reading surfaces held to full WCAG AA. Matched against the reported selector.
BODY_SURFACES = (
    # chat panel
    "help-msg-assistant", "help-msg-tool", "help-msg-error", "help-suggestion",
    "help-action-btn", "help-actions-intro", "help-title", "help-subtitle",
    "help-icon-btn", "help-toggle", "help-input",
    # audit panel
    "audit-title", "audit-subtitle", "audit-stat-label", "audit-stat-value",
    "audit-section-name", "audit-section-total", "audit-section-delta",
    "audit-line-name", "audit-line-side", "audit-line-num", "audit-formula",
    "audit-cause-chip", "audit-ctxmenu-item", "audit-warnings",
)

# ── Chat panel ───────────────────────────────────────────────────────────────
# Injects one of every node shape help_chat.js can build (class strings copied
# from appendMsg / appendToolNote / appendLoadingBubble / renderActions /
# renderSuggestions), so the sweep covers the whole panel and not just whatever
# a live conversation happened to produce. No network, no API key.
_INJECT_CHAT_JS = """
() => {
  const msgs = document.getElementById('help-messages');
  const sugg = document.getElementById('help-suggestions');
  const mk = (parent, cls, text) => {
    const el = document.createElement('div');
    el.className = cls;
    el.textContent = text;
    parent.appendChild(el);
    return el;
  };
  msgs.innerHTML = '';
  mk(msgs, 'help-msg help-msg-user', 'explain this formula');
  mk(msgs, 'help-msg help-msg-assistant', 'This line multiplies the panel area by the rate.');
  mk(msgs, 'help-msg help-msg-assistant help-msg-streaming', 'Streaming reply in flight');
  mk(msgs, 'help-msg help-msg-assistant help-msg-tool', 'looking up: bom_line…');
  mk(msgs, 'help-msg help-msg-error', 'The assistant is unavailable right now.');
  const loading = document.createElement('div');
  loading.className = 'help-msg help-msg-assistant help-msg-loading';
  loading.innerHTML = '<span class="help-spinner" aria-hidden="true"></span>'
                    + '<span class="help-loading-label">Thinking…</span>';
  msgs.appendChild(loading);
  const wrap = mk(msgs, 'help-actions', '');
  mk(wrap, 'help-actions-intro', 'Want me to:');
  const row = mk(wrap, 'help-actions-row', '');
  const btn = document.createElement('button');
  btn.className = 'help-action-btn';
  btn.textContent = 'Open the BOM';
  row.appendChild(btn);
  // Suggestions: the real renderer runs on load, but force both variants so the
  // primary (Excel-audit) chip is swept too.
  sugg.innerHTML = '';
  const s1 = document.createElement('button');
  s1.className = 'help-suggestion';
  s1.textContent = 'How do I update a price in a costing?';
  sugg.appendChild(s1);
  const s2 = document.createElement('button');
  s2.className = 'help-suggestion help-suggestion-primary';
  s2.textContent = '📊 Load costing sheet from Excel';
  sugg.appendChild(s2);
  sugg.style.display = '';
}
"""

# ── Audit panel ──────────────────────────────────────────────────────────────
# The audit panel is built lazily by help_audit.js and only renders after an
# Excel workbook is attached and /api/help/audit returns a report. Rather than
# hand-build its DOM, we feed the REAL renderers a fixture report — so the sweep
# measures exactly what a user sees, cause chips and formula rows included.
# Covers every delta class (zero / small / big / na) and every cause chip.
_AUDIT_REPORT = {
    "sheet_name": "Costing",
    "summary": {
        "excel_grand_total": 125000.0,
        "live_grand_total": 126500.0,
        "delta": 1500.0,
        "rounding_drift_total": 0.42,
        "live_body": "Trailer 20",
    },
    "warnings": ["2 rows on the sheet could not be parsed and were skipped."],
    "by_section": [
        {
            "section": "Panels",
            "excel_total": 50000.0, "live_total": 51500.0,
            "delta": 1500.0, "rounding_drift": 0.42,
            "matched": [
                {"name": "Side panel",
                 "excel": {"qty": 4, "unit_price": 1000.0, "total": 4000.0},
                 "live": {"qty": 4, "unit_price": 1100.0, "total": 4400.0},
                 "delta": {"qty": 0, "unit_price": 100.0, "total": 400.0},
                 "cause": {"cause": "price", "note": "Unit price differs by R100.00"},
                 "excel_formula": "=B4*C4", "app_formula": "area * rate",
                 "source_cell": "D4"},
                {"name": "Roof panel",
                 "excel": {"qty": 1, "unit_price": 9000.0, "total": 9000.0},
                 "live": {"qty": 1, "unit_price": 9000.0, "total": 9000.0},
                 "delta": {"qty": 0, "unit_price": 0.0, "total": 0.0},
                 "cause": {"cause": "match"}},
                {"name": "Front panel",
                 "excel": {"qty": 2, "unit_price": 500.0, "total": 1000.0},
                 "live": {"qty": 3, "unit_price": 500.0, "total": 1500.0},
                 "delta": {"qty": 1, "unit_price": 0.0, "total": 500.0},
                 "cause": {"cause": "formula", "note": "Quantity formula differs"},
                 "excel_formula": "=2", "app_formula": "ceil(length / 6)"},
                {"name": "Trim strip",
                 "excel": {"qty": 1, "unit_price": 10.005, "total": 10.005},
                 "live": {"qty": 1, "unit_price": 10.0, "total": 10.0},
                 "delta": {"qty": 0, "unit_price": 0.005, "total": 0.005},
                 "cause": {"cause": "rounding", "note": "Half-up vs banker's rounding"}},
                {"name": "Mystery item",
                 "excel": {"qty": 1, "unit_price": 700.0, "total": 700.0},
                 "live": {"qty": 1, "unit_price": 950.0, "total": 950.0},
                 "delta": {"qty": 0, "unit_price": 250.0, "total": 250.0},
                 "cause": {"cause": "unexplained", "note": "No matching rule found"}},
            ],
            "only_in_excel": [{"name": "Old trim", "qty": 2, "unit_price": 150.0, "total": 300.0}],
            "only_in_live": [{"name": "New bracket", "qty": 1, "unit_price": 220.0, "total": 220.0}],
            "matched_truncated": 3,
        },
        {
            "section": "Chassis mounting",
            "excel_total": 10000.0, "live_total": 19000.0,
            "delta": 9000.0, "rounding_drift": None,     # -> delta-big
            "matched": [], "only_in_excel": [], "only_in_live": [],
        },
        {
            "section": "Floor",
            "excel_total": 20000.0, "live_total": 20000.0,
            "delta": 0.0, "rounding_drift": None,        # -> delta-zero
            "matched": [], "only_in_excel": [], "only_in_live": [],
        },
        {
            "section": "Insulation",
            "excel_total": 15000.0, "live_total": None,
            "delta": None, "rounding_drift": None,       # -> delta-na
            "matched": [], "only_in_excel": [], "only_in_live": [],
        },
    ],
}

# help_audit.js bails out of runAudit() unless the chat panel reports an
# attached workbook. Stub that one getter (help_chat.js installs the real one on
# load, so this must run AFTER the page loads) and reveal the audit launcher.
_OPEN_AUDIT_JS = """
() => {
  window.helpChatGetAttachment = () => ({
    upload_id: 'stub-upload', filename: 'costing.xlsx',
    sheets: ['Costing'], sheet: 'Costing',
  });
  if (window.helpAuditAttachmentChanged) window.helpAuditAttachmentChanged(true);
  window.helpAuditOpen();
}
"""

# Composites each element's background over its ancestors (a bubble's
# rgba(255,255,255,.06) is transparent — getComputedStyle hands back the rgba,
# not what the eye sees), then returns the WCAG 2.x contrast ratio.
_SWEEP_JS = """
() => {
  const parse = (c) => {
    const m = /rgba?\\(([^)]+)\\)/.exec(c || '');
    if (!m) return null;
    const p = m[1].split(',').map(v => parseFloat(v.trim()));
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const lum = (c) => {
    const ch = [c.r, c.g, c.b].map(v => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  };
  // Walk up compositing until an opaque layer is hit; the browser canvas
  // (white) is the last resort. A background-image (gradient) on the way up has
  // no single colour to measure, so the result is flagged indeterminate rather
  // than guessed at.
  const effectiveBg = (el) => {
    const stack = [];
    let indeterminate = false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') { indeterminate = true; break; }
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    base.indeterminate = indeterminate;
    return base;
  };
  const label = (el) => {
    if (el.id) return '#' + el.id;
    const cls = (el.className || '').toString().trim().split(/\\s+/).filter(Boolean);
    return el.tagName.toLowerCase() + (cls.length ? '.' + cls.join('.') : '');
  };
  const push = (out, el, selector, fg, sample, colorText) => {
    const bg = effectiveBg(el);
    out.push({
      selector: selector,
      sample: (sample || '').slice(0, 40),
      color: colorText,
      bg: bg.indeterminate ? '(gradient)'
        : 'rgb(' + [bg.r, bg.g, bg.b].map(Math.round).join(', ') + ')',
      indeterminate: !!bg.indeterminate,
      ratio: bg.indeterminate ? null : Math.round(ratio(over(fg, bg), bg) * 100) / 100,
    });
  };
  const roots = ['#help-launcher', '#help-panel',
                 '#help-audit-launcher', '#help-audit-panel', '.audit-ctxmenu']
    .map(s => document.querySelector(s)).filter(Boolean);
  const out = [];
  const seen = new Set();
  for (const root of roots) {
    const all = [root, ...root.querySelectorAll('*')];
    for (const el of all) {
      if (seen.has(el)) continue;
      seen.add(el);
      // Only elements that paint their OWN text (a direct non-empty text node).
      const own = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3 && n.textContent.trim())
        .map(n => n.textContent.trim()).join(' ');
      if (!own) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue;
      const box = el.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) continue;
      const fg = parse(cs.color);
      if (!fg || fg.a === 0) continue;
      push(out, el, label(el), fg, own, cs.color);
    }
  }
  // The textarea holds no text NODE, so the loop above skips it. Its own text
  // colour and its ::placeholder pseudo-element are swept explicitly.
  const input = document.getElementById('help-input');
  if (input) {
    const ics = getComputedStyle(input);
    const ifg = parse(ics.color);
    if (ifg && ifg.a > 0) push(out, input, '#help-input', ifg, 'explain this formula', ics.color);
    const phText = getComputedStyle(input, '::placeholder').color;
    const ph = parse(phText);
    if (ph && ph.a > 0) {
      push(out, input, '#help-input::placeholder', ph,
           input.getAttribute('placeholder') || '', phText);
    }
  }
  return out;
}
"""

# Proves the page under test really is the light skin — without this a future
# change that quietly drops theme-mes.css would make the light cases vacuous.
_PAGE_THEME_JS = """
() => {
  const v = getComputedStyle(document.body).getPropertyValue('--text-head').trim();
  if (!v) return null;
  let r, g, b;
  if (v.startsWith('#')) {
    r = parseInt(v.slice(1, 3), 16); g = parseInt(v.slice(3, 5), 16); b = parseInt(v.slice(5, 7), 16);
  } else {
    const m = /rgba?\\(([^)]+)\\)/.exec(v);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    r = p[0]; g = p[1]; b = p[2];
  }
  return { value: v, luma: (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 };
}
"""


def _autologin(page, base: str) -> None:
    """Mint the admin session cookie only.

    Both widgets are Jinja-side (``base.html``, ``{% if user %}``), so this
    journey never touches the React shell — it just needs the cookie before
    navigating to a legacy page.
    """
    resp = page.request.post(f"{base}/api/mes/autologin", headers={"Origin": base})
    assert resp.ok, f"admin autologin failed: HTTP {resp.status}"


def _stub_help_routes(page) -> None:
    """Make both panels reachable regardless of the server's key/upload state.

    * ``/api/help/health`` — help_chat.js ships the launcher ``class="hidden"``
      and only reveals it once this confirms an ``ANTHROPIC_API_KEY``, so on a
      server without one (CI) the launcher never becomes clickable.
    * ``/api/help/audit`` — the audit panel renders nothing until a real report
      comes back. The fixture drives the REAL renderers.

    These tests are about what the panels PAINT, not about whether the key is
    wired or a workbook was uploaded. Everything downstream is the real JS.
    """
    page.route(
        "**/api/help/health",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"configured": true, "model": "stub"}',
        ),
    )
    page.route(
        "**/api/help/audit",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_AUDIT_REPORT),
        ),
    )


def _settle(page) -> None:
    """Bring the panel to its RESTING paint before measuring.

    Two sources of nondeterminism, both fixed here:

    * Playwright leaves the pointer wherever the last click landed, so a row
      under it keeps its ``:hover`` background.
    * ``.audit-section-row`` carries ``transition: background 0.12s``, so
      merely moving the pointer away starts a *fade-out* — sampling during it
      reads an interpolated background that exists for ~120ms and never at
      rest. That is what made the ``⊘ rounding`` chip read 4.31:1 on one run
      and 4.72:1 on the next, failing a different parametrised case each time.

    Transitions and animations are disabled outright rather than waited on, so
    the sweep can never race a fade, a spinner or the streaming caret. Hover
    and in-flight states are not the contract under test; the resting paint is.
    """
    page.mouse.move(0, 0)
    page.add_style_tag(content="*, *::before, *::after {"
                               " transition: none !important;"
                               " animation: none !important; }")


def _fmt(r) -> str:
    ratio = "(gradient)" if r["indeterminate"] else f"{r['ratio']:>6}:1"
    return (f"  {r['selector']:<46} {ratio}  "
            f"text {r['color']} on {r['bg']}   “{r['sample']}”")


def _assert_readable(rows, path: str, panel: str) -> None:
    measured = [r for r in rows if not r["indeterminate"]]
    skipped = [r for r in rows if r["indeterminate"]]
    context = ("\n  (indeterminate, gradient-backed, not asserted: "
               + ", ".join(r["selector"] for r in skipped) + ")") if skipped else ""

    assert len(measured) >= MIN_SWEPT, (
        f"{path} [{panel}]: only {len(measured)} measurable elements swept "
        f"(< {MIN_SWEPT}) — the panel did not render, or everything became "
        f"gradient-backed and the sweep is no longer proving anything.{context}"
    )

    too_low = [r for r in measured if r["ratio"] < FLOOR]
    assert not too_low, (
        f"{path} [{panel}]: text is unreadable (contrast < {FLOOR}:1) — a page "
        f"theme variable has leaked back in:\n"
        + "\n".join(_fmt(r) for r in too_low) + context
    )

    body_low = [r for r in measured
                if r["ratio"] < BODY_FLOOR
                and any(s in r["selector"] for s in BODY_SURFACES)]
    assert not body_low, (
        f"{path} [{panel}]: reading surfaces below WCAG AA ({BODY_FLOOR}:1):\n"
        + "\n".join(_fmt(r) for r in body_low) + context
    )


def _open_page(page, base: str, path: str, expect_light: bool):
    _autologin(page, base)
    _stub_help_routes(page)          # must be routed BEFORE the page loads
    page.goto(f"{base}{path}")

    theme = page.evaluate(_PAGE_THEME_JS)
    if expect_light:
        assert theme is not None, f"{path}: page defines no --text-head; skin never loaded"
        assert theme["luma"] < 0.5, (
            f"{path}: expected a LIGHT page skin (dark --text-head), got {theme['value']}. "
            "This case no longer reproduces the leak it was written for."
        )


@pytest.mark.parametrize("path,expect_light", PAGES, ids=[p for p, _ in PAGES])
def test_help_chat_panel_text_is_readable_on_every_skin(page, live_server, path, expect_light):
    base = live_server.rstrip("/")
    _open_page(page, base, path, expect_light)

    launcher = page.locator("#help-launcher")
    launcher.wait_for(state="visible")
    launcher.click()
    page.locator("#help-panel.open").wait_for(state="visible")
    page.evaluate(_INJECT_CHAT_JS)
    _settle(page)

    _assert_readable(page.evaluate(_SWEEP_JS), path, "help-chat")


@pytest.mark.parametrize("path,expect_light", PAGES, ids=[p for p, _ in PAGES])
def test_help_audit_panel_text_is_readable_on_every_skin(page, live_server, path, expect_light):
    base = live_server.rstrip("/")
    _open_page(page, base, path, expect_light)

    # The launcher must exist before helpAuditOpen() is callable (help_audit.js
    # bails on logged-out pages by looking for the chat launcher).
    page.locator("#help-launcher").wait_for(state="attached")
    page.evaluate(_OPEN_AUDIT_JS)
    page.locator("#help-audit-panel.open").wait_for(state="visible")
    page.locator(".audit-section-row").first.wait_for(state="visible")

    # Expand a section (reveals the line table), then a matched line (reveals
    # the formula block), then right-click for the context menu — all three are
    # separate paint surfaces with their own colours.
    #
    # renderReport sorts sections by abs(delta) desc, so the FIRST row is not
    # the one carrying line items. Target the section that actually holds an
    # expandable line rather than relying on that ordering.
    section = page.locator(".audit-section:has(.audit-line-expandable)").first
    section.locator(".audit-section-row").click()
    section.locator(".audit-line-expandable").first.click()
    page.locator(".audit-formula-block").first.wait_for(state="visible")
    section.locator(".audit-section-row").click(button="right")
    page.locator(".audit-ctxmenu").wait_for(state="visible")
    _settle(page)

    _assert_readable(page.evaluate(_SWEEP_JS), path, "help-audit")
