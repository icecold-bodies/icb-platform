"""v1.46 — the AI help panel must stay READABLE on every page skin.

Regression cover for the "assistant replies are invisible" defect: help_chat.css
painted the panel's own dark surface but took its *text* colours from
page-level theme variables (``--text-head``, ``--text-dim``, ``--accent`` …).
Those resolve DARK on the light MES/admin skins introduced in v1.40.1, so
``.help-msg-assistant`` rendered near-black on the near-black panel — present in
the DOM, legible only by drag-selecting it. Same class as the v1.39.8 leaks.

This test is deliberately written against the *mechanism*, not the one reported
bubble: it opens the panel, injects the full set of node shapes help_chat.js can
render, then sweeps EVERY visible text-bearing element inside the launcher and
the panel and asserts a sane WCAG contrast ratio between the computed text
colour and the composited background behind it. Any future page-theme change
that leaks into the panel — whichever element it lands on — goes red here.

Thresholds
----------
``FLOOR`` (3.0) applies to everything. It is set just under the panel's own
long-standing white-on-brand-blue chrome (#fff on #388bfd = 3.34:1, the user
bubble and the Send button), which is accepted design and not in scope. A real
theme leak lands around 1.1:1, so the floor separates the two with wide margin.
``BODY_FLOOR`` (4.5) — full WCAG AA — applies to the reading surfaces: assistant
replies, tool notes, suggestions, action buttons, the input and the header.

Selector policy: journeys normally select on ``data-testid`` only. This test is
the exception, and deliberately so — the CSS class names ARE the contract under
test here, so they are the correct handle.
"""
from __future__ import annotations

import pytest

# Pages the widget renders on. Each entry is (path, expects_light_page_theme).
# The light entries are the ones that regressed; the dark standalone app is kept
# in the sweep so a fix can't be "make it work on light, break it on dark".
PAGES = [
    ("/calculator?skin=mes", True),   # Michael's report: the costing calculator
    ("/?skin=mes", True),             # dashboard under the MES light skin
    ("/admin/customers?skin=mes", True),  # an admin page, per the WO click-through
    ("/calculator", False),           # standalone dark app — must be unchanged
]

FLOOR = 3.0
BODY_FLOOR = 4.5

# Reading surfaces held to full WCAG AA. Matched against the reported selector.
BODY_SURFACES = (
    "help-msg-assistant", "help-msg-tool", "help-msg-error", "help-suggestion",
    "help-action-btn", "help-actions-intro", "help-title", "help-subtitle",
    "help-icon-btn", "help-toggle", "help-input",
)

# Injects one of every node shape help_chat.js can build (class strings copied
# from appendMsg / appendToolNote / appendLoadingBubble / renderActions /
# renderSuggestions), so the sweep covers the whole panel and not just whatever
# a live conversation happened to produce. No network, no API key, no stubbing
# of the streaming route — this test is about paint, not about the chat.
_INJECT_JS = """
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
  // (white) is the last resort.
  const effectiveBg = (el) => {
    const stack = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; }
    }
    let base = { r: 255, g: 255, b: 255, a: 1 };
    for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base;
  };
  const label = (el) => {
    if (el.id) return '#' + el.id;
    const cls = (el.className || '').toString().trim().split(/\\s+/).filter(Boolean);
    return el.tagName.toLowerCase() + (cls.length ? '.' + cls.join('.') : '');
  };
  const roots = ['#help-launcher', '#help-panel']
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
      const bg = effectiveBg(el);
      out.push({
        selector: label(el),
        sample: own.slice(0, 40),
        color: cs.color,
        bg: 'rgb(' + [bg.r, bg.g, bg.b].map(Math.round).join(', ') + ')',
        ratio: Math.round(ratio(over(fg, bg), bg) * 100) / 100,
      });
    }
  }
  // The textarea holds no text NODE, so the loop above skips it. Its own text
  // colour and its ::placeholder pseudo-element are swept explicitly.
  const input = document.getElementById('help-input');
  if (input) {
    const ics = getComputedStyle(input);
    const ifg = parse(ics.color);
    if (ifg && ifg.a > 0) {
      const ibg = effectiveBg(input);
      out.push({
        selector: '#help-input',
        sample: 'explain this formula',
        color: ics.color,
        bg: 'rgb(' + [ibg.r, ibg.g, ibg.b].map(Math.round).join(', ') + ')',
        ratio: Math.round(ratio(over(ifg, ibg), ibg) * 100) / 100,
      });
    }
    const ph = parse(getComputedStyle(input, '::placeholder').color);
    if (ph && ph.a > 0) {
      const bg = effectiveBg(input);
      out.push({
        selector: '#help-input::placeholder',
        sample: input.getAttribute('placeholder') || '',
        color: getComputedStyle(input, '::placeholder').color,
        bg: 'rgb(' + [bg.r, bg.g, bg.b].map(Math.round).join(', ') + ')',
        ratio: Math.round(ratio(over(ph, bg), bg) * 100) / 100,
      });
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
  const m = /^#?([0-9a-f]{6})$/i.exec(v) || /rgba?\\(([^)]+)\\)/.exec(v);
  if (!v) return null;
  let r, g, b;
  if (v.startsWith('#')) {
    r = parseInt(v.slice(1, 3), 16); g = parseInt(v.slice(3, 5), 16); b = parseInt(v.slice(5, 7), 16);
  } else if (m && m[1] && m[1].includes(',')) {
    const p = m[1].split(',').map(x => parseFloat(x));
    r = p[0]; g = p[1]; b = p[2];
  } else { return null; }
  return { value: v, luma: (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 };
}
"""


def _autologin(page, base: str) -> None:
    """Mint the admin session cookie only.

    The help widget is Jinja-side (``base.html``, ``{% if user %}``), so this
    journey never touches the React shell — it just needs the cookie before
    navigating to a legacy page.
    """
    resp = page.request.post(f"{base}/api/mes/autologin", headers={"Origin": base})
    assert resp.ok, f"admin autologin failed: HTTP {resp.status}"


@pytest.mark.parametrize("path,expect_light", PAGES, ids=[p for p, _ in PAGES])
def test_help_panel_text_is_readable_on_every_skin(page, live_server, path, expect_light):
    base = live_server.rstrip("/")
    _autologin(page, base)
    page.goto(f"{base}{path}")

    launcher = page.locator("#help-launcher")
    launcher.wait_for(state="visible")

    theme = page.evaluate(_PAGE_THEME_JS)
    if expect_light:
        assert theme is not None, f"{path}: page defines no --text-head; skin never loaded"
        assert theme["luma"] < 0.5, (
            f"{path}: expected a LIGHT page skin (dark --text-head), got {theme['value']}. "
            "This case no longer reproduces the leak it was written for."
        )

    launcher.click()
    page.locator("#help-panel.open").wait_for(state="visible")
    page.evaluate(_INJECT_JS)

    rows = page.evaluate(_SWEEP_JS)
    assert len(rows) >= 12, f"{path}: swept only {len(rows)} elements — injection did not render"

    def fmt(r):
        return (f"  {r['selector']:<44} {r['ratio']:>6}:1  "
                f"text {r['color']} on {r['bg']}   “{r['sample']}”")

    too_low = [r for r in rows if r["ratio"] < FLOOR]
    assert not too_low, (
        f"{path}: help-panel text is unreadable (contrast < {FLOOR}:1) — a page theme "
        f"variable has leaked back into help_chat.css:\n" + "\n".join(fmt(r) for r in too_low)
    )

    body_low = [r for r in rows
                if r["ratio"] < BODY_FLOOR
                and any(s in r["selector"] for s in BODY_SURFACES)]
    assert not body_low, (
        f"{path}: help-panel reading surfaces below WCAG AA ({BODY_FLOOR}:1):\n"
        + "\n".join(fmt(r) for r in body_low)
    )
