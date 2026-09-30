"""v1.58.1 §3.3 (c) — does the customer PDF leave the excluded REAR FRAME lines out?

Against a running server (a CA side port on dev): autologin, then ICECREAM 4.9 UP (dev id 18) priced
with /api/calculate (compute only — saves nothing) for DRD and for SRD, each rendered by
/api/export/preview as PDF (renders the live result — saves nothing). Reads the PDF text and looks
for the REAR FRAME & FLOOR PLATE line names.

    python verify_pdf_preview.py http://127.0.0.1:8011 <out dir>
"""
import io
import sys
from pathlib import Path

import httpx
from pypdf import PdfReader

TID = 18
M = {"DRD EPS": 5425, "DRD PU": 5426, "SRD EPS": 5427, "SRD PU": 5428}
RF_LINES = ["3MM 3CR12 REAR FRAME", "TOP FRAME RAIN GUTTER", "M8*150 GALV. CUP SQUARES", "M8*45*3 FENDER WASHER",
            "M8 NYLOCK NUT", "5MM CORNER GUSSET", "2771-0824 MONOBOLTS"]


def main(base, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(base_url=base, headers={"Origin": base}, timeout=60)
    r = c.post("/api/mes/autologin")
    r.raise_for_status()
    csrf = c.get("/api/session").json().get("csrf_token") or ""
    c.headers["X-CSRF-Token"] = csrf
    ok = True
    for door in ("DRD", "SRD"):
        on = "DRD PU" if door == "DRD" else "SRD PU"
        sel = {str(v): (k == on) for k, v in M.items()}
        payload = {"trailer_type_id": TID, "dimensions": {"length": 6.7, "width": 2.6, "height": 2.6},
                   "overrides": {}, "body_option_selections": sel, "flag_overrides": {k: (k == on) for k in M},
                   "body_variable_overrides": {on: 0.12},
                   "excluded_categories": ["SRD", "SRD DOOR FITTINGS"] if door == "DRD" else ["DRD", "DRD DOOR FITTINGS"],
                   "user_excluded_bom_ids": [], "optional_sections_enabled": [], "insulation_foam": "32D",
                   "profit_margin": 0, "chassis": {"enabled": False}}
        res = c.post("/api/calculate", json=payload)
        res.raise_for_status()
        result = res.json()
        rf = [it for it in result["items"] if it.get("category") == "REAR FRAME & FLOOR PLATE"]
        pdf = c.post("/api/export/preview", json={"result": result, "dims": payload["dimensions"],
                                                   "trailer_type_id": TID, "body_option_selections": sel,
                                                   "format": "pdf", "detail": "items"})
        pdf.raise_for_status()
        (out / f"preview_{door}.pdf").write_bytes(pdf.content)
        txt = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf.content)).pages)
        found = [n for n in RF_LINES if n in txt]
        fittings = "SB 51111 DOOR SET" in txt or "DOOR SET" in txt
        print(f"{door}: calc RF lines {len(rf)}, excluded {sum(1 for it in rf if it.get('excluded'))}, "
              f"RF total {round(sum(float(it.get('line_cost') or 0) for it in rf), 2)} | PDF {len(pdf.content)} bytes, "
              f"REAR FRAME line names in PDF: {len(found)}/{len(RF_LINES)} | door fittings in PDF: {fittings}")
        good = (len(found) == len(RF_LINES)) if door == "DRD" else (len(found) == 0)
        ok &= good
        print("   ", "OK" if good else "!! FAIL", found)
    print("ALL OK" if ok else "!! FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
