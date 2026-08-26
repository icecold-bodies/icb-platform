"""The ICB quotation document — the RENDERER (v1.47 Lane D).

Addendum D1/D2: a reusable letterhead SHELL with a body dropped into it, drawn
with reportlab (no library switch — the existing costing PDF already uses it).

    shell  = letterhead art, the continuation header on pages 2+, the remittance
             + banking footer, "Page n/m", and the Carry Over lines
    body   = whatever the caller supplies; today that is the repair quotation

Nothing here decides anything: what the document says, what it totals and where
it breaks all come from `services/quote_document.py`, which is plain data and
separately tested. This module measures and draws.

Page geometry is chosen so page 1 is SHORTER than the rest — it carries the
letterhead and the header block — which is why the paginator takes a capacity
per page index rather than one number.
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from .quote_document import (LABEL_CARRY_OVER, carry_over_for, money,
                             paginate_lines)

# A4 portrait, matching the sample.
_PAGE_W_MM = 210.0
_PAGE_H_MM = 297.0
_MARGIN_MM = 12.0
_FOOTER_H_MM = 26.0          # remittance + banking block
_LETTERHEAD_H_MM = 22.0      # page 1 art
_CONT_HEADER_H_MM = 16.0     # pages 2+
_HEADER_BLOCK_H_MM = 46.0    # customer / reference / delivery block (page 1)
_CARRY_H_MM = 7.0


def _static_path(rel: str) -> str | None:
    """Resolve a branding asset under app/static, or None when it is missing —
    a missing letterhead must degrade to a text heading, never crash a quote."""
    if not rel:
        return None
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app/
    path = os.path.join(here, "static", *rel.split("/"))
    return path if os.path.isfile(path) else None


def render_repair_quote_pdf(ctx: dict[str, Any]) -> bytes:
    """Draw one repair quotation. Returns PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.platypus import Paragraph, Table, TableStyle

    cfg = ctx.get("config") or {}
    branding = cfg.get("branding") or {}
    terms = cfg.get("terms") or {}

    body_style = ParagraphStyle("qd_body", fontName="Helvetica", fontSize=8.5,
                                leading=10.5)
    small = ParagraphStyle("qd_small", fontName="Helvetica", fontSize=7.5, leading=9)
    bold = ParagraphStyle("qd_bold", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)

    content_w = (_PAGE_W_MM - 2 * _MARGIN_MM) * mm
    # Description | Quantity | Price | Total  (the sample's columns)
    #
    # v1.51 (Lezette, 25 Aug) — the description used to end where Quantity
    # began, so a full-width line read as though it ran into the figures. A
    # dedicated GUTTER column sits between them: it is drawn empty and never
    # carries content, which is what makes the separation hold for every row
    # rather than for the rows that happen to be short.
    _GUTTER_W = content_w * 0.04
    col_w = [content_w * 0.54, content_w * 0.12, content_w * 0.15, content_w * 0.15]

    _WIDTHS = None          # set once col_w / _GUTTER_W exist (see _widths())

    def _widths():
        return [9.0, col_w[0] - 9.0, _GUTTER_W, col_w[1], col_w[2], col_w[3]]

    def _row_style():
        """The paddings the real items table uses. One definition, so a MEASURED
        row and a DRAWN row can never disagree - which is exactly how the last
        rows ended up over the footer."""
        return [("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]

    def _row_height(line: dict) -> float:
        """The height this line costs IN THE REAL TABLE.

        v1.51 - measured by wrapping a one-row Table with the same widths and the
        same paddings, instead of a bare Paragraph plus a hand-added constant.
        The old estimate drifted from the truth whenever the padding changed, and
        pagination believed the estimate, so the last row or two of a long quote
        were drawn straight over the remittance footer (Lezette, 26 Aug).
        """
        probe = Table([[_Arrow(),
                        Paragraph(_esc(line.get("description") or ""), body_style),
                        "", "", "", ""]], colWidths=_widths())
        probe.setStyle(TableStyle(_row_style()))
        return probe.wrap(content_w, 10_000)[1]

    def _table_header_h() -> float:
        """The height of the "Description | Quantity | Price | Total" row.

        v1.51 - that row repeats on EVERY page (repeatRows=1) but was never
        subtracted from the page's capacity, so each page was over-committed by
        its height and the last row or two ran into the remittance footer.
        Measured rather than guessed: it moves with the table's own padding.
        """
        probe = Table([["", "Description", "", "Quantity", "Price", "Total"]],
                      colWidths=[9.0, col_w[0] - 9.0, _GUTTER_W,
                                 col_w[1], col_w[2], col_w[3]])
        probe.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return probe.wrap(content_w, 10_000)[1]

    def _carry_row_h() -> float:
        """The Carry Over row a continuation page opens with, measured."""
        probe = Table([["", Paragraph("<b>x</b>", body_style), "", "", "", "0.00"]],
                      colWidths=_widths())
        probe.setStyle(TableStyle(_row_style()))
        return probe.wrap(content_w, 10_000)[1]

    def _capacity(page_index: int) -> float:
        # Page 1's header is MEASURED, not assumed: the delivery address alone
        # swings it by three lines. A fixed guess either overflows the page or
        # leaves a void between the header and the table.
        top = (_letterhead_height() + 15 + _header_height()) if page_index == 0 \
            else (_CONT_HEADER_H_MM * mm)
        # Every page keeps room for the footer, for the Carry Over bar at its
        # foot, and for the column-heading row the table repeats at its top.
        avail = ((_PAGE_H_MM - 2 * _MARGIN_MM) * mm - top
                 - (_FOOTER_H_MM + _CARRY_H_MM) * mm - _table_header_h())
        # ...and a CONTINUATION page opens with a Carry Over row INSIDE the
        # table, which costs a full row and was never budgeted.
        if page_index > 0 and _shows_money:
            avail -= _carry_row_h()
        return avail

    lines = list(ctx.get("lines") or [])
    # Whether the money columns are printed at all. Computed HERE, before
    # pagination, because a continuation page carries a "Carry Over" row only
    # when they are - and that row costs height the paginator has to know about.
    _shows_money = any(ln.get("total") is not None for ln in lines)

    buf = BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{ctx.get('title', 'Quotation')} {ctx.get('document_number', '')}".strip())

    def draw_footer(page_no: int):
        y = _MARGIN_MM * mm + _FOOTER_H_MM * mm
        c.setStrokeColor(colors.HexColor("#999999"))
        c.setLineWidth(0.5)
        c.line(_MARGIN_MM * mm, y, (_PAGE_W_MM - _MARGIN_MM) * mm, y)
        rem = branding.get("remittance") or {}
        bank = branding.get("banking") or {}
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.black)
        c.drawString(_MARGIN_MM * mm, y - 10, rem.get("heading", ""))
        c.setFont("Helvetica", 7)
        c.drawString(_MARGIN_MM * mm, y - 19, rem.get("contact", ""))
        c.drawString(_MARGIN_MM * mm, y - 28, f"E-mail: {rem.get('email', '')}")
        bx = (_PAGE_W_MM / 2) * mm
        c.setFont("Helvetica-Bold", 7)
        c.drawString(bx, y - 10, bank.get("heading", ""))
        c.setFont("Helvetica", 7)
        for i, ln in enumerate(bank.get("lines") or []):
            c.drawString(bx, y - 19 - i * 8, ln)
        # Called from here so every page that gets a footer also gets its number,
        # including the terms and acceptance pages, with no extra plumbing.
        draw_page_number(page_no)

    def draw_page_number(page_no: int):
        """Top right, above the letterhead — where the sample puts it."""
        top = (_PAGE_H_MM - _MARGIN_MM + 3.5) * mm
        right_x = (_PAGE_W_MM - _MARGIN_MM) * mm
        c.setFillColor(_LABEL_GREY)
        c.setFont("Helvetica", 7)
        c.drawRightString(right_x - 34, top, "Page")
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawRightString(right_x, top, f"{page_no}/{total_pages}")

    def _letterhead_height() -> float:
        """The letterhead's drawn height in points, from the IMAGE's own aspect.

        v1.49 - it was a fixed 22mm. The art is ~5.4:1, so with its aspect
        preserved a 22mm box could only ever reach 119mm wide: the letterhead
        rendered at 64% of the page, exactly what Michael saw. Deriving the
        height from the content WIDTH means it spans the page whatever artwork
        is dropped in later - the placeholder today, the original when it lands.
        """
        img = _static_path(branding.get("letterhead_image") or "")
        if not img:
            return 20.0
        try:
            from reportlab.lib.utils import ImageReader
            iw, ih = ImageReader(img).getSize()
            if iw and ih:
                return content_w * (ih / iw)
        except Exception:
            pass
        return _LETTERHEAD_H_MM * mm

    def draw_letterhead() -> float:
        """Page 1 art, full content width. Falls back to a text heading when the
        file is absent."""
        top = (_PAGE_H_MM - _MARGIN_MM) * mm
        img = _static_path(branding.get("letterhead_image") or "")
        if img:
            h = _letterhead_height()
            c.drawImage(img, _MARGIN_MM * mm, top - h, width=content_w, height=h,
                        preserveAspectRatio=True, anchor="nw", mask="auto")
            # The sample carries a registration line directly under the art:
            #   Co. Reg. Nr:  2000/025936/07              VAT Nr:  451 019 0848
            # Small grey labels, black values, ends flush with the art's edges.
            y = top - h - 9
            left = _MARGIN_MM * mm
            right_x = (_PAGE_W_MM - _MARGIN_MM) * mm
            c.setFillColor(_LABEL_GREY)
            c.setFont("Helvetica", 7)
            c.drawString(left + 4, y, "Co. Reg. Nr:")
            c.setFillColor(colors.black)
            c.drawString(left + 50, y, str(branding.get("co_reg_nr", "")))
            c.setFillColor(_LABEL_GREY)
            c.drawRightString(right_x - 62, y, "VAT Nr:")
            c.setFillColor(colors.black)
            c.drawRightString(right_x, y, str(branding.get("vat_nr", "")))
            return y - 6
        c.setFont("Helvetica-Bold", 14)
        c.drawString(_MARGIN_MM * mm, top - 14, branding.get("company_name", "Icecold Bodies"))
        return top - 20

    def draw_continuation_header(page_no: int) -> float:
        """Pages 2+: small logo · Original · Repair Quotation · number · date."""
        top = (_PAGE_H_MM - _MARGIN_MM) * mm
        logo = _static_path(branding.get("continuation_logo") or "")
        if logo:
            c.drawImage(logo, _MARGIN_MM * mm, top - 12 * mm, width=12 * mm,
                        height=12 * mm, preserveAspectRatio=True, anchor="nw",
                        mask="auto")
        x = (_MARGIN_MM + 16) * mm
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.black)
        c.drawString(x, top - 12, ctx.get("title", ""))
        c.setFont("Helvetica", 8)
        c.drawString(x, top - 24, ctx.get("original_label", ""))
        c.setFont("Helvetica", 8)
        # v1.51 — Document Number and Document Date are drawn right-aligned from
        # the same edge on two lines, so they never collide with each other; what
        # DID collide (R-2002, 25 Aug) was a long number running left into the
        # title. Each value is fitted to the space actually left beside the
        # title, truncating with an ellipsis rather than overprinting it.
        _right = (_PAGE_W_MM - _MARGIN_MM) * mm
        _avail = _right - x - 8
        for dy, label, value in ((12, "Document Number", ctx.get("document_number", "")),
                                 (24, "Document Date", ctx.get("document_date", ""))):
            c.drawRightString(_right, top - dy,
                              f"{label}  {_fit(c, str(value or ''), 'Helvetica', 8, _avail - c.stringWidth(label + '  ', 'Helvetica', 8))}")
        return top - _CONT_HEADER_H_MM * mm

    # ── the sample's header grid ─────────────────────────────────────────────
    # Labels in small grey caps sit ABOVE their values, in four columns, each
    # band closed by a light-blue dotted rule. That rule is the sample's most
    # recognisable feature after the letterhead itself.
    _LABEL_GREY = colors.HexColor("#8A9099")
    _RULE_BLUE = colors.HexColor("#9CC3E5")
    _RULE_DOT = colors.HexColor("#C9CED6")   # the between-items separator (v1.51)
    # v1.51 (Lezette, 25 Aug) — "squeezed to the top". The bands were drawn on
    # the tightest rhythm that fit; against the old system's quote the whole
    # block reads as compressed. Each figure gains a couple of points, which the
    # measured paginator absorbs without any change to where pages break.
    _BAND_LABEL_DY = 10.0    # label baseline below the band top
    _BAND_VALUE_DY = 23.0    # first value baseline below the band top
    _BAND_LINE_DY = 9.5      # extra value lines
    _BAND_GAP = 12.0         # space between the last value and the rule
    _MISSING = "–"           # en-dash: "ICB never captured this", not content

    def _header_bands() -> list[list[tuple[str, list[str], int]]]:
        """The header as data: bands of (label, value lines, column index).

        Built here rather than drawn inline so the block's HEIGHT can be measured
        before anything is drawn — the delivery address alone swings it by three
        lines, and the paginator needs the real number or page 1 either overflows
        or leaves the void the first version had.
        """
        addr = [ln for ln in str(ctx.get("delivery_address") or "").splitlines() if ln.strip()][:4]
        contact = [v for v in (ctx.get("your_contact"), ctx.get("your_contact_phone")) if v]
        bands = [
            [("Vat Num - Partner", [ctx.get("customer_vat") or _MISSING], 0),
             ("Tel No.",           [ctx.get("customer_tel") or _MISSING], 1),
             ("Document Number",   [ctx.get("document_number") or _MISSING], 2),
             ("Document Date",     [ctx.get("document_date") or _MISSING], 3)],
            [("Email",             [ctx.get("customer_email") or _MISSING], 0),
             ("Your Contact",      contact or [_MISSING], 2)],
        ]
        third = []
        if addr:
            third.append(("Delivery Address", addr, 0))
        if ctx.get("your_reference"):
            third.append(("Your Reference", [ctx["your_reference"]], 2))
        if third:
            bands.append(third)
        if ctx.get("job_note"):
            bands.append([("Job Note", _wrap_plain(str(ctx["job_note"]), 110)[:3], 0)])
        return bands

    # The grid is four equal columns; a value is only ever allowed the width of
    # its own, less a gutter, so a long one can NEVER reach its neighbour.
    _COL_W = content_w / 4.0
    _COL_GUTTER = 8.0

    def _fit_band(values: list[str], col: int) -> list[str]:
        """A band value as the lines it will actually occupy.

        v1.51 (default 6) — Document Number and Document Date collided on R-2002
        because a templated number was three times its column wide and nothing
        measured it. Values wrap onto a second line where the text has spaces to
        wrap on, and are ellipsised where it has none (an unbroken 60-character
        reference), so the collision is impossible by construction rather than
        unlikely by convention. Capped at two lines: a header field is a label,
        not a paragraph, and the band height follows this measurement.
        """
        # The last column has the page edge, not a neighbour, to its right.
        avail = (_COL_W - _COL_GUTTER) if col < 3 else (_COL_W - 2.0)
        out: list[str] = []
        for v in values:
            v = str(v)
            if c.stringWidth(v, "Helvetica-Bold", 8.2) <= avail:
                out.append(v)
                continue
            wrapped = _wrap_to_width(c, v, "Helvetica-Bold", 8.2, avail)
            if len(wrapped) > 2:
                wrapped = wrapped[:2]
                wrapped[1] = wrapped[1] + " …"
            # Wrapping alone is not enough: a value with NO spaces in it (an
            # unbroken 120-character reference) is one "word", so the wrapper
            # hands it back whole and it would run clean across its neighbour.
            # Every line is ellipsised to the column here, which is what makes
            # the collision impossible rather than merely unlikely.
            out.extend(_fit(c, w, "Helvetica-Bold", 8.2, avail) for w in wrapped)
        return out or [""]

    def _band_height(band) -> float:
        lines = max(len(_fit_band(v, col)) for _l, v, col in band)
        return _BAND_VALUE_DY + (lines - 1) * _BAND_LINE_DY + _BAND_GAP

    def _header_height() -> float:
        """Customer name + every band + the rules, in points."""
        return 22.0 + sum(_band_height(b) for b in _header_bands())

    def draw_header_block(y: float) -> float:
        """Page 1's customer / reference / delivery grid, drawn like the sample."""
        left = _MARGIN_MM * mm
        right_x = (_PAGE_W_MM - _MARGIN_MM) * mm
        col_x = [left + content_w * f for f in (0.0, 0.25, 0.50, 0.75)]

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(left, y - 14, ctx.get("customer_name", ""))
        y -= 22.0

        for band in _header_bands():
            for label, values, col in band:
                x = col_x[col]
                c.setFillColor(_LABEL_GREY)
                c.setFont("Helvetica", 6.8)
                c.drawString(x, y - _BAND_LABEL_DY, label)
                for i, v in enumerate(_fit_band(values, col)):
                    # A value ICB never captured is shown as a light dash rather
                    # than a bold one: the eye should read "not supplied", not
                    # mistake a heavy em-dash for content.
                    blank = (v == _MISSING)
                    c.setFillColor(_LABEL_GREY if blank else colors.black)
                    c.setFont("Helvetica" if blank else "Helvetica-Bold", 8.2)
                    c.drawString(x, y - _BAND_VALUE_DY - i * _BAND_LINE_DY, str(v))
            y -= _band_height(band)
            # The light-blue dotted rule closing the band.
            c.setStrokeColor(_RULE_BLUE)
            c.setLineWidth(0.7)
            c.setDash(1, 2.6)
            c.line(left, y + 3.0, right_x, y + 3.0)
            c.setDash()
        return y

    from reportlab.platypus import Flowable

    class _Arrow(Flowable):
        """The sample's small right-pointing marker beside each line item.

        A drawn triangle rather than a character: Helvetica carries no arrow
        glyph, so a typed one renders as a tofu box — exactly what happened to
        the Carry Over bar on the first proof. Sized and nudged to sit on the
        first text line of the description beside it, not the top of the cell.
        """
        _W, _H = 4.0, 4.6

        def wrap(self, _aw, _ah):
            return self._W, self._H

        def draw(self):
            cv = self.canv
            cv.setFillColor(colors.HexColor("#C00000"))
            p = cv.beginPath()
            p.moveTo(0, -2.0)
            p.lineTo(self._W, -2.0 + self._H / 2.0)
            p.lineTo(0, -2.0 + self._H)
            p.close()
            cv.drawPath(p, stroke=0, fill=1)

    def draw_lines_table(rows: list[dict], y: float, carry_in: float | None) -> float:
        # A narrow leading column carries the sample's right-pointing marker.
        # It is DRAWN, not typed: Helvetica has no arrow glyph, and the character
        # forms render as a tofu box — the same trap the Carry Over bar hit.
        acol = 9.0
        widths = [acol, col_w[0] - acol, _GUTTER_W, col_w[1], col_w[2], col_w[3]]
        data = [["", "Description", "", "Quantity", "Price", "Total"]]
        if carry_in is not None:
            # Carry IN at the head of a continuation page — same wording as the
            # foot of the page before it, which is how the sample reads.
            data.append(["", Paragraph(f"<b>{LABEL_CARRY_OVER}</b>", body_style), "", "", "",
                         money(carry_in)])
        for ln in rows:
            data.append([
                _Arrow(),
                Paragraph(_esc(ln.get("description") or ""), body_style),
                "",
                "" if ln.get("qty") is None else _num(ln["qty"]),
                "" if ln.get("price") is None else money(ln["price"]),
                # v1.51 — None means "print nothing here". SUMMARY and BREAKDOWN
                # blank all three money columns, and money(None) would print a
                # real, wrong "0.00" in a column the customer reads as a price.
                "" if ln.get("total") is None else money(ln["total"]),
            ])
        t = Table(data, colWidths=widths, repeatRows=1)
        _first_line = 2 if carry_in is not None else 1
        style = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            # The sample brackets its column headings in the same blue as the
            # header rules, rather than a black underline.
            ("LINEABOVE", (0, 0), (-1, 0), 0.8, _RULE_BLUE),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, _RULE_BLUE),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (0, 0), (0, -1), 2),
            # v1.51 — more air per row. The old 3/4 pt pair packed the lines
            # tightly enough that a two-line description ran into the next item.
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        # v1.51 — a thin dotted rule BETWEEN items, matching the header bands.
        # Drawn between rows rather than under every row so the last item is not
        # underlined into the totals block, and skipped on the header (which has
        # its own blue rule) and on a Carry Over line (which belongs to the item
        # above it, not to a new one).
        for i in range(_first_line + 1, len(data)):
            style.append(("LINEABOVE", (1, i), (-1, i), 0.4, _RULE_DOT, None,
                          (1, 2.2)))
        t.setStyle(TableStyle(style))
        w, h = t.wrap(content_w, y)
        t.drawOn(c, _MARGIN_MM * mm, y - h)
        return y - h

    def draw_carry_out(y: float, amount: float):
        # The sample marks this line with a solid left bar. Drawn as a filled
        # RECTANGLE, not the "▌" character: Helvetica has no such glyph, so the
        # text form renders as a tofu box (seen in the first proof render).
        c.setFillColor(colors.black)
        c.rect(_MARGIN_MM * mm, y - 19, 2.2, 10, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 9)
        c.drawString((_MARGIN_MM * mm) + 6, y - 12, LABEL_CARRY_OVER)
        c.drawRightString((_PAGE_W_MM - _MARGIN_MM) * mm, y - 12, money(amount))

    def _totals_height() -> float:
        """How tall the totals block plus its Payment Term line will be.

        v1.51 - nothing reserved room for this. On a quote whose lines ended low
        on the last page the totals were drawn straight over the remittance
        footer: that is the defect on the very FIRST R-2001 ("Total before
        Discount: ZAR 30,408.40" interleaved with the ICB e-mail address), which
        predates the print modes and is the same bug Lezette photographed.
        """
        rows = ctx.get("totals") or []
        if not rows:
            return 0.0
        probe = Table([[str(r["label"]).replace(chr(10), " "), r.get("note") or "", "X"]
                       for r in rows],
                      colWidths=[content_w * 0.55, content_w * 0.15, content_w * 0.30])
        probe.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2)]))
        return probe.wrap(content_w, 10_000)[1] + 20.0   # + the Payment Term line

    def draw_totals(y: float) -> float:
        prefix = branding.get("currency_prefix", "ZAR")
        rows = []
        for r in ctx.get("totals") or []:
            label = str(r["label"]).replace("\n", " ")
            rows.append([label, r.get("note") or "", f"{prefix} {money(r['amount'])}"])
        t = Table(rows, colWidths=[content_w * 0.55, content_w * 0.15, content_w * 0.30])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, len(rows) - 1), (-1, len(rows) - 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("LINEABOVE", (0, len(rows) - 1), (-1, len(rows) - 1), 0.6, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        w, h = t.wrap(content_w, y)
        t.drawOn(c, _MARGIN_MM * mm, y - h)
        c.setFont("Helvetica", 8)
        c.drawString(_MARGIN_MM * mm, y - h - 12,
                     f"Payment Term   {ctx.get('payment_terms', 'COD')}")
        return y - h - 20

    # ── draw ──────────────────────────────────────────────────────────────────
    # Paginate only now: _capacity measures the header, whose helpers are defined
    # above. total_pages is read by draw_footer at call time, so it is in place
    # before the first page is stamped.
    pages = paginate_lines(lines, _capacity, _row_height) or [[]]
    carries = carry_over_for(pages)

    # v1.51 - does the totals block still fit under the last page's table?
    #
    # Decided BEFORE anything is drawn, not when we get there: page 1's footer
    # prints "n/m", so the page COUNT has to be right from the first stamp. The
    # arithmetic mirrors the drawing exactly (same helpers, same paddings), and
    # the same answer drives both the count and the placement, so the two can
    # never disagree.
    def _totals_fit_on_last_page() -> bool:
        idx = len(pages) - 1
        used_top = (_letterhead_height() + 15 + _header_height()) if idx == 0             else (_CONT_HEADER_H_MM * mm)
        y_start = (_PAGE_H_MM - _MARGIN_MM) * mm - used_top
        table_h = _table_header_h() + sum(_row_height(r) for r in pages[idx])
        if idx > 0 and _shows_money:
            table_h += _carry_row_h()            # the Carry Over row at the head
        return (y_start - table_h - 8) - _totals_height() >= (_MARGIN_MM + _FOOTER_H_MM) * mm

    _totals_spill = not _totals_fit_on_last_page()
    total_pages = len(pages) + (1 if _totals_spill else 0) + _extra_page_count(terms)

    page_no = 0
    for i, rows in enumerate(pages):
        page_no += 1
        if i == 0:
            y = draw_letterhead()
            y = draw_header_block(y)
        else:
            y = draw_continuation_header(page_no)
        carry_in = carries[i - 1] if (i > 0 and _shows_money) else None
        y = draw_lines_table(rows, y, carry_in)
        is_last = (i == len(pages) - 1)
        if not is_last:
            # A Carry Over bar states a running total of the LINE column. In
            # SUMMARY and BREAKDOWN that column is deliberately empty, so the bar
            # would announce a figure the page does not show. ITEMIZED only.
            if _shows_money:
                draw_carry_out((_MARGIN_MM + _FOOTER_H_MM + _CARRY_H_MM) * mm, carries[i])
            draw_footer(page_no)
            c.showPage()
        elif _totals_spill:
            # The totals get a page of their own rather than being painted over
            # the remittance footer - which is also how the old system's own
            # quote reads (R-231037388 puts its totals alone on page 2 of 4).
            draw_footer(page_no)
            c.showPage()
            page_no += 1
            y = draw_continuation_header(page_no)
            draw_totals(y - 8)
            draw_footer(page_no)
            c.showPage()
        else:
            draw_totals(y - 8)
            draw_footer(page_no)
            c.showPage()

    # pages_so_far must COUNT the totals spill page, or the terms pages would
    # re-use its number and the document would show two page 3s.
    _draw_terms_pages(c, ctx, terms, branding,
                      len(pages) + (1 if _totals_spill else 0), total_pages, draw_footer,
                      draw_continuation_header)
    c.save()
    return buf.getvalue()


def _extra_page_count(terms: dict) -> int:
    """Terms page + acceptance form (D7) — both admin-editable, both counted in
    the n/m total so page 1 does not claim to be "1/2" of a four-page quote."""
    n = 0
    if terms.get("notes") or terms.get("vat") or terms.get("blocks"):
        n += 1
    if terms.get("acceptance"):
        n += 1
    return n


def _draw_terms_pages(c, ctx, terms, branding, pages_so_far, total_pages,
                      draw_footer, draw_continuation_header):
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    page_no = pages_so_far
    if terms.get("notes") or terms.get("vat") or terms.get("blocks"):
        page_no += 1
        y = draw_continuation_header(page_no)
        y -= 6
        c.setFillColor(colors.black)
        notes = terms.get("notes") or {}
        if notes:
            y = _para_block(c, y, notes.get("heading", ""), bold=True)
            for tag, text in notes.get("items") or []:
                y = _para_block(c, y, f"{tag} {text}")
        vat = terms.get("vat") or {}
        if vat:
            y = _para_block(c, y, vat.get("heading", ""), bold=True)
            y = _para_block(c, y, vat.get("intro", ""))
            for i, text in enumerate(vat.get("items") or [], start=1):
                y = _para_block(c, y, f"{i}.  {text}")
        for blk in terms.get("blocks") or []:
            y = _para_block(c, y, blk.get("heading", ""), bold=True)
            if blk.get("body"):
                y = _para_block(c, y, blk["body"])
            if blk.get("signature_block"):
                c.setFont("Helvetica", 8)
                c.drawString(_MARGIN_MM * mm, y - 18, "Date")
                c.drawString((_MARGIN_MM + 70) * mm, y - 18, "Signature")
                # v1.50 (Lezette, 22 Aug) — a hand-completed Purchase Order line
                # beside Date / Signature: the customer writes their PO number on
                # the signed copy they return. Label text is admin-editable
                # (terms.blocks[].po_line); blank = the line is omitted. Drawn as
                # a rule, the same technique as the acceptance form's fields.
                po = str(blk.get("po_line") or "").strip()
                if po:
                    po_x = (_MARGIN_MM + 115) * mm
                    c.drawString(po_x, y - 18, po)
                    label_w = c.stringWidth(po, "Helvetica", 8)
                    c.setStrokeColor(colors.HexColor("#666666"))
                    c.setLineWidth(0.6)
                    c.line(po_x + label_w + 6, y - 20,
                           (_PAGE_W_MM - _MARGIN_MM) * mm, y - 20)
                y -= 26
        draw_footer(page_no)
        c.showPage()

    acc = terms.get("acceptance") or {}
    if acc:
        page_no += 1
        y = draw_continuation_header(page_no)
        y -= 10
        y = _para_block(c, y, acc.get("heading", ""), bold=True)
        y = _para_block(c, y, acc.get("intro", ""))
        # The sample renders its own reference thousands-separated ("231,035,462")
        # because SAP formatted a reference as a number. Print the document number.
        y = _para_block(c, y, (acc.get("body") or "").replace(
            "{ref}", str(ctx.get("document_number") or "")))
        for field in acc.get("fields") or []:
            y -= 18
            c.setFont("Helvetica", 9)
            c.drawString(_MARGIN_MM * mm, y, field)
            c.setStrokeColor(colors.HexColor("#666666"))
            c.setLineWidth(0.6)
            # v1.51 — the rule starts after the LABEL, not at a fixed 30 mm.
            # "Order Number:" is wider than "Date:" and would have been struck
            # through by a hardcoded start; measuring means any label an admin
            # types gets a line that begins where its text ends.
            _x = max((_MARGIN_MM + 30) * mm,
                     _MARGIN_MM * mm + c.stringWidth(str(field), "Helvetica", 9) + 8)
            c.line(_x, y - 2, (_PAGE_W_MM - _MARGIN_MM - 18) * mm, y - 2)
        draw_footer(page_no)
        c.showPage()


def _para_block(c, y, text, bold=False):
    """One wrapped paragraph of terms text, returning the new y."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph

    if not text:
        return y
    style = ParagraphStyle("t", fontName="Helvetica-Bold" if bold else "Helvetica",
                           fontSize=8.5, leading=11)
    width = (_PAGE_W_MM - 2 * _MARGIN_MM) * mm
    para = Paragraph(_esc(text).replace("\n", "<br/>"), style)
    _w, h = para.wrap(width, 10_000)
    para.drawOn(c, _MARGIN_MM * mm, y - h)
    return y - h - 5


def _fit(c, text: str, font: str, size: float, avail: float) -> str:
    """`text` shortened with an ellipsis until it fits `avail` points.

    Used where a value has NO room to wrap — the continuation header's two
    stacked fields, and the second line of a header band. Returns "" rather than
    a bare ellipsis when there is no room at all, because a lone "…" in a
    document header reads as corruption, not as truncation.
    """
    text = str(text or "")
    if avail <= 0:
        return ""
    if c.stringWidth(text, font, size) <= avail:
        return text
    ell = "…"
    if c.stringWidth(ell, font, size) > avail:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if c.stringWidth(text[:mid] + ell, font, size) <= avail:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo].rstrip() + ell) if lo else ell


def _wrap_to_width(c, text: str, font: str, size: float, avail: float) -> list[str]:
    """Greedy word wrap MEASURED in points rather than counted in characters.

    _wrap_plain counts characters, which is fine for the job note's fixed-width
    paragraph but wrong for a header value that must fit an exact column: "III"
    and "WWW" are the same character count and nearly double the width.
    """
    words = str(text or "").split()
    if not words:
        return [""]
    out: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and c.stringWidth(trial, font, size) > avail:
            out.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _num(v) -> str:
    f = float(v or 0)
    return str(int(f)) if abs(f - int(f)) < 1e-9 else f"{f:.2f}"


def _wrap_plain(text: str, width: int) -> list[str]:
    """Greedy word wrap for the few header values drawn with drawString.

    Not a Paragraph: the header grid is positioned by hand so every value shares
    one baseline rhythm, and a flowable would bring its own leading.
    """
    words, out, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out or [""]
