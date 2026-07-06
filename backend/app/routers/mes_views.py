"""Icecold Bodies MES skin fork — Work Order v4.7.

Serves MES-skinned copies of the Dashboard and Cost Calculator at /mes/*
URLs so the React MES mockup iframe can embed them without affecting how the
live app renders at / and /calculator (which must stay bit-for-bit pristine,
dark-Icecold styling, per the user's regression report).

`/mes/dashboard` still renders the thin `dashboard_mes.html` wrapper; the calculator
routes now render the live `calculator.html` / `calculator2.html` directly — base.html
applies the MES light skin off the `/mes/` request path (or a `?skin=mes` query param),
so no per-page wrapper is needed and every admin page reached from the sidebar skins too
(v1.40.1).
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db, TrailerType
from ..deps import get_current_user
from ..templates_config import templates
from .dashboard import build_dashboard_context

router = APIRouter(prefix="/mes", tags=["mes-views"])


def _login_redirect(request: Request) -> RedirectResponse:
    """v1.40.2 — bounce to /login carrying next=<this page incl. query>. These routes are
    EMBEDDED in the SPA's costing iframe; a bare /login redirect meant a post-login fall
    through to the /mes-app/ default — i.e. the full MES app rendering INSIDE its own
    iframe, recursively ("3 browsers in one", 6 Jul demo). next= returns the frame here."""
    nxt = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(url=f"/login?next={quote(nxt, safe='/')}")


@router.get("/dashboard", response_class=HTMLResponse)
async def mes_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _login_redirect(request)
    ctx = build_dashboard_context(request, db, user)
    return templates.TemplateResponse("dashboard_mes.html", ctx)


@router.get("/calculator", response_class=HTMLResponse)
async def mes_calculator(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return _login_redirect(request)
    trailers = db.query(TrailerType).filter_by(is_active=True).order_by(TrailerType.name).all()
    # v1.40.1 — render the live template directly; base.html applies the MES light skin because the
    # request path starts with /mes/ (no wrapper template needed).
    return templates.TemplateResponse("calculator.html", {
        "request": request, "user": user, "trailers": trailers,
    })


@router.get("/calculator2", response_class=HTMLResponse)
async def mes_calculator2(request: Request, db: Session = Depends(get_db)):
    # v1.40.1 — MES-skinned Cost Calculator 2 (base.html skins it off the /mes/ path).
    user = get_current_user(request, db)
    if not user:
        return _login_redirect(request)
    trailers = db.query(TrailerType).filter_by(is_active=True).order_by(TrailerType.name).all()
    return templates.TemplateResponse("calculator2.html", {
        "request": request, "user": user, "trailers": trailers,
    })
