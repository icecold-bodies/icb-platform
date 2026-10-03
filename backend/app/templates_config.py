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


# RT3 — body families. `family_groups(trailers)` -> [(family, [bodies])] in the families' order (each family
# {id, name, colour, ink, sort_order}); `family_vars(family)` -> the two custom properties the family CSS
# reads (theme-mes.css "RT3 — body families"); `body_family(tt)` -> one body's family.
from .services import body_family as _body_family  # noqa: E402


def family_vars(fam) -> str:
    return f"--fam:{fam['colour']};--fam-ink:{fam['ink']}"


templates.env.globals["family_groups"] = _body_family.group_bodies
templates.env.globals["body_family"] = _body_family.body_family
templates.env.globals["family_vars"] = family_vars
