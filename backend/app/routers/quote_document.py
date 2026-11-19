"""The ICB quotation document — download endpoint (v1.47 Lane D).

Its own router module rather than more of routers/exports.py: exports.py is a
1500-line file that three lanes were editing at once during v1.47, and this
needs nothing from it beyond the permission gate. Keeping it separate also keeps
D1's shell/body split visible at the routing layer — the document is its own
output, not another format of the internal costing export.

D10 is respected: this DOWNLOADS. Nothing here emails a customer.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy.orm import Session

from fastapi.responses import HTMLResponse, RedirectResponse

from ..database import CalculationRecord, get_db
from ..deps import get_current_user, require_admin, user_can
from ..services.quote_document import (PRINT_MODE_KEY,
                                       build_repair_quote_context,
                                       has_repair_quote_document,
                                       normalize_print_mode,
                                       repair_quote_filename,
                                       stored_print_mode)
from ..services.quote_document_config import (apply_edits, editable_view,
                                              get_config, save_config)
from ..services.quote_document_pdf import render_repair_quote_pdf
from ..templates_config import templates

router = APIRouter()

# v1.48 — this is the CUSTOMER quote, so it rides the same gate as the body
# Generate Quote button ("Generate customer quote PDF for a costing", granted to
# admin/full/user). It is not `export.pdf`, which covers the internal cost
# breakdown and is deliberately narrower (admin/full only).
#
# It was written "exports.pdf" through v1.47 — a key that is in no catalogue
# row, so `user_can` could only ever match it for admins, who short-circuit
# every gate. Nobody noticed because every test of this endpoint ran as admin.
_GATE = "quote.generate"


def _require_pdf_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    if not user_can(user, _GATE, db):
        raise HTTPException(status_code=403, detail=f"Permission denied: {_GATE}")
    return user


def _remember_print_mode(rec, db: Session, mode: str | None) -> None:
    """Persist the print mode this quote was last downloaded in."""
    mode = normalize_print_mode(mode)
    try:
        import json as _json
        result = _json.loads(rec.result_json) if rec.result_json else {}
        if not isinstance(result, dict):
            return
        if stored_print_mode(result) == mode and result.get(PRINT_MODE_KEY):
            return                      # already recorded — no write, no churn
        result[PRINT_MODE_KEY] = mode
        rec.result_json = _json.dumps(result)
        db.commit()
    except Exception:
        # A costing whose result_json cannot be re-serialised still gets its
        # PDF; only the memory of the choice is lost.
        db.rollback()
        logging.exception("could not store the print mode for record %s", rec.id)


@router.get("/api/calculations/{record_id}/repair-quote.pdf")
async def repair_quote_pdf(record_id: int, request: Request,
                           mode: str | None = None,
                           db: Session = Depends(get_db)):
    """The customer-facing repair quotation on the ICB letterhead.

    Only for a REPAIRS costing: the document's whole shape — repair lines, the
    type of repair, the vehicle registration — is meaningless for a body
    costing, and rendering one would produce an official-looking document full
    of blanks. A body costing gets the existing /results export instead, so this
    refuses with 409 rather than guessing.

    v1.51 — `mode` is one of quote_document.PRINT_MODES and decides how much of
    the costing the customer sees. Omitted, it is whatever this quote was last
    downloaded as, which is what makes a re-download reproduce the document
    already in the customer's inbox. An unreadable value falls back to the
    default rather than refusing: a formatting preference must never be able to
    take the quotation away.
    """
    _require_pdf_user(request, db)
    rec = db.query(CalculationRecord).filter_by(id=record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Costing not found")
    if getattr(rec, "deleted_at", None):
        # v1.49 (Michael's rule 1): a deleted repair cannot generate its quotation
        # again from the Deleted view. Same class as the exports, so a browser tab
        # gets the readable page rather than raw JSON.
        from .exports import DeletedCostingRefusal
        raise DeletedCostingRefusal(rec)
    if not has_repair_quote_document(rec):
        raise HTTPException(
            status_code=409,
            detail="The repair quotation document is only for repair costings.")

    ctx = build_repair_quote_context(
        rec, db, generated_at=datetime.now().strftime("%d %b %Y %H:%M"), mode=mode)
    pdf = render_repair_quote_pdf(ctx)

    # Remember the mode ON THE QUOTE (v1.51). A GET that writes is deliberate
    # and narrow: this is the only moment the choice exists, and it is stored
    # so the NEXT download of this quote — by anyone, from any screen —
    # reproduces the document that was sent. Written only when it actually
    # changes, only into result_json (no column, no migration), and a failure
    # here must never cost the user their PDF: the bytes are already rendered.
    _remember_print_mode(rec, db, ctx.get("print_mode"))

    # v1.50 (Lezette, 22 Aug) — {R-number} - {Customer} - {Vehicle reg}: the
    # document number now LEADS the filename, since it is the identifier the
    # sales side quotes back to a customer. Missing parts drop out cleanly.
    safe = repair_quote_filename(rec, ctx)
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        # v1.51 (26 Aug) — no-store is LOAD-BEARING, not hygiene. The URL ends
        # in ".pdf", and prod's public route (mes.icecoldgrp.online) rides a
        # Cloudflare tunnel whose zone caches BY EXTENSION and stamps a 4-hour
        # browser TTL onto responses that carry no Cache-Control. Two effects:
        #   * an AUTHENTICATED customer quotation gets parked on a public CDN
        #     edge, servable without ever reaching our auth again;
        #   * a re-download after a fix keeps returning the OLD document — the
        #     footer-overlap fix "didn't work" on prod for exactly this reason
        #     while the direct-IP route (no Cloudflare) was fine all along.
        # no-store forbids both the edge and the browser from keeping a copy;
        # private is belt-and-braces for any other intermediary.
        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"',
                 "Cache-Control": "no-store, private"},
    )


# ── admin: the document's own settings (D7/D9) ───────────────────────────────

@router.get("/admin/quote-document", response_class=HTMLResponse)
async def admin_quote_document(request: Request, db: Session = Depends(get_db)):
    """Edit the VAT rate, the branding and every block of terms.

    Its own screen, not /admin/pdf-template-builder: that builder is a visual
    layout tool bound to trailer-type BOM reports, and this config would appear
    in its list as a nonsense entry with no sensible editor. The pdf_templates
    TABLE is reused as the store; the SCREEN is not.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    cfg = get_config(db)
    return templates.TemplateResponse("admin_quote_document.html", {
        "request": request, "user": user,
        "fields": editable_view(cfg),
        "is_placeholder": bool((cfg.get("branding") or {}).get("letterhead_is_placeholder")),
    })


@router.get("/api/quote-document-config")
async def api_quote_document_config(request: Request, db: Session = Depends(get_db)):
    require_admin(request, db)
    return {"fields": editable_view(get_config(db))}


@router.put("/api/quote-document-config")
async def api_save_quote_document_config(payload: dict, request: Request,
                                         db: Session = Depends(get_db)):
    """Apply the submitted fields. Unknown keys are ignored by apply_edits, so an
    older form cannot wipe a setting it never knew about."""
    require_admin(request, db)
    cfg = apply_edits(get_config(db), payload or {})
    saved = save_config(db, cfg)
    return {"ok": True, "fields": editable_view(saved)}
