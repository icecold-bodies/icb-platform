"""Names: Excel sheet -> MES trailer, Excel section label -> MES section name.

Sheet->trailer is the September import's mapping (docs/audit/
september_price_update/SECTION_3_0_DISCOVERY.md §a), verified there two ways
(source_cell row identity + name/price set overlap). Sections match by NAME,
never by position — the calculator and the Body Templates admin page already
list them in different orders.
"""
from __future__ import annotations

import re

# Exact sheet spelling (leading/trailing spaces are Burt's) -> trailer_types.id
SHEET_TO_TRAILER: dict[str, int] = {
    "Adv Vacuum panels": 1,
    "ADVANTICA BODY": 2,                     # is_active=false in MES
    "TAUT LINER RIGID": 9,                   # different layout — needs a sheet_map
    "CHESTER SPEC MEAT BODY": 10,
    "MEAT BODY": 12,
    "DRY FREIGHT TRAILER": 13,
    "GRP TRAILERS": 14,
    "RHINORANGE TRAILER": 15,
    "icecream up to 3,2": 16,
    "icecream up to 4.8": 17,
    " icecream 4.9 up": 18,
    " UP TO 2,3 MTR FREEZER ": 19,
    " UP TO 4.8 MT FREEZER  (2": 20,
    " 4.9 & UP FREEZER BODY (2": 21,
    "EXPLOSIVE UP TO 2.7": 34,
    "EXPLOSIVE 2.7 TO 4.8": 37,
    "EXPLOSIVE 4.9 AND UP": 24,
    "UP TO 2.3 CHILLER BODY": 25,
    "UP TO 5.5 CHILLER AND 2.3 WIDE": 26,
    " 4.9 & UP CHILLER AND 2.5 WIDE ": 27,   # live block is L..U — see sheet_maps/
    "BAKERY BODIES": 39,                     # different layout — needs a sheet_map
    "SMALL MEAT BODY UP TO 5,2": 36,
}
TRAILER_TO_SHEET = {v: k for k, v in SHEET_TO_TRAILER.items()}

# The six insulated panels, in Burt's flag-block order. DRD/SRD are the rear
# door alternatives; the others are always present.
PANELS = ("FRONT", "DRD", "SRD", "SIDES", "ROOF", "FLOOR")
DOOR_PANELS = ("DRD", "SRD")


def norm_name(name: str | None) -> str:
    """Case/space/punctuation-insensitive form used for every name match.
    `&` and `+` are the same word (REAR FRAME & FLOOR PLATE / + FLOOR PLATE)."""
    s = (name or "").upper().replace("&", " + ")
    s = re.sub(r"[^A-Z0-9+.,/*]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_key(name: str | None) -> str:
    """Order-insensitive token key: 'DOOR FITTINGS SRD' == 'SRD DOOR FITTINGS'."""
    return " ".join(sorted(norm_name(name).split()))


def sheet_slug(sheet: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", sheet.strip().lower()).strip("_")


class SectionMapper:
    """Excel section label -> MES section name for one body.

    Default: normalised token-set equality. A pack may add explicit
    `section_map: {"EXCEL LABEL": "MES NAME"}` overrides. Unmapped Excel
    sections are reported, never silently dropped.
    """

    def __init__(self, mes_sections: list[str], overrides: dict[str, str] | None = None):
        self.mes_sections = list(mes_sections)
        self._by_key = {norm_key(s): s for s in mes_sections}
        self._overrides = {norm_key(k): v for k, v in (overrides or {}).items()}

    def to_mes(self, excel_label: str) -> str | None:
        k = norm_key(excel_label)
        if k in self._overrides:
            return self._overrides[k]
        return self._by_key.get(k)
