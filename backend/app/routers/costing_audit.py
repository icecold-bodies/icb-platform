"""Admin -> Costing audit (v1.59): run the Excel <-> MES costing audit from the MES.

    GET  /admin/costing-audit                              the page (Jinja, admin group)
    GET  /api/admin/costing-audit/overview                 environment, accepted list, golden per pack
    POST /api/admin/costing-audit/runs      {pack}         202 {id} at once | 409 already running
    GET  /api/admin/costing-audit/runs                     history, newest first
    GET  /api/admin/costing-audit/runs/{id}                status + progress + counts (the page polls this)
    GET  /api/admin/costing-audit/runs/{id}/changes        changed since the previous run (same pack + env)
    GET  /api/admin/costing-audit/runs/{id}/report         ?format=html|csv [&download=1]

Every route is gated on the admin.costing_audit permission IN CODE (403 for anyone
without it) — hiding the menu entry is display only. Nothing here writes pricing
data; the run itself lives in services/costing_audit_runs.

Every response is Cache-Control: no-store — the report routes carry no file
extension and are never cached (Cloudflare caches by extension; see #173).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..database import User, get_db
from ..deps import get_current_user, require_perm, user_can
from ..services import costing_audit_runs as svc
from ..templates_config import templates

router = APIRouter()

PERM = "admin.costing_audit"
NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache"}


def _json(payload, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=NO_STORE)


def _run_or_404(db: Session, run_id: int):
    r = svc.get_run(db, run_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"no costing audit run {run_id}")
    return r


@router.get("/admin/costing-audit", response_class=HTMLResponse)
async def admin_costing_audit(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if not user_can(user, PERM, db):
        raise HTTPException(status_code=403, detail="Not authorized")
    resp = templates.TemplateResponse("admin_costing_audit.html", {
        "request": request, "user": user,
        "overview": svc.overview(),
        "pack_choices": svc.PACK_CHOICES,
    })
    resp.headers.update(NO_STORE)
    return resp


@router.get("/api/admin/costing-audit/overview")
async def api_overview(user: User = Depends(require_perm(PERM))):
    return _json(svc.overview())


@router.post("/api/admin/costing-audit/runs")
async def api_start_run(payload: dict, user: User = Depends(require_perm(PERM))):
    pack = str((payload or {}).get("pack") or "")
    try:
        run_id = svc.start_run(pack, user)
    except svc.UnknownPack as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except svc.AlreadyRunning as exc:
        return _json({"detail": str(exc)}, status_code=409)
    return _json({"id": run_id}, status_code=202)


@router.get("/api/admin/costing-audit/runs")
async def api_list_runs(user: User = Depends(require_perm(PERM)), db: Session = Depends(get_db)):
    return _json({"runs": svc.list_runs(db)})


@router.get("/api/admin/costing-audit/runs/{run_id}")
async def api_get_run(run_id: int, user: User = Depends(require_perm(PERM)), db: Session = Depends(get_db)):
    return _json(svc.summary(_run_or_404(db, run_id)))


@router.get("/api/admin/costing-audit/runs/{run_id}/changes")
async def api_run_changes(run_id: int, user: User = Depends(require_perm(PERM)), db: Session = Depends(get_db)):
    return _json(svc.changes_since_previous(db, _run_or_404(db, run_id)))


@router.get("/api/admin/costing-audit/runs/{run_id}/report")
async def api_run_report(run_id: int, format: str = "html", download: int = 0,
                         user: User = Depends(require_perm(PERM)), db: Session = Depends(get_db)):
    r = _run_or_404(db, run_id)
    if not r.report_json_gz:
        raise HTTPException(status_code=409, detail=f"run {run_id} has no report ({r.status})")
    stamp = r.started_at.strftime("%Y%m%d-%H%M") if r.started_at else str(run_id)
    stem = f"costing_audit_{r.pack}_{r.environment}_{stamp}_run{r.id}"
    headers = dict(NO_STORE)
    if format == "csv":
        headers["Content-Disposition"] = f'attachment; filename="{stem}.csv"'
        return Response(svc.render_csv(r), media_type="text/csv; charset=utf-8", headers=headers)
    if format != "html":
        raise HTTPException(status_code=400, detail="format must be html or csv")
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{stem}.html"'
    return HTMLResponse(svc.render_html(r), headers=headers)
