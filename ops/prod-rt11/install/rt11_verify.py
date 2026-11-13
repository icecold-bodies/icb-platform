"""RT11 install kit — the read-back after the pip step: renders the five customer quote templates at REV 0 and REV 1
with the DEPLOYED code (app/report_engine.py, the templates, report.css and the shipped fonts under <backend>) and the
deployed venv's WeasyPrint, in this process, and checks each PDF: page count, the reference label, the price, and the
embedded faces EXACTLY Liberation Sans / Bold / Italic + Liberation Mono (no fallback face). Then the gate (#230):
check_letterhead_quote() must read True. Nothing is written but the PDFs' bytes in memory; no database, no network.

    <venv python> -I -B rt11_verify.py <backend dir>          (run as the venv owner, from the kit folder)

Prints one line per render, then `VERIFY: <n>/10 renders correct; gate <True|False>` and exits 0 only when all 10 are
correct and the gate is True."""
import io
import re
import sys

backend = sys.argv[1]
sys.path.insert(0, backend)
from app import report_engine  # noqa: E402  (imports jinja2 only: no settings, no database)
from pypdf import PdfReader  # noqa: E402

assert report_engine.__file__.startswith(backend), report_engine.__file__
TEMPLATES = {"freezer_quote": (7, 8), "meathanger_quote": (7, 8), "rhinorange_quote": (7, 8),
             "explosive_quote": (4, 5), "dry_freight_quote": (5, 6)}
LIBERATION = {"Liberation-Sans", "Liberation-Sans-Bold", "Liberation-Sans-Italic", "Liberation-Mono"}
QN = "RT11-VERIFY/11/2026"
RESULT = {"selling_price": 87125.40, "grand_total": 53934.77, "discount_amount": 4356.27, "net_total": 82769.13}
DIMS = {"length": 5.2, "width": 2.3, "height": 2.36}
CUSTOMER = {"name": "RT11 VERIFY", "email": "", "telephone": ""}


def faces(pdf: bytes) -> set:
    seen = set()

    def walk(res):
        if res is None:
            return
        res = res.get_object()
        fonts, xo = res.get("/Font"), res.get("/XObject")
        for f in (fonts.get_object() if fonts is not None else {}).values():
            seen.add(re.sub(r"^[A-Z]{6}\+", "", str(f.get_object().get("/BaseFont")).lstrip("/")))
        for x in (xo.get_object() if xo is not None else {}).values():
            walk(x.get_object().get("/Resources"))

    for p in PdfReader(io.BytesIO(pdf)).pages:
        walk(p.get("/Resources"))
    return seen


good = 0
for slug, (pages, labels) in TEMPLATES.items():
    for rev in (0, 1):
        label = QN if rev == 0 else f"{QN} · REV {rev}"
        try:
            pdf = report_engine.render_by_slug(slug=slug, record_id=0, customer=CUSTOMER, dimensions=DIMS,
                                               result=RESULT, quote_number=label)
        except Exception as e:  # noqa: BLE001
            print(f"   FAIL {slug} REV {rev}: {type(e).__name__}: {str(e).splitlines()[0][:160]}")
            continue
        reader = PdfReader(io.BytesIO(pdf))
        text = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in reader.pages))
        probs = []
        if len(reader.pages) != pages:
            probs.append(f"{len(reader.pages)} pages, expected {pages}")
        if text.count(label) != labels:
            probs.append(f"label x{text.count(label)}, expected {labels}")
        if "R 82 769.13" not in text:
            probs.append("the net price is not printed")
        got = faces(pdf)
        if got != LIBERATION:
            probs.append(f"faces {sorted(got)} (a fallback face)")
        good += not probs
        print(f"   {'ok  ' if not probs else 'FAIL'} {slug} REV {rev}: {len(reader.pages)} pages, {len(pdf)} bytes"
              + (f" — {'; '.join(probs)}" if probs else ", faces Liberation"))
report_engine._LETTERHEAD_OK = None
gate = report_engine.check_letterhead_quote()
print(f"VERIFY: {good}/10 renders correct; gate {gate}")
sys.exit(0 if good == 10 and gate else 1)
