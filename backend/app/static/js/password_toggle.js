/* ── Show / hide password toggle (v1.50, Michael 22 Aug) ─────────────────────
   Michael, 22 Aug: "on the sign-in screen the user must be able to reveal the
   password they typed" — mistyped passwords are currently invisible and the
   only feedback is a failed login.

   Written by MECHANISM, not per field. On DOMContentLoaded this sweeps the page
   for every input[type="password"] and injects the control, so the four fields
   on login.html (sign-in + the three on the change-password form) and the two
   on admin_manage_users.html are covered by one implementation — and any
   password field added anywhere in future gets the behaviour for free rather
   than depending on someone remembering to wire it up.

   Opt out with data-no-reveal on the input.

   Contract (deliberate, do not relax):
     * Always starts MASKED. The revealed state is never persisted — no
       localStorage, no cookie, no query param — so a reload always re-masks.
     * type="button", so it can never submit the form.
     * Reverts to masked on submit, so a password is not left on screen after
       sign-in or on a failed-login re-render.
     * Only the `type` attribute is touched. name / autocomplete / required /
       minlength / id are left exactly as authored, so browser autofill and
       password managers keep working as they do today.
     * Nothing about what is posted changes, and the revealed value is never
       read, logged or sent anywhere.                                          */
(function () {
  'use strict';

  var EYE =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
    '<circle cx="12" cy="12" r="3"/></svg>';

  var EYE_OFF =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"' +
    ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' +
    '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>' +
    '<path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>' +
    '<path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>' +
    '<line x1="1" y1="1" x2="23" y2="23"/></svg>';

  function parseColor(text) {
    var m = /rgba?\(([^)]+)\)/.exec(text || '');
    if (!m) return null;
    var p = m[1].split(',').map(function (v) { return parseFloat(v.trim()); });
    if (p.length < 3 || p.some(isNaN)) return null;
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }

  /* Composite the field's background over its ancestors until an opaque layer
     is reached. A field background of rgba(..., .06) is not what the eye sees. */
  function effectiveBg(el) {
    var stack = [];
    for (var n = el; n && n.nodeType === 1; n = n.parentElement) {
      var c = parseColor(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { stack.push(c); if (c.a === 1) break; }
    }
    var base = { r: 255, g: 255, b: 255, a: 1 };
    for (var i = stack.length - 1; i >= 0; i--) {
      var f = stack[i];
      base = {
        r: f.r * f.a + base.r * (1 - f.a),
        g: f.g * f.a + base.g * (1 - f.a),
        b: f.b * f.a + base.b * (1 - f.a),
        a: 1
      };
    }
    return base;
  }

  function rgb(c) {
    return 'rgb(' + [c.r, c.g, c.b].map(Math.round).join(', ') + ')';
  }

  function mix(fg, bg, weight) {
    return {
      r: fg.r * weight + bg.r * (1 - weight),
      g: fg.g * weight + bg.g * (1 - weight),
      b: fg.b * weight + bg.b * (1 - weight)
    };
  }

  /* THEME SAFETY: the icon's colours are derived from the field's OWN computed
     text colour and composited background — never from a page-level theme
     variable. The sign-in card is dark and the admin pages are light; consuming
     --text / --text-dim / --border here is exactly the v1.46 help-panel
     invisible-text defect. Whatever skin paints the field, the icon is legible
     on it by construction, because the field's own text already is. */
  function paint(btn, input) {
    var cs = getComputedStyle(input);
    var fg = parseColor(cs.color);
    var bg = effectiveBg(input);
    if (!fg || fg.a === 0) {
      // Unparseable (a keyword, a system colour): fall back to the field's own
      // colour string verbatim rather than guessing a light/dark value.
      btn.style.setProperty('--pwd-reveal-fg', cs.color || 'currentColor');
      btn.style.setProperty('--pwd-reveal-fg-strong', cs.color || 'currentColor');
      return;
    }
    var solid = {
      r: fg.r * fg.a + bg.r * (1 - fg.a),
      g: fg.g * fg.a + bg.g * (1 - fg.a),
      b: fg.b * fg.a + bg.b * (1 - fg.a)
    };
    // Softened toward the field background at rest so the icon reads as chrome
    // rather than as content; full strength on hover / keyboard focus. 72% of
    // the field's own text contrast clears WCAG AA on both current skins.
    btn.style.setProperty('--pwd-reveal-fg', rgb(mix(solid, bg, 0.72)));
    btn.style.setProperty('--pwd-reveal-fg-strong', rgb(solid));
  }

  function setState(btn, input, revealed) {
    // The ONLY attribute this feature touches.
    input.setAttribute('type', revealed ? 'text' : 'password');
    btn.setAttribute('aria-pressed', revealed ? 'true' : 'false');
    btn.setAttribute('aria-label', revealed ? 'Hide password' : 'Show password');
    btn.setAttribute('title', revealed ? 'Hide password' : 'Show password');
    btn.innerHTML = revealed ? EYE_OFF : EYE;
  }

  function enhance(input) {
    if (input.dataset.pwdReveal === '1') return;   // already wired
    if (input.hasAttribute('data-no-reveal')) return;
    input.dataset.pwdReveal = '1';

    var wrap = document.createElement('span');
    wrap.className = 'pwd-reveal-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement('button');
    btn.type = 'button';              // never submits the form
    btn.className = 'pwd-reveal-btn';
    btn.setAttribute('data-testid', 'password-reveal');
    // Keyboard reachable in the natural order — Enter/Space activate a <button>
    // natively, so no key handler of our own.
    btn.tabIndex = 0;
    setState(btn, input, false);      // masked on every page load, always
    paint(btn, input);
    wrap.appendChild(btn);

    // Do not let the press steal focus from the field: a mouse user keeps the
    // caret where they were typing, and a keyboard user keeps focus ON the
    // button so a second Enter re-masks (and so the focus ring stays visible).
    btn.addEventListener('mousedown', function (e) { e.preventDefault(); });

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var revealed = btn.getAttribute('aria-pressed') === 'true';
      setState(btn, input, !revealed);
    });

    // Re-mask on submit so the password is not left on screen after sign-in or
    // on a failed-login re-render.
    var form = input.form;
    if (form && form.dataset.pwdRevealSubmit !== '1') {
      form.dataset.pwdRevealSubmit = '1';
      form.addEventListener('submit', function () {
        var btns = form.querySelectorAll('.pwd-reveal-wrap > .pwd-reveal-btn');
        for (var i = 0; i < btns.length; i++) {
          var b = btns[i];
          var f = b.parentNode.querySelector('input');
          if (f) setState(b, f, false);
        }
      });
    }
  }

  function sweep(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var fields = scope.querySelectorAll('input[type="password"]');
    for (var i = 0; i < fields.length; i++) enhance(fields[i]);
  }

  // Exposed so a page that builds a password field after load can wire it up.
  window.passwordToggleSweep = sweep;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { sweep(document); });
  } else {
    sweep(document);
  }
})();
