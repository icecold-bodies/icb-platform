"""
HTML/Jinja2 + WeasyPrint reporting engine.

Designed to replace the cumbersome overlay-on-PDF workflow for quote-style
documents. Each report type is a single HTML file under app/templates/reports/
with Jinja2 placeholders, rendered against company data + a costing record.

Add a new report type by:
  1. Drop a new template in app/templates/reports/<name>.html
  2. Add a build_<name>_context() builder here that returns the dict
  3. Wire an endpoint that calls render_report("<name>", context)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

APP_DIR     = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(APP_DIR, "templates", "reports")
STATIC_DIR  = os.path.join(APP_DIR, "static")

# RT11_RULING_1 — the two refusals a person reads; the technical reason goes to the server log only.
NOT_AVAILABLE_MESSAGE = "Letterhead quotes are not available on this server yet. Official quotes are issued from SAP."
NOT_A_QUOTE_MESSAGE = "This template is not a customer quote."


class LetterheadUnavailable(RuntimeError):
    """WeasyPrint cannot load here: not installed (ImportError), or installed without its system libraries — Pango /
    the GTK runtime — which raises OSError ("cannot load library 'libgobject-2.0-0'") at import."""

    def __init__(self) -> None:
        super().__init__(NOT_AVAILABLE_MESSAGE)


class NotACustomerQuote(ValueError):
    """A ReportTemplate slug without a quote context builder — e.g. cost_breakdown, the old internal sheet of margin
    and ratio, which must never reach a customer."""

    def __init__(self) -> None:
        super().__init__(NOT_A_QUOTE_MESSAGE)

_env = Environment(
    loader=FileSystemLoader(REPORTS_DIR),
    autoescape=select_autoescape(["html"]),
)


def _file_url(path: str) -> str:
    """Return a file:// URL for WeasyPrint to resolve local images/css."""
    return "file:///" + os.path.abspath(path).replace("\\", "/")


def _fmt_mm(metres: Optional[float]) -> str:
    """2.4 (m) -> '2 400mm'. None/0 -> '0 000mm' (matches PDF placeholder style)."""
    try:
        mm = int(round(float(metres or 0) * 1000))
    except (TypeError, ValueError):
        mm = 0
    s = f"{mm:,}".replace(",", " ")
    return f"{s}mm"


def _fmt_money_zar(value: Optional[float]) -> str:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    s = f"{v:,.2f}".replace(",", " ")
    return f"R {s}"


def _as_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fmt_date_human(dt: Optional[datetime]) -> str:
    dt = dt or datetime.now()
    import platform
    fmt = "%#d %B %Y" if platform.system() == "Windows" else "%-d %B %Y"
    return dt.strftime(fmt)


def build_explosive_quote_context(
    *,
    record_id: int,
    customer: Optional[Dict[str, Any]],
    dimensions: Dict[str, Any],
    result: Dict[str, Any],
    created_at: Optional[datetime] = None,
    quote_number: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the context dict for explosive_quote.html from a CalculationRecord."""
    customer = customer or {}
    customer_name = (customer.get("name") or "").strip() or "Client Name"

    # RT11_RULING_1 Q3 — the letterhead prints the MES headline: the NET TOTAL when the costing carries a discount,
    # else the TOTAL COST (the selling price; the grand total when no margin or ratio made one). Chassis: unchanged.
    total = result.get("selling_price") or result.get("grand_total") or 0
    discounted = _as_float(result.get("discount_amount")) > 0 and result.get("net_total") is not None
    price_value = result.get("net_total") if discounted else total

    sarda_path_fs = os.path.join(STATIC_DIR, "sarda-logo.png")
    logo_path_fs  = os.path.join(STATIC_DIR, "IceCold-Logo.png")
    css_path_fs   = os.path.join(STATIC_DIR, "css", "report.css")

    # Attention-of contact (customer-contacts WO): the quote's 0035 write-time snapshot,
    # threaded in via the customer dict. With a contact picked, ATTENTION becomes the
    # PERSON (and TEL/EMAIL prefer the person's, falling back per-field to the customer's).
    # No contact → every field renders exactly as before (attention = customer name).
    contact_name = (customer.get("contact_name") or "").strip()
    return {
        "ref_no":        (quote_number or str(record_id)),
        "date":          _fmt_date_human(created_at),
        "customer_name": customer_name.upper() if customer_name else "Client Name",
        "attention":     contact_name or (customer.get("name") or "").strip() or "",
        "tel_no":        ((customer.get("contact_telephone") or "").strip() if contact_name else "")
                         or (customer.get("telephone") or "").strip() or "",
        "email":         ((customer.get("contact_email") or "").strip() if contact_name else "")
                         or (customer.get("email") or "").strip() or "",
        "length_mm":     _fmt_mm(dimensions.get("length")),
        "width_mm":      _fmt_mm(dimensions.get("width")),
        "height_mm":     _fmt_mm(dimensions.get("height")),
        "price":         _fmt_money_zar(price_value),
        "logo_path":     _file_url(logo_path_fs)  if os.path.exists(logo_path_fs)  else "",
        "sarda_path":    _file_url(sarda_path_fs) if os.path.exists(sarda_path_fs) else "",
        "css_path":      _file_url(css_path_fs),
        "is_repair":     bool(result.get("is_repair")),
    }


# RT10_RULING_2 (Michael chose option B, 23 Oct) — the MES letterhead quote ("Generate Quote", /results/<id>/report)
# is offered only where it can work: WeasyPrint imports AND a one-page smoke render returns a PDF. Checked once, at
# start-up (main.on_startup), and cached for the process; RT11 installs WeasyPrint and the page needs no second change.
# Where it cannot work the results page says "Official quotes are issued from SAP." instead of a button that 500s.
_LETTERHEAD_OK: Optional[bool] = None


def check_letterhead_quote() -> bool:
    """Can this process render a letterhead quote? Imports WeasyPrint and renders one small page; True only when a
    PDF comes back. Never raises: any failure (not installed, missing system libraries, a render error) is False."""
    global _LETTERHEAD_OK
    try:
        from weasyprint import HTML
        pdf = HTML(string="<html><body><p>ICB letterhead check</p></body></html>").write_pdf()
        ok = isinstance(pdf, (bytes, bytearray)) and bytes(pdf[:5]) == b"%PDF-"
    except Exception:
        ok = False
    _LETTERHEAD_OK = ok
    return ok


def letterhead_quote_available() -> bool:
    """The cached answer of check_letterhead_quote (checked on first use if start-up did not run it)."""
    if _LETTERHEAD_OK is None:
        return check_letterhead_quote()
    return _LETTERHEAD_OK


def render_report(template_name: str, context: Dict[str, Any]) -> bytes:
    """Render a report template to PDF bytes via WeasyPrint."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        # RT11_RULING_1 — not installed, or installed without Pango / GTK (an OSError, which the old ImportError-only
        # branch let through as a raw "cannot load library …" 500): a plain refusal, the reason in the server log
        logger.warning("Letterhead quote unavailable on this server: %s: %s", type(e).__name__, e)
        raise LetterheadUnavailable() from e

    template = _env.get_template(template_name)
    html_str = template.render(**context)

    base_url = STATIC_DIR  # for relative asset resolution if needed
    pdf_bytes = HTML(string=html_str, base_url=base_url).write_pdf()
    return pdf_bytes


def render_by_slug(
    *,
    slug: str,
    record_id: int,
    customer: Optional[Dict[str, Any]],
    dimensions: Dict[str, Any],
    result: Dict[str, Any],
    created_at: Optional[datetime] = None,
    quote_number: Optional[str] = None,
) -> bytes:
    """Render a customer quote by its slug, with its context builder from CONTEXT_BUILDERS. A slug without one is
    refused (NotACustomerQuote): RT11_RULING_1 Q4 — it used to fall back to the explosive-quote builder, which handed
    cost_breakdown (the internal sheet of margin and ratio) a quote's context; a new quote template is added to
    CONTEXT_BUILDERS deliberately."""
    builder = CONTEXT_BUILDERS.get(slug)
    if builder is None:
        raise NotACustomerQuote()
    ctx = builder(
        record_id=record_id,
        customer=customer,
        dimensions=dimensions,
        result=result,
        created_at=created_at,
        quote_number=quote_number,
    )
    return render_report(f"{slug}.html", ctx)


def render_explosive_quote(
    *,
    record_id: int,
    customer: Optional[Dict[str, Any]],
    dimensions: Dict[str, Any],
    result: Dict[str, Any],
    created_at: Optional[datetime] = None,
) -> bytes:
    ctx = build_explosive_quote_context(
        record_id=record_id,
        customer=customer,
        dimensions=dimensions,
        result=result,
        created_at=created_at,
    )
    return render_report("explosive_quote.html", ctx)


# Slug → context builder. Add new entries when a template needs different vars.
# FREEZER currently uses the same vars as EXPLOSIVE; swap to a dedicated
# builder when the FREEZER layout starts diverging.
CONTEXT_BUILDERS = {
    "explosive_quote":    build_explosive_quote_context,
    "freezer_quote":      build_explosive_quote_context,
    "rhinorange_quote":   build_explosive_quote_context,
    "meathanger_quote":   build_explosive_quote_context,
    "dry_freight_quote":  build_explosive_quote_context,
}
