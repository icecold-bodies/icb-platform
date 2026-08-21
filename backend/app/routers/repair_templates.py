"""Repair line SOURCES (v1.50 P3): body categories + reusable templates.

Lezette's two asks, one router. A repair that replaces an entire body section
(a SIDE, FRONT, DRD, SRD, FLOOR ...) can PULL that section's lines from the
body template instead of re-typing them; and the familiar bundle every repair
needs (GLUE, RIVETS, LABOUR ...) can be saved once as a TEMPLATE and reused.

Two principles hold everything here:

  * QUANTITIES ARE NEVER REIMPLEMENTED. The category preview calls the exact
    functions a body costing runs — ``_build_bom_items`` (in its
    ``include_all_items`` mode, which bypasses every body-option gate) and
    ``calculate_bom`` over the same geometry — so a SIDES pull on a
    7.5 x 2.3 x 2.3 vehicle computes the same quantities a body costing of
    those dimensions shows for SIDES. The preview is compute-only: nothing is
    written, and the repair stays a repair (no trailer_type_id ever lands on
    the costing — ``free_hand.is_repair_mode`` keys on that absence).

  * TEMPLATES STORE NO PRICES. A template is the item list + default
    quantities; prices resolve LIVE from the materials master at the moment of
    use (the /expand endpoint), so a template can never quote a stale price.
    Creating / editing / retiring is gated by ``costings.repair_templates_manage``
    ({admin, full} — the costings.price_master_edit pattern); USING one needs no
    key. Retire is SOFT and a retired template is unusable (409 on /expand).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import (
    get_db,
    BillOfMaterial, Material, RepairTemplate, RepairTemplateLine, TrailerType, User,
)
from ..deps import get_current_user, require_perm, user_can
from ..services import (
    _bom_load_options, get_formula_lib, get_global_vars, get_section_snapshot,
)
from ..services import free_hand
from .calculator import _build_bom_items, _build_body_variables
from app.formula_engine import calculate_bom

router = APIRouter()

MANAGE_PERM = "costings.repair_templates_manage"

# Template caps — a template is a repair bundle, so it obeys the repair
# surface's own line grammar and caps (free_hand.py is the source of truth).
MAX_TEMPLATE_NAME = 200
MAX_TEMPLATE_DESCRIPTION = 1000


def _require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    return user


# ─── Feature 1: pull a body category into a repair ───────────────────────────

def _category_rows(db: Session, trailer_type_id: int):
    """(trailer, bom_rows, ordered category names, name -> section_ids).

    Categories are the DISTINCT sections of the trailer's BOM rows, in the
    global section order — minus body-option master rows (pure toggles, never
    costed lines) and minus sections parked in the Unassigned tray
    (archived_at), which a body costing would never render either.
    """
    tt = db.query(TrailerType).filter_by(id=trailer_type_id).first()
    if not tt:
        raise HTTPException(status_code=404, detail="Body type not found")
    bom_rows = (db.query(BillOfMaterial)
                .filter_by(trailer_type_id=trailer_type_id)
                .options(*_bom_load_options()).all())
    snap = get_section_snapshot()
    counts: dict[str, int] = {}
    section_ids: dict[str, set] = {}
    for row in bom_rows:
        if row.is_body_option:
            continue
        sec = snap.by_id.get(row.bom_section_id) if row.bom_section_id else None
        if sec is not None and sec.archived_at is not None:
            continue
        cat = row.bom_section or (row.material.category.name
                                  if row.material and row.material.category
                                  else "Uncategorised")
        counts[cat] = counts.get(cat, 0) + 1
        if row.bom_section_id is not None:
            section_ids.setdefault(cat, set()).add(row.bom_section_id)
    ordered = sorted(counts, key=lambda name: (snap.order.get(name, 99998), name.lower()))
    return tt, bom_rows, ordered, section_ids


@router.get("/api/repair/body-categories")
async def repair_body_categories(trailer_type_id: int, request: Request,
                                 db: Session = Depends(get_db)):
    """The categories of one body type, for the "+ From body category" picker."""
    _require_user(request, db)
    tt, _rows, ordered, _ids = _category_rows(db, trailer_type_id)
    return {
        "trailer_type_id": tt.id,
        "trailer_name": tt.name,
        "categories": [{"name": c} for c in ordered],
    }


@router.post("/api/repair/category-preview")
async def repair_category_preview(request: Request, db: Session = Depends(get_db)):
    """Compute the lines of the chosen categories at the given dimensions.

    Same engine, same geometry as a body costing: ``_build_bom_items`` in
    ``include_all_items`` mode (every line of the category, no body-option
    context — the preview's tick boxes are the selection mechanism) into
    ``calculate_bom``. Compute-only; nothing is written.
    """
    _require_user(request, db)
    body = await request.json()

    try:
        trailer_type_id = int(body.get("trailer_type_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422,
                            detail="Set the vehicle's body type first.")

    dims_raw = body.get("dimensions") or {}
    dims: dict[str, float] = {}
    for d in ("length", "width", "height"):
        try:
            v = float(str(dims_raw.get(d, "")).replace(",", "."))
        except (TypeError, ValueError):
            v = 0.0
        if not (0 < v <= free_hand.MAX_VEHICLE_DIM):
            raise HTTPException(
                status_code=422,
                detail="Set the vehicle's dimensions first — length, width and "
                       "height are needed to compute quantities.")
        dims[d] = v

    chosen = body.get("categories")
    if not isinstance(chosen, list) or not chosen:
        raise HTTPException(status_code=422, detail="Pick at least one category.")
    chosen = [str(c).strip() for c in chosen if str(c).strip()]
    if not chosen:
        raise HTTPException(status_code=422, detail="Pick at least one category.")

    tt, bom_rows, available, section_ids = _category_rows(db, trailer_type_id)
    unknown = [c for c in chosen if c not in set(available)]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"{unknown[0]} is not a category on {tt.name} — reload and pick again.")

    # Enable every chosen category's sections so an OPTIONAL section the user
    # explicitly picked is not soft-excluded by the include_all path.
    enabled = sorted({sid for c in chosen for sid in section_ids.get(c, ())})
    items = _build_bom_items(
        bom_rows, dims, {}, None, db,
        trailer=tt, include_all_items=True, optional_sections_enabled=enabled)
    chosen_set = set(chosen)
    picked = []
    for it in items:
        if it.get("category_name") not in chosen_set:
            continue
        # The user picked the category; the preview's tick boxes decide what is
        # included, so nothing arrives pre-excluded.
        it["excluded"] = False
        it["excluded_reason"] = None
        picked.append(it)

    mat_by_bom = {row.id: row.material_id for row in bom_rows}
    result = calculate_bom(picked, dims, _build_body_variables(bom_rows),
                           get_formula_lib(), get_global_vars())

    lines = []
    for it in result.get("items", []):
        lines.append({
            "key":           f"cat{it.get('bom_id')}",
            "description":   it.get("material") or "",
            "qty":           it.get("quantity"),
            "unit":          it.get("unit") or "",
            "unit_price":    it.get("unit_price"),
            "line_total":    it.get("line_cost"),
            "category":      it.get("category"),
            "material_id":   mat_by_bom.get(it.get("bom_id")),
            "formula_error": bool(it.get("formula_error")),
        })
    return {
        "trailer_type_id": tt.id,
        "trailer_name":    tt.name,
        "dimensions":      dims,
        "lines":           lines,
        "category_totals": result.get("category_totals", {}),
        "total":           result.get("grand_total", 0),
    }


# ─── Feature 2: reusable repair templates ────────────────────────────────────

def _template_or_404(db: Session, template_id: int) -> RepairTemplate:
    tpl = db.query(RepairTemplate).filter_by(id=template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


def _parse_template_lines(db: Session, raw) -> list[RepairTemplateLine]:
    """Validate + normalise a template's lines. NO PRICES pass through here —
    by design there is nowhere to put one."""
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=422,
                            detail="A template needs at least one line.")
    if len(raw) > free_hand.MAX_LINES:
        raise HTTPException(status_code=422,
                            detail=f"Too many lines (max {free_hand.MAX_LINES}).")
    out: list[RepairTemplateLine] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="Each line must be an object.")
        kind = str(item.get("kind") or "free_hand").strip().lower()
        if kind not in ("stock", "free_hand"):
            raise HTTPException(status_code=422, detail="Unknown line type.")

        mat_id = item.get("material_id")
        try:
            mat_id = int(mat_id) if mat_id not in (None, "") else None
        except (TypeError, ValueError):
            mat_id = None

        if kind == "stock":
            mat = db.query(Material).filter_by(id=mat_id).first() if mat_id else None
            if mat is None or not mat.is_active:
                raise HTTPException(
                    status_code=422,
                    detail="A stock line must name a material from the list — "
                           "remove the line and pick again.")
            description = mat.name
            unit = mat.unit_of_measure or "each"
        else:
            description = str(item.get("description") or "").strip().upper()
            if not description:
                raise HTTPException(status_code=422,
                                    detail="Description is required on every line.")
            if len(description) > free_hand.MAX_DESCRIPTION:
                raise HTTPException(
                    status_code=422,
                    detail=f"Description is too long (max {free_hand.MAX_DESCRIPTION} characters).")
            unit = str(item.get("unit") or "").strip()[:free_hand.MAX_UNIT] or None
            # Provenance metadata (a body-category pull): keep only a real row.
            if mat_id is not None and not db.query(Material.id).filter_by(id=mat_id).first():
                mat_id = None

        qty = item.get("qty")
        if qty in (None, ""):
            qty = None
        else:
            try:
                qty = float(str(qty).replace(",", "."))
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="Quantity must be a number.")
            if not (0 <= qty <= free_hand.MAX_QTY):
                raise HTTPException(status_code=422,
                                    detail="Quantity is unrealistically large — check the value.")

        notes = str(item.get("notes") or "").strip()[:free_hand.MAX_NOTES] or None
        origin = str(item.get("origin") or "").strip()[:200] or None
        out.append(RepairTemplateLine(
            sort_order=idx, kind=kind, material_id=mat_id, description=description,
            qty=qty, unit=unit, notes=notes, origin=origin,
        ))
    return out


def _line_payload(db: Session, ln: RepairTemplateLine) -> dict:
    """One template line with its price resolved LIVE from the materials master.

    * stock line — the catalogue owns name / unit / price; a material that has
      left the list marks the line ``unavailable`` (the picker seeds it
      unticked with a plain note) rather than pricing it at a stale value.
    * free_hand line — the price is typed at use time; when the line carries a
      material reference (a body-category pull) today's list price is offered
      as the starting value, otherwise 0.
    """
    mat = db.query(Material).filter_by(id=ln.material_id).first() if ln.material_id else None
    live = mat is not None and bool(mat.is_active)
    if ln.kind == "stock":
        return {
            "id": ln.id, "kind": "stock", "material_id": ln.material_id,
            "description": mat.name if live else ln.description,
            "qty": ln.qty if ln.qty is not None else 1,
            "unit": (mat.unit_of_measure or "each") if live else (ln.unit or "each"),
            "unit_price": float(mat.price_per_unit or 0) if live else None,
            "notes": ln.notes, "origin": ln.origin,
            "unavailable": not live,
        }
    return {
        "id": ln.id, "kind": "free_hand", "material_id": ln.material_id if live else None,
        "description": ln.description,
        "qty": ln.qty if ln.qty is not None else 1,
        "unit": ln.unit or "each",
        "unit_price": float(mat.price_per_unit or 0) if live else None,
        "notes": ln.notes, "origin": ln.origin,
        "unavailable": False,
    }


def _template_payload(db: Session, tpl: RepairTemplate, *, with_lines: bool) -> dict:
    out = {
        "id": tpl.id,
        "name": tpl.name,
        "description": tpl.description,
        "line_count": len(tpl.lines),
        "created_by": tpl.created_by,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
        "updated_by": tpl.updated_by,
        "retired_at": tpl.retired_at.isoformat() if tpl.retired_at else None,
        "retired_by": tpl.retired_by,
    }
    if with_lines:
        out["lines"] = [_line_payload(db, ln) for ln in tpl.lines]
    return out


@router.get("/api/repair-templates")
async def list_repair_templates(request: Request, include_retired: bool = False,
                                db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if include_retired and not user_can(user, MANAGE_PERM, db):
        raise HTTPException(status_code=403, detail=f"Permission denied: {MANAGE_PERM}")
    q = db.query(RepairTemplate)
    if not include_retired:
        q = q.filter(RepairTemplate.retired_at.is_(None))
    tpls = q.order_by(RepairTemplate.name).all()
    return [_template_payload(db, t, with_lines=False) for t in tpls]


@router.post("/api/repair-templates")
async def create_repair_template(request: Request,
                                 user: User = Depends(require_perm(MANAGE_PERM)),
                                 db: Session = Depends(get_db)):
    body = await request.json()
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Give the template a name.")
    if len(name) > MAX_TEMPLATE_NAME:
        raise HTTPException(status_code=422,
                            detail=f"Name is too long (max {MAX_TEMPLATE_NAME} characters).")
    description = str(body.get("description") or "").strip()[:MAX_TEMPLATE_DESCRIPTION] or None
    tpl = RepairTemplate(
        name=name, description=description,
        created_by=getattr(user, "username", None),
        lines=_parse_template_lines(db, body.get("lines")),
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return _template_payload(db, tpl, with_lines=True)


@router.get("/api/repair-templates/{template_id}/expand")
async def expand_repair_template(template_id: int, request: Request,
                                 db: Session = Depends(get_db)):
    """The USE path: the template's lines priced at TODAY's material-list
    prices. Refuses a retired template — retirement means "stop using this"."""
    _require_user(request, db)
    tpl = _template_or_404(db, template_id)
    if tpl.retired_at is not None:
        raise HTTPException(status_code=409,
                            detail="That template was retired — pick another, or ask an "
                                   "admin to restore it.")
    return _template_payload(db, tpl, with_lines=True)


@router.get("/api/repair-templates/{template_id}")
async def get_repair_template(template_id: int, request: Request,
                              user: User = Depends(require_perm(MANAGE_PERM)),
                              db: Session = Depends(get_db)):
    """The MANAGE path: full detail, retired included."""
    return _template_payload(db, _template_or_404(db, template_id), with_lines=True)


@router.put("/api/repair-templates/{template_id}")
async def update_repair_template(template_id: int, request: Request,
                                 user: User = Depends(require_perm(MANAGE_PERM)),
                                 db: Session = Depends(get_db)):
    body = await request.json()
    tpl = _template_or_404(db, template_id)
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Give the template a name.")
        if len(name) > MAX_TEMPLATE_NAME:
            raise HTTPException(status_code=422,
                                detail=f"Name is too long (max {MAX_TEMPLATE_NAME} characters).")
        tpl.name = name
    if "description" in body:
        tpl.description = (str(body.get("description") or "").strip()
                           [:MAX_TEMPLATE_DESCRIPTION] or None)
    if "lines" in body:
        tpl.lines = _parse_template_lines(db, body.get("lines"))
    tpl.updated_at = datetime.now(timezone.utc)
    tpl.updated_by = getattr(user, "username", None)
    db.commit()
    db.refresh(tpl)
    return _template_payload(db, tpl, with_lines=True)


@router.post("/api/repair-templates/{template_id}/retire")
async def retire_repair_template(template_id: int, request: Request,
                                 user: User = Depends(require_perm(MANAGE_PERM)),
                                 db: Session = Depends(get_db)):
    tpl = _template_or_404(db, template_id)
    if tpl.retired_at is None:
        tpl.retired_at = datetime.now(timezone.utc)
        tpl.retired_by = getattr(user, "username", None)
        db.commit()
        db.refresh(tpl)
    return _template_payload(db, tpl, with_lines=False)


@router.post("/api/repair-templates/{template_id}/restore")
async def restore_repair_template(template_id: int, request: Request,
                                  user: User = Depends(require_perm(MANAGE_PERM)),
                                  db: Session = Depends(get_db)):
    tpl = _template_or_404(db, template_id)
    if tpl.retired_at is not None:
        tpl.retired_at = None
        tpl.retired_by = None
        db.commit()
        db.refresh(tpl)
    return _template_payload(db, tpl, with_lines=False)
