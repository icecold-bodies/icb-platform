"""The ICB quotation document — download endpoint (v1.47 Lane D).

Its own router module rather than more of routers/exports.py: exports.py is a
1500-line file that three lanes were editing at once during v1.47, and this
needs nothing from it beyond the permission gate. Keeping it separate also keeps
D1's shell/body split visible at the routing layer — the document is its own
output, not another format of the internal costing export.

D10 is respected: this DOWNLOADS. Nothing here emails a customer.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy.orm import Session

from ..database import CalculationRecord, get_db
from ..deps import get_current_user, user_can
from ..services.quote_document import build_repair_quote_context
from ..services.quote_document_pdf import render_repair_quote_pdf

router = APIRouter()

# The same gate the PDF export uses — this IS a PDF of a costing.
_GATE = "exports.pdf"


def _require_pdf_user(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    if not user_can(user, _GATE, db):
        raise HTTPException(status_code=403, detail=f"Permission denied: {_GATE}")
    return user


@router.get("/api/calculations/{record_id}/repair-quote.pdf")
async def repair_quote_pdf(record_id: int, request: Request,
                           db: Session = Depends(get_db)):
    """The customer-facing repair quotation on the ICB letterhead.

    Only for a REPAIRS costing: the document's whole shape — repair lines, the
    type of repair, the vehicle registration — is meaningless for a body
    costing, and rendering one would produce an official-looking document full
    of blanks. A body costing gets the existing /results export instead, so this
    refuses with 409 rather than guessing.
    """
    _require_pdf_user(request, db)
    rec = db.query(CalculationRecord).filter_by(id=record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Costing not found")
    if not (bool(getattr(rec, "is_repair", False)) and rec.trailer_type_id is None):
        raise HTTPException(
            status_code=409,
            detail="The repair quotation document is only for repair costings.")

    ctx = build_repair_quote_context(
        rec, db, generated_at=datetime.now().strftime("%d %b %Y %H:%M"))
    pdf = render_repair_quote_pdf(ctx)

    # The document number is the customer-facing identifier, so it names the file.
    stem = (ctx.get("document_number") or rec.quote_number or f"repair-{rec.id}")
    safe = "".join(ch for ch in str(stem) if ch not in '\\/:*?"<>|\r\n').strip()
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'},
    )
