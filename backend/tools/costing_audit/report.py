"""Report writers: one self-contained HTML (no CDN), CSV, JSON, and a short
Markdown summary suitable for a PR comment (ratified default 9)."""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .compare import RunReport, Cell

STATUS_ORDER = ["FLAG", "PRESENCE", "UNMAPPED", "EXPIRED", "NO_GOLDEN", "UNVERIFIABLE", "ACCEPTED", "PASS", "SKIP"]
STATUS_RANK = {s: i for i, s in enumerate(STATUS_ORDER)}


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def write_json(rep: RunReport, path: Path) -> None:
    Path(path).write_text(json.dumps(rep.to_dict(), indent=1, default=str), encoding="utf-8")


def write_csv(rep: RunReport, path: Path) -> None:
    cols = ["scenario_id", "sheet", "trailer_id", "trailer_name", "variant", "length", "width", "height",
            "section_excel", "section_mes", "excel_total", "mes_total", "variance_pct", "status", "reason",
            "likely_cause", "accepted_reason"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for c in rep.cells:
            w.writerow([c.scenario_id, c.sheet, c.trailer_id, c.trailer_name, c.variant, c.length, c.width, c.height,
                        c.section_excel, c.section_mes, c.excel_total, c.mes_total, c.variance_pct, c.status,
                        c.reason, c.likely_cause, (c.accepted or {}).get("reason")])


def _scenario_label(sid: str, c: Cell | None = None) -> str:
    tail = sid.split("~", 1)[1] if "~" in sid else sid
    return tail.replace("~", " ")


def write_markdown(rep: RunReport, path: Path, *, html_name: str | None = None) -> str:
    m = rep.golden_manifest or {}
    fp = (m.get("workbook") or {}).get("files") or {}
    lines = [f"## Costing audit — pack `{rep.pack}` — {'FAIL' if rep.exit_code else 'PASS'}", ""]
    lines.append(f"- Run: {rep.generated_at} · tolerance {rep.tolerance_pct} % · MES: {rep.mes_source}")
    lines.append(f"- Golden: {m.get('generated_at', '?')} · workbook month {m.get('workbook_month', '?')} · "
                 f"GRP sha256 `{(fp.get('GRP Costings 2018.xlsx') or '?')[:12]}` · {m.get('scenario_count', '?')} scenarios")
    counts = rep.counts
    lines.append("- Cells: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: STATUS_RANK.get(kv[0], 99))))
    if html_name:
        lines.append(f"- Full report: `{html_name}` (CI artifact)")
    for w in rep.warnings:
        lines.append(f"- ⚠ {w}")
    failing = sorted(rep.failing, key=lambda c: (c.sheet, c.section_excel or c.section_mes or "", c.variant))
    if failing:
        lines += ["", f"### Unaccepted differences ({len(failing)})", "",
                  "| body | section | scenario | Excel | MES | var % | status | likely cause |", "|---|---|---|---:|---:|---:|---|---|"]
        for c in failing:
            lines.append(f"| {c.sheet.strip()} | {c.section_excel or c.section_mes} | {_scenario_label(c.scenario_id)} | "
                         f"{_fmt(c.excel_total)} | {_fmt(c.mes_total)} | {_fmt(c.variance_pct)} | {c.status}"
                         f"{(' ' + c.reason) if c.reason else ''} | {c.likely_cause or ''} |")
    unver = [c for c in rep.cells if c.status == "UNVERIFIABLE"]
    if unver:
        seen = {}
        for c in unver:
            seen.setdefault((c.sheet.strip(), c.section_excel, c.reason), 0)
            seen[(c.sheet.strip(), c.section_excel, c.reason)] += 1
        lines += ["", f"### Unverifiable ({len(unver)} cells)", ""]
        for (sheet, sec, reason), n in sorted(seen.items()):
            lines.append(f"- {sheet} · {sec} · {reason} ({n} scenarios)")
    for kind, title in (("known_defect", "Known defects — accepted, tracked, awaiting a work order"),
                        ("tolerated", "Tolerated differences")):
        acc = [c for c in rep.cells if c.status == "ACCEPTED" and (c.accepted or {}).get("kind", "tolerated") == kind]
        if not acc:
            continue
        seen = {}
        for c in acc:
            a = c.accepted or {}
            key = (c.sheet.strip(), c.section_excel or c.section_mes, a.get("reason"), a.get("review_by"))
            seen[key] = seen.get(key, 0) + 1
        lines += ["", f"### {title} ({len(acc)} cells)", ""]
        for (sheet, sec, reason, rb), n in sorted(seen.items()):
            lines.append(f"- {sheet} · {sec} · {reason} — review by {rb} ({n})")
    findings = {}
    for s in rep.scenarios:
        for f in s.findings:
            findings.setdefault((s.scenario["sheet"].strip(), f), 0)
            findings[(s.scenario["sheet"].strip(), f)] += 1
        for u in s.unmatched_flags:
            key = (s.scenario["sheet"].strip(), f"sheet flag {u!r} has no MES master (left at body default)")
            findings[key] = findings.get(key, 0) + 1
        for n in s.notes:
            key = (s.scenario["sheet"].strip(), n)
            findings[key] = findings.get(key, 0) + 1
    if findings:
        lines += ["", "### Oracle findings and probe notes", ""]
        for (sheet, f), n in sorted(findings.items()):
            lines.append(f"- {sheet}: {f} ({n})")
    text = "\n".join(lines) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    return text


_CSS = """
body{font:14px/1.4 system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f7f9;color:#1e2430}
header{background:#1e2430;color:#fff;padding:14px 20px}header h1{margin:0 0 6px;font-size:18px}
header .meta{font-size:12px;opacity:.85}header .meta span{margin-right:16px}
main{padding:16px 20px}table{border-collapse:collapse;background:#fff;font-size:13px}
th,td{border:1px solid #d9dde3;padding:4px 8px;text-align:left;vertical-align:top}th{background:#eef0f3}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.st{display:inline-block;min-width:74px;text-align:center;border-radius:3px;padding:1px 6px;font-weight:600;cursor:pointer}
.PASS{background:#d9f2e3;color:#146c3a}.FLAG{background:#fbd9d9;color:#a11a1a}.PRESENCE{background:#fbd9d9;color:#a11a1a}
.UNMAPPED{background:#fbd9d9;color:#a11a1a}.EXPIRED{background:#f6c4c4;color:#7a0d0d}.NO_GOLDEN{background:#f6c4c4;color:#7a0d0d}
.ACCEPTED{background:#e3e5e8;color:#555}.ACCEPTED.known_defect{background:#ffe0b3;color:#7a4a00}.UNVERIFIABLE{background:#ffe9c2;color:#8a5a00}.SKIP{background:#f6f7f9;color:#aaa}
.warn{background:#fff4d6;border:1px solid #f0c060;padding:8px 12px;margin:8px 0;border-radius:4px}
#detail{margin-top:18px}#detail h2,#detail h3{margin:14px 0 6px;font-size:15px}.muted{color:#777}
.counts span{margin-right:12px}.tri td.MISSING_IN_MES,.tri td.EXTRA_IN_MES{color:#a11a1a}
.tri td.PRICE_DIFF,.tri td.QTY_DIFF,.tri td.BOTH,.tri td.GROUP_DIFF{color:#8a5a00;font-weight:600}.tri td.STALE_LINK{color:#8a5a00}
pre{background:#fff;border:1px solid #d9dde3;padding:8px;font-size:12px;overflow:auto;max-height:280px}
"""

_JS = r"""
const D = window.__AUDIT__;
const rank = {FLAG:0,PRESENCE:1,UNMAPPED:2,EXPIRED:3,NO_GOLDEN:4,UNVERIFIABLE:5,ACCEPTED:6,PASS:7,SKIP:8};
const fmt = v => (v==null? '' : (typeof v==='number'? v.toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2}) : String(v)));
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function worst(cells){ let w='SKIP', k=''; for(const c of cells){ if((rank[c.status]??9) < (rank[w]??9)){ w=c.status; k=(c.accepted&&c.accepted.kind)||''; } } return w+(k?' '+k:''); }
function byScenario(){ const m={}; for(const c of D.cells){ (m[c.scenario_id] ||= []).push(c);} return m; }
function matrix(){
  const bs = byScenario(); const sheets=[]; const cols=[]; const grid={};
  for(const [sid, cells] of Object.entries(bs)){ const c=cells[0]; const lab=sid.includes('~')? sid.slice(sid.indexOf('~')+1).replace(/~/g,' ') : sid;
    if(!sheets.includes(c.sheet)) sheets.push(c.sheet); if(!cols.includes(lab)) cols.push(lab); grid[c.sheet+'|'+lab]={sid, st: worst(cells)}; }
  let h='<table><tr><th>body \\ scenario</th>'+cols.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr>';
  for(const s of sheets){ h+='<tr><th>'+esc(s.trim())+'</th>'; for(const col of cols){ const g=grid[s+'|'+col];
    h+= g? '<td><span class="st '+g.st+'" onclick="showScenario(\''+esc(g.sid)+'\')">'+g.st.split(' ')[0]+'</span></td>' : '<td></td>'; } h+='</tr>'; }
  return h+'</table>';
}
function showScenario(sid){
  const cells = D.cells.filter(c=>c.scenario_id===sid); const sc = (D.scenarios.find(s=>s.scenario.id===sid)||{});
  const s = sc.scenario||{}; let h='<h2>'+esc(sid)+'</h2>';
  h+='<div class="muted">door '+esc(s.door)+' · foam '+esc(s.foam)+' · gate '+esc(s.gate_mode)+' · panels '+esc(Object.entries(s.panels||{}).map(([k,v])=>k+':'+v.insulation+(v.thickness?('@'+v.thickness):'')).join(' '))+
     ' · Excel grand '+fmt(sc.excel_grand)+' · MES grand '+fmt(sc.mes_grand)+'</div>';
  if((sc.findings||[]).length) h+='<div class="warn">'+sc.findings.map(esc).join('<br>')+'</div>';
  if((sc.unmatched_flags||[]).length) h+='<div class="muted">sheet flags with no MES master: '+esc(sc.unmatched_flags.join(', '))+'</div>';
  h+='<table><tr><th>Excel section</th><th>MES section</th><th>Excel</th><th>MES</th><th>var %</th><th>status</th><th>likely cause</th></tr>';
  cells.forEach((c,i)=>{ h+='<tr><td>'+esc(c.section_excel)+'</td><td>'+esc(c.section_mes)+'</td><td class="num">'+fmt(c.excel_total)+'</td><td class="num">'+fmt(c.mes_total)+'</td><td class="num">'+fmt(c.variance_pct)+'</td>'+
    '<td><span class="st '+c.status+'" onclick="showTriage(\''+esc(sid)+'\','+i+')">'+c.status+'</span>'+(c.reason?' <span class="muted">'+esc(c.reason)+'</span>':'')+(c.accepted?'<div class="muted">accepted: '+esc(c.accepted.reason)+' ('+esc(c.accepted.owner)+', review '+esc(c.accepted.review_by)+')</div>':'')+'</td><td>'+esc(c.likely_cause)+'</td></tr>'; });
  h+='</table><div id="triage"></div><details><summary>MES payload</summary><pre>'+esc(JSON.stringify(sc.payload||{},null,1))+'</pre></details>';
  document.getElementById('detail').innerHTML=h; location.hash='#detail';
}
function showTriage(sid,i){
  const c = D.cells.filter(x=>x.scenario_id===sid)[i]; if(!c || !(c.triage||[]).length){ document.getElementById('triage').innerHTML='<p class="muted">no line triage (section within tolerance or not priced on both sides)</p>'; return; }
  let h='<h3>'+esc(c.section_excel||c.section_mes)+' — lines</h3><table class="tri"><tr><th>line</th><th>Excel qty</th><th>Excel price</th><th>Excel total</th><th>MES qty</th><th>MES price</th><th>MES total</th><th>Δ rand</th><th>class</th><th>MES formula</th></tr>';
  for(const t of c.triage){ h+='<tr><td>'+esc(t.desc)+'</td><td class="num">'+fmt(t.excel_qty)+'</td><td class="num">'+fmt(t.excel_price)+'</td><td class="num">'+fmt(t.excel_total)+'</td><td class="num">'+fmt(t.mes_qty)+'</td><td class="num">'+fmt(t.mes_price)+'</td><td class="num">'+fmt(t.mes_total)+'</td><td class="num">'+fmt(t.delta)+'</td><td class="'+t.cls+'">'+t.cls+(t.hint?' <b>'+esc(t.hint)+'</b>':'')+'</td><td class="muted">'+esc(t.mes_formula)+'</td></tr>'; }
  document.getElementById('triage').innerHTML=h+'</table>';
}
document.getElementById('matrix').innerHTML = matrix();
"""


def write_html(rep: RunReport, path: Path) -> None:
    m = rep.golden_manifest or {}
    fp = (m.get("workbook") or {}).get("files") or {}
    counts = " ".join(f'<span class="st {k}">{k} {v}</span>' for k, v in
                      sorted(rep.counts.items(), key=lambda kv: STATUS_RANK.get(kv[0], 99)))
    warns = "".join(f'<div class="warn">{html.escape(w)}</div>' for w in rep.warnings)
    verdict = "FAIL" if rep.exit_code else "PASS"
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>Costing audit — {html.escape(rep.pack)} — {verdict}</title>
<style>{_CSS}</style></head><body>
<header><h1>Costing audit · pack {html.escape(rep.pack)} · {verdict}</h1>
<div class="meta"><span>run {html.escape(rep.generated_at)}</span><span>tolerance {rep.tolerance_pct} %</span>
<span>MES: {html.escape(rep.mes_source)}</span><span>golden {html.escape(str(m.get('generated_at', '?')))}</span>
<span>workbook month {html.escape(str(m.get('workbook_month', '?')))}</span>
<span>GRP sha256 {html.escape((fp.get('GRP Costings 2018.xlsx') or '?')[:12])}</span>
<span>PRICE {html.escape((fp.get('PRICE 2017 MARCH.xlsx') or '?')[:12])}</span>
<span>FORMULAS {html.escape((fp.get('FORMULAS 2018.xls') or '?')[:12])}</span></div></header>
<main>{warns}<div class="counts">{counts}</div><p class="muted">Click a cell for the section table, a section status for its line triage.</p>
<div id="matrix"></div><div id="detail"></div></main>
<script>window.__AUDIT__ = {json.dumps(rep.to_dict(), default=str)};</script>
<script>{_JS}</script></body></html>"""
    Path(path).write_text(doc, encoding="utf-8")


def write_all(rep: RunReport, out_dir: Path, stem: str | None = None) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or f"costing_audit_{rep.pack}"
    paths = {"html": out_dir / f"{stem}.html", "csv": out_dir / f"{stem}.csv",
             "json": out_dir / f"{stem}.json", "md": out_dir / f"{stem}.md"}
    write_html(rep, paths["html"])
    write_csv(rep, paths["csv"])
    write_json(rep, paths["json"])
    write_markdown(rep, paths["md"], html_name=paths["html"].name)
    return paths
