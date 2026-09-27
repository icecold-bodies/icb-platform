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
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;display:flex;flex-direction:column;overflow:hidden;font:13px/1.4 system-ui,Segoe UI,Arial,sans-serif;background:#f6f7f9;color:#1e2430}
header{flex:none;background:#1e2430;color:#fff;padding:8px 16px}
header h1{margin:0 0 4px;font-size:16px}
header .meta{font-size:11.5px;opacity:.85}header .meta span{margin-right:14px;white-space:nowrap}
header .counts{margin-top:6px}header .counts .st{cursor:default;margin-right:6px}
.warn{background:#fff4d6;color:#5a4200;border:1px solid #f0c060;padding:4px 10px;margin:6px 0 0;border-radius:4px;font-size:12px}
#app{flex:1;min-height:0;display:flex;flex-direction:column}
#top{flex:none;height:50%;overflow:auto;background:#fff}
#divider{flex:none;height:9px;cursor:row-resize;background:#d9dde3;border-top:1px solid #c3c9d2;border-bottom:1px solid #c3c9d2;
  display:flex;align-items:center;justify-content:center;touch-action:none;user-select:none}
#divider::after{content:"";width:48px;height:3px;border-radius:2px;background:#8a93a3}
#divider:hover,#divider.drag{background:#c3c9d2}
#bottom{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr)}
#left,#right{overflow:auto;padding:8px 14px 16px;min-width:0}
#right{border-left:1px solid #d9dde3;background:#fbfbfc}
@media (max-width:640px){#bottom{grid-template-columns:1fr;grid-auto-rows:minmax(0,1fr)}#right{border-left:0;border-top:1px solid #d9dde3}}
table{border-collapse:separate;border-spacing:0;font-size:12.5px}
th,td{border-bottom:1px solid #e3e6ea;padding:3px 8px;text-align:left;vertical-align:top;white-space:nowrap}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
#grid table{width:100%}
#grid thead th{position:sticky;top:0;z-index:3;background:#eef0f3;border-bottom:1px solid #c3c9d2;font-weight:600}
#grid th.body{position:sticky;top:26px;z-index:2;background:#1e2430;color:#fff;font-weight:600;padding:5px 10px}
#grid td.dims{color:#1e2430;font-variant-numeric:tabular-nums;padding-left:22px}
#grid td.dims b{font-weight:600;margin-right:2px;color:#556070}
#grid td.cell{text-align:center}
#grid tr:hover td{background:#f4f6f9}
.st{display:inline-block;min-width:78px;text-align:center;border-radius:3px;padding:1px 6px;font-weight:600;font-size:11.5px;border:1px solid transparent}
#grid .st{cursor:pointer;scroll-margin-top:64px;scroll-margin-bottom:10px}
.st.sel{outline:2px solid #1e5bd6;outline-offset:1px}
.PASS{background:#d9f2e3;color:#146c3a}.FLAG,.PRESENCE,.UNMAPPED{background:#fbd9d9;color:#a11a1a}
.EXPIRED,.NO_GOLDEN{background:#f6c4c4;color:#7a0d0d}
.ACCEPTED{background:#e3e5e8;color:#555}.ACCEPTED.known_defect{background:#ffe0b3;color:#7a4a00}
.UNVERIFIABLE{background:#ffe9c2;color:#8a5a00}.SKIP{background:#f1f2f4;color:#9aa1ab}
.placeholder{color:#8a93a3;padding:18px 4px}
h2{font-size:14px;margin:2px 0 4px}h3{font-size:13.5px;margin:2px 0 4px}
.muted{color:#6b7482}.small{font-size:11.5px}
.sec tbody tr{cursor:pointer}.sec tbody tr:hover td{background:#f4f6f9}
.sec tbody tr.sel td{background:#e6eefc}
.sec td .why{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:260px;margin-top:1px}
.tri td{white-space:nowrap}.tri td.qpt{text-align:right;font-variant-numeric:tabular-nums}.tri td.qpt i{font-style:normal;color:#8a93a3}
.tri .f{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px;color:#6b7482;font-family:ui-monospace,Consolas,monospace;font-size:11px;margin-top:1px}
.tri tr.ok td,.tri tr.ok td.qpt i{color:#9aa1ab}.tri tr.ok .f{color:#b3b9c2}
.tri td.MISSING_IN_MES,.tri td.EXTRA_IN_MES{color:#a11a1a;font-weight:600}
.tri td.PRICE_DIFF,.tri td.QTY_DIFF,.tri td.BOTH,.tri td.GROUP_DIFF,.tri td.STALE_LINK{color:#8a5a00;font-weight:600}
.pos{color:#a11a1a}.neg{color:#1e5bd6}
details{margin-top:10px}pre{background:#fff;border:1px solid #d9dde3;padding:8px;font-size:11.5px;overflow:auto;max-height:240px}
"""

_JS = r"""
const D = window.__AUDIT__;
const RANK = {FLAG:0,PRESENCE:1,UNMAPPED:2,EXPIRED:3,NO_GOLDEN:4,UNVERIFIABLE:5,ACCEPTED:6,PASS:7,SKIP:8};
const VARIANT_ORDER = ['as_sheet','all_eps','all_pu','srd','drd','foam_4g'];
const SHORT = {UNVERIFIABLE:'UNVERIF.', NO_GOLDEN:'NO GOLDEN'};
const fmt = v => (v==null? '' : (typeof v==='number'? v.toLocaleString('en-ZA',{minimumFractionDigits:2,maximumFractionDigits:2}) : String(v)));
const esc = s => String(s==null?'':s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = v => (typeof v==='number' ? v : 0);
const q = v => (v==null? '' : (typeof v==='number'? v.toLocaleString('en-ZA',{maximumFractionDigits:3}) : String(v)));
function qpt(qty, price, total){
  if (qty==null && price==null && total==null) return '<i>—</i>';
  if (qty==null || price==null) return '<b>'+fmt(total)+'</b>';
  return q(qty)+' <i>×</i> '+fmt(price)+' <i>=</i> <b>'+fmt(total)+'</b>';
}
const $ = id => document.getElementById(id);

// ── index the report ───────────────────────────────────────────────────
const cellsBySid = {};
for (const c of D.cells) (cellsBySid[c.scenario_id] ||= []).push(c);
const scen = {};
for (const s of (D.scenarios||[])) scen[s.scenario.id] = s;
function scenarioOf(sid){
  const s = scen[sid]; if (s) return s.scenario;
  const c = (cellsBySid[sid]||[])[0] || {};
  return {id:sid, sheet:c.sheet||'?', variant:c.variant||'?', length:c.length, width:c.width, height:c.height};
}
function worst(cells){
  let w = null;
  for (const c of cells) if (!w || (RANK[c.status]??9) < (RANK[w.status]??9)) w = c;
  return w || {status:'SKIP'};
}
function kindOf(c){ return (c && c.accepted && c.accepted.kind) ? ' '+c.accepted.kind : ''; }
function tally(cells){
  const t = {}; for (const c of cells) t[c.status] = (t[c.status]||0)+1;
  return Object.entries(t).sort((a,b)=>(RANK[a[0]]??9)-(RANK[b[0]]??9)).map(([k,v])=>k+' '+v).join(' · ');
}

// bodies in report order; dimension rows sorted numerically; variant columns in canonical order
const bodies = [], byBody = {}, variants = [];
for (const sid of Object.keys(cellsBySid)){
  const s = scenarioOf(sid);
  if (!byBody[s.sheet]){ byBody[s.sheet] = {}; bodies.push(s.sheet); }
  const dk = [s.length, s.width, s.height].join('|');
  (byBody[s.sheet][dk] ||= {dims:[s.length, s.width, s.height], v:{}}).v[s.variant] = sid;
  if (!variants.includes(s.variant)) variants.push(s.variant);
}
variants.sort((a,b)=>{
  const ia = VARIANT_ORDER.indexOf(a), ib = VARIANT_ORDER.indexOf(b);
  return (ia<0?99:ia) - (ib<0?99:ib) || a.localeCompare(b);
});

// ── top half: the parameter grid ───────────────────────────────────────
function renderGrid(){
  let h = '<table><thead><tr><th>body · L × W × H (m)</th>' + variants.map(v=>'<th style="text-align:center">'+esc(v)+'</th>').join('') + '</tr></thead>';
  for (const b of bodies){
    const rows = Object.values(byBody[b]).sort((x,y)=>x.dims[0]-y.dims[0] || x.dims[1]-y.dims[1] || x.dims[2]-y.dims[2]);
    const all = rows.flatMap(r => Object.values(r.v).flatMap(sid => cellsBySid[sid]));
    h += '<tbody><tr><th class="body" colspan="'+(variants.length+1)+'">'+esc(b.trim())+' <span class="small" style="opacity:.75;font-weight:400;margin-left:10px">'+esc(tally(all))+'</span></th></tr>';
    for (const r of rows){
      h += '<tr><td class="dims"><b>L</b>'+esc(r.dims[0])+' &nbsp; <b>W</b>'+esc(r.dims[1])+' &nbsp; <b>H</b>'+esc(r.dims[2])+'</td>';
      for (const v of variants){
        const sid = r.v[v];
        if (!sid){ h += '<td class="cell muted">–</td>'; continue; }
        const cs = cellsBySid[sid], w = worst(cs), sr = scen[sid] || {};
        const tip = tally(cs) + (sr.excel_grand!=null ? '\nExcel grand '+fmt(sr.excel_grand)+' · MES grand '+fmt(sr.mes_grand) : '');
        h += '<td class="cell"><span class="st '+w.status+kindOf(w)+'" data-sid="'+esc(sid)+'" title="'+esc(tip)+'">'+esc(SHORT[w.status]||w.status)+'</span></td>';
      }
      h += '</tr>';
    }
    h += '</tbody>';
  }
  $('grid').innerHTML = h + '</table>';
}

// ── bottom-left: the scenario's section table ──────────────────────────
let current = null;
function showScenario(sid){
  current = sid;
  document.querySelectorAll('#grid .st.sel').forEach(e=>e.classList.remove('sel'));
  const el = document.querySelector('#grid .st[data-sid="'+CSS.escape(sid)+'"]'); if (el) el.classList.add('sel');
  const cells = cellsBySid[sid] || [], sr = scen[sid] || {}, s = scenarioOf(sid);
  let h = '<h2>'+esc(String(s.sheet).trim())+' · L '+esc(s.length)+' · W '+esc(s.width)+' · H '+esc(s.height)+' · '+esc(s.variant)+'</h2>';
  const panels = Object.entries(s.panels||{}).map(([k,v])=>k+' '+v.insulation+(v.thickness?(' '+v.thickness):'')).join(', ');
  h += '<div class="muted small">door '+esc(s.door)+' · foam '+esc(s.foam)+(panels?' · '+esc(panels):'')+'</div>';
  h += '<div class="small" style="margin:2px 0 6px">Excel grand <b>'+fmt(sr.excel_grand)+'</b> · MES grand <b>'+fmt(sr.mes_grand)+'</b>'+
       (sr.excel_grand!=null && sr.mes_grand!=null ? ' · Δ <b class="'+(num(sr.mes_grand)-num(sr.excel_grand)>=0?'pos':'neg')+'">'+fmt(num(sr.mes_grand)-num(sr.excel_grand))+'</b>' : '')+'</div>';
  if ((sr.findings||[]).length) h += '<div class="warn">'+sr.findings.map(esc).join('<br>')+'</div>';
  if ((sr.unmatched_flags||[]).length) h += '<div class="muted small">sheet flags with no MES master: '+esc(sr.unmatched_flags.join(', '))+'</div>';
  h += '<table class="sec" style="margin-top:6px"><thead><tr><th>section</th><th class="num">Excel</th><th class="num">MES</th><th class="num">Δ rand</th><th class="num">var %</th><th>status</th></tr></thead><tbody>';
  cells.forEach((c,i)=>{
    const name = c.section_excel || c.section_mes, alias = (c.section_mes && c.section_excel && c.section_mes !== c.section_excel) ? '<div class="muted small">MES: '+esc(c.section_mes)+'</div>' : '';
    const d = (c.excel_total!=null || c.mes_total!=null) ? num(c.mes_total)-num(c.excel_total) : null;
    const whyTxt = [c.reason, c.likely_cause].filter(Boolean).join(' · ');
    const why = whyTxt ? '<div class="why muted small" title="'+esc(whyTxt)+'">'+esc(whyTxt)+'</div>' : '';
    const acc = '';   // the accepted reason is shown in full on the right when the section is selected
    h += '<tr data-i="'+i+'"><td>'+esc(name)+alias+'</td><td class="num">'+fmt(c.excel_total)+'</td><td class="num">'+fmt(c.mes_total)+'</td>'+
         '<td class="num '+(d==null||Math.abs(d)<0.005?'':(d>0?'pos':'neg'))+'">'+(d==null?'':fmt(d))+'</td><td class="num">'+fmt(c.variance_pct)+'</td>'+
         '<td><span class="st '+c.status+kindOf(c)+'">'+esc(SHORT[c.status]||c.status)+'</span>'+why+acc+'</td></tr>';
  });
  h += '</tbody></table><details><summary class="small">MES payload</summary><pre>'+esc(JSON.stringify(sr.payload||{},null,1))+'</pre></details>';
  $('left').innerHTML = h;
  $('left').scrollTop = 0;
  // open the most interesting section on the right: an unaccepted one first, then any other difference
  const RED = ['FLAG','PRESENCE','UNMAPPED','EXPIRED','NO_GOLDEN'];
  let pick = cells.findIndex(c => RED.includes(c.status));
  if (pick < 0) pick = cells.findIndex(c => !['PASS','SKIP'].includes(c.status) && (c.triage||[]).length);
  if (pick < 0) pick = cells.findIndex(c => !['PASS','SKIP'].includes(c.status));
  showSection(pick < 0 ? 0 : pick);
}

// ── bottom-right: the section's lines ──────────────────────────────────
function showSection(i){
  const cells = cellsBySid[current] || [], c = cells[i];
  document.querySelectorAll('#left tr.sel').forEach(e=>e.classList.remove('sel'));
  const row = document.querySelector('#left tr[data-i="'+i+'"]'); if (row) row.classList.add('sel');
  if (!c){ $('right').innerHTML = '<div class="placeholder">No sections in this scenario.</div>'; return; }
  let h = '<h3>'+esc(c.section_excel || c.section_mes)+' <span class="st '+c.status+kindOf(c)+'" style="margin-left:6px">'+esc(SHORT[c.status]||c.status)+'</span></h3>';
  h += '<div class="small" style="margin-bottom:6px">Excel <b>'+fmt(c.excel_total)+'</b> · MES <b>'+fmt(c.mes_total)+'</b>'+(c.variance_pct!=null?' · '+fmt(c.variance_pct)+' %':'')+
       (c.likely_cause?' · likely cause: <b>'+esc(c.likely_cause)+'</b>':'')+'</div>';
  if (c.accepted) for (const a of [c.accepted, ...(c.accepted.also||[])])
    h += '<div class="warn">'+(a.kind==='known_defect'?'Known defect':'Accepted')+': '+esc(a.reason)+' — '+esc(a.owner)+', review by '+esc(a.review_by)+'</div>';
  const tri = c.triage || [];
  if (!tri.length){
    h += '<div class="placeholder">'+(c.status==='PASS'?'Within tolerance — the line comparison is only recorded for sections that differ.'
         : c.status==='SKIP'?'Not priced on either side in this scenario.'
         : c.status==='UNVERIFIABLE'?'The workbook cannot price this section ('+esc(c.reason)+'), so there is nothing to compare.'
         : 'No line comparison recorded.')+'</div>';
  } else {
    const order = t => (t.cls==='OK'?1:0);
    const rows = tri.map((t,k)=>[t,k]).sort((a,b)=>order(a[0])-order(b[0]) || Math.abs(num(b[0].delta))-Math.abs(num(a[0].delta)) || a[1]-b[1]);
    h += '<table class="tri"><thead><tr><th>line</th><th class="num">Excel &nbsp;qty × price = total</th><th class="num">MES &nbsp;qty × price = total</th>'+
         '<th class="num">Δ rand</th><th>class</th></tr></thead><tbody>';
    for (const [t] of rows){
      const d = num(t.delta);
      h += '<tr class="'+(t.cls==='OK'?'ok':'')+'"><td>'+esc(t.desc)+(t.mes_formula?'<span class="f" title="MES quantity formula">'+esc(t.mes_formula)+'</span>':'')+'</td>'+
           '<td class="qpt">'+qpt(t.excel_qty, t.excel_price, t.excel_total)+'</td><td class="qpt">'+qpt(t.mes_qty, t.mes_price, t.mes_total)+'</td>'+
           '<td class="num '+(Math.abs(d)<0.005?'':(d>0?'pos':'neg'))+'">'+fmt(t.delta)+'</td><td class="'+t.cls+'">'+esc(t.cls)+(t.hint?' <b>'+esc(t.hint)+'</b>':'')+'</td></tr>';
    }
    h += '</tbody></table><div class="muted small" style="margin-top:6px">Differing lines first, largest rand difference first; matching lines greyed. The grey text under a line is its MES quantity formula.</div>';
  }
  $('right').innerHTML = h;
  $('right').scrollTop = 0;
}

// ── wiring ─────────────────────────────────────────────────────────────
$('grid').addEventListener('click', e => { const t = e.target.closest('.st[data-sid]'); if (t) showScenario(t.dataset.sid); });
$('left').addEventListener('click', e => { if (e.target.closest('details')) return; const r = e.target.closest('tr[data-i]'); if (r) showSection(+r.dataset.i); });

// draggable divider; the split is remembered per browser (never required: storage may be blocked)
const KEY = 'costingAudit.split';
function setSplit(frac){
  frac = Math.min(0.85, Math.max(0.15, frac));
  $('top').style.height = (frac*100).toFixed(2)+'%';
  return frac;
}
let split = 0.5;
try { const v = parseFloat(localStorage.getItem(KEY)); if (v > 0 && v < 1) split = v; } catch(e) {}
setSplit(split);
const div = $('divider');
div.addEventListener('pointerdown', e => {
  e.preventDefault(); div.setPointerCapture(e.pointerId); div.classList.add('drag');
  const app = $('app').getBoundingClientRect();
  const move = ev => { split = setSplit((ev.clientY - app.top) / app.height); };
  const up = () => { div.classList.remove('drag'); div.removeEventListener('pointermove', move); div.removeEventListener('pointerup', up);
                     try { localStorage.setItem(KEY, String(split)); } catch(e) {} };
  div.addEventListener('pointermove', move); div.addEventListener('pointerup', up);
});
div.addEventListener('dblclick', () => { split = setSplit(0.5); try { localStorage.setItem(KEY, '0.5'); } catch(e) {} });

renderGrid();
// open on the first unaccepted difference (what needs action), else the first non-PASS scenario
const first = bodies.flatMap(b => Object.values(byBody[b]).sort((x,y)=>x.dims[0]-y.dims[0]||x.dims[1]-y.dims[1]||x.dims[2]-y.dims[2])
  .flatMap(r => variants.map(v => r.v[v]).filter(Boolean)));
const FAILING = ['FLAG','PRESENCE','UNMAPPED','EXPIRED','NO_GOLDEN'];
const start = first.find(sid => FAILING.includes(worst(cellsBySid[sid]).status))
           || first.find(sid => !['PASS','SKIP'].includes(worst(cellsBySid[sid]).status)) || first[0];
if (start){
  showScenario(start);
  const el = document.querySelector('#grid .st.sel'); if (el) el.scrollIntoView({block:'nearest'});
}
"""


def write_html(rep: RunReport, path: Path) -> None:
    m = rep.golden_manifest or {}
    fp = (m.get("workbook") or {}).get("files") or {}
    counts = " ".join(f'<span class="st {k}">{k} {v}</span>' for k, v in
                      sorted(rep.counts.items(), key=lambda kv: STATUS_RANK.get(kv[0], 99)))
    warns = "".join(f'<div class="warn">{html.escape(w)}</div>' for w in rep.warnings)
    verdict = "FAIL" if rep.exit_code else "PASS"
    # the report data rides in a <script>; a "</" inside any string must not close it
    data = json.dumps(rep.to_dict(), default=str).replace("</", "<\\/")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Costing audit — {html.escape(rep.pack)} — {verdict}</title>
<style>{_CSS}</style></head><body>
<header><h1>Costing audit · pack {html.escape(rep.pack)} · {verdict}</h1>
<div class="meta"><span>run {html.escape(rep.generated_at)}</span><span>tolerance {rep.tolerance_pct} %</span>
<span>MES: {html.escape(rep.mes_source)}</span><span>golden {html.escape(str(m.get('generated_at', '?')))}</span>
<span>workbook month {html.escape(str(m.get('workbook_month', '?')))}</span>
<span>GRP sha256 {html.escape((fp.get('GRP Costings 2018.xlsx') or '?')[:12])}</span>
<span>PRICE {html.escape((fp.get('PRICE 2017 MARCH.xlsx') or '?')[:12])}</span>
<span>FORMULAS {html.escape((fp.get('FORMULAS 2018.xls') or '?')[:12])}</span></div>
<div class="counts">{counts}</div>{warns}</header>
<div id="app">
<section id="top" aria-label="Scenarios tested"><div id="grid"></div></section>
<div id="divider" role="separator" aria-orientation="horizontal" title="Drag to resize · double-click to reset"></div>
<section id="bottom">
<div id="left" aria-label="Sections"><div class="placeholder">Click a result above to see its sections here.</div></div>
<div id="right" aria-label="Lines"><div class="placeholder">Click a section on the left to see its lines here.</div></div>
</section></div>
<script>window.__AUDIT__ = {data};</script>
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
