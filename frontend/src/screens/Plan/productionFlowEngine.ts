// @ts-nocheck
/* A06 Production Flow — the approved mockup's ENGINE, ported verbatim (Rapid Prototype Phase).
   Source of truth: "A06 - Production Flow v0.3 (job detail).html". Deliberate transforms ONLY:
   - everything is scoped to the mount root (no document-level ids/listeners leak into the MES)
   - image paths resolve to /static/plan/ (the shipped raster assets)
   - body/chassis images get explicit inline sizes (Tailwind's preflight img reset would
     otherwise fight the width/height attributes the mockup relies on)
   - drag ghosts + shockwave rings append to the root (kept inside the .a06-flow CSS scope)
   - initProductionFlow(root) returns a cleanup for React unmount
   Behaviour, state machine, timings, copy: UNCHANGED. Do not "improve" logic here. */

const A = (f) => '/static/plan/' + f;

const SHELL = `
<div class="app">

  <div class="hdr">
    <div class="mark" title="Icecold Bodies — Range Rhino 2.0"><svg viewBox="0 0 104 84"><polygon points="6,16 34,42 22,50" fill="#141414"/><polygon points="6,16 34,42 27,38" fill="#E2231A"/><polygon points="40,40 50,18 57,40" fill="#141414"/><polygon points="62,40 68,26 74,42" fill="#141414"/><polygon points="22,50 34,42 60,40 78,52 66,70 36,70 24,62" fill="#E2231A"/><polygon points="24,62 36,70 66,70 60,60 38,58" fill="#B81B16"/><polygon points="34,42 60,40 58,52 40,52" fill="#F2F2F2" opacity=".9"/><circle cx="46" cy="52" r="3.4" fill="#141414"/></svg></div>
    <div class="brand"><h1>Production Flow</h1><div class="sub"><b style="color:var(--brand-red);font-weight:800">ICECOLD</b> BODIES · Kempton Park · click any card for full job detail</div></div>
    <div class="spacer"></div>
    <button class="flat-btn" id="resetBtn" title="Restore the starting layout">↺ Reset</button>
  </div>

  <div class="kpis" id="kpiRow"></div>

  <div class="zone">
    <div class="zhead"><span class="zt">Panels ready</span><span class="zc">from Vacuum / Press</span><span class="zr">drag a panel-set down into a bay ↓ · click for detail</span></div>
    <div class="strip" id="panels"></div>
  </div>

  <div class="zone">
    <div class="zhead"><span class="zt">Pre-Assembly → Merge</span><span class="zc">body builds along the track; the planner brings it &amp; its chassis into the Merge block</span><span class="zr">drag the ready assembly into Merge, then its chassis ↓</span></div>
    <div id="preRows"></div>
  </div>

  <div class="zone">
    <div class="zhead"><span class="zt">Parking</span><span class="zc">chassis booked-in, awaiting their body</span><span class="zr">drag a chassis up ↑ into its line's Merge block · click for detail</span></div>
    <div class="strip" id="parking"></div>
  </div>

  <div class="hint"><span>✋</span><span>Drag a <b>panel-set</b> into a bay to start a body, build it down the track, then — when <b>you</b> deem it ready — drag the <b>assembly</b> into its Merge block and bring its <b>chassis</b> up to meet it (they attach on matching job; no auto-merge). <b>Click any card</b> for the full job detail. <b>↺ Reset</b> restores the start.</span></div>
  <div class="foot" id="foot"></div>
</div>

<!-- JOB DETAIL MODAL -->
<div class="scrim" id="scrim"></div>
<aside class="modal" id="modal">
  <div class="mh">
    <div class="top">
      <div><div class="kind" id="mKind"></div><div class="num" id="mNum"></div><div class="meta" id="mMeta"></div><div class="job" id="mJob"></div></div>
      <button class="x" id="mClose">✕</button>
    </div>
    <div class="tabs" id="mTabs"></div>
  </div>
  <div class="mbody" id="mBody"></div>
</aside>
`;

const STATUS = {
  green: { label: 'On schedule', edge: '#0F9D7A', fill: 'rgba(16,157,122,.22)' },
  amber: { label: 'Attention', edge: '#D97706', fill: 'rgba(217,119,6,.22)' },
  red: { label: 'Delayed', edge: '#DC4A3D', fill: 'rgba(220,74,61,.20)' },
  grey: { label: 'Waiting', edge: '#64748B', fill: 'rgba(100,116,139,.18)' }
};
const TPAD = 0; /* body image has no internal coupling margin -> body left = padL + pos*PX */

/* Body on the assembly track = the supplied top-view image. It starts all-white (empty) and
   fills GREEN left->right by build progress: prog 0 = white, prog 1 (front edge at Merge) = full green. */
function renderTrailer(o) {
  const len = o.lengthM, prog = Math.max(0, Math.min(1, o.progress || 0));
  const px = o.pxPerM || 26, bh = o.bodyH || 42;
  const bodyW = Math.round(len * px), pct = (prog * 100).toFixed(1);
  const sc = o.status === 'amber' ? ' b-attn' : (o.status === 'red' ? ' b-late' : '');
  return `<div class="bodyimg${sc}" style="width:${bodyW}px;height:${bh}px">
    <img class="bi-empty" src="${A('Body%20top%20view%20-%20empty.png')}" style="width:${bodyW}px;height:${bh}px;max-width:none" draggable="false">
    <div class="bi-fill" style="width:${pct}%"><img src="${A('Body%20top%20view%20-%20full.png')}" style="width:${bodyW}px;height:${bh}px;max-width:none" draggable="false"></div>
  </div>`;
}
function chassisSvg(w) { w = w || 120; return `<img src="${A('Chassis%203.png')}" style="display:block;height:auto;max-width:100%;width:${w}px" alt="chassis top view">`; }
function truckSvg(w) { w = w || 140; return `<img src="${A('Truck.png')}" style="display:block;height:auto;max-width:100%;width:${w}px" alt="truck chassis">`; }
function trailerSvg(w) { w = w || 140; return `<img src="${A('Chassis%202.png')}" style="display:block;height:auto;max-width:100%;width:${w}px" alt="trailer chassis">`; }

const CHUTE = 40, NPOS = 4, PX = 26, BODYH = 42, LANEH = 80;
const POS = ['Entry', 'Pre-Assembly', 'Stage 2', 'Stage 3'];
/* BOM line items — real SAP codes read from the MES Materials module */
const BOM = [
  ['GRP-MPS-A-0077', 'GRP panel skin 90mm white gel', '6 sheet', 'SA Composites'],
  ['PNL-FLR-100-BG', 'Floor panel 100mm bottom-grade', '1', 'SA Composites'],
  ['INS-PUR-50', 'PUR insulation 50mm sheet', '8 sheet', 'Lambda Insul.'],
  ['DOR-RR-2000', 'Rear roller door 2000mm', '1', 'Whiting SA'],
  ['EDG-ALU-3M', 'Aluminium edge profile 3m', '8', 'Wispeco'],
  ['GLU-2K-5L', '2K polyurethane glue 5L', '4', 'Sika SA'],
  ['RIV-A4-200', 'Aluminium rivet A4 200-pack', '3', 'Fastenal SA'],
  ['SUB-FRM-3200', 'Subframe 3200mm I-beam', '1', 'Macsteel'],
  ['FRZ-CT-380', 'Carrier Transicold 380 unit', '1', 'Carrier SA'],
  ['PNT-WHT-PRO', 'White automotive paint 20L', '1', 'Plascon SA']
];
function S0() {
  return {
    PANELS: [
      { id: 'PS-41030', job: '41030', cust: 'AFRIT (Pty) Ltd', len: 5.4, type: 'Chiller', method: 'Vacuum', ready: true },
      { id: 'PS-41040', job: '41040', cust: 'AGRING Consultants CC', len: 5.4, type: 'Chiller', method: 'Vacuum', ready: true },
      { id: 'PS-41070', job: '41070', cust: 'Chilleweni Cold Storage', len: 6.0, type: 'Freezer', method: 'Press', ready: true },
      { id: 'PS-41051', job: '41051', cust: 'Amcotts Trading (VAT)', len: 5.4, type: 'Chiller', method: 'Vacuum', ready: false }
    ],
    PRE: [
      { id: 'Bay 1', bodies: [{ id: '40401', job: '40401', cust: 'Chilleweni Cold Storage', len: 5.4, type: 'Chiller', status: 'green', prog: .55, pos: 18, days: 2, chassisVin: 'DEMV436A000000401' }], merge: { chassis: null, assembly: null, attached: null } },
      { id: 'Bay 2', bodies: [{ id: '40402', job: '40402', cust: 'DIE GROENE OASE', len: 6.0, type: 'Freezer', status: 'amber', prog: .40, pos: 12, days: 4, issue: 'Awaiting roof panel', chassisVin: 'DEMV436A000000402' }], merge: { chassis: null, assembly: null, attached: null } },
      { id: 'Bay 3', bodies: [], merge: { chassis: null, assembly: null, attached: null } },
      { id: 'Bay 4', bodies: [{ id: '40500', job: '40500', cust: 'DJW Boerdery Vervoer', len: 5.4, type: 'Chiller', status: 'green', prog: .97, pos: 33.5, days: 3, chassisVin: 'DEMV436A000000500' }], merge: { chassis: null, assembly: null, attached: null } },
      { id: 'Bay 5', bodies: [], merge: { chassis: null, assembly: null, attached: null } }
    ],
    PARK: [
      { id: 'DEMV436A000000401', cust: 'Chilleweni Cold Storage', model: 'Hino FVR 900', job: '40401', kind: 'truck' },
      { id: 'DEMV436A000000402', cust: 'DIE GROENE OASE', model: 'Isuzu FVR 900', job: '40402', kind: 'truck' },
      { id: 'DEMV436A000000500', cust: 'DJW Boerdery Vervoer', model: 'Hino FVR 900', job: '40500', kind: 'truck' },
      { id: 'DEMV436T000000071', cust: 'Unitrans', model: 'Afrit drawbar trailer', job: '41095', kind: 'trailer' },
      { id: 'DEMV436T000000072', cust: 'Vector Logistics', model: 'Henred tri-axle', job: '41096', kind: 'trailer' },
      { id: 'DEMV436A000000940', cust: '—', model: 'FAW 28.380 FVR 900', job: null, kind: 'truck' }
    ]
  };
}

export function initProductionFlow(root) {
  root.innerHTML = SHELL;
  const $ = (sel) => root.querySelector(sel);
  const $$ = (sel) => root.querySelectorAll(sel);

  let D = S0();

  function occPos(bodies) { const o = [false, false, false, false]; bodies.forEach(x => { const a = x.pos, b = x.pos + x.len; for (let p = 0; p < NPOS; p++) { if (a < (p + 1) * 10 && b > p * 10) o[p] = true; } }); return o; }
  function bayState(b) {
    const occ = occPos(b.bodies); const delay = b.bodies.some(x => x.status === 'amber' || x.status === 'red');
    let key, lbl, col;
    if (b.merge.attached) { key = 'done'; lbl = 'Merge complete'; col = '#0F9D7A'; }
    else if (b.merge.assembly) { key = 'busy'; lbl = 'Busy with merge'; col = '#2563EB'; }
    else if (!b.bodies.length) { key = 'avail'; lbl = 'Available'; col = '#94A3B8'; }
    else if (delay) { key = 'attn'; lbl = 'Attention'; col = STATUS.amber.edge; }
    else { key = 'flow'; lbl = 'Building'; col = STATUS.green.edge; }
    return { occ, key, lbl, col };
  }
  function findFreePos(others, len, desired) {
    const max = CHUTE - len; desired = Math.max(0, Math.min(max, desired));
    const occ = others.map(o => [o.pos, o.pos + o.len]).sort((a, b) => a[0] - b[0]); const gaps = []; let cur = 0;
    for (const iv of occ) { if (iv[0] - cur >= len) gaps.push([cur, iv[0] - len]); cur = Math.max(cur, iv[1]); }
    if (CHUTE - cur >= len) gaps.push([cur, CHUTE - len]); if (!gaps.length) return null;
    let best = null, bd = 1e9; for (const g of gaps) { const p = Math.max(g[0], Math.min(g[1], desired)); const d = Math.abs(p - desired); if (d < bd) { bd = d; best = p; } } return best;
  }
  function applyStageFill(b) { if (b.status === 'green') { b.prog = Math.max(0, Math.min(1, b.pos / (CHUTE - b.len))); } }
  function readyBody(b) { return b.bodies.find(x => x.prog >= .95); }
  function vinTag(v) { return v && v !== '—' ? 'DEMV…' + String(v).slice(-3) : 'awaiting'; }
  function findBodyLoc(id) { for (let ci = 0; ci < D.PRE.length; ci++) { const bi = D.PRE[ci].bodies.findIndex(b => b.id === id); if (bi >= 0) return { ci, bi, body: D.PRE[ci].bodies[bi] }; } return null; }
  function findAssembly(id) { const l = findBodyLoc(id); if (l) return { loc: 'track', ci: l.ci, body: l.body }; for (let li = 0; li < D.PRE.length; li++) { const a = D.PRE[li].merge.assembly; if (a && a.id === id) return { loc: 'merge', li, body: a }; } return null; }
  function assemblyBackToTrack(id, targetLi, desired) { for (let li = 0; li < D.PRE.length; li++) { const m = D.PRE[li].merge; if (m.assembly && m.assembly.id === id) { const body = m.assembly; const pos = findFreePos(D.PRE[targetLi].bodies, body.len, desired != null ? desired : (body.pos || 0)); if (pos == null) return false; m.assembly = null; body.pos = pos; D.PRE[targetLi].bodies.push(body); return true; } } return false; }

  function computeKPIs() {
    const inPre = D.PRE.reduce((s, b) => s + b.bodies.length, 0);
    const ready = D.PRE.flatMap(b => b.bodies).filter(x => x.prog >= .95).length;
    const done = D.PRE.filter(b => b.merge.attached).length;
    const panelsReady = D.PANELS.filter(p => p.ready).length;
    const avail = D.PRE.filter(b => !b.bodies.length && !b.merge.attached && !b.merge.assembly).length;
    return [
      { v: panelsReady, suf: '/ ' + D.PANELS.length, k: 'Panel sets ready' },
      { v: inPre, k: 'Bodies in pre-assembly' },
      { v: ready, k: 'Ready to merge', accent: ready > 0 ? STATUS.green.edge : null },
      { v: D.PARK.length, k: 'Chassis in parking' },
      { v: done, k: 'Body + chassis (done)', accent: done > 0 ? STATUS.green.edge : null },
      { v: avail, k: 'Available bays' }
    ];
  }
  function renderKPIs() {
    $('#kpiRow').innerHTML = computeKPIs().map(c => `
  <div class="kpi">${c.accent ? `<span class="accent" style="background:${c.accent}"></span>` : ''}
   <div class="v">${c.v}${c.suf ? ` <small>${c.suf}</small>` : ''}</div><div class="k">${c.k}</div></div>`).join('');
  }

  function renderPanels() {
    const el = $('#panels');
    if (!D.PANELS.length) { el.innerHTML = '<span class="empty">No panel-sets waiting — all started.</span>'; return; }
    el.innerHTML = D.PANELS.map(p => {
      const col = p.ready ? STATUS.green.edge : STATUS.amber.edge, methCol = p.method === 'Vacuum' ? '#475569' : '#7C3AED';
      return `<div class="pcard" data-id="${p.id}" data-kind="panel" data-ready="${p.ready ? 1 : 0}" ${p.ready ? '' : 'style="opacity:.6"'}>
      <span class="accent" style="background:${col}"></span>
      <div class="pt">${p.id}<span class="meth" style="background:${methCol}">${p.method}</span></div>
      <div class="ps">${p.len.toFixed(1)} m ${p.type} body</div>
      <div class="pf"><span class="dot" style="background:${col}"></span>${p.ready ? 'Panels cut · ready' : 'On ' + p.method + ' · not ready'} · ${p.cust}</div></div>`;
    }).join('');
  }

  function paLane(b, ci) {
    const st = bayState(b), padL = 12;
    let guides = ''; for (let i = 0; i < NPOS; i++) { const mx = padL + (CHUTE * (i / NPOS)) * PX; guides += `<div class="guide" style="left:${mx}px"></div><div class="glab" style="left:${mx}px">${POS[i]}</div>`; }
    let els = '';
    b.bodies.forEach(x => {
      const left = padL + x.pos * PX - TPAD;
      els += `<div class="btag" style="left:${padL + x.pos * PX}px;top:5px"><span class="bj">J${x.job}</span> <span class="bch">⛓ ${x.chassisVin && x.chassisVin !== '—' ? x.chassisVin : 'awaiting'}</span></div>`;
      els += `<div class="body-wrap" data-id="${x.id}" data-kind="body" style="left:${left}px">${renderTrailer({ lengthM: x.len, status: x.status, progress: x.prog, pxPerM: PX, bodyH: BODYH })}</div>`;
      if (x.prog >= .95) { const t = (LANEH - (BODYH + 6)) / 2; els += `<div class="ready-ring" style="left:${padL + x.pos * PX - 3}px;top:${t}px;width:${x.len * PX + 6}px;height:${BODYH + 6}px"></div>`; }
    });
    const empty = b.bodies.length || b.merge.attached || b.merge.assembly ? '' : `<div class="empty-note"><span class="o"></span>Available — drop a panel-set to start</div>`;
    const dotStyle = st.key === 'avail' ? `background:transparent;border:1.5px dashed ${st.col}` : `background:${st.col}`;
    const dots = st.occ.map(o => `<span class="pdot ${o ? 'on' : ''}"></span>`).join('');
    const m = b.merge; let cls = '', mc;
    if (m.attached) {
      cls = 'done'; const a = m.attached; const vin = (a.chassis && a.chassis.id) ? a.chassis.id : '—';
      mc = `<div class="mt" style="color:var(--green)">✓ Merge complete</div>
        <div class="mergedwrap"><div class="mglow"></div><img class="mergedimg" src="${A('Merged.png')}" alt="merged unit — body on chassis" draggable="false"><div class="mbadge">✓ MERGED</div></div>
        <div class="mmeta clk" data-detail-kind="body" data-detail-id="${a.body.id}">J${a.body.job} · ${vin} · ${a.matched ? '✓ same job' : 'attached'}</div>
        <div class="mdone">Done <span class="mdisp" data-dispatch="${ci}">→ QA</span></div>`;
    } else if (m.assembly && m.chassis) {
      cls = 'busy';
      mc = `<div class="mt" style="color:#2563EB">● Busy with merge</div><div class="busyrow"><div class="mbody mbodypic" data-id="${m.assembly.id}" data-kind="body"><img src="${A('Body%20only.png')}" style="width:100px" alt="assembled body" draggable="false"><span class="mbtag">J${m.assembly.job}</span></div><span class="plus">+</span><div class="cmerge clk" data-detail-kind="chassis" data-detail-id="${m.chassis.id}">${chassisSvg(118)}</div></div><button class="confirmbtn" data-confirm="${ci}">✓ Confirm merge complete</button>`;
    } else if (m.chassis) {
      cls = 'active';
      mc = `<div class="mt">Merge</div><div class="cabove"><span class="cvins">${m.chassis.id}</span> <span class="cbadge">AWAITING BODY</span></div><div class="cmerge cpull" data-kind="chassis" data-id="${m.chassis.id}">${chassisSvg(150)}</div><div class="msub">${m.chassis.model} · waiting — bring a body, or drag back to parking ↓</div>`;
    } else if (m.assembly) {
      cls = 'busy';
      mc = `<div class="mt" style="color:#2563EB">● Busy with merge</div><div class="mbody mbodypic" data-id="${m.assembly.id}" data-kind="body"><img src="${A('Body%20only.png')}" style="width:100px" alt="assembled body" draggable="false"><span class="mbtag">J${m.assembly.job} · ${m.assembly.len.toFixed(1)}m</span></div><div class="msub">bring chassis <b>${vinTag(m.assembly.chassisVin)}</b> ⤓, or drag back ↑</div>`;
    } else if (readyBody(b)) {
      cls = 'active'; const rb = readyBody(b);
      mc = `<div class="mt">Merge</div><div class="mready">J${rb.job} ready ✓</div><div class="msub">drag it in, then chassis <b>${vinTag(rb.chassisVin)}</b></div>`;
    } else {
      mc = `<div class="mt">Merge</div><div class="msub">body meets<br>chassis here</div>`;
    }
    return `<div class="pa-rail"><div class="bid">${b.id}</div>
      <div class="st" style="color:${st.col}"><span class="d" style="${dotStyle}"></span>${st.lbl}</div>
      <div class="dots">${dots}</div></div>
    <div class="pa-lane" data-bi="${ci}" style="height:${LANEH}px;border-left-color:${st.key === 'attn' ? STATUS.amber.edge : 'transparent'}">${guides}${empty}${els}</div>
    <div class="m-block ${cls}" data-merge="${ci}">${mc}</div>`;
  }
  function renderPre() { $('#preRows').innerHTML = D.PRE.map((b, i) => `<div class="pa-row">${paLane(b, i)}</div>`).join(''); }

  function renderPark() {
    const el = $('#parking');
    if (!D.PARK.length) { el.innerHTML = '<span class="empty">No chassis waiting.</span>'; return; }
    el.innerHTML = D.PARK.map(c => `<div class="ccard" data-id="${c.id}" data-kind="chassis">
     <div class="ctruck">${c.kind === 'trailer' ? trailerSvg(124) : truckSvg(112)}</div>
     <div class="cinfo"><div class="cid">${c.id}</div><div class="crow2"><span class="cmodel">${c.model}</span><span class="wpill">WAITING</span></div><div class="ckind">${c.kind === 'trailer' ? 'Trailer chassis' : 'Truck chassis'}</div></div></div>`).join('');
  }
  function renderAll() { renderKPIs(); renderPanels(); renderPre(); renderPark(); }

  /* ===== transitions (no auto-merge — planner brings both halves in) ===== */
  function startBody(panelId, li) {
    const pi = D.PANELS.findIndex(p => p.id === panelId); if (pi < 0) return false; const p = D.PANELS[pi]; if (!p.ready) return false;
    const pos = findFreePos(D.PRE[li].bodies, p.len, 0); if (pos == null) return false;
    D.PANELS.splice(pi, 1);
    D.PRE[li].bodies.push({ id: p.job, job: p.job, cust: p.cust, len: p.len, type: p.type, status: 'green', prog: 0, pos, days: 0, chassisVin: '—' });
    return true;
  }
  function moveBody(id, li, desired) {
    const loc = findBodyLoc(id); if (!loc) return false;
    const others = D.PRE[li].bodies.filter(b => b.id !== id);
    const p = findFreePos(others, loc.body.len, desired); if (p == null) return false;
    D.PRE[loc.ci].bodies.splice(loc.bi, 1); loc.body.pos = p; applyStageFill(loc.body); D.PRE[li].bodies.push(loc.body);
    return true; /* NO auto-merge */
  }
  function dropChassis(li, id) {
    const m = D.PRE[li].merge; if (m.attached || m.chassis) return false;
    const ci = D.PARK.findIndex(c => c.id === id); if (ci < 0) return false; const chassis = D.PARK[ci];
    if (m.assembly && m.assembly.job !== chassis.job) return false;  /* same job only */
    D.PARK.splice(ci, 1); m.chassis = chassis; return true; /* if assembly already here → Busy with merge (no auto-attach) */
  }
  function dropAssembly(id, li) {
    const m = D.PRE[li].merge; if (m.attached || m.assembly) return false;
    const loc = findBodyLoc(id); if (!loc || loc.ci !== li) return false; /* only its own line's merge */
    const body = loc.body;
    if (m.chassis && m.chassis.job !== body.job) return false;
    D.PRE[li].bodies.splice(loc.bi, 1); m.assembly = body; return true; /* if chassis already here → Busy with merge (no auto-attach) */
  }
  function dispatch(li) { D.PRE[li].merge.attached = null; renderAll(); }
  function confirmMerge(li) { const m = D.PRE[li].merge; if (m.assembly && m.chassis) { m.attached = { body: m.assembly, chassis: m.chassis, matched: m.chassis.job === m.assembly.job }; m.assembly = null; m.chassis = null; renderAll(); requestAnimationFrame(() => mergeCrescendo(li)); } }
  /* The Merge Crescendo: plays once, only when the planner confirms (classes are added here, not in render). */
  function mergeCrescendo(li) {
    const bay = root.querySelector('.m-block[data-merge="' + li + '"]'); if (!bay) return;
    const img = bay.querySelector('.mergedimg'), wrap = bay.querySelector('.mergedwrap'), badge = bay.querySelector('.mbadge');
    if (wrap) wrap.classList.add('lit'); if (img) img.classList.add('reveal'); if (badge) badge.classList.add('pop');
    const r = bay.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    [0, 170].forEach(d => { const ring = document.createElement('div'); ring.className = 'shockwave'; ring.style.left = cx + 'px'; ring.style.top = cy + 'px'; ring.style.animationDelay = d + 'ms'; root.appendChild(ring); setTimeout(() => ring.remove(), 1500 + d); });
  }
  function chassisInMerge(id) { for (let li = 0; li < D.PRE.length; li++) { const m = D.PRE[li].merge; if (m.chassis && m.chassis.id === id && !m.assembly) return li; } return -1; }
  function chassisBackToParking(id) { const li = chassisInMerge(id); if (li < 0) return false; D.PARK.push(D.PRE[li].merge.chassis); D.PRE[li].merge.chassis = null; return true; }

  /* ===== drag ===== */
  let drag = null;
  function onPointerDown(e) {
    const el = e.target.closest('.pcard,.body-wrap,.ccard,.mbody,.cpull'); if (!el) return;
    if (el.classList.contains('pcard') && el.dataset.ready === '0') return;
    drag = { id: el.dataset.id, kind: el.dataset.kind, el, fromPark: el.classList.contains('ccard'), sx: e.clientX, sy: e.clientY, moved: false, ghost: null };
    window.addEventListener('pointermove', onMove); window.addEventListener('pointerup', onUp); e.preventDefault();
  }
  function clearHi() { $$('.drop-ok').forEach(x => x.classList.remove('drop-ok')); }
  /* Show a guide highlight on the merge bay whose assembly (in merge or still on the track) matches this chassis's job. */
  function showMergeGuides(chassisId) {
    let c = D.PARK.find(x => x.id === chassisId);
    if (!c) { for (const b of D.PRE) { if (b.merge.chassis && b.merge.chassis.id === chassisId) { c = b.merge.chassis; break; } } }
    if (!c || !c.job) return;
    D.PRE.forEach((b, i) => {
      const m = b.merge; if (m.attached || m.chassis) return;
      const match = (m.assembly && m.assembly.job === c.job) || b.bodies.some(x => x.job === c.job);
      if (match) { const mb = root.querySelector('.m-block[data-merge="' + i + '"]'); if (mb) mb.classList.add('merge-guide'); }
    });
  }
  function clearMergeGuides() { $$('.merge-guide').forEach(x => x.classList.remove('merge-guide')); }
  function validTarget(kind, id, el) {
    if (!el) return null;
    if (kind === 'panel') { const l = el.closest('.pa-lane'); return l ? { t: 'pa', el: l, li: +l.dataset.bi } : null; }
    if (kind === 'body') {
      const mb = el.closest('.m-block');
      if (mb) {
        const li = +mb.dataset.merge; const loc = findBodyLoc(id);
        if (loc && loc.ci === li && !D.PRE[li].merge.attached && !D.PRE[li].merge.assembly) return { t: 'merge', el: mb, li }; return null;
      }
      const l = el.closest('.pa-lane'); return l ? { t: 'pa', el: l, li: +l.dataset.bi } : null;
    }
    if (kind === 'chassis') { const mb = el.closest('.m-block'); if (mb) { const li = +mb.dataset.merge; if (!D.PRE[li].merge.attached && !D.PRE[li].merge.chassis) return { t: 'merge', el: mb, li }; return null; } const pk = el.closest('#parking'); if (pk) return { t: 'park', el: pk }; return null; }
    return null;
  }
  function onMove(e) {
    if (!drag) return; const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy;
    if (!drag.moved && Math.hypot(dx, dy) > 4) {
      drag.moved = true; const r = drag.el.getBoundingClientRect(); drag.gdx = drag.sx - r.left; drag.gdy = drag.sy - r.top;
      const g = drag.el.cloneNode(true); g.classList.add('drag-ghost'); g.style.position = 'fixed'; g.style.left = r.left + 'px'; g.style.top = r.top + 'px'; g.style.width = r.width + 'px'; g.style.height = r.height + 'px';
      root.appendChild(g); drag.ghost = g; drag.el.classList.add('dragging');
      if (drag.kind === 'chassis' && drag.fromPark) showMergeGuides(drag.id);
    }
    if (drag.moved) {
      drag.ghost.style.left = (e.clientX - drag.gdx) + 'px'; drag.ghost.style.top = (e.clientY - drag.gdy) + 'px';
      clearHi(); const tgt = validTarget(drag.kind, drag.id, document.elementFromPoint(e.clientX, e.clientY)); if (tgt) tgt.el.classList.add('drop-ok');
    }
  }
  function onUp(e) {
    window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp);
    const d = drag; drag = null; if (!d) return; clearHi(); clearMergeGuides();
    if (!d.moved) { openModal(d.kind, d.id); return; }   /* a click → detail modal */
    if (d.ghost) d.ghost.remove();
    const tgt = validTarget(d.kind, d.id, document.elementFromPoint(e.clientX, e.clientY));
    if (tgt) {
      if (d.kind === 'panel' && tgt.t === 'pa') startBody(d.id, tgt.li);
      else if (d.kind === 'body' && tgt.t === 'pa') { const lr = tgt.el.getBoundingClientRect(); const desired = ((e.clientX - d.gdx) - lr.left - 12 + TPAD) / PX; const a = findAssembly(d.id); if (a && a.loc === 'merge') assemblyBackToTrack(d.id, tgt.li, desired); else moveBody(d.id, tgt.li, desired); }
      else if (d.kind === 'body' && tgt.t === 'merge') dropAssembly(d.id, tgt.li);
      else if (d.kind === 'chassis' && tgt.t === 'merge') dropChassis(tgt.li, d.id);
      else if (d.kind === 'chassis' && tgt.t === 'park') chassisBackToParking(d.id);
    }
    renderAll();
  }
  function onClick(e) {
    const cf = e.target.closest('[data-confirm]'); if (cf) { confirmMerge(+cf.dataset.confirm); return; }
    const dsp = e.target.closest('[data-dispatch]'); if (dsp) { dispatch(+dsp.dataset.dispatch); return; }
    const det = e.target.closest('[data-detail-kind]'); if (det) { openModal(det.dataset.detailKind, det.dataset.detailId); }
  }
  root.addEventListener('pointerdown', onPointerDown);
  root.addEventListener('click', onClick);
  $('#resetBtn').addEventListener('click', () => { D = S0(); renderAll(); });

  /* ===== JOB DETAIL MODAL ===== */
  function findAny(kind, id) {
    if (kind === 'panel') return D.PANELS.find(p => p.id === id);
    if (kind === 'chassis') { let c = D.PARK.find(x => x.id === id); if (c) return c; for (const b of D.PRE) { if (b.merge.chassis && b.merge.chassis.id === id) return b.merge.chassis; if (b.merge.attached && b.merge.attached.chassis.id === id) return b.merge.attached.chassis; } return null; }
    // body
    const l = findBodyLoc(id); if (l) return l.body;
    for (const b of D.PRE) { if (b.merge.assembly && b.merge.assembly.id === id) return b.merge.assembly; if (b.merge.attached && b.merge.attached.body.id === id) return b.merge.attached.body; }
    return null;
  }
  function getDetail(kind, it) {
    const isCh = kind === 'chassis';
    const job = it.job || '—', cust = it.cust || '—';
    const len = it.len || 5.4, type = it.type || 'Chiller';
    let ch;
    if (isCh) { ch = { vin: it.id, model: it.model, cust: it.cust, make: (it.model || '').split(' ')[0] }; }
    else { const m = D.PARK.find(c => c.job === job) || { id: '(awaiting assignment)', model: '—', make: '—' }; ch = { vin: m.id, model: m.model, cust, make: m.make || (m.model || '—').split(' ')[0] }; }
    return {
      kind, id: it.id, job, cust, spec: `${len.toFixed(1)} m ${type} body`,
      chassis: { vin: ch.vin, cust, dealer: '—', contact: '—', tel: '—', make: ch.make, model: ch.model, desc: '—', origin: 'Auto · Planning', cycles: 1, status: isCh ? 'in assembly' : 'awaiting attachment', vcl: '2026-06-18' },
      prejob: {
        template: `${type} body · ${len.toFixed(1)} m`, dims: `${Math.round(len * 1000)} × 2480 × 2600 mm`, costingRef: `EST-${job}`,
        checklist: [['Body template confirmed', 1], ['Dimensions vs customer spec', 1], ['Costing accepted', 1], ['Materials reserved', 1], ['Drawings released', 0]]
      },
      drawings: { ref: `GA-${type.slice(0, 3).toUpperCase()}-${Math.round(len * 1000)}-R3`, ver: 'Rev 3 · released 2026-06-15', sheets: ['General arrangement', 'Floor &amp; subframe', 'Door &amp; seal detail', 'Fridge unit mount'] },
      signoff: [['Costing / Estimating', 'Nadie', '2026-06-12', 'signed'], ['Planning', 'Simeon', '2026-06-14', 'signed'], ['Production / QC', 'Kenny', '—', 'pending']],
      vcl: {
        date: '2026-06-18', inspector: 'Simeon', odo: '12 480 km', fuel: '½ tank',
        checks: [['Cab &amp; windscreen', 'OK'], ['Lights &amp; indicators', 'OK'], ['Tyres &amp; rims', 'RH front worn'], ['Mirrors', 'OK'], ['Body / paintwork', '2 scratches LH door'], ['Battery &amp; electrics', 'OK']],
        dcl: 'Pending — captured at dispatch'
      }
    };
  }
  const TABS = [['chassis', 'Chassis'], ['bom', 'BOM'], ['prejob', 'Pre-Job'], ['drawings', 'Drawings'], ['signoff', 'Sign-off'], ['vcl', 'VCL']];
  let modalState = { d: null, tab: 'chassis' };
  function row(k, v) { return `<div class="frow"><span class="k">${k}</span><span class="v">${v}</span></div>`; }
  function renderTab(tab, d) {
    if (tab === 'chassis') {
      const c = d.chassis;
      return row('VIN', c.vin) + row('Customer', c.cust) + row('Dealer', c.dealer) + row('Contact', c.contact) + row('Telephone', c.tel) + row('Make', c.make) + row('Model', c.model) + row('Description', c.desc) + row('Origin', c.origin) + row('Cycles', c.cycles) + row('Status', c.status)
        + `<div class="sec-t">Lifecycle history</div>` + row('VCL captured', c.vcl) + row('Assembly assigned', '2026-06-27') + row('Current', 'Cycle 1 · in assembly');
    }
    if (tab === 'bom') {
      return `<div class="sec-t">Bill of materials · job ${d.job}</div><table class="bom"><tr><th>SAP code</th><th>Description</th><th>Qty</th></tr>` +
        BOM.map(r => `<tr><td class="code">${r[0]}</td><td>${r[1]}<div class="sup">${r[3]}</div></td><td>${r[2]}</td></tr>`).join('') +
        `</table><div class="msub" style="margin-top:10px;color:var(--ink-3);font-size:11px">Computed from the job BOM × planned start (MES Materials module). Stock &amp; PO status live in Materials.</div>`;
    }
    if (tab === 'prejob') {
      const p = d.prejob;
      return row('Body template', p.template) + row('Dimensions (L×W×H)', p.dims) + row('Costing ref', p.costingRef) +
        `<div class="sec-t">Pre-job checklist</div>` + p.checklist.map(c => `<div class="chk"><span class="b ${c[1] ? 'ok' : 'no'}">${c[1] ? '✓' : ''}</span>${c[0]}</div>`).join('');
    }
    if (tab === 'drawings') {
      const g = d.drawings;
      return row('Drawing ref', g.ref) + row('Version', g.ver) +
        `<div class="draw"><svg width="220" height="96" viewBox="0 0 220 96" fill="none"><rect x="14" y="20" width="150" height="56" rx="4" stroke="#94A3B8" stroke-width="1.4"/><rect x="18" y="24" width="142" height="48" rx="3" stroke="#CBD5E1" stroke-width="1"/><line x1="160" y1="20" x2="160" y2="76" stroke="#94A3B8" stroke-width="1.4"/><rect x="6" y="40" width="8" height="16" rx="1.5" stroke="#94A3B8" stroke-width="1.4"/><circle cx="50" cy="84" r="6" stroke="#94A3B8" stroke-width="1.4"/><circle cx="120" cy="84" r="6" stroke="#94A3B8" stroke-width="1.4"/><text x="80" y="52" font-size="9" fill="#94A3B8" text-anchor="middle">GA · ${d.spec}</text></svg><div class="msub" style="margin-top:6px">General arrangement (representative)</div></div>` +
        `<div class="sec-t">Sheets</div>` + g.sheets.map(s => `<div class="chk"><span class="b ok">▤</span>${s}</div>`).join('');
    }
    if (tab === 'signoff') {
      return `<div class="sec-t">Pre-job 3-role sign-off (v4.33)</div>` + d.signoff.map(s => `<div class="frow"><span class="k">${s[0]}<div style="font-size:11px;color:var(--ink-3)">${s[1]} · ${s[2]}</div></span><span class="v"><span class="pill ${s[3] === 'signed' ? 's' : 'p'}">${s[3]}</span></span></div>`).join('')
        + `<div class="msub" style="margin-top:12px;color:var(--ink-3);font-size:11px">Job starts once all three roles have signed.</div>`;
    }
    if (tab === 'vcl') {
      const v = d.vcl;
      return `<div class="sec-t">Vehicle Check List · book-in</div>` + row('Captured', v.date) + row('Inspector', v.inspector) + row('Odometer', v.odo) + row('Fuel', v.fuel) +
        `<div class="sec-t">Condition checks</div>` + v.checks.map(c => `<div class="frow"><span class="k">${c[0]}</span><span class="v" style="color:${/OK/.test(c[1]) ? 'var(--green)' : 'var(--amber)'}">${c[1]}</span></div>`).join('') +
        `<div class="vcl-photos"><div class="ph">photo</div><div class="ph">photo</div><div class="ph">photo</div></div>` +
        `<div class="sec-t">DCL (dispatch)</div><div class="msub" style="color:var(--ink-3)">${v.dcl}</div>`;
    }
    return '';
  }
  function paintModal() {
    const d = modalState.d; if (!d) return;
    $('#mKind').textContent = d.kind === 'chassis' ? 'Chassis' : (d.kind === 'panel' ? 'Panel-set' : 'Assembly');
    $('#mNum').textContent = d.id;
    $('#mMeta').textContent = `${d.cust} · ${d.spec}`;
    $('#mJob').textContent = `Job J${d.job}`;
    $('#mTabs').innerHTML = TABS.map(t => `<button class="tab ${modalState.tab === t[0] ? 'on' : ''}" data-tab="${t[0]}">${t[1]}</button>`).join('');
    $('#mBody').innerHTML = renderTab(modalState.tab, d);
  }
  function openModal(kind, id) {
    const it = findAny(kind, id); if (!it) return;
    modalState = { d: getDetail(kind, it), tab: 'chassis' };
    paintModal();
    $('#modal').classList.add('open'); $('#scrim').classList.add('show');
  }
  function closeModal() { $('#modal').classList.remove('open'); $('#scrim').classList.remove('show'); }
  $('#mClose').addEventListener('click', closeModal);
  $('#scrim').addEventListener('click', closeModal);
  $('#mTabs').addEventListener('click', e => { const t = e.target.closest('[data-tab]'); if (t) { modalState.tab = t.dataset.tab; paintModal(); } });

  $('#foot').innerHTML =
    `<b>A06 · Production Flow v0.4.</b> Upgraded visuals (component spec): trailer top-view with <b>4 stage-segments</b> + drawbar, top-view <b>ladder chassis</b>, AWAITING-BODY chassis cards, and the <b>full chassis VIN</b> on every assembly card. Merge per your rules (A07): <b>no auto-merge</b> — the planner drags the ready assembly into its Merge block and brings the chassis up; a block holds only a chassis <em>or</em> an assembly until its same-job partner arrives. <b>Click any card</b> (panel-set, assembly or chassis) for the full job detail — Chassis, BOM, Pre-Job, Drawings, Sign-off and VCL — built from the live MES data (read-only). Mocked locally; VCL = Vehicle Check List (book-in), DCL = dispatch.
 <div class="br"><b>RANGE RHINO 2.0</b> · Icecold Bodies · all data placeholder for the real records.</div>`;

  renderAll();

  /* cleanup for React unmount — remove root + any transient window listeners and DOM leftovers */
  return function cleanup() {
    root.removeEventListener('pointerdown', onPointerDown);
    root.removeEventListener('click', onClick);
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    if (drag && drag.ghost) drag.ghost.remove();
    drag = null;
    root.innerHTML = '';
  };
}
