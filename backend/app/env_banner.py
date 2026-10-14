"""RT6 (RT6_DISPATCH default 6, RT6_RULING_1 Q6) — the "TEST SERVER" banner.

Every HTML page served by a server that is not POSITIVELY identified as prod carries a fixed amber bar
"TEST SERVER — <host:port> — not prod", and its tab title starts with "[TEST] ". Three pastes in two days landed on
the wrong server; this makes the server say where it is before anyone clicks.

ONE key decides it: settings.ICB_ENVIRONMENT. Only exactly "prod" (trimmed, any case) turns the banner off —
unset, "dev", "mirror", a typo: all show it. Prod sets the key in /etc/icb/backend.env (RT6 release kit, merge).
The admin dashboard's PROD/DEV badge and /health/version read the same key (environment_name / is_prod).

One pure-ASGI middleware, registered INSIDE GZip so it sees the page uncompressed:
  - text/html responses only (every Jinja page, the login page, error pages, the SPA's index.html);
  - not for a page loaded into an iframe (Sec-Fetch-Dest: iframe — the MES SPA embeds /mes/calculator: one bar,
    not two);
  - the bar ignores the pointer (pointer-events: none), so it never takes a click from the page under it;
  - the host shown is the request's own Host header — the address the user actually typed.
"""
from __future__ import annotations

import html
import re

from .config import settings

BANNER_ID = "icb-test-banner"
_TITLE = re.compile(rb"<title>", re.I)
_BODY = re.compile(rb"<body[^>]*>", re.I)


def environment_name() -> str:
    """The server's declared environment, lower-cased; '' when unset."""
    return (getattr(settings, "ICB_ENVIRONMENT", "") or "").strip().lower()


def is_prod() -> bool:
    """True only when the server is POSITIVELY declared prod."""
    return environment_name() == "prod"


def banner_html(host: str) -> bytes:
    text = f"TEST SERVER — {host or '?'} — not prod"
    return (f'<div id="{BANNER_ID}" role="status" aria-live="polite" data-environment="{html.escape(environment_name() or "unset")}" '
            'style="position:fixed;top:0;left:0;right:0;z-index:2147483647;pointer-events:none;'
            'background:#F59E0B;color:#111827;font:700 11px/18px system-ui,-apple-system,Segoe UI,sans-serif;'
            'letter-spacing:.06em;text-align:center;height:18px;box-shadow:0 1px 2px rgba(0,0,0,.25)">'
            f"{html.escape(text)}</div>").encode("utf-8")


def inject(body: bytes, host: str) -> bytes:
    """The page with the bar right after <body…> and '[TEST] ' at the head of its <title>. A page without a <body>
    tag is left as it is (a fragment); a title is prefixed once."""
    m = _BODY.search(body)
    if not m:
        return body
    body = body[:m.end()] + banner_html(host) + body[m.end():]
    if b"<title>[TEST] " not in body:
        body = _TITLE.sub(b"<title>[TEST] ", body, count=1)
    return body


class EnvBanner:
    """ASGI middleware: a no-op on prod; elsewhere it injects the bar into text/html responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or is_prod():
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        if headers.get("sec-fetch-dest") == "iframe":
            await self.app(scope, receive, send)
            return
        host = headers.get("host", "")
        start: dict = {}
        chunks: list[bytes] = []
        passthrough = False

        async def _send(message):
            nonlocal passthrough
            if message["type"] == "http.response.start":
                hdrs = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in message.get("headers") or []}
                ctype = hdrs.get("content-type", "")
                if not ctype.startswith("text/html") or "content-encoding" in hdrs:
                    passthrough = True
                    await send(message)
                    return
                start.update(message)
                return
            if message["type"] == "http.response.body" and not passthrough:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = inject(b"".join(chunks), host)
                hdrs = [(k, v) for k, v in start.get("headers") or [] if k.lower() != b"content-length"]
                hdrs.append((b"content-length", str(len(body)).encode("latin-1")))
                await send({**start, "headers": hdrs})
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, _send)
