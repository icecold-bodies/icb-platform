"""Read-only integration bearer-token auth (v1.43 ERP enablement; ADR 0038).

External systems (first consumer: the ICB ERP, Marnus — see
docs/handoffs/ERP_MES_INTEGRATION_PACK_v1.0.md §2/§4) may read an allowlisted set
of GET endpoints with `Authorization: Bearer {token}` instead of a browser session.

Design (WO-ratified shape):
  * Tokens live in the env key `INTEGRATION_API_TOKENS` — comma-separated
    ``token=name`` pairs (e.g. ``abc123=erp``). Empty/missing = feature off:
    every bearer-presenting request is rejected and session auth is untouched.
  * The allowlist is the OPT-IN ITSELF: an endpoint grants token access by taking
    `Depends(require_user_or_integration)` (or calling
    `integration_identity_if_bearer` in the legacy inline-auth idiom) instead of
    `Depends(require_user)`. There is no path table to drift from the routes.
  * Everything else stays session-only, enforced at the single session chokepoint:
    `deps.get_current_user` calls `reject_integration_bearer` first, so ANY route
    that resolves a session (require_user / require_admin / require_perm chains and
    every legacy inline caller) answers a bearer request with 401 (bad token) or
    403 (valid token, endpoint not in the read allowlist) — never a session.
  * A matched token resolves to a synthetic read-only IntegrationIdentity: no user
    row, no session row, no CSRF (GETs are CSRF-exempt), zero permissions
    (`user_can` consults `_perm_cache` and finds an empty frozenset — every
    permission-gated field/route denies). Requests are visible in the per-request
    log line (diagnostics.install_request_logger) tagged ``integ=<name>``.
  * Token comparison is constant-time (`secrets.compare_digest`) across ALL
    configured tokens; the presented token value is never logged or echoed.
"""
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db

# Parsed-pairs memo keyed on the raw env string, so a per-request parse is a dict
# hit and tests that monkeypatch `settings.INTEGRATION_API_TOKENS` still take effect.
_parsed: tuple[str, dict[str, str]] = ("", {})


def _token_map() -> dict[str, str]:
    """{token: integration_name} from INTEGRATION_API_TOKENS. Malformed entries
    (no '=', empty token or name) are skipped — a bad pair must never widen access."""
    global _parsed
    raw = settings.INTEGRATION_API_TOKENS or ""
    if raw == _parsed[0]:
        return _parsed[1]
    pairs: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        token, _, name = entry.partition("=")
        token, name = token.strip(), name.strip()
        if token and name:
            pairs[token] = name
    _parsed = (raw, pairs)
    return pairs


class IntegrationIdentity:
    """Synthetic read-only principal a matched token resolves to. Quacks like the
    slice of `User` the allowlisted GET handlers touch; `_perm_cache` (the cache
    `deps.user_can` consults first) is an empty frozenset so every permission check
    answers False without a DB round-trip."""

    id = None
    is_active = True
    branch_id = None
    email = None

    def __init__(self, name: str):
        self.integration_name = name
        self.username = f"integration:{name}"
        self.display_name = f"Integration: {name}"
        self.role = "integration"
        self._perm_cache = frozenset()

    def __repr__(self) -> str:  # keeps accidental log/debug output token-free
        return f"<IntegrationIdentity {self.integration_name}>"


def _presented_bearer(request: Request) -> Optional[str]:
    """The Bearer credential on the request, or None. Non-Bearer Authorization
    schemes are ignored (not this feature's claim)."""
    header = request.headers.get("authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    credential = credential.strip()
    return credential or None


def _match(presented: str) -> Optional[str]:
    """Constant-time match of the presented token against every configured pair
    (no early break — timing does not reveal which slot matched)."""
    matched: Optional[str] = None
    for token, name in _token_map().items():
        if secrets.compare_digest(presented, token):
            matched = name
    return matched


def integration_identity_if_bearer(request: Request) -> Optional[IntegrationIdentity]:
    """Allowlist-side resolver: None when no Bearer token is presented (caller
    falls through to session auth); an IntegrationIdentity when a configured token
    matches. 401 for an unmatched token, 403 if a matched token arrives on a
    non-GET (belt — only GET handlers opt in)."""
    presented = _presented_bearer(request)
    if presented is None:
        return None
    name = _match(presented)
    if name is None:
        request.state.integration_name = "invalid"
        raise HTTPException(status_code=401, detail="Invalid integration token")
    request.state.integration_name = name
    if request.method != "GET":
        raise HTTPException(
            status_code=403,
            detail="Integration tokens are read-only (GET endpoints only)")
    return IntegrationIdentity(name)


def require_user_or_integration(request: Request, db: Session = Depends(get_db)):
    """THE opt-in dependency for allowlisted GET endpoints (Pack §4): a valid
    integration token resolves to the synthetic read-only identity; no token falls
    through to the byte-identical session path (`require_user`)."""
    identity = integration_identity_if_bearer(request)
    if identity is not None:
        return identity
    from .deps import require_user
    return require_user(request, db)


def reject_integration_bearer(request: Request) -> None:
    """Session-chokepoint guard (called first by `deps.get_current_user`): a
    bearer-presenting request must never fall through to session auth. No-op when
    no Bearer token is presented. Allowlisted handlers resolve the token BEFORE
    get_current_user runs, so reaching this with a valid token means the endpoint
    did not opt in → 403; an unmatched token → 401."""
    presented = _presented_bearer(request)
    if presented is None:
        return
    name = _match(presented)
    if name is None:
        request.state.integration_name = "invalid"
        raise HTTPException(status_code=401, detail="Invalid integration token")
    request.state.integration_name = name
    raise HTTPException(
        status_code=403,
        detail="Integration token not valid for this endpoint (read-only allowlist)")
