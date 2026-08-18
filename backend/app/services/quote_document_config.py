"""ICB quotation-document configuration — branding, VAT and terms (v1.47 Lane D).

Addendum D1/D7/D9: the ICB letterhead is becoming the house format for outgoing
quotes, with repairs as its first user. Everything about the document that is
NOT the quote's own data lives here, in ONE place, so it can be changed without
touching a renderer:

  * branding — the three branch blocks, the registration numbers, the remittance
    contact and the banking details (D9)
  * vat_rate_pct — the VAT rate, seeded at 15 % and never hardcoded in a
    renderer (D4)
  * terms — the NOTE / V.A.T. / VALIDITY / COMPLETION / WARRANTY / TERMS OF
    SALES / CONDITIONS OF SALES blocks and the acceptance form, seeded verbatim
    from the sample quote, editable afterwards (D7)

Stored as a single `pdf_templates` row (name = ICB QUOTE DOCUMENT) carrying a
JSON blob — no migration.

⚠ A §3.0 correction worth stating plainly: `pdf_templates` is a fine STORE, but
the existing /admin/pdf-template-builder screen is NOT an editor for this. That
builder is a visual layout tool bound to trailer-type BOM reports (sections,
trailer_type_ids); this row would appear in its list as a nonsense entry and
could not be edited sensibly there. D7's "manage them wherever report/PDF
templates are already managed" therefore needs its own small admin surface over
this config — the TABLE is reused, the SCREEN is not.

Seeded content is taken verbatim from
`231034795 Atlantic Seafoods - Ridhwan - LT 15 FB GP.pdf`, which is ICB's
current outgoing paperwork. Two deliberate deviations from that sample, both
noted at the call site: the SAP footer line is dropped, and the acceptance
form's document reference is printed as the document number (the sample renders
it thousands-separated — "231,035,462" — which is a SAP formatting bug on a
reference, not something to reproduce).
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..database import PDFTemplate

CONFIG_NAME = "ICB QUOTE DOCUMENT"
CONFIG_KIND = "icb_quote_document"

# ── Seeded defaults, verbatim from the sample ────────────────────────────────

DEFAULT_BRANDING: dict[str, Any] = {
    # The letterhead artwork. PLACEHOLDER_* files were extracted from the sample
    # PDF at SAP's output resolution (737x136 ≈ 99 dpi across a 190 mm content
    # width) — good enough to lay out and review, NOT good enough to print.
    # Michael's original artwork replaces these files without a code change.
    "letterhead_image": "img/quote_doc/PLACEHOLDER_img0.png",
    "continuation_logo": "img/quote_doc/PLACEHOLDER_img2.png",
    "letterhead_is_placeholder": True,
    "company_name": "Icecold Bodies (Pty) Ltd",
    "branches": [
        {"label": "MANUFACTURING PLANT",
         "lines": ["4 END STREET", "HEIDELBERG", "GAUTENG", "TEL: 016 349 1140"]},
        {"label": "SERVICE AND REPAIRS",
         "lines": ["4 LOPER AVENUE", "KEMPTON PARK", "GAUTENG", "TEL: 087 822 2341"]},
        {"label": "MANUFACTURING PLANT",
         "lines": ["21-23 WIMBLEDON ROAD", "BLACKHEATH", "CAPE TOWN", "TEL: 021 555 3076"]},
    ],
    "email": "INFO@ICECOLDGRP.CO.ZA",
    "web": "WWW.ICECOLDGRP.CO.ZA",
    "quality_banner": "THE QUALITY OF OUR BUSINESS IS THE QUALITY OF OUR RELATIONSHIP",
    "co_reg_nr": "2000/025936/07",
    "vat_nr": "451 019 0848",
    "customs_code": "20117899",
    "remittance": {
        "heading": "FORWARD REMITTANCE TO :",
        "contact": "Martie Snyman",
        "email": "martie@icecoldgrp.co.za",
    },
    "banking": {
        "heading": "BANKING DETAILS :",
        "lines": ["Capitec Business", "Current Account", "Acc No: 105 068 2114",
                  "Branch Code: 450 105", "SWIFT Code :  CABLZAJJ"],
    },
    "order_fax": "(086) 571-6181",
    "order_email": "info@icecoldbodies.co.za",
    "currency_prefix": "ZAR",
}

DEFAULT_VAT_RATE_PCT = 15.0

DEFAULT_TERMS: dict[str, Any] = {
    "notes": {
        "heading": "NOTE:",
        "items": [
            ("A.", "No provision has been made in our pricing for hidden faults. Should we "
                   "come across any, we reserve the right to re-quote."),
            ("B.", "Above pricing does not allow for any repairs and/or servicing of the "
                   "existing refrigeration equipment. “Icecold Bodies” cannot be held "
                   "responsible for any fridge failure while vehicle is in our possession."),
            ("C.", "Should Icecold Bodies (Pty) Ltd. Go ahead with the above repairs please "
                   "fax an order through to the following number (086)571-6181 or email to "
                   "info@icecoldbodies.co.za"),
        ],
    },
    "vat": {
        "heading": "V.A.T.:",
        "intro": "V.A.T. excluded in all prices quoted.",
        "items": [
            "As per the requirements of the South African Revenue Services all cross "
            "border transactions must be declared at the border.",
            "Icecold Bodies (Pty) Ltd is the Exporter.",
            "The responsibility remains with the Customer to make the necessary "
            "arrangements with a Clearing Agent to declare the transaction.",
            "Kindly ensure that the SAD500, EDI Release Note and all other relevant "
            "documentation is provided to Icecold Bodies (Pty) Ltd by no later than two "
            "months from month of Tax Invoice.",
        ],
    },
    "blocks": [
        {"heading": "VALIDITY:",
         "body": "The validity period on this quote is thirty (30) days from date hereof. "
                 "After this period, we reserve the right to re-quote."},
        {"heading": "COMPLETION:",
         "body": "Delivery date will be discussed at time of placing order.\n"
                 "Although our discussed delivery periods will be given in good faith, we "
                 "cannot be responsible for late delivery due to non-availability of labour "
                 "and/or materials."},
        {"heading": "WARRANTY:",
         "body": "All repairs and or modifications done by Icecold Bodies are guaranteed "
                 "for a period of six (6) months from date of delivery. Accidents, abuse, "
                 "fair wear and tear excluded."},
        {"heading": "TERMS OF SALES:",
         "body": "Our payment terms are strictly C.O.D., unless payment terms have been "
                 "agreed upon prior to manufacturing."},
        {"heading": "CONDITIONS OF SALES:", "body": "", "signature_block": True},
    ],
    "acceptance": {
        "heading": "Quote Acceptance form",
        "intro": "Please complete and return this form to FAX:  (086) 571-6181 .",
        # {ref} is the document number. The sample prints it thousands-separated
        # ("231,035,462") because SAP formatted a reference as a number — a bug,
        # not a format to reproduce.
        "body": "I hereby accept the Icecold Bodies Quote Ref: {ref} and the terms and "
                "conditions as stated in the quote.",
        "fields": ["Signature:", "PRINT NAME:", "Date:"],
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "kind": CONFIG_KIND,
    "vat_rate_pct": DEFAULT_VAT_RATE_PCT,
    "branding": DEFAULT_BRANDING,
    "terms": DEFAULT_TERMS,
}


def _row(db: Session) -> PDFTemplate | None:
    return (db.query(PDFTemplate)
              .filter(PDFTemplate.name == CONFIG_NAME)
              .order_by(PDFTemplate.id.desc())
              .first())


def get_config(db: Session) -> dict[str, Any]:
    """The document configuration, seeding the row on first use.

    Always returns a COMPLETE config: a stored row is merged over the defaults
    at the top level, so a partially-edited row (or one written before a key
    existed) can never leave the renderer without branding or terms.
    """
    row = _row(db)
    if row is None:
        return dict(DEFAULT_CONFIG)
    try:
        stored = json.loads(row.template_data) or {}
    except (TypeError, ValueError):
        return dict(DEFAULT_CONFIG)
    if not isinstance(stored, dict):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(stored)
    for key in ("branding", "terms"):
        if not isinstance(merged.get(key), dict) or not merged.get(key):
            merged[key] = DEFAULT_CONFIG[key]
    return merged


def save_config(db: Session, config: dict[str, Any]) -> dict[str, Any]:
    """Persist the configuration (creating the row on first save)."""
    payload = dict(config)
    payload["kind"] = CONFIG_KIND
    row = _row(db)
    if row is None:
        row = PDFTemplate(name=CONFIG_NAME, template_data=json.dumps(payload),
                          is_active=True)
        db.add(row)
    else:
        row.template_data = json.dumps(payload)
        row.is_active = True
    db.commit()
    return get_config(db)


def vat_rate_pct(db: Session) -> float:
    """The VAT rate as a percentage. Never hardcoded in a renderer (D4)."""
    try:
        v = float(get_config(db).get("vat_rate_pct", DEFAULT_VAT_RATE_PCT))
    except (TypeError, ValueError):
        return DEFAULT_VAT_RATE_PCT
    # A negative or absurd rate is a mis-edit, not a tax regime.
    return v if 0 <= v <= 100 else DEFAULT_VAT_RATE_PCT


def vat_amount(net: float, rate_pct: float) -> float:
    """VAT on a net figure, rounded to cents. Prices are quoted EXCLUSIVE of
    VAT (the sample says so in its own terms), so this is added, never
    extracted."""
    return round(float(net or 0) * float(rate_pct or 0) / 100.0, 2)


# ── admin editing (D7) ───────────────────────────────────────────────────────
#
# The config is a nested structure, but an admin screen should be a list of
# labelled boxes, not a JSON editor — Michael should not have to keep brackets
# balanced to change a warranty period. These two functions flatten it into
# addressable fields and put the edits back, so the template can just loop.

# (path, label, multiline) — path is dotted, with [i] for list members.
EDITABLE_FIELDS: list[tuple[str, str, bool]] = [
    ("vat_rate_pct",                    "VAT rate (%)",                     False),
    ("branding.company_name",           "Company name",                     False),
    ("branding.email",                  "E-mail (letterhead)",              False),
    ("branding.web",                    "Website (letterhead)",             False),
    ("branding.quality_banner",         "Quality banner",                   False),
    ("branding.co_reg_nr",              "Co. Reg. Nr",                      False),
    ("branding.vat_nr",                 "ICB VAT Nr",                       False),
    ("branding.customs_code",           "Customs code",                     False),
    ("branding.remittance.contact",     "Remittance contact",               False),
    ("branding.remittance.email",       "Remittance e-mail",                False),
    ("branding.banking.lines",          "Banking details (one per line)",   True),
    ("branding.order_fax",              "Order fax",                        False),
    ("branding.order_email",            "Order e-mail",                     False),
    ("terms.notes.items[0]",            "NOTE A",                           True),
    ("terms.notes.items[1]",            "NOTE B",                           True),
    ("terms.notes.items[2]",            "NOTE C",                           True),
    ("terms.vat.intro",                 "V.A.T. statement",                 True),
    ("terms.vat.items[0]",              "V.A.T. clause 1",                  True),
    ("terms.vat.items[1]",              "V.A.T. clause 2",                  True),
    ("terms.vat.items[2]",              "V.A.T. clause 3",                  True),
    ("terms.vat.items[3]",              "V.A.T. clause 4",                  True),
    ("terms.blocks[0].body",            "VALIDITY",                         True),
    ("terms.blocks[1].body",            "COMPLETION",                       True),
    ("terms.blocks[2].body",            "WARRANTY",                         True),
    ("terms.blocks[3].body",            "TERMS OF SALES",                   True),
    ("terms.acceptance.intro",          "Acceptance form — intro",          True),
    ("terms.acceptance.body",           "Acceptance form — body ({ref} = document number)", True),
]


def _walk(cfg: dict, path: str):
    """Resolve a dotted path to (container, key). Returns (None, None) when the
    path does not exist, so a stale field name is ignored rather than crashing."""
    node: Any = cfg
    parts = path.split(".")
    for i, part in enumerate(parts):
        idx = None
        if part.endswith("]") and "[" in part:
            part, raw = part[:part.index("[")], part[part.index("[") + 1:-1]
            try:
                idx = int(raw)
            except ValueError:
                return None, None
        last = (i == len(parts) - 1)
        if last and idx is None:
            return (node, part) if isinstance(node, dict) else (None, None)
        if not isinstance(node, dict) or part not in node:
            return None, None
        node = node[part]
        if idx is not None:
            if not isinstance(node, list) or idx >= len(node):
                return None, None
            if last:
                return node, idx
            node = node[idx]
    return None, None


def read_field(cfg: dict, path: str):
    container, key = _walk(cfg, path)
    if container is None:
        return ""
    value = container[key]
    # NOTE items are (tag, text) pairs — the admin edits the TEXT.
    if isinstance(value, (list, tuple)) and path.startswith("terms.notes.items"):
        return value[1] if len(value) > 1 else ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return value


def write_field(cfg: dict, path: str, raw: str) -> None:
    container, key = _walk(cfg, path)
    if container is None:
        return
    current = container[key]
    if isinstance(current, (list, tuple)) and path.startswith("terms.notes.items"):
        tag = current[0] if len(current) else ""
        container[key] = (tag, raw)          # keep the A./B./C. tag
    elif isinstance(current, list):
        container[key] = [ln for ln in str(raw).splitlines() if ln.strip()]
    elif isinstance(current, (int, float)) and not isinstance(current, bool):
        try:
            container[key] = float(raw)
        except (TypeError, ValueError):
            pass                              # keep the old value on a bad number
    else:
        container[key] = raw


def editable_view(cfg: dict) -> list[dict]:
    """The admin screen's field list, ready to loop over in a template."""
    return [{"path": p, "label": lbl, "multiline": ml, "value": read_field(cfg, p)}
            for p, lbl, ml in EDITABLE_FIELDS]


def apply_edits(cfg: dict, form: dict) -> dict:
    """Put submitted values back. Unknown keys are ignored, so an older form
    cannot wipe a field it never knew about."""
    import copy
    out = copy.deepcopy(cfg)
    for path, _lbl, _ml in EDITABLE_FIELDS:
        if path in form:
            write_field(out, path, form[path])
    return out
