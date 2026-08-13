"""v1.46 — help_chat.css must stay theme-self-contained.

The panel paints its own dark skin on every page. When it read page-level theme
variables (``--text-head``, ``--text-dim``, ``--bg-input``, ``--blue``,
``--accent`` …) the light MES/admin skins from v1.40.1 leaked in and rendered
assistant replies dark-on-dark.

``tests/journeys/test_help_chat_contrast_journey.py`` proves the *pixels* are
readable, but the journey suite is excluded from the default CI run
(``pytest --ignore=tests/journeys``). This is the cheap always-on guard on the
same invariant: every custom property the panel consumes must be one it defines
itself.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_CSS = Path(__file__).resolve().parents[1] / "app" / "static" / "css" / "help_chat.css"

_VAR_REF = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
_VAR_DEF = re.compile(r"^\s*(--[A-Za-z0-9_-]+)\s*:", re.MULTILINE)

# The launcher is a sibling of the panel, so the tokens are declared on both.
_TOKEN_HOSTS = "#help-launcher,\n#help-panel {"


@pytest.fixture(scope="module")
def css() -> str:
    return _CSS.read_text(encoding="utf-8")


def test_panel_consumes_only_its_own_tokens(css: str) -> None:
    """No var() in help_chat.css may reach for a page-level theme variable."""
    referenced = set(_VAR_REF.findall(css))
    assert referenced, "no var() references found — did the file move?"
    leaked = sorted(v for v in referenced if not v.startswith("--help-"))
    assert not leaked, (
        "help_chat.css reads page-level theme variable(s) "
        f"{leaked} — these resolve DARK on the light MES/admin skins and make the "
        "panel's text invisible (v1.46 regression). Add a --help-* token on "
        "#help-panel instead and reference that."
    )


def test_every_help_token_is_defined_by_the_panel(css: str) -> None:
    """Every --help-* token used must be declared, so nothing falls through."""
    defined = set(_VAR_DEF.findall(css))
    referenced = set(_VAR_REF.findall(css))
    missing = sorted(referenced - defined)
    assert not missing, f"--help-* token(s) referenced but never defined: {missing}"


def test_tokens_are_declared_on_the_panel_root(css: str) -> None:
    """The tokens must sit on the launcher + panel, not on :root.

    Declaring them at :root would put them back in the page's inheritance path,
    where a page stylesheet loaded later could override them — the very leak
    this fix closes.
    """
    assert _TOKEN_HOSTS in css, (
        "the --help-* tokens must be declared on '#help-launcher, #help-panel'"
    )
    root_block = re.search(r"(?:^|})\s*:root\s*{([^}]*)}", css)
    assert root_block is None, (
        "help_chat.css must not declare a :root block — panel tokens belong on "
        f"the panel root, found: {root_block.group(1).strip() if root_block else ''}"
    )
