"""Shared Jinja2Templates instance used by all routers."""
import os
from fastapi.templating import Jinja2Templates

from .deps import user_can

_BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))
templates.env.globals["user_can"] = user_can

# Longest first: the bare "imported from" also prefixes the two sheet-qualified
# forms the importers write into TrailerType.description.
_IMPORT_PREFIXES = ("imported from grp sheet:", "imported from sheet:",
                    "imported from")


def original_template_name(name, description):
    """Pre-rename template name behind the Body Type dropdown tooltip.

    The Excel importers stamp TrailerType.description with
    "Imported from …{original sheet name}" — the string Admin / Trailer
    Templates shows as each template's subtitle. Returns that original name
    only when it differs from the current name (case-insensitive), so
    never-renamed templates get no tooltip; returns None for empty or
    hand-written descriptions.
    """
    desc = (description or "").strip()
    low = desc.lower()
    for prefix in _IMPORT_PREFIXES:
        if low.startswith(prefix):
            orig = desc[len(prefix):].strip()
            if orig and orig.casefold() != (name or "").strip().casefold():
                return orig
            return None
    return None


templates.env.globals["original_template_name"] = original_template_name
