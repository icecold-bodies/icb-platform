"""v1.46 — the help-assistant panels must stay theme-self-contained.

Both panels paint their own dark skin on every page. When they read page-level
theme variables (``--text-head``, ``--text-dim``, ``--bg-input``, ``--border``,
``--blue``, ``--accent`` …) the light MES/admin skins from v1.40.1 leaked in:

* ``help_chat.css`` — ``.help-msg-assistant`` rendered dark-on-dark, so
  assistant replies were invisible.
* ``help_audit.css`` — worse, because the panel root sets ``color``, so every
  element that declares no colour of its own inherited near-black onto the
  dark surface.

``tests/journeys/test_help_panels_contrast_journey.py`` proves the *pixels* are
readable, but the journey suite is excluded from the default CI run
(``pytest --ignore=tests/journeys``). This is the cheap always-on guard on the
same invariant: every custom property a panel consumes must be one it defines
itself, in its stylesheet AND in any inline style its JS writes.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_STATIC = Path(__file__).resolve().parents[1] / "app" / "static"

_VAR_REF = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
_VAR_DEF = re.compile(r"^\s*(--[A-Za-z0-9_-]+)\s*:", re.MULTILINE)
# Comments explain the rule by quoting the old declarations, e.g. "was
# `color: var(--text)`" — prose is not cascade, so strip it before matching or
# the guard fails on its own documentation.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# (css file, companion js, token prefix, selector the tokens must be declared on)
PANELS = [
    ("css/help_chat.css", "js/help_chat.js", "--help-",
     "#help-launcher,\n#help-panel {"),
    ("css/help_audit.css", "js/help_audit.js", "--audit-",
     "#help-audit-panel,\n.audit-ctxmenu {"),
]
IDS = [p[0].split("/")[-1] for p in PANELS]


def _read(rel: str) -> str:
    """Source with block comments stripped — only live declarations are cascade."""
    return _BLOCK_COMMENT.sub(" ", (_STATIC / rel).read_text(encoding="utf-8"))


def _read_raw(rel: str) -> str:
    return (_STATIC / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("css_rel,js_rel,prefix,hosts", PANELS, ids=IDS)
def test_panel_consumes_only_its_own_tokens(css_rel, js_rel, prefix, hosts) -> None:
    """No var() in the panel's CSS may reach for a page-level theme variable."""
    css = _read(css_rel)
    referenced = set(_VAR_REF.findall(css))
    assert referenced, f"no var() references found in {css_rel} — did it move?"
    leaked = sorted(v for v in referenced if not v.startswith(prefix))
    assert not leaked, (
        f"{css_rel} reads page-level theme variable(s) {leaked} — these resolve "
        "DARK on the light MES/admin skins and make the panel's text invisible "
        f"(v1.46 regression). Add a {prefix}* token on the panel root instead "
        "and reference that."
    )


@pytest.mark.parametrize("css_rel,js_rel,prefix,hosts", PANELS, ids=IDS)
def test_inline_styles_use_only_panel_tokens(css_rel, js_rel, prefix, hosts) -> None:
    """The JS writes some style="" strings — they leak just as easily."""
    js = _read(js_rel)
    leaked = sorted({v for v in _VAR_REF.findall(js) if not v.startswith(prefix)})
    assert not leaked, (
        f"{js_rel} writes inline style(s) referencing page-level variable(s) "
        f"{leaked}. A colour is no safer in a style attribute than in the "
        "stylesheet — use the panel's own tokens."
    )


@pytest.mark.parametrize("css_rel,js_rel,prefix,hosts", PANELS, ids=IDS)
def test_every_token_is_defined_by_the_panel(css_rel, js_rel, prefix, hosts) -> None:
    """Every token used must be declared, so nothing silently falls through."""
    css = _read(css_rel)
    defined = set(_VAR_DEF.findall(css))
    referenced = set(_VAR_REF.findall(css)) | set(_VAR_REF.findall(_read(js_rel)))
    missing = sorted(v for v in referenced - defined if v.startswith(prefix))
    assert not missing, f"{prefix}* token(s) referenced but never defined: {missing}"


@pytest.mark.parametrize("css_rel,js_rel,prefix,hosts", PANELS, ids=IDS)
def test_tokens_are_declared_on_the_panel_root(css_rel, js_rel, prefix, hosts) -> None:
    """The tokens must sit on the panel's own root(s), not on :root.

    Declaring them at :root would put them back in the page's inheritance path,
    where a page stylesheet loaded later could override them — the very leak
    this fix closes.
    """
    css = _read_raw(css_rel)
    assert hosts in css, (
        f"{css_rel}: the {prefix}* tokens must be declared on "
        f"{hosts.rstrip(' {')!r}"
    )
    root_block = re.search(r"(?:^|})\s*:root\s*{([^}]*)}", css)
    assert root_block is None, (
        f"{css_rel} must not declare a :root block — panel tokens belong on the "
        f"panel root, found: {root_block.group(1).strip() if root_block else ''}"
    )
