"""v1.50 — the show/hide password toggle (Michael, 22 Aug).

Michael's report: on the sign-in screen a mistyped password is invisible and the
only feedback is a failed login. The fix injects the standard eye control inside
every ``input[type="password"]`` on the page — the four fields on ``login.html``
(sign-in plus the three on the change-password form) and the two on
``admin_manage_users.html`` — from one helper, ``password_toggle.js``.

Written against the MECHANISM (a page sweep), not against a hand-listed set of
fields, so a password field added anywhere in future is covered here too: the
counts below are asserted as "every password input on the page has a toggle",
not as literal sixes.

What is pinned, and why each one:

* **type flips both ways.** password -> text -> password. The one-way half is
  the feature; the way back is what stops a password being left on screen.
* **aria-pressed / aria-label flip.** A screen reader must be told which state
  the field is in, and the icon alone does not say it.
* **the toggle never submits.** It is inside a ``<form method="post">``; a
  default-type ``<button>`` would submit it, and the user would be bounced to a
  failed login by the act of trying to read what they typed.
* **nothing but ``type`` is touched.** name / autocomplete / required /
  minlength / id are compared before and after a toggle. Browser autofill and
  password managers key off exactly these, and the WO makes keeping them working
  a hard requirement.
* **never persisted.** A reload after revealing must come back masked, and
  neither localStorage nor sessionStorage may hold anything about it.
* **CONTRAST on BOTH skins.** The sign-in card is dark and the admin page is
  light (``theme-mes.css``, v1.40.1). The toggle takes its colour from the
  field's own computed colour rather than from a page-level theme variable —
  consuming ``--text`` / ``--text-dim`` here is precisely the v1.46 help-panel
  invisible-text defect, which shipped twice. The check is generic (computed
  icon colour vs the composited background behind it), so any future theme leak
  into this control goes red whatever colour it lands on.
"""
from __future__ import annotations

import pytest

# Deliberately just under WCAG AA for non-text/UI (3.0) — a real theme leak
# lands near 1.1:1, so this separates the two with a wide margin. The current
# implementation measures ~5:1 on dark and ~4:1 on light.
CONTRAST_FLOOR = 3.0

# Attributes password managers and browser autofill key off. None may change.
PRESERVED = ("name", "id", "autocomplete", "required", "minlength", "placeholder")


_TOGGLE_STATE_JS = """
(sel) => {
  const input = document.querySelector(sel);
  const btn = input.closest('.pwd-reveal-wrap').querySelector('.pwd-reveal-btn');
  return {
    type: input.getAttribute('type'),
    pressed: btn.getAttribute('aria-pressed'),
    label: btn.getAttribute('aria-label'),
    btnType: btn.getAttribute('type'),
  };
}
"""

# Every password/revealed field on the page, with the attributes that must
# survive a toggle untouched.
_FIELDS_JS = """
() => {
  const wraps = [...document.querySelectorAll('.pwd-reveal-wrap')];
  return wraps.map(w => {
    const i = w.querySelector('input');
    const b = w.querySelector('.pwd-reveal-btn');
    const attrs = {};
    for (const a of ['name', 'id', 'autocomplete', 'required', 'minlength', 'placeholder']) {
      attrs[a] = i.hasAttribute(a) ? i.getAttribute(a) : null;
    }
    return { type: i.getAttribute('type'), attrs, hasBtn: !!b };
  });
}
"""

# Password inputs the sweep did NOT reach — must always be empty.
_UNWIRED_JS = """
() => [...document.querySelectorAll('input[type="password"]')]
        .filter(i => !i.closest('.pwd-reveal-wrap'))
        .map(i => i.name || i.id || '(anonymous)')
"""

# Computed icon colour vs the background composited behind it. Mirrors the
# sweep in test_help_panels_contrast_journey.py — same WCAG 2.x maths, scoped to
# this control.
_CONTRAST_JS = """
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
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
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
  return [...document.querySelectorAll('.pwd-reveal-btn')].map(btn => {
    const input = btn.closest('.pwd-reveal-wrap').querySelector('input');
    const box = btn.getBoundingClientRect();
    const cs = getComputedStyle(btn);
    const fg = parse(cs.color);
    // The icon is a stroked SVG inheriting currentColor from the button, so the
    // button's own computed colour IS what is painted.
    const bg = effectiveBg(btn);
    return {
      field: input.name || input.id || '(anonymous)',
      color: cs.color,
      bg: bg.indeterminate ? '(gradient)'
        : 'rgb(' + [bg.r, bg.g, bg.b].map(Math.round).join(', ') + ')',
      indeterminate: !!bg.indeterminate,
      ratio: bg.indeterminate ? null : Math.round(ratio(over(fg, bg), bg) * 100) / 100,
      visible: cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0',
      width: Math.round(box.width),
      height: Math.round(box.height),
      // Guards the "icon must sit INSIDE the field" layout requirement: the
      // button's box has to be within the input's box.
      insideField: (() => {
        const ib = input.getBoundingClientRect();
        return box.left >= ib.left - 1 && box.right <= ib.right + 1
            && box.top >= ib.top - 1 && box.bottom <= ib.bottom + 1;
      })(),
    };
  });
}
"""

_PAGE_IS_LIGHT_JS = """
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
  // Dark heading text => light page.
  return { value: v, luma: (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 };
}
"""

_STORAGE_JS = """
() => ({
  local: Object.keys(localStorage),
  session: Object.keys(sessionStorage),
})
"""


def _btn_for(page, selector: str):
    return page.locator(f"{selector} + .pwd-reveal-btn")


def _open_login(page, base: str):
    page.goto(f"{base}/login")
    page.locator("input[name='password']").wait_for(state="visible")
    # The helper wires up on DOMContentLoaded; the control must exist by the
    # time the field is visible.
    page.locator("[data-testid='password-reveal']").first.wait_for(state="attached")


def _open_login_change_form(page, base: str):
    """The change-password form on the same template — three more fields.

    It is rendered ``display:none`` behind the "Change password" link, so it has
    to be revealed before its toggles can be clicked or measured laid-out.
    """
    _open_login(page, base)
    page.click("#show-change-link")
    page.locator("input[name='new_password']").wait_for(state="visible")


def _open_admin_users(page, base: str):
    """Admin User Setup under the LIGHT MES skin — the second theme under test.

    The password fields live in modals, so the New User modal is opened: a
    display:none control has no laid-out box and would make the layout and
    contrast checks vacuous.
    """
    resp = page.request.post(f"{base}/api/mes/autologin", headers={"Origin": base})
    assert resp.ok, f"admin autologin failed: HTTP {resp.status}"
    page.goto(f"{base}/admin/users?skin=mes")
    page.locator("#new-user-password").wait_for(state="attached")
    page.click("button:has-text('+ New User')")
    page.locator("#new-user-password").wait_for(state="visible")


# ── The core behaviour, on the field Michael actually reported ───────────────

def test_signin_password_reveals_and_remasks(page, live_server):
    base = live_server.rstrip("/")
    _open_login(page, base)

    sel = "input[name='password']"
    page.fill(sel, "Wr0ngP@ssword")

    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "password", (
        "the sign-in field must be MASKED on load"
    )

    btn = _btn_for(page, sel)
    btn.click()
    after_show = page.evaluate(_TOGGLE_STATE_JS, sel)
    assert after_show["type"] == "text", "clicking the eye must reveal the password"
    assert after_show["pressed"] == "true"
    assert after_show["label"] == "Hide password"

    btn.click()
    after_hide = page.evaluate(_TOGGLE_STATE_JS, sel)
    assert after_hide["type"] == "password", "a second click must re-mask"
    assert after_hide["pressed"] == "false"
    assert after_hide["label"] == "Show password"

    # The typed value is untouched throughout — revealing must not clear the
    # field, which would be worse than the bug it fixes.
    assert page.input_value(sel) == "Wr0ngP@ssword"


def test_toggle_does_not_submit_the_form(page, live_server):
    """A default-type <button> inside the sign-in form would POST /login.

    The user would be signed out to a failed-login page by the act of trying to
    read what they typed — so this is pinned separately from the type flip.
    """
    base = live_server.rstrip("/")
    _open_login(page, base)

    sel = "input[name='password']"
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["btnType"] == "button"

    page.fill("input[name='username']", "admin")
    page.fill(sel, "definitely-not-the-password")
    before = page.url

    _btn_for(page, sel).click()
    page.wait_for_timeout(400)          # a submit would have navigated by now

    assert page.url == before, f"the toggle navigated: {before} -> {page.url}"
    assert page.locator("#login-form").count() == 1, "still on the sign-in page"
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "text"


def test_reveal_is_never_persisted(page, live_server):
    """Defaults to masked on EVERY load — no localStorage, cookie or query param."""
    base = live_server.rstrip("/")
    _open_login(page, base)

    sel = "input[name='password']"
    _btn_for(page, sel).click()
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "text"

    storage = page.evaluate(_STORAGE_JS)
    leaked = [k for k in storage["local"] + storage["session"]
              if "pwd" in k.lower() or "reveal" in k.lower() or "password" in k.lower()]
    assert not leaked, f"the revealed state was persisted: {leaked}"

    page.reload()
    page.locator(sel).wait_for(state="visible")
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "password", (
        "a page load must always come back MASKED"
    )
    assert "reveal" not in page.url and "show_password" not in page.url


def test_submit_remasks_the_field(page, live_server):
    """A failed login re-renders the page; the password must not be left on screen.

    Belt and braces — the server re-renders login.html fresh, so the masked
    state also follows from the load. This pins the submit-time re-mask itself
    so a future single-page variant of this form cannot regress it silently.
    """
    base = live_server.rstrip("/")
    _open_login(page, base)

    sel = "input[name='password']"
    page.fill("input[name='username']", "no-such-user-v150")
    page.fill(sel, "whatever")
    _btn_for(page, sel).click()
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "text"

    page.evaluate("() => document.getElementById('login-form').requestSubmit()")
    page.locator("input[name='password']").wait_for(state="visible")
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "password"


# ── Sweep: every password field on both templates, not just the reported one ──

@pytest.mark.parametrize("opener,expected_min", [
    (_open_login, 4),          # sign-in + current/new/confirm on the change form
    (_open_admin_users, 2),    # New User + Edit User modals
], ids=["login", "admin-users"])
def test_every_password_field_on_the_page_gets_a_toggle(page, live_server, opener, expected_min):
    base = live_server.rstrip("/")
    opener(page, base)

    unwired = page.evaluate(_UNWIRED_JS)
    assert not unwired, f"password fields the sweep missed: {unwired}"

    fields = page.evaluate(_FIELDS_JS)
    assert len(fields) >= expected_min, (
        f"expected at least {expected_min} wired password fields, got {len(fields)}"
    )
    assert all(f["hasBtn"] for f in fields), "a wired field is missing its button"
    assert all(f["type"] == "password" for f in fields), (
        "every field must start masked: " + repr([f["type"] for f in fields])
    )


@pytest.mark.parametrize("opener,selector", [
    (_open_login_change_form, "input[name='new_password']"),
    (_open_admin_users, "#new-user-password"),
], ids=["login-change-form", "admin-new-user"])
def test_only_the_type_attribute_changes(page, live_server, opener, selector):
    """Password managers and autofill key off name/autocomplete/required/minlength."""
    base = live_server.rstrip("/")
    opener(page, base)

    read = ("(args) => { const i = document.querySelector(args.sel); const o = {};"
            " for (const a of args.attrs) o[a] = i.hasAttribute(a) ? i.getAttribute(a) : null;"
            " return o; }")
    before = page.evaluate(read, {"sel": selector, "attrs": list(PRESERVED)})

    _btn_for(page, selector).click()
    assert page.evaluate(_TOGGLE_STATE_JS, selector)["type"] == "text"
    assert page.evaluate(read, {"sel": selector, "attrs": list(PRESERVED)}) == before, (
        "the toggle altered an attribute other than `type`"
    )

    _btn_for(page, selector).click()
    assert page.evaluate(read, {"sel": selector, "attrs": list(PRESERVED)}) == before


def test_toggle_is_keyboard_operable(page, live_server):
    """Tab from the field reaches the button; Enter activates it."""
    base = live_server.rstrip("/")
    _open_login(page, base)

    sel = "input[name='password']"
    page.focus(sel)
    page.keyboard.press("Tab")

    focused = page.evaluate("() => (document.activeElement.className || '').toString()")
    assert "pwd-reveal-btn" in focused, f"Tab did not reach the toggle (landed on {focused!r})"

    page.keyboard.press("Enter")
    assert page.evaluate(_TOGGLE_STATE_JS, sel)["type"] == "text"

    # A visible focus ring, drawn in the control's own colour so it shows on
    # either skin.
    outline = page.evaluate(
        "() => { const cs = getComputedStyle(document.querySelector('.pwd-reveal-btn'));"
        " return { style: cs.outlineStyle, width: cs.outlineWidth }; }"
    )
    assert outline["style"] != "none" and outline["width"] not in ("0px", ""), (
        f"no visible focus ring: {outline}"
    )


# ── Theme safety: legible on the DARK sign-in card AND the LIGHT admin page ──

@pytest.mark.parametrize("opener,expect_light", [
    (_open_login, False),        # standalone dark sign-in card
    (_open_admin_users, True),   # MES light skin
], ids=["dark-login", "light-admin"])
def test_toggle_is_legible_on_both_skins(page, live_server, opener, expect_light):
    """Generic contrast check — any future theme leak into this control goes red.

    Not a colour assertion: it measures the computed icon colour against the
    composited background behind it, so it holds whatever palette a future skin
    brings.
    """
    base = live_server.rstrip("/")
    opener(page, base)

    if expect_light:
        theme = page.evaluate(_PAGE_IS_LIGHT_JS)
        assert theme is not None, "page defines no --text-head; the skin never loaded"
        assert theme["luma"] < 0.5, (
            f"expected a LIGHT skin (dark --text-head), got {theme['value']} — "
            "this case no longer covers the light half of the contract."
        )

    rows = page.evaluate(_CONTRAST_JS)
    assert rows, "no toggles found to measure"

    measured = [r for r in rows if not r["indeterminate"]]
    assert measured, (
        "every toggle became gradient-backed — the check is no longer proving "
        "anything: " + repr(rows)
    )

    too_low = [r for r in measured if r["ratio"] < CONTRAST_FLOOR]
    assert not too_low, (
        f"the reveal icon is unreadable (< {CONTRAST_FLOOR}:1) — it is taking a "
        f"page-level theme colour again:\n"
        + "\n".join(f"  {r['field']:<20} {r['ratio']:>6}:1  "
                    f"{r['color']} on {r['bg']}" for r in too_low)
    )


@pytest.mark.parametrize("opener", [_open_login, _open_admin_users],
                         ids=["login", "admin-users"])
def test_icon_sits_inside_the_field(page, live_server, opener):
    """Right-aligned INSIDE the input, so the card layout is unchanged."""
    base = live_server.rstrip("/")
    opener(page, base)

    # Only measure fields that are actually laid out — the admin modals are
    # display:none until opened, and a zero box says nothing.
    rows = [r for r in page.evaluate(_CONTRAST_JS) if r["width"] and r["height"]]
    assert rows, "no laid-out toggles to measure"
    outside = [r["field"] for r in rows if not r["insideField"]]
    assert not outside, f"the toggle escaped its field (layout shift): {outside}"
