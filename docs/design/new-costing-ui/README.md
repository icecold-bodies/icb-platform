# New Costing UI — design concept (design phase, no app code)

Redesign of the ICB costing experience per `docs/handoffs/MES_COSTING_CURRENT_STATE_AND_NEW_UI_REQUIREMENTS.md`.

| File | What |
|---|---|
| `index.html` + `assets/` | **Clickable mockup** — static, self-contained, sample data only. Open in a browser (serve the folder; `file://` works too). Both target journeys (body costing + REPAIR). "Where to click" button in the top bar. |
| `IA.md` | Information architecture: page regions, category vocabulary, option→category mapping rule, visible-state model, row + provenance grammar, journey inventory. |
| `wireframe-lofi.html` | The greybox that preceded the mockup (kept for the record). |
| `RULE_COVERAGE.md` | All 81 Part-14 rules → design element / engine-side / flagged (49 · 21 · 11, zero unmapped). |
| `DATA_MODEL_DELTA.md` | Concrete storage + contract delta (costing_type, repair_types, input_state v2, fingerprint v2 migration, permissions, endpoints). |
| `DESIGN_NOTE.md` | Decisions, trade-offs, rejected alternatives; D1–D6 citations; what to decide first at build. |

Serve locally (any static server; never on :8000):

```bash
python -m http.server 8020 --bind 127.0.0.1 --directory docs/design/new-costing-ui
```

All prices, customers and quote numbers in the mockup are invented. Body / section / material names mirror the spec's vocabulary.
