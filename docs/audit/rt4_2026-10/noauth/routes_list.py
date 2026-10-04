"""List every route the app registers: methods, path, endpoint module.function, source line, schema flag,
and the auth-shaped calls inside the handler body (static hint only; the dynamic sweep is the evidence)."""
import inspect, json, re, sys
from app.main import app
from starlette.routing import Mount

AUTH_RE = re.compile(r"\b(require_admin|require_user|require_perm|require_permission|get_current_user|"
                     r"_require_admin_api|_require_admin|_admin_or_403|_require_[a-z_]+|user_can|"
                     r"integration_identity_if_bearer|_current_user|_user_or_401)\b")
out = []
for r in app.routes:
    if isinstance(r, Mount):
        out.append({"kind": "mount", "path": r.path, "name": r.name})
        continue
    ep = getattr(r, "endpoint", None)
    methods = sorted(getattr(r, "methods", None) or [])
    mod = getattr(ep, "__module__", "?"); fn = getattr(ep, "__qualname__", "?")
    try:
        src, line = inspect.getsourcelines(ep)
        body = "".join(src)
        srcfile = inspect.getsourcefile(ep)
    except Exception:
        body, line, srcfile = "", 0, "?"
    deps = []
    dant = getattr(r, "dependant", None)
    def walk(d):
        for sd in d.dependencies:
            c = sd.call
            deps.append(getattr(c, "__qualname__", repr(c)))
            walk(sd)
    if dant is not None:
        walk(dant)
    out.append({"kind": "route", "methods": methods, "path": r.path, "endpoint": f"{mod}.{fn}",
                "file": (srcfile or "?").replace("\\", "/").split("/backend/")[-1], "line": line,
                "in_schema": getattr(r, "include_in_schema", True),
                "deps": sorted(set(deps)),
                "auth_calls": sorted(set(AUTH_RE.findall(body)))})
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
print(len([o for o in out if o["kind"] == "route"]), "routes;", len([o for o in out if o["kind"] == "mount"]), "mounts")
