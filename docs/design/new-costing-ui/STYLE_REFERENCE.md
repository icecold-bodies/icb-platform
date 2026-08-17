# Style reference — the ICB "PULL BOARD" look, applied to the costing mockup

**Source:** the live floor system at `floor.icecoldgrp.online` (Next.js + Tailwind v4), read from its shipped global stylesheet on 17 Aug 2026 (`/_next/static/chunks/*.css`, public). ICB likes this style (Michael, 17 Aug); the mockup's default theme now uses these tokens. Values are the exact ones the floor app ships (Tailwind v4 palette, hex-rounded), not approximations.

## Foundations
| Token | Value | Tailwind | Used for |
|---|---|---|---|
| ground | `#020618` | slate-950 | page background |
| paper | `#0f172b` | slate-900 | cards, bars, drawer |
| raised | `#1d293d` | slate-800 | menus, buttons, demo bar |
| input | `#0b1120` | (the app's dark `--background`) | inputs |
| line | `#314158` | slate-700 | borders |
| line-2 | `#1d293d` | slate-800 | hairlines inside cards |
| ink | `#e2e8f0` | slate-200 | text |
| ink-2 | `#cad5e2` | slate-300 | secondary text |
| mute | `#90a1b9` | slate-400 | labels, captions |
| dim | `#62748e` | slate-500 | excluded / rule rows |

Font: `ui-sans-serif, system-ui, …` (no webfont in the floor app); figures use tabular numerals; mono (`ui-monospace, …`) is available for code. Sizes: xs .75rem · sm .875rem · base 1rem. Radii: md .375 · lg .5 · xl .75rem (mockup uses 6–8 px).

## Semantic accents (the board's usage)
| Meaning | Text | Solid | Tint bg | Tint line | Tailwind |
|---|---|---|---|---|---|
| ok / live | `#5ee9b5` | `#00bb7f` | `#002c22` | `#004e3b` | emerald 300/500/950/900 |
| warn | `#fee685` | `#f99c00` | `#461901` | `#7b3306` | amber 200/500/950/900 |
| danger / attention | `#ffa2ae` | `#ff2357` | `#4d0218` | `#a30037` | rose 300/500/950/800 |
| typed-by-you (mockup) | `#77d4ff` | — | `#052f4a` | `#024a70` | sky 300/950/900 |
| primary (buttons, selected) | `#ffffff` on `#3b82f6` | `#3b82f6` | — | — | the app's `--primary` (blue-500) |
| chip families | `#a4b3ff` indigo-300 · `#96f7e4` teal-200 · `#00b7d7` cyan-500 | | | | |

## Idioms taken from the board
- Bold caps section titles with letter-spacing; small caps labels for fields and table heads.
- Pill badges (`LIVE`, counts) — rounded-full, tinted bg + border in the semantic colour.
- Chip rows for choices; selected chip/segment = primary blue solid.
- Left accent bar on rows/sections that need attention (rose) or were switched off (slate).
- Dark cards on a darker ground with a 1 px hairline; no heavy shadows.

## How the provenance grammar maps (IA §5)
blue = typed → **sky-300**; black = system → **slate-200**; red = attention → **rose-300 text / rose-500 stripe**; zero-by-rule → **slate-500 italic**; recipe `ƒ` / permanent pin glyphs unchanged; price-age dot → emerald-500 / amber-500.

## Themes in the mockup
`<html data-theme="floor">` (default) or `data-theme="light"` (the neutral review theme). Toggle in the demo bar or `?theme=light`. Every colour in `assets/mock.css` is a token; no hardcoded colours remain outside the two token blocks.
