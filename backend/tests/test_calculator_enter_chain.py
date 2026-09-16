"""v1.55 — Enter walks to the next parameter on the costing calculator.

Michael (16 Sep): "when the user has changed or typed in a parameter such as length,
width, height, margin or ratio and hits the enter button the app will auto move to the
next text box … similar to excel".

The behaviour itself is proven in a real browser by
tests/journeys/test_enter_next_field_journey.py. This module pins the two things a
journey cannot see cheaply:

  * the CHAIN still names controls that exist in calculator.html (a renamed id would
    silently drop a box out of the walk, with nothing failing);
  * the WRAP and SKIP rules, by running the calculator's own `_focusNextParameter` and
    `_enterChainFields` under node against a stub DOM — including the repair-surface
    case (dimensions hidden) and the rule that Enter never wraps onto the body-type
    select.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
CALC_JS = APP / "static" / "js" / "calculator.js"
CALC_HTML = APP / "templates" / "calculator.html"


def _js_function(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth = 0
    for j in range(src.index("{", start), len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _chain_line(src: str) -> str:
    return next(l for l in src.splitlines() if l.startswith("const ENTER_CHAIN ="))


def _chain() -> list[str]:
    line = _chain_line(CALC_JS.read_text(encoding="utf-8"))
    return json.loads(line.split("=", 1)[1].strip().rstrip(";").replace("'", '"'))


def _harness(src: str) -> str:
    """The calculator's OWN chain constant and functions, over a stub DOM."""
    return _HARNESS % (_chain_line(src),
                       _js_function(src, "_enterChainFields"),
                       _js_function(src, "_focusNextParameter"))


def test_every_control_in_the_chain_exists_on_the_page():
    html = CALC_HTML.read_text(encoding="utf-8")
    chain = _chain()
    assert chain[0] == "trailer-select", chain
    for el_id in chain:
        assert f'id="{el_id}"' in html, f"{el_id} is in ENTER_CHAIN but not on calculator.html"


def test_the_walk_is_armed_at_page_load():
    src = CALC_JS.read_text(encoding="utf-8")
    assert "bindEnterAdvance();" in src, "bindEnterAdvance() is never called"
    handler = _js_function(src, "bindEnterAdvance")
    assert "e.preventDefault();" in handler
    assert "_recalcNow();" in handler, "Enter must price the costing, not only move focus"
    assert "e.isComposing" in handler, "an IME mid-word must not be treated as Enter"


_HARNESS = r"""
%s
%s
%s
// A stub DOM: each id maps to a fake control. offsetParent === null means hidden,
// exactly as the browser reports a display:none box.
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = cases.map(({fields, focusOn}) => {
  const els = {};
  for (const [id, spec] of Object.entries(fields)) {
    els[id] = {
      id,
      disabled: !!spec.disabled,
      offsetParent: spec.hidden ? null : {},
      focused: false,
      selected: false,
      focus() { this.focused = true; },
      select() { this.selected = true; },
    };
  }
  global.document = { getElementById: (id) => els[id] || null };
  const target = els[focusOn];
  _focusNextParameter(target);
  const landed = Object.values(els).find(e => e.focused);
  return landed ? { id: landed.id, selected: landed.selected } : null;
});
process.stdout.write(JSON.stringify(out));
"""

ALL_VISIBLE = {i: {} for i in ("trailer-select", "f-length", "f-width", "f-height", "f-margin", "f-ratio")}
REPAIR = {**ALL_VISIBLE, "f-length": {"hidden": True}, "f-width": {"hidden": True}, "f-height": {"hidden": True}}

CASES = [
    # (what the page looks like, where Enter is pressed, where focus must land, why)
    (ALL_VISIBLE, "trailer-select", "f-length", "body type hands over to the first typed box"),
    (ALL_VISIBLE, "f-length", "f-width", "down the block, in screen order"),
    (ALL_VISIBLE, "f-width", "f-height", "down the block, in screen order"),
    (ALL_VISIBLE, "f-height", "f-margin", "dimensions hand over to the margin"),
    (ALL_VISIBLE, "f-margin", "f-ratio", "margin hands over to the ratio"),
    (ALL_VISIBLE, "f-ratio", "f-length", "the last box wraps to the first TYPED box, never the body-type select"),
    (REPAIR, "f-margin", "f-ratio", "a REPAIRS costing has no dimensions to walk"),
    (REPAIR, "f-ratio", "f-margin", "and wraps to the first box it still has"),
    ({**ALL_VISIBLE, "f-width": {"disabled": True}}, "f-length", "f-height", "a disabled box is stepped over"),
    ({**ALL_VISIBLE, "f-width": {"hidden": True}}, "f-length", "f-height", "a hidden box is stepped over"),
]


def test_the_chain_walks_wraps_and_skips_as_specified():
    node = shutil.which("node")
    assert node, "node is needed to run the calculator's own chain logic (CI sets it up)"
    src = CALC_JS.read_text(encoding="utf-8")
    harness = _harness(src)
    payload = [{"fields": fields, "focusOn": focus_on} for fields, focus_on, _want, _why in CASES]
    run = subprocess.run([node, "-e", harness], input=json.dumps(payload),
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[:2000]
    got = json.loads(run.stdout)
    for (fields, focus_on, want, why), landed in zip(CASES, got):
        assert landed is not None, f"Enter in {focus_on} moved nowhere — {why}"
        assert landed["id"] == want, f"Enter in {focus_on} landed on {landed['id']}, expected {want} — {why}"
        assert landed["selected"] is True, f"the value in {want} must be selected so typing replaces it"


def test_a_control_outside_the_chain_is_left_alone():
    node = shutil.which("node")
    assert node
    src = CALC_JS.read_text(encoding="utf-8")
    harness = _harness(src)
    payload = [{"fields": {**ALL_VISIBLE, "cust-search": {}}, "focusOn": "cust-search"}]
    run = subprocess.run([node, "-e", harness], input=json.dumps(payload),
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr[:2000]
    assert json.loads(run.stdout) == [None], "only the parameter block walks on Enter"


def test_the_bundle_tag_moved_with_the_javascript():
    """calculator.js changed, so the cache-bust tag must have moved or browsers keep the
    old file (the v1.51 double-tag lesson)."""
    html = CALC_HTML.read_text(encoding="utf-8")
    tags = [l for l in html.splitlines() if "calculator.js?v=" in l]
    assert len(tags) == 1, f"expected exactly one calculator.js tag, found {len(tags)}"
    assert "calculator.js?v=182" in tags[0], tags[0]
