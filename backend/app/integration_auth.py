"""Read-only integration bearer-token auth (v1.43 ERP enablement; ADR 0038).

External systems (first consumer: the ICB ERP, Marnus — see
docs/handoffs/ERP_MES_INTEGRATION_PACK_v1.0.md §2/§4) may read an allowlisted set
of GET endpoints with `Authorization: Bearer {token}` instead of a browser session.

Design (WO-ratified shape, adjusted post-CI to the house test-override contract):
  * Tokens live in the env key `INTEGRATION_API_TOKENS` — comma-separated
    ``token=name`` pairs (e.g. ``abc123=erp``). Empty/missing = feature off:
    every bearer-presenting request is rejected and session auth is untouched.
  * The allowlist is the OPT-IN ITSELF: an endpoint grants token access by adding
    the `@integration_readable` marker under its `@router.get(...)` (or, in the
    one legacy inline-auth case, calling `integration_identity_if_bearer` before
    `get_current_user`). Grep `@integration_readable` to enumerate the surface.
    There is no path table to drift from the routes.
  * Handlers KEEP `Depends(require_user)` — deliberately. The house rule (see
    `deps.require_perm`) is that tests override `require_user` via
    `app.dependency_overrides[require_user]`; a wrapper dependency would silently
    detach every marked route from those overrides (exactly the CI breakage that
    reshaped this module). `require_user` consults `identity_for_marked_route`
    first; the marker on `request.scope["endpoint"]` carries the opt-in.
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

from fastapi import HTTPException, Request

from .config import settings

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


def integration_readable(fn):
    """Marker for GET handlers on the integration read allowlist (Pack §4). Place
    UNDER the `@router.get(...)` line so the registered endpoint carries the mark.
    `require_user` honours it via `identity_for_marked_route`; non-GET handlers
    must never carry it (the resolver hard-ignores non-GET as a belt)."""
    fn._integration_readable = True
    return fn


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
    non-GET (belt — only GET endpoints are ever allowlisted)."""
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


def identity_for_marked_route(request: Request) -> Optional[IntegrationIdentity]:
    """`require_user`'s accept branch: an IntegrationIdentity ONLY when a Bearer
    token is presented AND the routed endpoint carries the `@integration_readable`
    mark AND the method is GET AND the token matches. In every other bearer case
    return None — the request then falls into `get_current_user`, whose
    `reject_integration_bearer` guard raises the correct 401/403."""
    presented = _presented_bearer(request)
    if presented is None:
        return None
    endpoint = request.scope.get("endpoint")
    if not getattr(endpoint, "_integration_readable", False) or request.method != "GET":
        return None
    name = _match(presented)
    if name is None:
        return None
    request.state.integration_name = name
    return IntegrationIdentity(name)


def reject_integration_bearer(request: Request) -> None:
    """Session-chokepoint guard (called first by `deps.get_current_user`): a
    bearer-presenting request must never fall through to session auth. No-op when
    no Bearer token is presented. Allowlisted endpoints resolve the token BEFORE
    get_current_user runs (`identity_for_marked_route` in require_user, or the
    inline `integration_identity_if_bearer` idiom), so reaching this with a valid
    token means the endpoint did not opt in → 403; an unmatched token → 401."""
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
