/* ============================================================================
   New Costing UI — clickable mockup (§3.2). Static. No backend. Vanilla JS.
   One state object → one render(). Event delegation on data-act attributes.
   The "engine" here is a stand-in that reproduces the SHAPE of the real rules
   (gating, multiplier, 3.2 m rule, formula error, unpriced, sibling/master
   exclusion, money pipeline) so the page behaves — numbers are invented.
   ============================================================================ */
(function () {
  'use strict';
  const M = window.MOCK;
  const app = document.getElementById('app');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const R0 = (n) => Math.round(n);
  const fmtR = (n) => 'R ' + R0(n).toLocaleString('en-ZA').replace(/,/g, ' ');
  const fmtQ = (n) => (Math.round(n * 100) / 100).toLocaleString('en-US', { maximumFractionDigits: 2 });
  const body = () => M.BODIES.find((b) => b.id === S.bodyId);
  const stateEXISTING = M.EXISTING.map((e) => Object.assign({}, e));
  const REFS = M.REFS.map((r) => Object.assign({}, r, { identity: JSON.parse(JSON.stringify(r.identity)) }));
  const TEMPLATE_INS = {}; // body id → per-cat insulation template (mutable copy, for "save to template")
  M.BODIES.forEach((b) => { TEMPLATE_INS[b.id] = JSON.parse(JSON.stringify(b.insDefaults)); });

  // ---------------------------------------------------------------- state
  let S;
  let addSeq = 1;
  function freshState(bodyId, keep) {
    const b = M.BODIES.find((x) => x.id === bodyId) || M.BODIES[1];
    const fam = {};
    Object.values(b.families).flat().forEach((f) => { fam[f.key] = Array.isArray(f.def) ? f.def.slice() : f.def; });
    b.strip.forEach((f) => { fam[f.key] = Array.isArray(f.def) ? f.def.slice() : f.def; });
    return {
      role: keep ? keep.role : 'full',
      type: 'body', bodyId: b.id,
      dims: Object.assign({}, b.dims), margin: b.markup, ratio: 0.55,
      disc: { kind: 'percent', val: 0 },
      customer: keep ? keep.customer : null, contact: keep ? keep.contact : null,
      door: 'DRD',
      ins: JSON.parse(JSON.stringify(TEMPLATE_INS[b.id])),
      fam,
      excluded: new Set(), optOn: new Set(), collapsed: new Set(), lineOff: new Set(),
      qtyOv: {}, priceOv: {}, permPrice: {}, formulaBase: {},
      added: [],
      chassis: { on: false, length: null, axles: 2, lift: 0, tyre: 'dual', susp: 1, liftType: 1, brake: 1, tyreId: 1, rim: 1 },
      repair: { type: '', work: '' },
      saved: null, dirty: false, saveMode: null, reuse: true, ack: false,
      loadedRef: null,
      ui: { drawer: null, pendingExclude: null, assist: null, menu: null, savePop: false, rowMenu: null, toast: null, editing: null, focus: null, stockQ: '', stockAll: false, drawerData: {} },
    };
  }
  S = freshState(20);

  // ---------------------------------------------------------------- engine
  function geom(st) {
    const w = M.WASTE, L = +st.dims.L || 0, W = +st.dims.W || 0, H = +st.dims.H || 0;
    return {
      L, W, H, w,
      front: (W + w) * (H + w), side: (L + w) * (H + w), roof: (L + w) * (W + w),
      perim: 2 * L + W, len: L,
    };
  }
  const FTEXT = { front: '(width+{Waste})×(height+{Waste})', side: '(length+{Waste})×(height+{Waste})', roof: '(length+{Waste})×(width+{Waste})', perim: '(2×length+width)', len: 'length', const: '' };
  function baseQty(row, g) {
    const v = row.f === 'const' ? 1 : g[row.f];
    return v * (row.k == null ? 1 : row.k);
  }
  function rule32Active(st) { const b = M.BODIES.find((x) => x.id === st.bodyId); return b && /MEDIUM/.test(b.name) && Math.abs((+st.dims.L) - 3.2) < 1e-9; }

  function famHas(st, key, val) { const v = st.fam[key]; return Array.isArray(v) ? v.includes(val) : v === val; }

  function evalRow(st, sec, row, idx, g) {
    const key = sec.name + '#' + idx;
    const line = { key, row, sec, qty: 0, price: null, total: 0, state: 'costed', reason: '', prov: {} };
    // gating
    if (row.ins) { const s = st.ins[sec.name]; if (!s || s.side !== row.ins) { line.state = 'gated'; line.reason = sec.name + ' ' + row.ins + ' = N'; } }
    if (row.gate && !famHas(st, row.gate.fam, row.gate.val)) { line.state = 'gated'; line.reason = row.gate.val + ' = N'; }
    if (row.link && !famHas(st, 'LEGACY|DRD', row.link)) { line.state = 'gated'; line.reason = 'linked to ' + row.link; line.derived = true; }
    // quantity
    let q = baseQty(row, g) * (sec.mult || 1);
    if (row.rule32 && rule32Active(st)) { q = 0; if (line.state === 'costed') line.state = 'rule'; }
    if (row.err) { line.err = row.err; if (line.state === 'costed') line.state = 'err'; }
    line.formulaQty = q;
    if (st.qtyOv[key] != null && !row.err) { q = st.qtyOv[key]; line.prov.qtyTyped = true; if (st.formulaBase[key] != null && Math.abs(st.formulaBase[key] - line.formulaQty) > 1e-6) line.prov.qtyDelta = line.formulaQty; }
    line.qty = q;
    // price precedence: quote override > permanent(row/session) > insulation-scaled > catalogue
    let p = row.price;
    if (row.ins && st.ins[sec.name]) p = row.price * (st.ins[sec.name].mm / 60);
    if (row.perm != null) { p = row.perm; line.prov.perm = true; }
    if (st.permPrice[key] != null) { p = st.permPrice[key]; line.prov.perm = true; }
    if (row.recipe) line.prov.recipe = row.recipe;
    if (st.priceOv[key]) { p = st.priceOv[key].price; line.prov.priceTyped = st.priceOv[key].reason; }
    line.price = p;
    if (p == null) { if (line.state === 'costed') line.state = 'unpriced'; }
    if (row.age != null && !line.prov.priceTyped) line.prov.age = row.age;
    if (st.lineOff.has(key)) line.state = 'user-off';
    line.total = (line.state === 'costed' || line.state === 'rule') && p != null && !row.err ? q * p : 0;
    if (line.state === 'err' || line.state === 'unpriced') line.total = 0;
    return line;
  }
  function evalAdded(st, a) {
    const line = { key: a.key, added: a, sec: { name: a.section }, qty: a.qty, price: a.price, total: 0, state: 'costed', reason: '', prov: { stock: a.kind === 'stock', manual: a.kind === 'manual', age: a.age } };
    if (st.priceOv[a.key]) { line.price = st.priceOv[a.key].price; line.prov.priceTyped = st.priceOv[a.key].reason; }
    if (line.price == null) line.state = 'unpriced';
    if (st.lineOff.has(a.key)) line.state = 'user-off';
    line.total = line.state === 'costed' ? line.qty * line.price : 0;
    return line;
  }
  function bodyHasBothDoors(st) { const b = M.BODIES.find((x) => x.id === st.bodyId); return b.sections.some((s) => s.door === 'DRD') && b.sections.some((s) => s.door === 'SRD'); }
  function catState(st, sec) {
    if (sec.optional) return st.optOn.has(sec.name) ? 'included' : 'optional-off';
    if (sec.door && sec.door !== st.door && bodyHasBothDoors(st)) return 'sibling';
    if (sec.master && !famHas(st, sec.master.fam, sec.master.val)) return 'rule-off';
    if (st.excluded.has(sec.name)) return 'user-off';
    return 'included';
  }
  function chassisCalc(st) {
    const c = st.chassis, g = geom(st);
    if (!c.on) return { total: 0, lines: [] };
    const axles = +c.axles, lift = +c.lift, perAxle = c.tyre === 'super' ? 2 : 4;
    const tyres = (axles + lift) * perAxle;
    const pick = (arr, id) => arr.find((x) => x.id === +id);
    const L = c.length || g.L;
    const lines = [
      { name: pick(M.CHASSIS.suspension, c.susp).name, qty: axles, price: pick(M.CHASSIS.suspension, c.susp).price },
      { name: pick(M.CHASSIS.brake, c.brake).name, qty: axles, price: pick(M.CHASSIS.brake, c.brake).price },
      { name: pick(M.CHASSIS.tyre, c.tyreId).name, qty: tyres, price: pick(M.CHASSIS.tyre, c.tyreId).price },
      { name: pick(M.CHASSIS.rim, c.rim).name, qty: tyres, price: pick(M.CHASSIS.rim, c.rim).price },
    ];
    if (lift > 0) lines.push({ name: pick(M.CHASSIS.lift, c.liftType).name, qty: lift, price: pick(M.CHASSIS.lift, c.liftType).price });
    M.CHASSIS.constants.forEach((k) => { const q = k.perM * L + k.k; if (q > 0) lines.push({ name: k.name, qty: k.perM ? L : 1, price: k.perM ? k.perM : k.k }); });
    lines.forEach((l) => { l.total = l.qty * l.price; });
    return { total: lines.reduce((a, l) => a + l.total, 0), lines, tyres, kits: axles };
  }
  function compute(st) {
    const b = M.BODIES.find((x) => x.id === st.bodyId), g = geom(st);
    const cats = [];
    let materials = 0, attn = 0;
    if (st.type === 'body') {
      b.sections.forEach((sec) => {
        const state = catState(st, sec);
        const lines = sec.rows.map((r, i) => evalRow(st, sec, r, i, g)).concat(st.added.filter((a) => a.section === sec.name).map((a) => evalAdded(st, a)));
        const subtotal = lines.reduce((a, l) => a + l.total, 0);
        const removedLines = lines.filter((l) => l.state !== 'gated').length;
        const a = state === 'included' ? lines.filter((l) => l.state === 'unpriced' || l.state === 'err').length : 0;
        attn += a;
        if (state === 'included') materials += subtotal;
        cats.push({ sec, state, lines, subtotal, removedLines, attn: a });
      });
      const ch = chassisCalc(st);
      materials += ch.total;
      var chassis = ch;
    } else {
      const lines = st.added.map((a) => evalAdded(st, a));
      const subtotal = lines.reduce((a, l) => a + l.total, 0);
      attn = lines.filter((l) => l.state === 'unpriced').length;
      materials = subtotal;
      cats.push({ sec: { name: 'REPAIR' }, state: 'included', lines, subtotal, attn });
    }
    const margin = st.margin > 0 ? materials * st.margin / 100 : 0;
    const total = (materials + margin) / st.ratio;
    let discount = 0;
    if (st.disc.kind === 'percent') discount = total * Math.min(100, Math.max(0, +st.disc.val || 0)) / 100;
    else discount = Math.min(total, Math.max(0, +st.disc.val || 0));
    const net = total - discount;
    return { cats, materials, margin, total, discount, net, attn, chassis: chassis || { total: 0, lines: [] } };
  }

  // ---- validated references: identity + baseline
  function identityOf(st) {
    const b = body();
    const ins = {}; b.insulated.forEach((c) => { const v = st.ins[c]; ins[c] = v ? v.side + '/' + v.mm : ''; });
    const extras = st.optOn.has('OPTIONAL EXTRAS') ? st.added.filter((a) => a.section === 'OPTIONAL EXTRAS').map((a) => a.name).sort() : [];
    return { dims: { L: +(+st.dims.L).toFixed(3), W: +(+st.dims.W).toFixed(3), H: +(+st.dims.H).toFixed(3) }, door: st.door, ins, extras, excluded: Array.from(st.excluded).sort() };
  }
  function stateFromRef(ref, keep) {
    const st = freshState(ref.bodyId, keep);
    st.dims = Object.assign({}, ref.identity.dims); st.door = ref.identity.door;
    Object.keys(ref.identity.ins).forEach((c) => { const [side, mm] = ref.identity.ins[c].split('/'); st.ins[c] = { side, mm: +mm }; });
    ref.identity.excluded.forEach((c) => st.excluded.add(c));
    if (ref.identity.extras.length) { st.optOn.add('OPTIONAL EXTRAS'); ref.identity.extras.forEach((n) => { const s = M.STOCK.find((x) => x.name === n); st.added.push({ key: 'add#r' + (addSeq++), section: 'OPTIONAL EXTRAS', kind: 'stock', name: n, unit: s ? s.unit : 'Each', price: s ? s.price : null, qty: 1, sap: s ? s.sap : '', age: s ? s.age : null }); }); }
    return st;
  }
  function ensureBaselines() {
    REFS.forEach((r) => { if (r.baseline == null) { const c = compute(stateFromRef(r)); r.baseline = { materials: c.materials, cats: Object.fromEntries(c.cats.map((x) => [x.sec.name, x.state === 'included' ? x.subtotal : 0])) }; } });
  }
  function matchedRef(st) {
    if (st.type !== 'body') return null;
    const id = JSON.stringify(identityOf(st));
    return REFS.find((r) => r.bodyId === st.bodyId && JSON.stringify(r.identity) === id) || null;
  }

  // ---- save info (the truthful button)
  function saveInfo(st, C) {
    const cust = st.customer;
    const dup = cust ? stateEXISTING.find((e) => e.customer === cust && e.type === st.type && (st.type === 'repair' || e.bodyId === st.bodyId)) : null;
    const info = { modes: [], label: '', dup, warnNoCust: !cust, disabled: false, blockers: [] };
    if (st.type === 'repair' && !st.repair.type) info.blockers.push('Type of repair is required');
    if (st.saved && !st.dirty) { info.label = 'Saved ' + st.saved.quote + ' · rev ' + st.saved.rev; info.disabled = true; return info; }
    if (st.saved) {
      info.modes = [{ id: 'overwrite', label: 'Overwrite rev ' + st.saved.rev + ' (pending)' }, { id: 'revision', label: 'Revision ' + (st.saved.rev + 1), reuse: true }];
      if (!st.saveMode || !info.modes.some((m) => m.id === st.saveMode)) { st.saveMode = 'overwrite'; st.reuse = true; } // RULE-SAVE-003: edit flow defaults reuse ON
      info.label = st.saveMode === 'overwrite' ? 'Overwrite rev ' + st.saved.rev + ' of ' + st.saved.quote : 'Save revision ' + (st.saved.rev + 1) + ' of ' + st.saved.quote;
      return info;
    }
    if (!cust) { info.label = st.type === 'repair' ? 'Save repair without customer' : 'Save without customer'; return info; }
    if (dup) {
      info.modes = [{ id: 'revision', label: 'Revision ' + (dup.revs + 1) + ' of ' + dup.quote, reuse: true }, { id: 'new', label: 'New costing' }];
      if (!st.saveMode || !info.modes.some((m) => m.id === st.saveMode)) { st.saveMode = 'revision'; st.reuse = false; } // RULE-SAVE-003: duplicate flow defaults reuse OFF
      info.label = st.saveMode === 'revision' ? 'Save revision ' + (dup.revs + 1) + ' of ' + dup.quote : (st.type === 'repair' ? 'Save as new repair costing' : 'Save as new costing');
      return info;
    }
    info.label = st.type === 'repair' ? 'Save as new repair costing' : 'Save as new costing';
    return info;
  }

  // ---------------------------------------------------------------- render
  const money = (n) => S.role === 'user' ? '<span class="masked">••••</span>' : fmtR(n);
  const canPrices = () => S.role !== 'user';

  function render() {
    ensureBaselines();
    const C = compute(S);
    const b = body();
    const html = [];
    html.push(renderDemoBar());
    html.push('<div class="page">');
    html.push('<div class="sticky-top">' + renderTotals(C) + renderBanners(C) + '</div>');
    html.push(renderHeader(C));
    if (S.type === 'body') { html.push(renderStrip(b)); html.push(renderCards(C, b)); }
    else html.push(renderRepairLines(C));
    html.push('<div class="foot">Mockup · sample data only · no prices or customers here are real · design/new-costing-ui-concept</div>');
    html.push('</div>');
    html.push(renderSaveBar(C));
    html.push(renderDrawer(C));
    if (S.ui.toast) html.push('<div class="toast ' + (S.ui.toast.kind || '') + '">' + esc(S.ui.toast.msg) + '</div>');
    app.innerHTML = html.join('');
    if (S.ui.focus) { const el = app.querySelector(S.ui.focus); if (el) { el.focus(); if (el.select) el.select(); } S.ui.focus = null; }
  }

  function renderDemoBar() {
    return '<div class="demo-bar"><b>MOCKUP</b> New Costing UI · design concept §3.2 · sample data (anonymised)'
      + '<span class="sp"></span>'
      + '<span>demo role: <select data-act="role"><option value="full"' + (S.role === 'full' ? ' selected' : '') + '>full (Nadie)</option><option value="user"' + (S.role === 'user' ? ' selected' : '') + '>user (no prices)</option></select></span>'
      + '<button class="btn" style="padding:1px 8px;font-size:12px" data-act="drawer" data-kind="guide">Where to click</button>'
      + '<button class="btn" style="padding:1px 8px;font-size:12px" data-act="reset">Reset</button></div>';
  }

  function renderTotals(C) {
    const ratioLbl = Math.round(S.ratio * 100) + '%';
    const discLbl = S.disc.val > 0 ? (S.disc.kind === 'percent' ? S.disc.val + '%' : fmtR(S.disc.val)) : 'none';
    let modeChip = '';
    if (S.loadedRef) modeChip = '<span class="pill mode ref">Loaded from reference “' + esc(S.loadedRef.label) + '” · balances ✓</span>';
    else if (S.saved) modeChip = '<span class="pill mode edit">' + (S.dirty ? 'Editing ' : 'Saved ') + esc(S.saved.quote) + ' · rev ' + S.saved.rev + ' · pending</span>';
    else modeChip = '<span class="pill mode">' + (S.type === 'repair' ? 'New repair costing' : 'New costing') + '</span>';
    const attn = C.attn > 0 ? '<span class="pill bad" data-act="jump-attn" title="jump to the first line needing attention">⚠ ' + C.attn + ' line' + (C.attn > 1 ? 's' : '') + ' need' + (C.attn > 1 ? '' : 's') + ' attention</span>' : '<span class="pill ok">✓ no attention items</span>';
    return '<div class="totals">'
      + '<div class="stage"><div class="lbl">Materials</div><div class="val">' + money(C.materials) + '</div><div class="sub">' + (S.chassis.on && S.type === 'body' ? 'incl. chassis ' + money(C.chassis.total) : (S.type === 'body' ? 'excl. chassis' : 'repair lines')) + (S.type === 'body' && canPrices() ? ' · ' + fmtR((C.materials - C.chassis.total) / Math.max(1e-9, (+S.dims.L) * (+S.dims.W))) + ' / m² floor' : '') + '</div></div>'
      + '<div class="stage"><div class="lbl"><span class="op">+</span> Margin ' + esc(S.margin) + '%</div><div class="val">' + money(C.margin) + '</div><div class="sub">' + (S.margin > 0 ? 'on materials' : 'no margin') + '</div></div>'
      + '<div class="stage"><div class="lbl"><span class="op">÷</span> Ratio ' + ratioLbl + ' <span class="op">=</span> Total</div><div class="val">' + money(C.total) + '</div><div class="sub">selling price</div></div>'
      + '<div class="stage net"><div class="lbl"><span class="op">−</span> Discount <span class="op">=</span> Net</div><div class="val">' + money(C.net) + '</div><div class="sub">discount ' + esc(discLbl) + '</div></div>'
      + '<div class="status">' + attn + modeChip + '</div>'
      + '</div>';
  }

  function renderBanners(C) {
    let out = '';
    if (S.type === 'body') {
      const ref = matchedRef(S);
      if (ref && ref.baseline && !S.loadedRef) {
        const d = ref.baseline.materials ? (C.materials - ref.baseline.materials) / ref.baseline.materials : 0;
        if (Math.abs(d) > 0.02) {
          const deltas = C.cats.map((c) => ({ n: c.sec.name, d: (c.state === 'included' ? c.subtotal : 0) - (ref.baseline.cats[c.sec.name] || 0) })).filter((x) => Math.abs(x.d) > 0.5).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 3);
          out += '<div class="banner warn"><span>⚠ Matches reference “' + esc(ref.label) + '” · <b>' + (d > 0 ? '+' : '') + (d * 100).toFixed(1) + '%</b> vs baseline' + (canPrices() ? ' (' + fmtR(ref.baseline.materials) + ')' : '') + '</span>'
            + (canPrices() && deltas.length ? '<span class="mute">' + deltas.map((x) => esc(x.n) + ' ' + (x.d > 0 ? '+' : '−') + fmtR(Math.abs(x.d))).join(' · ') + '</span>' : '') + '<span class="sp"></span><span class="tiny">display-only · tolerance 2%</span></div>';
        } else out += '<div class="banner ok">✓ Matches validated reference “' + esc(ref.label) + '” — within tolerance</div>';
      }
      if (rule32Active(S)) out += '<div class="banner warn">3.2 m rule in force: 4MM PF PLYWOOD and its GLUE LINE in FRONT / SIDES / FLOOR cost R0 (rows stay visible at qty 0). <span class="sp"></span><span class="tiny">RULE-SPEC-001</span></div>';
    }
    return out;
  }

  function renderHeader(C) {
    const b = body();
    const custOpts = '<option value="">— none —</option>' + M.CUSTOMERS.map((c) => '<option value="' + c.id + '"' + (S.customer === c.id ? ' selected' : '') + '>' + esc(c.name) + '</option>').join('');
    const cust = M.CUSTOMERS.find((c) => c.id === S.customer);
    const contOpts = '<option value="">— none —</option>' + (cust ? cust.contacts.map((n) => '<option' + (S.contact === n ? ' selected' : '') + '>' + esc(n) + '</option>').join('') : '');
    let h = '<div class="header">';
    // costing type / body
    h += '<div class="field"><label>Costing</label><select class="body" data-act="pick-body">'
      + '<optgroup label="Body types">' + M.BODIES.map((x) => '<option value="' + x.id + '"' + (S.type === 'body' && S.bodyId === x.id ? ' selected' : '') + '>' + esc(x.name) + (x.v2 ? '' : ' (legacy options)') + '</option>').join('') + '</optgroup>'
      + '<optgroup label="Other"><option value="repair"' + (S.type === 'repair' ? ' selected' : '') + '>REPAIR</option></optgroup></select></div>';
    if (S.type === 'body') {
      h += '<div class="field"><label>Length m</label><input class="dim" data-act="dim" data-k="L" value="' + esc(S.dims.L) + '"></div>'
        + '<div class="field"><label>Width m</label><input class="dim" data-act="dim" data-k="W" value="' + esc(S.dims.W) + '"></div>'
        + '<div class="field"><label>Height m</label><input class="dim" data-act="dim" data-k="H" value="' + esc(S.dims.H) + '"></div>';
    }
    h += '<div class="field"><label>Margin %</label><input class="pct" data-act="margin" value="' + esc(S.margin) + '"></div>'
      + '<div class="field"><label>Ratio</label><select data-act="ratio">' + [0.3, 0.325, 0.35, 0.375, 0.4, 0.425, 0.45, 0.475, 0.5, 0.525, 0.55, 0.575, 0.6, 0.625, 0.65, 0.675, 0.7].map((r) => '<option value="' + r + '"' + (Math.abs(r - S.ratio) < 1e-9 ? ' selected' : '') + '>' + Math.round(r * 100) + '%</option>').join('') + '</select></div>';
    h += '<div class="field' + (!S.customer ? ' warn' : '') + '"><label>Customer</label><select data-act="customer">' + custOpts + '</select></div>'
      + '<div class="field"><label>Contact</label><select data-act="contact"' + (!cust ? ' disabled' : '') + '>' + contOpts + '</select></div>';
    if (S.type === 'repair') {
      h += '<div class="field' + (!S.repair.type ? ' warn' : '') + '"><label>Type of repair <span class="req">*</span></label><select class="rtype" data-act="rtype"><option value="">— choose —</option>' + M.REPAIR_TYPES.map((t) => '<option' + (S.repair.type === t ? ' selected' : '') + '>' + esc(t) + '</option>').join('') + '</select></div>'
        + '<div class="field"><label>Work description (optional)</label><textarea class="work" data-act="work" placeholder="e.g. Replace damaged rear panel and re-seal">' + esc(S.repair.work) + '</textarea></div>';
    }
    h += '<div class="grow"></div>';
    if (S.type === 'body') {
      const refs = REFS.filter((r) => r.bodyId === S.bodyId);
      h += '<div class="field"><label>&nbsp;</label><button class="linkbtn" data-act="drawer" data-kind="refs"' + (refs.length ? '' : ' disabled') + '>Validated references (' + refs.length + ')</button></div>';
      if (S.saved && S.role === 'full') h += '<div class="field"><label>&nbsp;</label><button class="linkbtn" data-act="drawer" data-kind="markref">Mark as validated reference</button></div>';
    }
    h += '<div class="field"><label>&nbsp;</label><button class="linkbtn" data-act="drawer" data-kind="legend">Legend</button></div>';
    h += '</div>';
    return h;
  }

  function famControl(f, inCard) {
    const v = S.fam[f.key];
    let c = '<span class="fam"><span class="lbl">' + esc(f.label) + '</span>';
    if (f.mode === 'single') c += '<span class="seg">' + f.options.map((o) => '<button data-act="fam" data-key="' + esc(f.key) + '" data-val="' + esc(o) + '" class="' + (v === o ? 'on' : '') + '">' + esc(o) + '</button>').join('') + '</span>';
    else c += f.options.map((o) => '<label class="chip' + (v.includes(o) ? ' on' : '') + '"><input type="checkbox" data-act="fam" data-key="' + esc(f.key) + '" data-val="' + esc(o) + '"' + (v.includes(o) ? ' checked' : '') + '> ' + esc(o) + '</label>').join('');
    return c + '</span>';
  }
  function renderStrip(b) {
    const hasDoors = bodyHasBothDoors(S);
    if (!hasDoors && !b.strip.length) return '';
    let h = '<div class="strip"><span class="cap">Body choices</span>';
    if (hasDoors) h += '<span class="fam"><span class="lbl">Rear door</span><span class="seg"><button data-act="door" data-val="DRD" class="' + (S.door === 'DRD' ? 'on' : '') + '">DRD</button><button data-act="door" data-val="SRD" class="' + (S.door === 'SRD' ? 'on' : '') + '">SRD</button></span><span class="tiny mute">double · single</span></span>';
    b.strip.forEach((f) => { h += famControl(f); });
    if (b.strip.length) h += '<span class="tiny mute">legacy option group — matches no category, so it lives here (D5)</span>';
    return h + '</div>';
  }

  function priceCell(l) {
    if (!canPrices()) return '<span class="cell ro"><span class="masked">••••</span></span>';
    if (l.state === 'unpriced') return '<span class="cell bad click" data-act="price" data-key="' + esc(l.key) + '" title="no price on the catalogue item — click to set">no price</span>';
    let g = '';
    if (l.prov.recipe) g = '<span class="glyph f" title="' + esc('Computed price — ' + l.prov.recipe) + '">ƒ</span>';
    else if (l.prov.perm) g = '<span class="glyph" title="Permanent price for this section (set 12 Jul)">📌</span>';
    else if (l.prov.age != null) g = '<span class="dot ' + (l.prov.age <= 7 ? 'fresh' : (l.prov.age >= 90 ? 'old' : 'none')) + '" title="' + (l.prov.age <= 7 ? 'Price updated ' + l.prov.age + ' days ago' : (l.prov.age >= 90 ? 'Outdated price — ' + l.prov.age + ' days old' : 'Catalogue price · ' + l.prov.age + ' days old')) + '"></span>';
    const typed = l.prov.priceTyped ? ' typed' : '';
    const star = l.prov.priceTyped ? '<span title="' + esc('Quote override: ' + l.prov.priceTyped) + '">*</span>' : '';
    const act = l.prov.recipe ? 'recipe' : 'price';
    return '<span class="cell click' + typed + '" data-act="' + act + '" data-key="' + esc(l.key) + '" title="' + (l.prov.recipe ? 'computed price — click for breakdown' : 'click to edit price') + '">' + fmtR(l.price) + star + g + '</span>';
  }
  function qtyCell(l) {
    if (S.ui.editing === l.key) return '<input class="cell-input" data-act="qty-commit" data-key="' + esc(l.key) + '" value="' + esc(fmtQ(l.qty).replace(/\s/g, '')) + '" id="qedit">';
    if (l.state === 'err') return '<span class="cell bad ro" title="' + esc('Unknown token ' + l.err) + '">— err —</span>';
    if (l.added) return '<span class="cell click typed" data-act="qty-edit" data-key="' + esc(l.key) + '">' + fmtQ(l.qty) + '</span>';
    const tip = 'formula: ' + (FTEXT[l.row.f] || '') + (l.row.k !== 1 && l.row.f !== 'const' ? ' × ' + l.row.k : (l.row.f === 'const' ? l.row.k : '')) + (l.sec.mult > 1 ? ' · × ' + l.sec.mult + ' (' + l.sec.name + ')' : '') + ' → ' + fmtQ(l.formulaQty);
    if (l.prov.qtyTyped) return '<span class="cell click typed" data-act="qty-edit" data-key="' + esc(l.key) + '" title="' + esc('you set ' + fmtQ(l.qty) + ' · ' + tip) + '">' + (l.prov.qtyDelta != null ? '<span class="delta" title="the formula moved since you overrode this">formula now ' + fmtQ(l.prov.qtyDelta) + '</span>' : '') + fmtQ(l.qty) + '<button class="revert" data-act="qty-revert" data-key="' + esc(l.key) + '" title="revert to formula">↺</button></span>';
    return '<span class="cell click" data-act="qty-edit" data-key="' + esc(l.key) + '" title="' + esc(tip) + ' · click to override">' + fmtQ(l.qty) + '</span>';
  }
  function lineRow(l, opts) {
    const cls = [];
    if (l.state === 'user-off' || l.state === 'gated') cls.push('dim');
    if (l.state === 'rule') cls.push('rule');
    if (l.state === 'unpriced' || l.state === 'err') cls.push('attn');
    const tags = [];
    if (l.prov.stock) tags.push('<span class="tag stock">stock</span>');
    if (l.prov.manual) tags.push('<span class="tag manual">manual</span>');
    if (l.state === 'gated') tags.push('<span class="tag reason" title="' + (l.derived ? 'reason derived from the legacy link — nothing to author' : 'per-item condition') + '">gated · ' + esc(l.reason) + '</span>');
    if (l.state === 'rule') tags.push('<span class="tag rule">R0 by rule (3.2 m)</span>');
    if (l.state === 'err') tags.push('<span class="tag bad">formula error · unknown ' + esc(l.err) + '</span>');
    if (l.state === 'unpriced') tags.push('<span class="tag bad">no price</span>');
    if (l.state === 'user-off') tags.push('<span class="tag">excluded by you</span>');
    const name = l.added ? l.added.name : l.row.name;
    const inc = l.state === 'gated' ? '<input type="checkbox" disabled title="gated by a body choice">' : '<input type="checkbox" data-act="line-toggle" data-key="' + esc(l.key) + '"' + (l.state === 'user-off' ? '' : ' checked') + '>';
    return '<tr class="' + cls.join(' ') + '" id="row-' + esc(l.key) + '">'
      + '<td class="inc">' + inc + '</td>'
      + '<td class="desc">' + esc(name) + tags.join('') + (l.added && l.added.note ? '<span class="tiny mute"> — ' + esc(l.added.note) + '</span>' : '') + '</td>'
      + '<td class="qty num">' + qtyCell(l) + '</td>'
      + '<td class="unit">' + esc(l.added ? l.added.unit : l.row.unit) + '</td>'
      + '<td class="price num">' + priceCell(l) + '</td>'
      + '<td class="total num">' + (l.state === 'user-off' || l.state === 'gated' ? '—' : (l.state === 'unpriced' || l.state === 'err' ? '<span class="cell bad ro">R 0</span>' : money(l.total))) + '</td>'
      + '<td class="menu-cell"><button data-act="rowmenu" data-key="' + esc(l.key) + '" title="line actions">⋯</button>' + (S.ui.rowMenu === l.key ? rowMenu(l) : '') + '</td>'
      + '</tr>';
  }
  function rowMenu(l) {
    let m = '<div class="menu right rowmenu">';
    if (l.state !== 'gated') m += '<button data-act="line-toggle" data-key="' + esc(l.key) + '">' + (l.state === 'user-off' ? 'Include line' : 'Exclude line') + '</button>';
    if (l.prov.qtyTyped) m += '<button data-act="qty-revert" data-key="' + esc(l.key) + '">Revert quantity to formula</button>';
    if (canPrices() && !l.prov.recipe) m += '<button data-act="price" data-key="' + esc(l.key) + '">Edit price…</button>';
    if (l.prov.recipe) m += '<button data-act="recipe" data-key="' + esc(l.key) + '">Show computed price…</button>';
    if (!l.added) m += '<div class="sep"></div><button data-act="formula" data-key="' + esc(l.key) + '"><span class="glyph f">ƒ</span> Edit formula… <span class="tiny mute">changes the body template</span></button>';
    if (l.added) m += '<div class="sep"></div><button class="danger" data-act="line-remove" data-key="' + esc(l.key) + '">Remove line</button>';
    return m + '</div>';
  }
  const TH = '<thead><tr><th></th><th>Description</th><th class="num">Qty</th><th>Unit</th><th class="num">Price</th><th class="num">Total</th><th></th></tr></thead>';

  function renderCards(C, b) {
    let h = '<div class="cards">';
    C.cats.forEach((c) => {
      const sec = c.sec, st = c.state, name = sec.name;
      const collapsed = S.collapsed.has(name) || (st !== 'included' && st !== 'optional-off');
      const cls = ['card'];
      if (st !== 'included') cls.push('off');
      if (st === 'user-off') cls.push('user-off');
      if (st === 'rule-off') cls.push('rule-off');
      if (st === 'sibling') cls.push('sibling');
      if (sec.optional) cls.push('optional'); if (sec.optional && st === 'included') cls.push('on');
      if (c.attn > 0) cls.push('attn');
      h += '<div class="' + cls.join(' ') + '" id="cat-' + esc(name) + '"><div class="hd">';
      h += '<button class="caret" data-act="collapse" data-cat="' + esc(name) + '" title="collapse / expand">' + (collapsed ? '▸' : '▾') + '</button>';
      // name + state text
      if (st === 'sibling') h += '<span class="nm">' + esc(name) + ' — not quoted (' + esc(S.door) + ' chosen)</span>';
      else if (st === 'rule-off') h += '<span class="nm">' + esc(name) + '</span><span class="tag reason">excluded — needs ' + esc(sec.master.val) + '</span>';
      else h += '<span class="nm">' + esc(name) + '</span>';
      if (sec.mult > 1) h += '<span class="mult" title="' + esc('section multiplier × ' + sec.mult + ' — ' + (canPrices() ? fmtR(c.subtotal / sec.mult) + ' per side' : 'per-side amount masked')) + '">× ' + sec.mult + '</span>';
      // include control
      if (st === 'sibling') h += '<span class="inc mute" title="choose ' + esc(name) + ' in Body choices → Rear door">Include ▫ via Rear door</span>';
      else if (st === 'rule-off') h += '<span class="inc mute"><input type="checkbox" disabled> Include</span>';
      else h += '<label class="inc"><input type="checkbox" data-act="cat-toggle" data-cat="' + esc(name) + '"' + (st === 'included' ? ' checked' : '') + '> Include</label>';
      if (c.attn > 0 && st === 'included') h += '<span class="tag bad">⚠ ' + c.attn + '</span>';
      // right side
      if (st === 'included') h += '<span class="sub">' + money(c.subtotal) + '</span>';
      else if (st === 'user-off') h += '<span class="why">excluded by you · ' + c.removedLines + ' lines · ' + (canPrices() ? fmtR(c.subtotal) + ' removed' : 'amount masked') + '</span>';
      else if (st === 'optional-off') h += '<span class="why">optional · off</span>';
      else h += '<span class="why">—</span>';
      h += '</div>';
      // pending exclude warning
      if (S.ui.pendingExclude === name) h += '<div class="warnbox">⚠ Excluding <b>' + esc(name) + '</b> removes ' + c.removedLines + ' lines' + (canPrices() ? ' (' + fmtR(c.subtotal) + ')' : '') + ' from this costing.<span style="flex:1"></span><button class="primary" data-act="cat-exclude" data-cat="' + esc(name) + '">Exclude anyway</button><button data-act="cat-keep">Keep</button></div>';
      if (!collapsed) {
        // choices strip inside the card
        const fams = (b.families[name] || []);
        const insul = b.insulated.includes(name);
        if (insul || fams.length) {
          h += '<div class="choices">';
          if (insul) {
            const v = S.ins[name]; const t = TEMPLATE_INS[b.id][name];
            const diff = t && (t.side !== v.side || +t.mm !== +v.mm);
            h += '<span class="fam"><span class="lbl">Insulation</span><span class="seg"><button data-act="ins-side" data-cat="' + esc(name) + '" data-val="EPS" class="' + (v.side === 'EPS' ? 'on' : '') + '">EPS</button><button data-act="ins-side" data-cat="' + esc(name) + '" data-val="PU" class="' + (v.side === 'PU' ? 'on' : '') + '">PU</button></span>'
              + '<input class="mm' + (diff ? ' typed' : '') + '" data-act="ins-mm" data-cat="' + esc(name) + '" value="' + esc(v.mm) + '" title="thickness in mm (' + (v.mm / 1000) + ' m) — this costing only">'
              + '<span class="tiny mute">mm</span>'
              + (diff ? '<span class="tmpl" title="differs from the body template (' + esc(t.side + ' ' + t.mm + ' mm') + ') — this costing only; use ⋯ → Save insulation to template">≠ template</span>' : '')
              + '</span>';
            if (S.ui.assist && S.ui.assist.from === name) h += '<span class="assist">Apply ' + esc(S.ui.assist.side) + ' to all ' + b.insulated.filter((x) => catState(S, b.sections.find((s) => s.name === x)) === 'included').length + ' insulated categories? <button data-act="assist-yes">Apply</button><button data-act="assist-no">✕</button></span>';
          }
          fams.forEach((f) => { h += famControl(f, true); });
          h += '</div>';
        }
        // rows
        if (sec.optional && !c.lines.length) h += '<div class="emptyx">No extras chosen yet — only chosen extras appear here' + (st === 'optional-off' ? '; adding one includes the category' : '') + '.</div>';
        else if (c.lines.length) h += '<table' + (st === 'optional-off' ? ' style="opacity:.55" title="category is off — lines are not costed"' : '') + '>' + TH + '<tbody>' + c.lines.map((l) => lineRow(l)).join('') + '</tbody></table>';
        h += '<div class="addrow">';
        if (sec.optional) h += '<button class="addbtn" data-act="drawer" data-kind="stock" data-sec="' + esc(name) + '">+ Add extra</button><span class="tiny mute">picker pre-filtered to the extras list</span>';
        else h += '<button class="addbtn" data-act="drawer" data-kind="stock" data-sec="' + esc(name) + '">+ Add from stock</button>';
        h += '<button class="addbtn" data-act="drawer" data-kind="freehand" data-sec="' + esc(name) + '">+ Free-hand line</button>';
        h += '</div>';
      }
      h += '</div>';
    });
    h += renderChassisCard(C);
    h += '</div>';
    return h;
  }
  function renderChassisCard(C) {
    const c = S.chassis, on = c.on;
    let h = '<div class="card' + (on ? '' : ' off') + '" id="cat-CHASSIS"><div class="hd"><span class="caret">' + (on ? '▾' : '▸') + '</span><span class="nm">CHASSIS</span><label class="inc"><input type="checkbox" data-act="chassis-toggle"' + (on ? ' checked' : '') + '> Include</label>';
    h += on ? '<span class="sub">' + money(C.chassis.total) + '</span>' : '<span class="why">not quoted</span>';
    h += '</div>';
    if (on) {
      const sel = (arr, id, act) => '<select data-act="chassis" data-k="' + act + '">' + arr.map((x) => '<option value="' + x.id + '"' + (+id === x.id ? ' selected' : '') + '>' + esc(x.name) + '</option>').join('') + '</select>';
      h += '<div class="chassis-grid">'
        + '<div class="field"><label>Chassis length m</label><input data-act="chassis" data-k="length" value="' + esc(c.length || S.dims.L) + '"></div>'
        + '<div class="field"><label>Axles</label><select data-act="chassis" data-k="axles"><option' + (c.axles == 2 ? ' selected' : '') + '>2</option><option' + (c.axles == 3 ? ' selected' : '') + '>3</option></select></div>'
        + '<div class="field"><label>Lift axles</label><select data-act="chassis" data-k="lift"' + (c.axles != 3 ? ' disabled title="3-axle only"' : '') + '><option value="0"' + (c.lift == 0 ? ' selected' : '') + '>0</option><option value="1"' + (c.lift == 1 ? ' selected' : '') + '>1</option></select></div>'
        + '<div class="field"><label>Tyres</label><select data-act="chassis" data-k="tyre"><option value="dual"' + (c.tyre === 'dual' ? ' selected' : '') + '>dual (4 / axle)</option><option value="super"' + (c.tyre === 'super' ? ' selected' : '') + '>super-single (2 / axle)</option></select></div>'
        + '<div class="field"><label>Suspension</label>' + sel(M.CHASSIS.suspension, c.susp, 'susp') + '</div>'
        + '<div class="field"><label>Lift type</label>' + sel(M.CHASSIS.lift, c.liftType, 'liftType') + '</div>'
        + '<div class="field"><label>Brake</label>' + sel(M.CHASSIS.brake, c.brake, 'brake') + '</div>'
        + '<div class="field"><label>Tyre</label>' + sel(M.CHASSIS.tyre, c.tyreId, 'tyreId') + '</div>'
        + '<div class="field"><label>Rim</label>' + sel(M.CHASSIS.rim, c.rim, 'rim') + '</div>'
        + '</div>';
      h += '<table>' + TH + '<tbody>' + C.chassis.lines.map((l) => '<tr><td class="inc"></td><td class="desc">' + esc(l.name) + '<span class="tag">derived</span></td><td class="qty num">' + fmtQ(l.qty) + '</td><td class="unit">each</td><td class="price num">' + money(l.price) + '</td><td class="total num">' + money(l.total) + '</td><td></td></tr>').join('') + '</tbody></table>';
      h += '<div class="derived">Derived: ' + C.chassis.tyres + ' tyres/rims · ' + C.chassis.kits + ' suspension & brake kits' + (c.lift > 0 ? ' · 1 lifting axle' : '') + ' — counts follow axles/tyre style (RULE-CALC-013)</div>';
    }
    return h + '</div>';
  }

  function renderRepairLines(C) {
    const c = C.cats[0];
    let h = '<div class="repair-lines"><div class="card' + (c.attn ? ' attn' : '') + '"><div class="hd"><span class="nm">REPAIR LINES</span><span class="tiny mute">flat list · stock picks + free-hand · same row grammar</span><span class="sub">' + money(c.subtotal) + '</span></div>';
    if (c.lines.length) h += '<table>' + TH + '<tbody>' + c.lines.map((l) => lineRow(l)).join('') + '</tbody></table>';
    else h += '<div class="emptyx">No lines yet — add from the stock list or free-hand.</div>';
    h += '<div class="addrow"><button class="addbtn" data-act="drawer" data-kind="stock" data-sec="REPAIR">+ From stock list</button><button class="addbtn" data-act="drawer" data-kind="freehand" data-sec="REPAIR">+ Free-hand line</button></div></div></div>';
    return h;
  }

  function renderSaveBar(C) {
    const info = saveInfo(S, C);
    let h = '<div class="sticky-bottom"><div class="inner">';
    h += '<span class="disc"><span class="small mute">Discount</span><span class="seg"><button data-act="disc-kind" data-val="percent" class="' + (S.disc.kind === 'percent' ? 'on' : '') + '">%</button><button data-act="disc-kind" data-val="amount" class="' + (S.disc.kind === 'amount' ? 'on' : '') + '">R</button></span><input data-act="disc" value="' + esc(S.disc.val || '') + '" placeholder="0"><span class="tiny mute">one clears the other</span></span>';
    h += '<span class="savegroup">';
    if (info.modes.length) h += '<span class="modesel">' + info.modes.map((m) => '<label><input type="radio" name="mode" data-act="mode" value="' + m.id + '"' + (S.saveMode === m.id ? ' checked' : '') + '> ' + esc(m.label) + '</label>').join('') + (S.saveMode === 'revision' ? '<label><input type="checkbox" data-act="reuse"' + (S.reuse ? ' checked' : '') + '> reuse quote no.</label>' : '') + '</span>';
    const warnCls = info.warnNoCust && !info.disabled ? ' warn' : '';
    h += '<button class="btn primary' + warnCls + '" data-act="save"' + (info.disabled ? ' disabled' : '') + ' title="' + (info.blockers.join('; ') || 'saves exactly what is on screen (server result hash)') + '">' + esc(info.label) + '</button>';
    h += '<button class="btn more" data-act="more" title="more actions">⋯</button>';
    if (S.ui.savePop) h += renderSavePop(C, info);
    if (S.ui.menu === 'more') h += renderMoreMenu();
    h += '</span></div></div>';
    return h;
  }
  function renderSavePop(C, info) {
    let h = '<div class="pop"><h4>' + esc(info.label) + '</h4>';
    if (info.blockers.length) { h += '<div class="small" style="color:var(--bad)">' + info.blockers.map(esc).join('<br>') + '</div><div class="row"><span class="sp"></span><button class="btn" data-act="savepop-close">Close</button></div></div>'; return h; }
    if (info.warnNoCust) h += '<div class="small">No customer attached — the costing saves without one (you can add the customer on a later revision).</div>';
    if (C.attn > 0) h += '<label style="margin-top:8px"><input type="checkbox" data-act="ack"' + (S.ack ? ' checked' : '') + '> <span class="txt">I acknowledge <b>' + C.attn + ' line' + (C.attn > 1 ? 's' : '') + '</b> with no price / a formula error will be saved at R 0 <span class="tiny mute">(recorded on the costing — D3)</span></span></label>';
    h += '<div class="small mute" style="margin-top:8px">Binds exactly what is on screen: the server’s last result hash travels with the save and a changed input is refused, not silently re-costed.</div>';
    h += '<div class="row"><span class="sp"></span><button class="btn" data-act="savepop-close">Cancel</button><button class="btn primary" data-act="save-confirm"' + (C.attn > 0 && !S.ack ? ' disabled' : '') + '>Save</button></div></div>';
    return h;
  }
  function renderMoreMenu() {
    const canRef = S.saved && S.type === 'body' && S.role === 'full';
    return '<div class="menu right" style="bottom:calc(100% + 8px);top:auto">'
      + '<div class="hd">This costing</div>'
      + '<button data-act="stub" data-msg="Print preview would open here">🖨 Print</button>'
      + '<button data-act="stub" data-msg="Full report (all lines incl. excluded, with reasons) would open here">📄 Full report</button>'
      + '<button data-act="stub" data-msg="Export dialog (Excel / Word / PDF, ratios, email) would open here">⇩ Export…</button>'
      + '<button data-act="stub" data-msg="Excel settings-block paste would open here (transition assist, RULE-SPEC-003)"' + (S.type === 'repair' ? ' disabled' : '') + '>📋 Paste Excel settings…</button>'
      + '<div class="sep"></div><div class="hd">Template</div>'
      + '<button data-act="drawer" data-kind="template"' + (S.type === 'repair' || S.role !== 'full' ? ' disabled' : '') + '>Save insulation to template… <span class="tiny mute">admin · full</span></button>'
      + '<div class="sep"></div><div class="hd">References</div>'
      + '<button data-act="drawer" data-kind="markref"' + (canRef ? '' : ' disabled') + '>Mark as validated reference <span class="tiny mute">' + (S.saved ? '' : 'save first') + '</span></button>'
      + '<div class="sep"></div><div class="hd">Danger</div>'
      + '<button class="danger" data-act="drawer" data-kind="replace"' + (S.customer ? '' : ' disabled') + '>Replace all costings for this customer + body…</button>'
      + '</div>';
  }

  // ---------------------------------------------------------------- drawer
  function renderDrawer(C) {
    const d = S.ui.drawer; if (!d) return '';
    let title = '', bodyH = '', foot = '';
    const close = '<button class="x" data-act="drawer-close" title="close">×</button>';
    if (d.kind === 'stock') {
      const isExtras = d.sec === 'OPTIONAL EXTRAS';
      title = isExtras ? 'Add extra → OPTIONAL EXTRAS' : 'Add from stock list → ' + d.sec;
      const q = (S.ui.stockQ || '').toLowerCase();
      let list = M.STOCK.filter((s) => !isExtras || S.ui.stockAll || s.extra);
      if (q) list = list.filter((s) => (s.name + ' ' + s.sap + ' ' + s.cat + ' ' + s.sub).toLowerCase().includes(q));
      bodyH += '<div class="field"><input id="stockq" placeholder="Search name · SAP code · category · sub-category" data-act="stockq" value="' + esc(S.ui.stockQ) + '"></div>';
      if (isExtras) bodyH += '<label class="small"><input type="checkbox" data-act="stockall"' + (S.ui.stockAll ? ' checked' : '') + '> show the whole stock list (not only extras)</label>';
      bodyH += '<table><thead><tr><th>Item</th><th>SAP</th><th>Unit</th><th class="num">Price</th><th>Age</th><th></th></tr></thead><tbody>'
        + list.map((s) => { const added = S.added.some((a) => a.section === d.sec && a.stockId === s.id); return '<tr class="pick"><td>' + esc(s.name) + '<div class="tiny mute">' + esc(s.cat + ' · ' + s.sub) + '</div></td><td class="tiny nowrap">' + esc(s.sap) + '</td><td>' + esc(s.unit) + '</td><td class="num">' + (s.price == null ? '<span class="tag bad" style="margin:0">no price</span>' : (canPrices() ? fmtR(s.price) : '••••')) + '</td><td class="nowrap">' + (s.age == null ? '—' : '<span class="dot ' + (s.age <= 7 ? 'fresh' : (s.age >= 90 ? 'old' : 'none')) + '"></span> <span class="tiny">' + s.age + ' d</span>') + '</td><td><button class="addmini' + (added ? ' on' : '') + '" data-act="stock-add" data-id="' + s.id + '" data-sec="' + esc(d.sec) + '">' + (added ? 'Added ✓ (+1)' : 'Add') + '</button></td></tr>'; }).join('')
        + '</tbody></table>';
      if (!list.length) bodyH += '<div class="note">No matches.</div>';
      bodyH += '<div class="note">Stock list = the materials catalogue, SAP-ready by SAP code. No on-hand quantities (not a stock system). Unpriced items are shown as such <b>before</b> you add them.</div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Done</button>';
    } else if (d.kind === 'freehand') {
      title = 'Free-hand line → ' + d.sec;
      const fv = d.vals || {};
      bodyH += '<div class="field"><label>Description <span class="req">*</span></label><input id="fh-desc" placeholder="e.g. Sub-contract panel beating" value="' + esc(fv.desc || '') + '"></div>'
        + '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px"><div class="field"><label>Qty <span class="req">*</span></label><input id="fh-qty" value="' + esc(fv.qty != null ? fv.qty : '1') + '"></div><div class="field"><label>Unit</label><input id="fh-unit" value="' + esc(fv.unit != null ? fv.unit : 'each') + '"></div><div class="field"><label>Unit price R <span class="req">*</span></label><input id="fh-price" placeholder="0" value="' + esc(fv.price || '') + '"></div></div>'
        + '<div class="field"><label>Note (optional)</label><input id="fh-note" value="' + esc(fv.note || '') + '"></div>'
        + '<div class="note">Free-hand lines live inside this costing only — never a template row, never a catalogue item. Shown blue with a <span class="tag manual" style="margin:0">manual</span> tag. Needs <code>costings.freehand_items</code>.</div>'
        + (d.error ? '<div class="small" style="color:var(--bad)">' + esc(d.error) + '</div>' : '');
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Cancel</button><button class="btn primary" data-act="fh-add" data-sec="' + esc(d.sec) + '">Add to ' + esc(d.sec) + '</button>';
    } else if (d.kind === 'price') {
      const l = findLine(C, d.key); if (!l) return '';
      title = 'Price → ' + esc(l.added ? l.added.name : l.row.name);
      const cur = l.price == null ? 'no price' : fmtR(l.price);
      const src = l.prov.priceTyped ? 'quote override (' + l.prov.priceTyped + ')' : l.prov.perm ? 'permanent price for this section' : l.added && l.added.kind === 'manual' ? 'manually entered' : 'catalogue price' + (l.prov.age != null ? ' · updated ' + l.prov.age + ' days ago' : '');
      const scope = d.scope || 'costing';
      bodyH += '<div class="kv"><span class="k">Current</span><span>' + cur + '</span><span class="k">Source</span><span>' + esc(src) + '</span></div>'
        + '<div class="field"><label>New unit price R</label><input id="pr-val" value="' + esc(d.val != null ? d.val : (l.price == null ? '' : R0(l.price))) + '"></div>'
        + '<div class="radio' + (scope === 'costing' ? ' on' : '') + '"><input type="radio" name="scope" data-act="scope" value="costing"' + (scope === 'costing' ? ' checked' : '') + '><div><div class="t">This costing only</div><div class="d">Blue with <b>*</b>; a reason is required (≥ 5 chars) and shows in the tooltip and on the saved record.</div>' + (scope === 'costing' ? '<div class="field" style="margin-top:6px"><input id="pr-reason" placeholder="Reason (e.g. supplier quote 14 Aug)" value="' + esc(d.reason || '') + '"></div>' : '') + '</div></div>'
        + '<div class="radio' + (scope === 'perm' ? ' on' : '') + '"><input type="radio" name="scope" data-act="scope" value="perm"' + (scope === 'perm' ? ' checked' : '') + (S.role !== 'full' || l.added ? ' disabled' : '') + '><div><div class="t">Permanently for this section ' + (S.role !== 'full' ? '<span class="tiny mute">(needs costings.price_master_edit)</span>' : '') + (l.added ? '<span class="tiny mute">(not for added lines)</span>' : '') + '</div><div class="d">Writes the row’s price on the body template (this section only — the same material elsewhere is untouched). Journalled; clears any quote override.</div></div></div>'
        + '<div class="note">Setting the price back to the original clears the override with no reason needed. Price-age badges are suppressed while a quote override is in force.</div>'
        + (d.error ? '<div class="small" style="color:var(--bad)">' + esc(d.error) + '</div>' : '');
      foot = '<button class="btn" data-act="price-clear" data-key="' + esc(l.key) + '"' + (l.prov.priceTyped ? '' : ' disabled') + '>Clear override</button><span class="sp"></span><button class="btn" data-act="drawer-close">Cancel</button><button class="btn primary" data-act="price-apply" data-key="' + esc(l.key) + '">Apply</button>';
    } else if (d.kind === 'recipe') {
      const l = findLine(C, d.key); if (!l) return '';
      title = 'Computed price → ' + esc(l.row.name);
      bodyH += '<div class="kv"><span class="k">Engine</span><span>' + esc(l.prov.recipe) + '</span><span class="k">Unit price</span><span>' + fmtR(l.price) + ' / ' + esc(l.row.unit) + '</span></div>'
        + '<table><thead><tr><th>Ingredient</th><th class="num">qty / m²</th><th class="num">price</th><th class="num">contrib.</th></tr></thead><tbody>'
        + '<tr><td>Resin (sample)</td><td class="num">1.20</td><td class="num">R 95</td><td class="num">R 114</td></tr><tr><td>Gelcoat (sample)</td><td class="num">0.60</td><td class="num">R 140</td><td class="num">R 84</td></tr><tr><td>Mat 450 (sample)</td><td class="num">2.00</td><td class="num">R 41</td><td class="num">R 82</td></tr>'
        + '</tbody></table>'
        + '<div class="note">Read-only here. Recipe prices are maintained on the admin pricing pages; the calculation stays server-side (no client re-implementation — R-18 retired). <button class="linkbtn" data-act="stub" data-msg="Would deep-link to the recipe editor (admin)">edit recipe →</button></div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Close</button>';
    } else if (d.kind === 'legend') {
      title = 'Legend — how to read a value';
      bodyH += '<div class="legend-grid">'
        + '<span class="cell typed" style="justify-content:flex-start">15 ↺</span><span><b>Blue</b> = you typed it for this costing (qty override, quote price, free-hand). ↺ reverts to the formula.</span>'
        + '<span>14.56</span><span><b>Black</b> = the system (formula quantity, catalogue price). Hover shows the formula.</span>'
        + '<span>R 280 <span class="glyph f">ƒ</span></span><span>Computed price from a recipe engine (skin / taping / floor plate / cleat). Click for the breakdown.</span>'
        + '<span>R 300 <span class="glyph">📌</span></span><span>Permanent price set for this section on the body template.</span>'
        + '<span class="cell typed" style="justify-content:flex-start">R 250 *</span><span>Quote price override — the reason is in the tooltip.</span>'
        + '<span><span class="dot fresh"></span> / <span class="dot old"></span></span><span>Price age: green ≤ 7 days · amber ≥ 90 days (outdated).</span>'
        + '<span><span class="tag stock" style="margin:0">stock</span> <span class="tag manual" style="margin:0">manual</span></span><span>Line added from the stock list / entered free-hand.</span>'
        + '<span><span class="tag reason" style="margin:0">gated · X = N</span></span><span>Row not costed because of a body choice; the reason is derived, not authored.</span>'
        + '<span class="mute" style="font-style:italic">R0 by rule</span><span>Deliberately zero by a business rule (e.g. 3.2 m plywood). Not an attention item.</span>'
        + '<span class="cell bad" style="justify-content:flex-start">no price</span><span><b>Red</b> = needs attention: unpriced or formula error. Counted in the ⚠ pill; save asks you to acknowledge.</span>'
        + '<span class="mult" style="width:max-content">× 2</span><span>Section multiplier (SIDES). Tooltip shows the per-side amount.</span>'
        + '</div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Close</button>';
    } else if (d.kind === 'refs') {
      title = 'Validated references — ' + esc(body().name);
      const refs = REFS.filter((r) => r.bodyId === S.bodyId);
      bodyH += refs.map((r) => '<div class="radio"><div style="flex:1"><div class="t">' + esc(r.label) + '</div><div class="d">' + r.identity.dims.L + ' × ' + r.identity.dims.W + ' × ' + r.identity.dims.H + ' m · ' + esc(r.identity.door) + ' · ' + esc(Object.entries(r.identity.ins).map(([k, v]) => k + ' ' + v.replace('/', ' ') + 'mm').join(', ')) + (r.identity.extras.length ? ' · extras: ' + esc(r.identity.extras.join(', ')) : '') + ' · marked ' + esc(r.marked) + (canPrices() && r.baseline ? ' · baseline ' + fmtR(r.baseline.materials) : '') + '</div></div><button class="btn" data-act="ref-recall" data-id="' + r.id + '">Recall</button></div>').join('')
        + '<div class="note">Recall loads the reference as a <b>copy</b> that balances — it never binds to the reference’s record. Identity = body + dims + door + insulation + extras + excluded categories (extras re-enter identity, OQ-15). Drift banner appears under the totals when the current costing matches an identity and the total moves &gt; 2%.</div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Close</button>';
    } else if (d.kind === 'markref') {
      title = 'Mark as validated reference';
      bodyH += '<div class="kv"><span class="k">Record</span><span>' + (S.saved ? esc(S.saved.quote) + ' · rev ' + S.saved.rev : '<span style="color:var(--bad)">not saved — save first</span>') + '</span><span class="k">Body</span><span>' + esc(body().name) + '</span><span class="k">Dims</span><span>' + S.dims.L + ' × ' + S.dims.W + ' × ' + S.dims.H + '</span></div>'
        + '<div class="field"><label>Label <span class="req">*</span></label><input id="ref-label" placeholder="e.g. Std 5.6 m freezer · PU (2026)" maxlength="120" value="' + esc(d.label || '') + '"></div>'
        + '<div class="note">Binds to the record on screen (server-verified: same body, dims match ±0.0005). Needs <code>costings.validated_refs_manage</code>. Re-marking relabels.</div>'
        + (d.error ? '<div class="small" style="color:var(--bad)">' + esc(d.error) + '</div>' : '');
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Cancel</button><button class="btn primary" data-act="markref-do"' + (S.saved ? '' : ' disabled') + '>Mark</button>';
    } else if (d.kind === 'template') {
      title = 'Save insulation to template — ' + esc(body().name);
      const b = body(); const diffs = b.insulated.filter((c) => { const t = TEMPLATE_INS[b.id][c], v = S.ins[c]; return t.side !== v.side || +t.mm !== +v.mm; });
      if (!diffs.length) bodyH += '<div class="note">This costing’s insulation equals the template — nothing to write.</div>';
      else bodyH += '<table><thead><tr><th>Category</th><th>Template</th><th>This costing</th><th></th></tr></thead><tbody>' + diffs.map((c) => '<tr><td>' + esc(c) + '</td><td>' + esc(TEMPLATE_INS[b.id][c].side + ' ' + TEMPLATE_INS[b.id][c].mm + ' mm') + '</td><td class="cell typed" style="justify-content:flex-start">' + esc(S.ins[c].side + ' ' + S.ins[c].mm + ' mm') + '</td><td><input type="checkbox" checked data-tpl="' + esc(c) + '"></td></tr>').join('') + '</tbody></table>';
      bodyH += '<div class="note">The only template write left on the page — explicit, listed, gated {admin, full} (<code>costings.template_save</code>). Every future costing of this body starts from the new values; existing costings keep theirs.</div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Cancel</button><button class="btn primary" data-act="template-write"' + (diffs.length ? '' : ' disabled') + '>Write ' + diffs.length + ' change' + (diffs.length === 1 ? '' : 's') + ' to template</button>';
    } else if (d.kind === 'replace') {
      const cust = M.CUSTOMERS.find((c) => c.id === S.customer);
      const dup = stateEXISTING.find((e) => e.customer === S.customer && e.type === S.type && (S.type === 'repair' || e.bodyId === S.bodyId));
      title = 'Replace — destructive';
      bodyH += '<div class="banner warn" style="margin:0">This deletes <b>all ' + (dup ? dup.revs : 0) + ' costing' + (dup && dup.revs === 1 ? '' : 's') + '</b> for ' + esc(cust ? cust.name : '—') + ' on ' + (S.type === 'repair' ? 'REPAIR' : esc(body().name)) + ' — including any validated reference pointing at them — and saves this one as revision 1.</div>'
        + '<div class="field"><label>Type REPLACE to confirm</label><input id="rep-confirm" placeholder="REPLACE"></div>'
        + '<div class="note">Today this is a one-click bulk delete with no second confirm (R-05). Here it needs the typed word.</div>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Cancel</button><button class="btn warn" data-act="replace-do">Replace</button>';
    } else if (d.kind === 'guide') {
      title = 'Where to click — the two journeys';
      bodyH += '<ol class="small" style="margin:0;padding-left:18px;line-height:1.7">'
        + '<li><b>Body</b> is pre-selected (FREEZER MEDIUM). Change L/W/H — the totals bar moves. Try <b>L = 3.2</b> to see the 3.2 m rule banner and grey “R0 by rule” lines in FLOOR.</li>'
        + '<li><b>Exclude a category</b>: untick Include on ROOF → inline warning → “Exclude anyway”. Re-tick to bring it back.</li>'
        + '<li><b>Insulation inside FLOOR</b>: flip PU→EPS, change 100 → 76 mm; note “≠ template”; use the “Apply to all” chip.</li>'
        + '<li><b>Rear door</b> in Body choices: DRD ⇄ SRD — the sibling card stays visible, “not quoted”.</li>'
        + '<li><b>Qty in place</b>: click a quantity (e.g. GLUE LINE in FRONT), type 15, Enter → blue + ↺. Now change L → amber “formula now …” chip.</li>'
        + '<li><b>Price</b>: click a price → drawer → new value + scope (this costing needs a reason). Click an <i>ƒ</i> price for the recipe breakdown.</li>'
        + '<li><b>Add lines</b>: “+ Add from stock” / “+ Free-hand line” on any card; on OPTIONAL EXTRAS tick Include then “+ Add extra” — add “Fixed strip curtains – DRD” (unpriced) and watch the ⚠ pill.</li>'
        + '<li><b>Chassis</b>: tick Include on the CHASSIS card; 3 axles enables lift axle.</li>'
        + '<li><b>Save</b>: pick Customer A → the button reads “Save revision 3 of Q-A101” with a mode selector; with unpriced lines the popover asks for acknowledgement. After saving, “Mark as validated reference” appears.</li>'
        + '<li><b>References</b>: “Validated references (2)” → Recall → chip “Loaded from reference … balances ✓”; then change a qty → drift banner.</li>'
        + '<li><b>REPAIR</b>: change the Costing dropdown to REPAIR → Type of repair + Work description; add stock/free-hand lines; Customer B → “Save revision 2 of Q-B207”.</li>'
        + '<li>Try <b>demo role: user</b> (top bar) to see price masking; ⋯ next to Save for Print / Report / Export / Save-to-template / Replace.</li>'
        + '</ol>';
      foot = '<span class="sp"></span><button class="btn" data-act="drawer-close">Close</button>';
    }
    return '<div class="backdrop" data-act="drawer-close"></div><div class="drawer" role="dialog"><div class="dh"><h3>' + title + '</h3>' + close + '</div><div class="db">' + bodyH + '</div><div class="df">' + foot + '</div></div>';
  }
  function findLine(C, key) { for (const c of C.cats) { const l = c.lines.find((x) => x.key === key); if (l) return l; } return null; }

  // ---------------------------------------------------------------- actions
  function toast(msg, kind) { S.ui.toast = { msg, kind }; render(); clearTimeout(toast.t); toast.t = setTimeout(() => { S.ui.toast = null; render(); }, 2600); }
  function dirty() { if (S.saved) S.dirty = true; S.loadedRef = null; S.ack = false; }
  function closeTransient() { S.ui.menu = null; S.ui.rowMenu = null; S.ui.savePop = false; }

  function num(v, fallback) { const n = parseFloat(String(v).replace(/[^\d.\-]/g, '')); return isNaN(n) ? fallback : n; }

  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-act]');
    if (!t) { if (!e.target.closest('.menu') && !e.target.closest('.pop')) { if (S.ui.menu || S.ui.rowMenu || S.ui.savePop) { closeTransient(); render(); } } return; }
    const act = t.dataset.act;
    if (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA') { if (t.type !== 'checkbox' && t.type !== 'radio') return; }
    switch (act) {
      case 'reset': S = freshState(20); render(); return;
      case 'collapse': { const c = t.dataset.cat; if (S.collapsed.has(c)) S.collapsed.delete(c); else S.collapsed.add(c); render(); return; }
      case 'cat-toggle': {
        const c = t.dataset.cat, sec = body().sections.find((s) => s.name === c);
        if (sec.optional) { if (S.optOn.has(c)) S.optOn.delete(c); else S.optOn.add(c); dirty(); render(); return; }
        if (S.excluded.has(c)) { S.excluded.delete(c); dirty(); render(); return; }
        S.ui.pendingExclude = c; render(); return;
      }
      case 'cat-exclude': S.excluded.add(t.dataset.cat); S.ui.pendingExclude = null; dirty(); render(); return;
      case 'cat-keep': S.ui.pendingExclude = null; render(); return;
      case 'door': S.door = t.dataset.val; dirty(); render(); return;
      case 'ins-side': { const c = t.dataset.cat, v = t.dataset.val; if (S.ins[c].side !== v) { S.ins[c].side = v; S.ui.assist = { from: c, side: v }; dirty(); } render(); return; }
      case 'assist-yes': { const b = body(); b.insulated.forEach((c) => { S.ins[c].side = S.ui.assist.side; }); S.ui.assist = null; dirty(); toast('Applied ' + (S.ins[b.insulated[0]].side) + ' to all insulated categories — this costing only'); return; }
      case 'assist-no': S.ui.assist = null; render(); return;
      case 'fam': {
        const k = t.dataset.key, v = t.dataset.val, cur = S.fam[k];
        if (Array.isArray(cur)) { const i = cur.indexOf(v); if (i >= 0) cur.splice(i, 1); else cur.push(v); }
        else S.fam[k] = v;
        dirty(); render(); return;
      }
      case 'line-toggle': { const k = t.dataset.key; if (S.lineOff.has(k)) S.lineOff.delete(k); else S.lineOff.add(k); S.ui.rowMenu = null; dirty(); render(); return; }
      case 'line-remove': { S.added = S.added.filter((a) => a.key !== t.dataset.key); S.ui.rowMenu = null; dirty(); render(); return; }
      case 'rowmenu': S.ui.rowMenu = S.ui.rowMenu === t.dataset.key ? null : t.dataset.key; S.ui.menu = null; render(); return;
      case 'qty-edit': S.ui.editing = t.dataset.key; S.ui.focus = '#qedit'; S.ui.rowMenu = null; render(); return;
      case 'qty-revert': delete S.qtyOv[t.dataset.key]; delete S.formulaBase[t.dataset.key]; S.ui.rowMenu = null; dirty(); render(); return;
      case 'formula': S.ui.rowMenu = null; toast('Formula editor (power users) would open — it changes the body template, not this costing', 'warn'); return;
      case 'price': S.ui.rowMenu = null; S.ui.drawer = { kind: 'price', key: t.dataset.key, scope: 'costing' }; S.ui.focus = '#pr-val'; render(); return;
      case 'recipe': S.ui.rowMenu = null; S.ui.drawer = { kind: 'recipe', key: t.dataset.key }; render(); return;
      case 'scope': { const pv = document.getElementById('pr-val'), pr = document.getElementById('pr-reason'); if (pv) S.ui.drawer.val = pv.value; if (pr) S.ui.drawer.reason = pr.value; S.ui.drawer.scope = t.value; render(); return; }
      case 'price-clear': delete S.priceOv[t.dataset.key]; S.ui.drawer = null; dirty(); toast('Override cleared'); return;
      case 'price-apply': {
        const key = t.dataset.key, C = compute(S), l = findLine(C, key);
        S.ui.drawer.val = document.getElementById('pr-val').value; S.ui.drawer.reason = (document.getElementById('pr-reason') || {}).value || '';
        const v = num(S.ui.drawer.val, NaN);
        if (isNaN(v) || v < 0) { S.ui.drawer.error = 'Enter a price ≥ 0'; render(); return; }
        if (S.ui.drawer.scope === 'perm') { if (l.added) { S.ui.drawer.error = 'Permanent price applies to template rows only'; render(); return; } S.permPrice[key] = v; delete S.priceOv[key]; S.ui.drawer = null; dirty(); toast('Permanent price saved for ' + l.row.name + ' in ' + l.sec.name + ' (journalled)'); return; }
        const orig = l.added ? l.added.price : (S.permPrice[key] != null ? S.permPrice[key] : (l.row.perm != null ? l.row.perm : (l.row.ins ? l.row.price * (S.ins[l.sec.name].mm / 60) : l.row.price)));
        if (orig != null && Math.abs(v - orig) < 0.005) { delete S.priceOv[key]; S.ui.drawer = null; dirty(); toast('Back to the original price — override cleared'); return; }
        const reason = S.ui.drawer.reason || '';
        if (reason.trim().length < 5) { S.ui.drawer.error = 'A reason of at least 5 characters is required for a quote-only price'; render(); return; }
        S.priceOv[key] = { price: v, reason: reason.trim() }; S.ui.drawer = null; dirty(); toast('Price overridden for this costing'); return;
      }
      case 'drawer': { const kind = t.dataset.kind; S.ui.menu = null; S.ui.savePop = false; S.ui.drawer = { kind, sec: t.dataset.sec }; S.ui.stockQ = ''; S.ui.stockAll = false; if (kind === 'stock') S.ui.focus = '#stockq'; if (kind === 'freehand') S.ui.focus = '#fh-desc'; if (kind === 'markref') S.ui.focus = '#ref-label'; if (kind === 'replace') S.ui.focus = '#rep-confirm'; render(); return; }
      case 'drawer-close': S.ui.drawer = null; render(); return;
      case 'stock-add': {
        const s = M.STOCK.find((x) => x.id === +t.dataset.id), sec = t.dataset.sec;
        const ex = S.added.find((a) => a.section === sec && a.stockId === s.id);
        if (ex) ex.qty += 1; else S.added.push({ key: 'add#' + (addSeq++), section: sec, kind: 'stock', stockId: s.id, name: s.name, unit: s.unit, price: s.price, qty: 1, sap: s.sap, age: s.age });
        if (sec === 'OPTIONAL EXTRAS') S.optOn.add(sec);
        dirty(); render(); return;
      }
      case 'fh-add': {
        S.ui.drawer.vals = { desc: document.getElementById('fh-desc').value, qty: document.getElementById('fh-qty').value, unit: document.getElementById('fh-unit').value, price: document.getElementById('fh-price').value, note: document.getElementById('fh-note').value };
        const fv = S.ui.drawer.vals, desc = fv.desc.trim(), qty = num(fv.qty, NaN), unit = fv.unit.trim() || 'each', price = num(fv.price, NaN), note = fv.note.trim();
        if (!desc) { S.ui.drawer.error = 'Description is required'; render(); return; }
        if (isNaN(qty) || qty <= 0) { S.ui.drawer.error = 'Quantity must be > 0'; render(); return; }
        if (isNaN(price) || price < 0) { S.ui.drawer.error = 'Unit price must be ≥ 0'; render(); return; }
        const sec = t.dataset.sec; S.added.push({ key: 'add#' + (addSeq++), section: sec, kind: 'manual', name: desc, unit, price, qty, note });
        if (sec === 'OPTIONAL EXTRAS') S.optOn.add(sec);
        S.ui.drawer = null; dirty(); toast('Free-hand line added to ' + sec); return;
      }
      case 'chassis-toggle': S.chassis.on = !S.chassis.on; dirty(); render(); return;
      case 'mode': S.saveMode = t.value; render(); return;
      case 'reuse': S.reuse = t.checked; render(); return;
      case 'ack': S.ack = t.checked; render(); return;
      case 'save': { closeTransient(); S.ui.savePop = true; render(); return; }
      case 'savepop-close': S.ui.savePop = false; render(); return;
      case 'save-confirm': doSave(); return;
      case 'more': S.ui.menu = S.ui.menu === 'more' ? null : 'more'; S.ui.savePop = false; render(); return;
      case 'stub': S.ui.menu = null; toast(t.dataset.msg); return;
      case 'jump-attn': { const C = compute(S); const l = C.cats.flatMap((c) => c.state === 'included' ? c.lines : []).find((x) => x.state === 'unpriced' || x.state === 'err'); if (l) { S.collapsed.delete(l.sec.name); render(); const el = document.getElementById('row-' + l.key); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } return; }
      case 'ref-recall': { const r = REFS.find((x) => x.id === +t.dataset.id); S = stateFromRef(r, S); S.loadedRef = r; S.ui.drawer = null; render(); return; }
      case 'markref-do': {
        S.ui.drawer.label = document.getElementById('ref-label').value; const label = S.ui.drawer.label.trim(); if (!label) { S.ui.drawer.error = 'Label is required'; render(); return; }
        const C = compute(S); const id = identityOf(S);
        const ex = REFS.find((r) => r.bodyId === S.bodyId && JSON.stringify(r.identity) === JSON.stringify(id));
        if (ex) { ex.label = label; } else REFS.push({ id: REFS.length + 1, bodyId: S.bodyId, label, marked: 'today', identity: id, baseline: { materials: C.materials, cats: Object.fromEntries(C.cats.map((x) => [x.sec.name, x.state === 'included' ? x.subtotal : 0])) } });
        S.ui.drawer = null; toast(ex ? 'Reference relabelled' : 'Marked “' + label + '” as a validated reference'); return;
      }
      case 'template-write': {
        const b = body(); const boxes = Array.from(document.querySelectorAll('[data-tpl]')).filter((x) => x.checked).map((x) => x.dataset.tpl);
        boxes.forEach((c) => { TEMPLATE_INS[b.id][c] = { side: S.ins[c].side, mm: +S.ins[c].mm }; });
        S.ui.drawer = null; toast('Wrote ' + boxes.length + ' insulation change' + (boxes.length === 1 ? '' : 's') + ' to the ' + b.name + ' template'); return;
      }
      case 'replace-do': {
        if (document.getElementById('rep-confirm').value !== 'REPLACE') { toast('Type REPLACE to confirm', 'warn'); return; }
        const i = stateEXISTING.findIndex((e) => e.customer === S.customer && e.type === S.type && (S.type === 'repair' || e.bodyId === S.bodyId));
        const q = i >= 0 ? stateEXISTING[i].quote : 'Q-' + S.customer + (300 + stateEXISTING.length);
        if (i >= 0) stateEXISTING.splice(i, 1);
        stateEXISTING.push({ customer: S.customer, type: S.type, bodyId: S.bodyId, quote: q, revs: 1 });
        S.saved = { quote: q, rev: 1 }; S.dirty = false; S.ui.drawer = null; toast('Replaced — saved as ' + q + ' rev 1'); return;
      }
    }
  });

  function doSave() {
    const C = compute(S), info = saveInfo(S, C);
    if (info.blockers.length) return;
    if (C.attn > 0 && !S.ack) return;
    let quote, rev;
    if (S.saved) {
      if (S.saveMode === 'overwrite') { quote = S.saved.quote; rev = S.saved.rev; }
      else { quote = S.reuse ? S.saved.quote : 'Q-' + (S.customer || 'X') + (400 + stateEXISTING.length); rev = S.saved.rev + 1; const e = stateEXISTING.find((x) => x.quote === S.saved.quote); if (e) e.revs = rev; }
    } else if (info.dup && S.saveMode === 'revision') { rev = info.dup.revs + 1; quote = S.reuse ? info.dup.quote : 'Q-' + S.customer + (400 + stateEXISTING.length); info.dup.revs = rev; }
    else { rev = 1; quote = 'Q-' + (S.customer || 'X') + (100 + stateEXISTING.length * 7); stateEXISTING.push({ customer: S.customer, type: S.type, bodyId: S.bodyId, quote, revs: 1 }); }
    S.saved = { quote, rev, ack: S.ack, attn: C.attn }; S.dirty = false; S.ui.savePop = false; S.loadedRef = null; S.saveMode = null;
    toast('Saved ' + quote + ' · rev ' + rev + (C.attn ? ' · ' + C.attn + ' unpriced acknowledged' : '') + ' · quote number assigned');
  }

  document.addEventListener('change', (e) => {
    const t = e.target.closest('[data-act]'); if (!t) return;
    const act = t.dataset.act;
    switch (act) {
      case 'role': S.role = t.value; render(); return;
      case 'pick-body': {
        if (t.value === 'repair') { const keep = { role: S.role, customer: S.customer, contact: S.contact }; S = freshState(S.bodyId, keep); S.type = 'repair'; S.margin = 0; render(); return; }
        S = freshState(+t.value, { role: S.role, customer: S.customer, contact: S.contact }); render(); return;
      }
      case 'dim': { const v = num(t.value, NaN); if (isNaN(v) || v < 0.01) { toast('Dimension must be ≥ 0.01 m', 'warn'); render(); return; } S.dims[t.dataset.k] = v; dirty(); render(); return; }
      case 'margin': { const v = num(t.value, NaN); if (isNaN(v) || v < 0 || v > 100) { toast('Margin must be 0–100', 'warn'); render(); return; } S.margin = v; dirty(); render(); return; }
      case 'ratio': S.ratio = +t.value; dirty(); render(); return;
      case 'customer': S.customer = t.value || null; S.contact = null; S.saveMode = null; dirty(); render(); return;
      case 'contact': S.contact = t.value || null; dirty(); render(); return;
      case 'rtype': S.repair.type = t.value; dirty(); render(); return;
      case 'work': S.repair.work = t.value; dirty(); return;
      case 'ins-mm': { const v = num(t.value, NaN); if (isNaN(v) || v <= 0 || v >= 1000) { toast('Thickness must be > 0 and < 1000 mm', 'warn'); render(); return; } S.ins[t.dataset.cat].mm = v; dirty(); render(); return; }
      case 'disc': { const v = num(t.value, 0); S.disc.val = Math.max(0, v); dirty(); render(); return; }
      case 'chassis': { const k = t.dataset.k; S.chassis[k] = k === 'length' ? num(t.value, null) : (k === 'tyre' ? t.value : +t.value); if (k === 'axles' && S.chassis.axles !== 3) S.chassis.lift = 0; dirty(); render(); return; }
      case 'qty-commit': commitQty(t); return;
      case 'stockq': return; // handled on input
    }
  });
  document.addEventListener('input', (e) => {
    const t = e.target; if (t.id === 'stockq') { S.ui.stockQ = t.value; const pos = t.selectionStart; render(); const el = document.getElementById('stockq'); if (el) { el.focus(); el.setSelectionRange(pos, pos); } }
    if (t.dataset && t.dataset.act === 'stockall') { S.ui.stockAll = t.checked; render(); }
  });
  document.addEventListener('click', (e) => {
    const t = e.target; if (t.dataset && t.dataset.act === 'disc-kind') { S.disc.kind = t.dataset.val; S.disc.val = 0; dirty(); render(); }
  });
  function commitQty(t) {
    const key = t.dataset.key, v = num(t.value, NaN);
    S.ui.editing = null;
    if (isNaN(v) || v < 0) { toast('Quantity must be ≥ 0', 'warn'); return; }
    const C = compute(S), l = findLine(C, key);
    if (l && l.added) { l.added.qty = v; dirty(); render(); return; }
    if (l && Math.abs(v - l.formulaQty) < 1e-6) { delete S.qtyOv[key]; delete S.formulaBase[key]; dirty(); render(); return; }
    S.qtyOv[key] = v; S.formulaBase[key] = l ? l.formulaQty : null; dirty(); render();
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (S.ui.editing) { S.ui.editing = null; render(); return; } if (S.ui.drawer || S.ui.menu || S.ui.rowMenu || S.ui.savePop) { S.ui.drawer = null; closeTransient(); render(); } }
    if (e.key === 'Enter' && e.target && e.target.dataset && e.target.dataset.act === 'qty-commit') { e.preventDefault(); commitQty(e.target); }
    if (e.key === 'Enter' && e.target && e.target.id === 'fh-price') { const b = document.querySelector('[data-act="fh-add"]'); if (b) b.click(); }
    if (e.key === 'Enter' && e.target && e.target.id === 'pr-reason') { const b = document.querySelector('[data-act="price-apply"]'); if (b) b.click(); }
  });
  document.addEventListener('focusout', (e) => { if (e.target && e.target.dataset && e.target.dataset.act === 'qty-commit' && S.ui.editing) { setTimeout(() => { if (S.ui.editing) commitQty(e.target); }, 0); } });

  render();
})();
