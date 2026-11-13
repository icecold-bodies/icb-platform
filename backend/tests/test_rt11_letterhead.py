"""RT11 — the MES letterhead quote ("Generate Quote", /results/{id}/report) renders, with WeasyPrint.

  1. the five customer quote templates at REV 0 and REV 1, rendered for real: page count, the REF. NO. label on every
     reference (with `· REV 1` from REV 1, none at REV 0), the ACCEPTANCE OF QUOTE NO line, the price, and the
     embedded faces EXACTLY Liberation Sans / Bold / Italic + Liberation Mono (RULING_1 Q1) — negative controls: the
     @font-face dropped (a fallback face appears), a wrong label, a wrong price;
  2. the price is the MES headline: the NET TOTAL when a discount exists, else the TOTAL COST (Q3), with an NC;
  3. cost_breakdown (margin and ratio) is refused — never rendered with a quote's context (Q4);
  4. the gate (#230) on REAL WeasyPrint: True when it works; False when the smoke render raises or returns no PDF —
     NC: an import-only gate says True while the render fails (RULING_0A);
  5. the route: a plain 503 when WeasyPrint cannot load (OSError: Pango / GTK missing; ImportError), the technical
     reason in the server log only (F3) — NC: the old raw 500; a plain 400 for a non-quote template; a real render
     through the route, discounted, at REV 1.
Render tests skip ONLY where WeasyPrint cannot render (the reason is named), and never on the ubuntu CI runner.
"""
from __future__ import annotations

import builtins
import io
import json
import logging
import os
import re
import shutil
import sys
import uuid
from types import SimpleNamespace

import pytest

from app import report_engine
from app.services import revisions


def _cannot_render() -> str | None:
    try:
        from weasyprint import HTML
        pdf = HTML(string="<p>RT11 capability probe</p>").write_pdf()
        return None if bytes(pdf[:5]) == b"%PDF-" else "WeasyPrint returned no PDF"
    except Exception as e:  # noqa: BLE001 — ImportError, or OSError when Pango / the GTK runtime is missing
        return f"WeasyPrint cannot render on this machine: {type(e).__name__}: {str(e).splitlines()[0][:140]}"


CANNOT_RENDER = _cannot_render()
needs_weasyprint = pytest.mark.skipif(CANNOT_RENDER is not None, reason=CANNOT_RENDER or "")

# template → (pages, REF. NO. label count in the text): the layout at Liberation's (= Arial's) metrics
TEMPLATES = {
    "freezer_quote": (7, 8),
    "meathanger_quote": (7, 8),
    "rhinorange_quote": (7, 8),
    "explosive_quote": (4, 5),
    "dry_freight_quote": (5, 6),
}
LIBERATION = {"Liberation-Sans", "Liberation-Sans-Bold", "Liberation-Sans-Italic", "Liberation-Mono"}
QN = "N10001/11/2026"
CUSTOMER = {"name": "SAMPLE CUSTOMER (PTY) LTD", "email": "", "telephone": "", "contact_name": "SAMPLE CONTACT",
            "contact_email": "sample@example.invalid", "contact_telephone": "000 000 0000"}
DIMS = {"length": 5.2, "width": 2.3, "height": 2.36}
PLAIN = {"selling_price": 170371.53, "grand_total": 88400.32}
DISCOUNTED = {"selling_price": 87125.40, "grand_total": 53934.77, "discount_kind": "percent", "discount_input": 5.0,
              "discount_amount": 4356.27, "net_total": 82769.13}
# the only WeasyPrint warning a correct render may carry: the GTK runtime on Windows has no HarfBuzz subsetter
ALLOWED_WARNING = "Using fontTools instead of HarfBuzz-Subset"


class _Grab(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.seen: list[str] = []

    def emit(self, record):
        self.seen.append(record.getMessage())


def _render(slug: str, rev: int, result: dict) -> tuple[bytes, list[str]]:
    grab = _Grab()
    lg = logging.getLogger("weasyprint")
    lg.addHandler(grab)
    try:
        pdf = report_engine.render_by_slug(slug=slug, record_id=0, customer=CUSTOMER, dimensions=DIMS, result=result,
                                           quote_number=revisions.doc_label(QN, rev + 1))
    finally:
        lg.removeHandler(grab)
    return pdf, grab.seen


def _fonts(pdf: bytes) -> set[str]:
    from pypdf import PdfReader
    seen: set[str] = set()

    def walk(res):
        if res is None:
            return
        res = res.get_object()
        fonts, xo = res.get("/Font"), res.get("/XObject")
        for f in (fonts.get_object() if fonts is not None else {}).values():
            seen.add(re.sub(r"^/?[A-Z]{6}\+", "", str(f.get_object().get("/BaseFont")).lstrip("/")))
        for x in (xo.get_object() if xo is not None else {}).values():
            walk(x.get_object().get("/Resources"))

    for page in PdfReader(io.BytesIO(pdf)).pages:
        walk(page.get("/Resources"))
    return seen


def quote_problems(pdf: bytes, *, slug: str, label: str, price: str, rev: int) -> list[str]:
    """Everything a correct letterhead quote must show; [] when it does."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(pdf))
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in reader.pages))
    pages, labels = TEMPLATES[slug]
    probs = []
    if len(reader.pages) != pages:
        probs.append(f"{len(reader.pages)} pages, expected {pages}")
    if "REF. NO." not in text or text.count(label) != labels:
        probs.append(f"the label {label!r} appears {text.count(label)} times, expected {labels}")
    if not re.search(r"ACCEPTANCE OF QUOTE NO:?\s*" + re.escape(label), text):
        probs.append("no ACCEPTANCE OF QUOTE NO line with the label")
    if (rev == 0) != (not re.search(r"REV \d", text)):
        probs.append(f"REV {rev}: 'REV n' {'appears' if rev == 0 else 'is missing'}")
    if price not in text:
        probs.append(f"the price {price!r} is not printed")
    fonts = _fonts(pdf)
    if fonts != LIBERATION:
        probs.append(f"embedded faces {sorted(fonts)}, expected exactly {sorted(LIBERATION)} (a fallback face?)")
    return probs


# ── 1. the five templates, REV 0 and REV 1 ────────────────────────────────────
@needs_weasyprint
@pytest.mark.parametrize("rev", [0, 1])
@pytest.mark.parametrize("slug", list(TEMPLATES))
def test_every_quote_template_renders_with_its_reference_price_acceptance_line_and_the_shipped_faces(slug, rev):
    pdf, warnings = _render(slug, rev, PLAIN)
    label = revisions.doc_label(QN, rev + 1)
    assert label == (QN if rev == 0 else f"{QN} · REV 1")
    assert quote_problems(pdf, slug=slug, label=label, price="R 170 371.53", rev=rev) == []
    assert [w for w in warnings if ALLOWED_WARNING not in w] == []          # no failed font, image or stylesheet


@needs_weasyprint
def test_negative_control_without_the_font_face_a_fallback_face_appears_and_is_caught(monkeypatch, tmp_path):
    static = tmp_path / "static"
    (static / "css").mkdir(parents=True)
    shutil.copy(os.path.join(report_engine.STATIC_DIR, "IceCold-Logo.png"), static / "IceCold-Logo.png")
    css = open(os.path.join(report_engine.STATIC_DIR, "css", "report.css"), encoding="utf-8").read()
    css = re.sub(r"@font-face \{[^}]*\}\r?\n", "", css).replace('"Liberation Sans", ', "").replace('"Liberation Mono", ', "")
    assert "@font-face" not in css and '"Liberation' not in css     # no shipped face is loaded or named
    (static / "css" / "report.css").write_text(css, encoding="utf-8")
    monkeypatch.setattr(report_engine, "STATIC_DIR", str(static))
    pdf, _ = _render("freezer_quote", 0, PLAIN)
    probs = quote_problems(pdf, slug="freezer_quote", label=QN, price="R 170 371.53", rev=0)
    # caught: a face that is not the shipped set. (Which one varies: DejaVu on prod; Arial on Windows; on the ubuntu CI
    # runner, whose image installs Liberation system-wide, fontconfig maps Arial to it and only the mono face falls back
    # to DejaVu Sans Mono — 13 Nov. The exact-set check catches each of them.)
    assert [p for p in probs if p.startswith("embedded faces")], probs
    assert _fonts(pdf) != LIBERATION


@needs_weasyprint
def test_negative_controls_a_wrong_label_or_a_wrong_price_is_caught():
    pdf, _ = _render("explosive_quote", 1, PLAIN)
    assert quote_problems(pdf, slug="explosive_quote", label=f"{QN} · REV 1", price="R 170 371.53", rev=1) == []
    assert quote_problems(pdf, slug="explosive_quote", label=QN + " · REV 2", price="R 170 371.53", rev=1)
    assert quote_problems(pdf, slug="explosive_quote", label=f"{QN} · REV 1", price="R 170 371.54", rev=1)
    assert quote_problems(pdf, slug="explosive_quote", label=f"{QN} · REV 1", price="R 170 371.53", rev=0)


# ── 2. the price ─────────────────────────────────────────────────────────────
def _price(result: dict) -> str:
    return report_engine.build_explosive_quote_context(record_id=0, customer=None, dimensions=DIMS,
                                                       result=result)["price"]


def test_the_price_is_the_net_total_when_discounted_else_the_total_cost():
    assert _price(DISCOUNTED) == "R 82 769.13"                         # NET TOTAL: 87 125.40 − 5 % (4 356.27)
    assert _price(PLAIN) == "R 170 371.53"                              # TOTAL COST
    assert _price({"grand_total": 1000.0}) == "R 1 000.00"              # no margin, no ratio: the grand total
    assert _price({**PLAIN, "discount_amount": 0, "net_total": 170371.53}) == "R 170 371.53"


def test_negative_control_the_old_rule_printed_the_total_before_the_discount():
    old = DISCOUNTED.get("selling_price") or DISCOUNTED.get("grand_total")
    assert report_engine._fmt_money_zar(old) == "R 87 125.40" != _price(DISCOUNTED)


@needs_weasyprint
def test_a_discounted_quote_prints_the_net_total_and_not_the_total_before_it():
    pdf, _ = _render("freezer_quote", 0, DISCOUNTED)
    assert quote_problems(pdf, slug="freezer_quote", label=QN, price="R 82 769.13", rev=0) == []
    assert "R 87 125.40" not in " ".join(p.extract_text() for p in __import__("pypdf").PdfReader(io.BytesIO(pdf)).pages)


# ── 3. cost_breakdown is not a customer quote ────────────────────────────────
@pytest.mark.parametrize("slug", ["cost_breakdown", "no_such_template"])
def test_a_template_without_a_quote_builder_is_refused_before_anything_renders(slug, monkeypatch):
    monkeypatch.setattr(report_engine, "render_report", lambda *a, **k: pytest.fail("rendered"))
    with pytest.raises(report_engine.NotACustomerQuote, match=r"^This template is not a customer quote\.$"):
        report_engine.render_by_slug(slug=slug, record_id=0, customer=None, dimensions=DIMS, result=PLAIN)
    assert set(report_engine.CONTEXT_BUILDERS) == set(TEMPLATES)        # the five quote templates, and only those


# ── 4. the gate (#230) on real WeasyPrint ────────────────────────────────────
def _gate_answers(gate, monkeypatch) -> dict:
    import weasyprint
    real = weasyprint.HTML.write_pdf
    out = {}
    for case, fake in (("works", real), ("raises", lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("render"))),
                       ("not_a_pdf", lambda self, *a, **k: b"<html>not a pdf")):
        monkeypatch.setattr(weasyprint.HTML, "write_pdf", fake)
        monkeypatch.setattr(report_engine, "_LETTERHEAD_OK", None)
        out[case] = gate()
    monkeypatch.setattr(weasyprint.HTML, "write_pdf", real)
    return out


@needs_weasyprint
def test_the_gate_reads_true_where_weasyprint_works_and_false_when_the_smoke_render_fails(monkeypatch):
    assert _gate_answers(report_engine.check_letterhead_quote, monkeypatch) == \
        {"works": True, "raises": False, "not_a_pdf": False}


@needs_weasyprint
def test_negative_control_an_import_only_gate_would_offer_a_button_that_cannot_render(monkeypatch):
    def import_only():
        try:
            import weasyprint  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False
    assert _gate_answers(import_only, monkeypatch) != {"works": True, "raises": False, "not_a_pdf": False}


@pytest.mark.skipif(CANNOT_RENDER is None, reason="WeasyPrint renders here: the gate-False case is the other test")
def test_where_weasyprint_cannot_render_the_gate_reads_false(monkeypatch):
    monkeypatch.setattr(report_engine, "_LETTERHEAD_OK", None)
    assert report_engine.check_letterhead_quote() is False
    assert report_engine.letterhead_quote_available() is False


def test_the_ubuntu_ci_runner_renders_for_real():
    """CI installs Pango + HarfBuzz on ubuntu (ci.yml): the render tests must RUN there, never skip."""
    if not (os.environ.get("GITHUB_ACTIONS") == "true" and sys.platform.startswith("linux")):
        pytest.skip("only on the ubuntu CI runner")
    assert CANNOT_RENDER is None, CANNOT_RENDER


# ── 5. the route ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin():
    from app.database import SessionLocal, User, UserSession
    sid = f"rt11-{uuid.uuid4().hex[:12]}"
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="admin").first()
        db.merge(UserSession(id=sid, user_id=user.id, role=user.role, expires_at=None, csrf_token=f"csrf-{sid}"))
        db.commit()
    yield {"Cookie": f"session_id={sid}", "X-CSRF-Token": f"csrf-{sid}"}
    with SessionLocal() as db:
        db.query(UserSession).filter_by(id=sid).delete()
        db.commit()


@pytest.fixture(scope="module")
def record():
    """One marker costing (RT11T…), REV 1 (stored version 2), discounted 5 %; removed afterwards."""
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        db.query(CalculationRecord).filter(CalculationRecord.quote_number.like("RT11T%")).delete(synchronize_session=False)
        rec = CalculationRecord(quote_number="RT11T/11/2026", status="pending", is_repair=False,
                                dimensions_json=json.dumps(DIMS),
                                result_json=json.dumps({**DISCOUNTED, "version": 2, "items": []}),
                                discount_kind="percent", discount_input=5.0, discount_amount=4356.27,
                                net_total=82769.13)
        db.add(rec)
        db.commit()
        rid = rec.id
    yield rid
    with SessionLocal() as db:
        db.query(CalculationRecord).filter(CalculationRecord.quote_number.like("RT11T%")).delete(synchronize_session=False)
        db.commit()


@pytest.fixture()
def template(monkeypatch):
    import app.routers.exports as exports

    def use(slug):
        monkeypatch.setattr(exports, "resolve_report_template", lambda tt: SimpleNamespace(slug=slug, name=slug))
    return use


def refusal_problems(status: int, detail: str, log: str) -> list[str]:
    """The no-WeasyPrint refusal: a plain 503 a person can read; the library's own words only in the server log."""
    probs = []
    if status != 503:
        probs.append(f"status {status}, expected 503")
    if detail != report_engine.NOT_AVAILABLE_MESSAGE:
        probs.append(f"detail {detail!r} is not the plain message")
    if "libgobject" in detail or "libgobject" not in log:
        probs.append("the technical reason is in the response, or missing from the log")
    return probs


@pytest.mark.parametrize("exc", [OSError("cannot load library 'libgobject-2.0-0': error 0x7e"),
                                 ImportError("No module named 'weasyprint'")])
def test_without_weasyprint_the_route_says_so_plainly_and_logs_the_reason(client, admin, record, template, exc,
                                                                         monkeypatch, caplog):
    template("freezer_quote")
    real_import = builtins.__import__

    def no_weasyprint(name, *a, **k):
        if name == "weasyprint" or name.startswith("weasyprint."):
            if isinstance(exc, ImportError):
                raise ImportError("No module named 'weasyprint' (libgobject-2.0-0 never looked for)")
            raise exc
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_weasyprint)
    with caplog.at_level(logging.WARNING, logger="app.report_engine"):
        r = client.get(f"/results/{record}/report", headers=admin)
    assert refusal_problems(r.status_code, r.json().get("detail", ""), caplog.text) == []


def test_negative_control_the_old_raw_500_is_caught():
    old = "Report generation failed: cannot load library 'libgobject-2.0-0': error 0x7e"
    assert refusal_problems(500, old, "") == ["status 500, expected 503",
                                              f"detail {old!r} is not the plain message",
                                              "the technical reason is in the response, or missing from the log"]


def test_a_non_quote_template_is_refused_plainly_by_the_route(client, admin, record, template):
    template("cost_breakdown")
    r = client.get(f"/results/{record}/report", headers=admin)
    assert (r.status_code, r.json()) == (400, {"detail": "This template is not a customer quote."})


@needs_weasyprint
def test_the_route_renders_the_saved_costing_discounted_at_rev_1(client, admin, record, template):
    template("freezer_quote")
    r = client.get(f"/results/{record}/report", headers=admin)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf", r.text[:300]
    label = "RT11T/11/2026 · REV 1"
    pdf = r.content
    from pypdf import PdfReader
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages))
    assert text.count(label) == 8 and "R 82 769.13" in text and "R 87 125.40" not in text
    assert _fonts(pdf) == LIBERATION
