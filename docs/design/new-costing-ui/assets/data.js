/* ============================================================================
   New Costing UI — mockup sample data (§3.2)
   ANONYMISED. Prices are round, invented numbers. Customers are letters.
   Body / section / material vocabulary mirrors the public spec so the page
   reads true to the domain, but NOTHING here is a real price or a real quote.
   ============================================================================ */
window.MOCK = (function () {
  // Formula kinds — the mock engine evaluates these from L/W/H (metres).
  //   front  = (W+w)*(H+w)   side = (L+w)*(H+w)   roof/floor = (L+w)*(W+w)
  //   perim  = 2L+W          len  = L             const = k
  // 'w' = the {Waste} global (0.05 m) — shown in tooltips exactly as the app does.
  const R = (name, unit, price, f, k, opts) => Object.assign({ name, unit, price, f, k: k == null ? 1 : k }, opts || {});

  // ---- Insulated bodies share the same insulation row shape per category ----
  // ins:'EPS'|'PU' rows are gated by the category's insulation choice; their
  // price scales with thickness in the mock (60 mm = base) so the totals move.
  function insulatedCat(name, extra) {
    return [
      R('EXT GRP SKIN 2×450', 'm²', 280, name === 'FRONT' || name === 'DRD' || name === 'SRD' ? 'front' : name === 'SIDES' ? 'side' : 'roof', 1, { recipe: 'Skin formula · GRP 2×450 (standard region)', age: 3 }),
      R('EPS', 'm²', 160, name === 'FRONT' || name === 'DRD' || name === 'SRD' ? 'front' : name === 'SIDES' ? 'side' : 'roof', 1, { ins: 'EPS' }),
      R('PU', 'm²', 520, name === 'FRONT' || name === 'DRD' || name === 'SRD' ? 'front' : name === 'SIDES' ? 'side' : 'roof', 1, { ins: 'PU', age: 2 }),
      R('GLUE LINE', 'metre', 28, name === 'FRONT' || name === 'DRD' || name === 'SRD' ? 'front' : name === 'SIDES' ? 'side' : 'roof', 1),
      R('INT GRP SKIN 2×300', 'm²', 190, name === 'FRONT' || name === 'DRD' || name === 'SRD' ? 'front' : name === 'SIDES' ? 'side' : 'roof', 1, { recipe: 'Skin formula · GRP 2×300 (standard region)', age: 130 }),
    ].concat(extra || []);
  }

  const FREEZER_MEDIUM = {
    id: 20, name: 'FREEZER MEDIUM', v2: true,
    dims: { L: 5.6, W: 2.5, H: 2.4 }, markup: 5,
    insulated: ['FRONT', 'DRD', 'SRD', 'SIDES', 'ROOF', 'FLOOR'],
    insDefaults: { FRONT: { side: 'PU', mm: 60 }, DRD: { side: 'PU', mm: 60 }, SRD: { side: 'PU', mm: 60 }, SIDES: { side: 'PU', mm: 60 }, ROOF: { side: 'PU', mm: 100 }, FLOOR: { side: 'PU', mm: 100 } },
    // choice families INSIDE categories (group == section name), by subgroup
    families: {
      FLOOR: [
        { key: 'FLOOR|PLYWOOD', label: 'Plywood', mode: 'single', options: ['18MM FINN', '18MM PHENO'], def: '18MM FINN' },
        { key: 'FLOOR|KICK', label: 'Kick plates', mode: 'multi', options: ['ALU', '2ND ROW ALU'], def: [] },
        { key: 'FLOOR|SURFACE', label: 'Surface', mode: 'multi', options: ['RICE GRAIN'], def: [] },
      ],
    },
    strip: [],                       // v2: only the door choice sits in the strip
    sections: [
      { name: 'FRONT', mult: 1, rows: insulatedCat('FRONT', [R('CORNER MOULDING', 'metre', 60, 'const', 4.9)]) },
      { name: 'DRD', mult: 1, door: 'DRD', rows: insulatedCat('DRD', [R('DOOR FRAME ALU', 'each', 1200, 'const', 2), R('HINGE SET HD', 'each', 640, 'const', 4, { age: 95 })]) },
      { name: 'SRD', mult: 1, door: 'SRD', rows: insulatedCat('SRD', [R('DOOR FRAME ALU', 'each', 1200, 'const', 1), R('HINGE SET HD', 'each', 640, 'const', 2, { age: 95 })]) },
      { name: 'DRD DOOR FITTINGS', mult: 1, door: 'DRD', rows: [R('LOCK BAR SET', 'each', 950, 'const', 2), R('DOOR SEAL', 'metre', 45, 'perim', 1), R('KEEPER PLATE', 'each', 85, 'const', 4)] },
      { name: 'SRD DOOR FITTINGS', mult: 1, door: 'SRD', rows: [R('LOCK BAR SET', 'each', 950, 'const', 1), R('DOOR SEAL', 'metre', 45, 'perim', 1), R('KEEPER PLATE', 'each', 85, 'const', 2)] },
      { name: 'SIDES', mult: 2, rows: insulatedCat('SIDES', [R('SIDE RUB RAIL', 'metre', 95, 'len', 1)]) },
      { name: 'ROOF', mult: 1, rows: insulatedCat('ROOF', [R('ROOF BOW ALU', 'each', 210, 'len', 1.4)]) },
      { name: 'FLOOR', mult: 1, rows: [
        R('EXT GRP SKIN 2×450', 'm²', 280, 'roof', 1, { recipe: 'Skin formula · GRP 2×450 (standard region)', age: 3 }),
        R('EPS', 'm²', 160, 'roof', 1, { ins: 'EPS' }),
        R('PU', 'm²', 520, 'roof', 1, { ins: 'PU', age: 2 }),
        R('GLUE LINE', 'metre', 28, 'roof', 1),
        R('18 MM FINN PLYWOOD', 'm²', 470, 'roof', 1, { gate: { fam: 'FLOOR|PLYWOOD', val: '18MM FINN' } }),
        R('18 MM PF PLYWOOD', 'm²', 240, 'roof', 1, { gate: { fam: 'FLOOR|PLYWOOD', val: '18MM PHENO' } }),
        R('4MM PF PLYWOOD', 'm²', 95, 'roof', 1, { rule32: true }),
        R('GLUE LINE', 'metre', 28, 'roof', 1, { rule32: true }),
        R('100×50 R.T. TUBE', 'each', 124, 'len', 2.9),
        R('100×50 LVL', 'each', 128, 'len', 8.4, { err: '{LVL_PITCH}' }),
        R('RICE GRAIN FLOOR', 'each', 21650, 'len', 0.137, { gate: { fam: 'FLOOR|SURFACE', val: 'RICE GRAIN' } }),
        R('ALU KICK PLATE', 'each', 400, 'perim', 1, { gate: { fam: 'FLOOR|KICK', val: 'ALU' } }),
        R('2ND ROW ALU KICK PLATE', 'each', 400, 'perim', 1, { gate: { fam: 'FLOOR|KICK', val: '2ND ROW ALU' } }),
        R('ANTI-SKID FINAL COAT', 'm²', 32, 'roof', 1.9, { recipe: 'Floor plate · anti-skid (÷12 op-chain)' }),
      ] },
      { name: 'ALUMINIUM', mult: 1, rows: [R('ALU ANGLE 50×50', 'metre', 78, 'perim', 2), R('ALU FLAT BAR', 'metre', 46, 'perim', 1, { perm: 52, age: 40 })] },
      { name: 'SUB FRAME + LIGHT BOX ASSY', mult: 1, rows: [R('SUB FRAME KIT', 'each', 4800, 'const', 1), R('LIGHT BOX', 'each', 1350, 'const', 1), R('MUDGUARD SET', 'each', 900, 'const', 1), R('WIRING LOOM', 'each', 720, 'const', 1)] },
      { name: 'REAR FRAME & FLOOR PLATE', mult: 1, rows: [R('REAR FRAME ASSY', 'each', 3900, 'const', 1), R('FLOOR PLATE 3CR12', 'each', 1650, 'const', 1, { recipe: 'Floor plate · SRD floor plate' })] },
      { name: 'SPRAY PAINTING', mult: 1, rows: [R('SPRAY PAINT (BODY)', 'each', 6500, 'const', 1)] },
      { name: 'REFLEXITE TAPE', mult: 1, rows: [R('REFLEXITE TAPE', 'metre', 38, 'perim', 1)] },
      { name: 'OPTIONAL EXTRAS', mult: 1, optional: true, rows: [] },
    ],
  };

  const CHILLER_LARGE = {
    id: 27, name: 'CHILLER LARGE', v2: true,
    dims: { L: 7.5, W: 2.6, H: 2.6 }, markup: 5,
    insulated: ['FRONT', 'DRD', 'SRD', 'SIDES', 'ROOF', 'FLOOR'],
    insDefaults: { FRONT: { side: 'EPS', mm: 60 }, DRD: { side: 'EPS', mm: 60 }, SRD: { side: 'EPS', mm: 60 }, SIDES: { side: 'EPS', mm: 60 }, ROOF: { side: 'EPS', mm: 76 }, FLOOR: { side: 'EPS', mm: 76 } },
    families: { FLOOR: [{ key: 'FLOOR|PLYWOOD', label: 'Plywood', mode: 'single', options: ['18MM FINN', '18MM PHENO'], def: '18MM PHENO' }] },
    strip: [],
    sections: [
      { name: 'FRONT', mult: 1, rows: insulatedCat('FRONT') },
      { name: 'DRD', mult: 1, door: 'DRD', rows: insulatedCat('DRD', [R('DOOR FRAME ALU', 'each', 1200, 'const', 2)]) },
      { name: 'SRD', mult: 1, door: 'SRD', rows: insulatedCat('SRD', [R('DOOR FRAME ALU', 'each', 1200, 'const', 1)]) },
      { name: 'SIDES', mult: 2, rows: insulatedCat('SIDES') },
      { name: 'ROOF', mult: 1, rows: insulatedCat('ROOF') },
      { name: 'FLOOR', mult: 1, rows: [
        R('EXT GRP SKIN 2×450', 'm²', 280, 'roof', 1, { recipe: 'Skin formula · GRP 2×450 (standard region)', age: 3 }),
        R('EPS', 'm²', 160, 'roof', 1, { ins: 'EPS' }), R('PU', 'm²', 520, 'roof', 1, { ins: 'PU' }),
        R('18 MM FINN PLYWOOD', 'm²', 470, 'roof', 1, { gate: { fam: 'FLOOR|PLYWOOD', val: '18MM FINN' } }),
        R('18 MM PF PLYWOOD', 'm²', 240, 'roof', 1, { gate: { fam: 'FLOOR|PLYWOOD', val: '18MM PHENO' } }),
        R('ANTI-SKID FINAL COAT', 'm²', 32, 'roof', 1.9, { recipe: 'Floor plate · anti-skid (÷12 op-chain)' }),
      ] },
      { name: 'SUB FRAME + LIGHT BOX ASSY', mult: 1, rows: [R('SUB FRAME KIT', 'each', 5600, 'const', 1), R('LIGHT BOX', 'each', 1350, 'const', 1)] },
      { name: 'SPRAY PAINTING', mult: 1, rows: [R('SPRAY PAINT (BODY)', 'each', 7800, 'const', 1)] },
      { name: 'OPTIONAL EXTRAS', mult: 1, optional: true, rows: [] },
    ],
  };

  // Legacy body: no insulation pairs; a messy option group ("DRD") that matches
  // no category → lands in the Body choices strip (D5); one card gated by a
  // strip chip (excluded-by-rule); one row linked to a strip chip (derived reason).
  const TAUT_LINER = {
    id: 9, name: 'TAUT LINER RIGID', v2: false,
    dims: { L: 7.2, W: 2.6, H: 2.6 }, markup: 0,
    insulated: [], insDefaults: {}, families: {},
    strip: [
      { key: 'LEGACY|DRD', label: 'Legacy group “DRD”', mode: 'multi', options: ['SOLID TAIL BOARD', 'REFLEXITE TAPE', '3MM3CR12 FLOOR', '4.5MM3CR12 FLOOR'], def: ['SOLID TAIL BOARD', 'REFLEXITE TAPE'] },
    ],
    sections: [
      { name: 'HEAD BOARD', mult: 1, rows: [R('HEAD BOARD PANEL', 'each', 2400, 'const', 1), R('HEAD BOARD FRAME', 'each', 1100, 'const', 1)] },
      { name: 'DRD', mult: 1, door: 'DRD', rows: [R('DOOR FRAME ALU', 'each', 1200, 'const', 2), R('DOOR PANEL', 'm²', 310, 'front', 1)] },
      { name: 'DRD DOOR FITTINGS', mult: 1, door: 'DRD', rows: [R('LOCK BAR SET', 'each', 950, 'const', 2), R('DOOR SEAL', 'metre', 45, 'perim', 1)] },
      { name: 'CURTAINS', mult: 1, rows: [R('CURTAIN PVC', 'm²', 180, 'side', 2), R('BUCKLE SET', 'each', 22, 'len', 6)] },
      { name: 'TAIL BOARD', mult: 1, rows: [R('TAIL BOARD PANEL', 'each', 1900, 'const', 1, { link: 'SOLID TAIL BOARD' }), R('TAIL BOARD HINGE', 'each', 140, 'const', 4, { link: 'SOLID TAIL BOARD' })] },
      { name: 'ROOF', mult: 1, rows: [R('ROOF SHEET', 'm²', 210, 'roof', 1), R('ROOF BOW ALU', 'each', 210, 'len', 1.4)] },
      { name: '3MM 3CR12 S/STEEL FLOOR', mult: 1, master: { fam: 'LEGACY|DRD', val: '3MM3CR12 FLOOR' }, rows: [R('3MM 3CR12 SHEET', 'm²', 890, 'roof', 1), R('FLOOR WELD CONSUMABLES', 'each', 400, 'const', 1)] },
      { name: '4.5MM 3CR12 S/STEEL FLOOR', mult: 1, master: { fam: 'LEGACY|DRD', val: '4.5MM3CR12 FLOOR' }, rows: [R('4.5MM 3CR12 SHEET', 'm²', 1250, 'roof', 1)] },
      { name: 'SUB FRAME + LIGHT BOX ASSY', mult: 1, rows: [R('SUB FRAME KIT', 'each', 5200, 'const', 1), R('LIGHT BOX', 'each', 1350, 'const', 1)] },
      { name: 'REFLEXITE TAPE', mult: 1, rows: [R('REFLEXITE TAPE', 'metre', 38, 'perim', 1, { link: 'REFLEXITE TAPE' })] },
      { name: 'OPTIONAL EXTRAS', mult: 1, optional: true, rows: [] },
    ],
  };

  const BODIES = [CHILLER_LARGE, FREEZER_MEDIUM, TAUT_LINER];

  // ---- Stock list (materials) — the picker's source. Some deliberately unpriced.
  const STOCK = [
    { id: 1, sap: 'S-1001', name: 'Marker light – each', cat: 'ELECTRICAL', sub: 'LIGHTS', unit: 'Each', price: 500, age: 6, extra: true },
    { id: 2, sap: 'S-1002', name: 'Interior light – each', cat: 'ELECTRICAL', sub: 'LIGHTS', unit: 'Each', price: 405, age: 12, extra: true },
    { id: 3, sap: 'S-1003', name: 'Load lock rail', cat: 'FITTINGS', sub: 'CARGO', unit: 'Meter', price: 205, age: 120, extra: true },
    { id: 4, sap: 'S-1004', name: 'Shoring bar', cat: 'FITTINGS', sub: 'CARGO', unit: 'Each', price: 750, age: 30, extra: true },
    { id: 5, sap: 'S-1005', name: 'Fixed strip curtains – DRD', cat: 'FITTINGS', sub: 'DOORS', unit: 'Each', price: null, age: null, extra: true },
    { id: 6, sap: 'S-1006', name: 'Fixed strip curtains – SRD', cat: 'FITTINGS', sub: 'DOORS', unit: 'Each', price: 2650, age: 45, extra: true },
    { id: 7, sap: 'S-1007', name: 'Side door with access step – Single', cat: 'DOORS', sub: 'SIDE DOORS', unit: 'Each', price: 8600, age: 20, extra: true },
    { id: 8, sap: 'S-1008', name: 'Side door with access step – Double', cat: 'DOORS', sub: 'SIDE DOORS', unit: 'Each', price: 26500, age: 20, extra: true },
    { id: 9, sap: 'S-1009', name: 'Emergency hatch', cat: 'FITTINGS', sub: 'SAFETY', unit: 'Each', price: 750, age: 200, extra: true },
    { id: 10, sap: 'S-1010', name: 'Micro switch at door', cat: 'ELECTRICAL', sub: 'SWITCHES', unit: 'Each', price: 520, age: 9, extra: true },
    { id: 11, sap: 'S-1011', name: 'Stainless steel access ladder', cat: 'FITTINGS', sub: 'ACCESS', unit: 'Each', price: 1930, age: 60, extra: true },
    { id: 12, sap: 'S-1012', name: 'Stainless steel evaporator protector', cat: 'FITTINGS', sub: 'REFRIGERATION', unit: 'Each', price: null, age: null, extra: true },
    { id: 13, sap: 'S-1013', name: 'Two drain holes', cat: 'FITTINGS', sub: 'FLOOR', unit: 'Each', price: 578, age: 15, extra: true },
    { id: 14, sap: 'S-1014', name: 'Meat rail – per metre', cat: 'FITTINGS', sub: 'MEAT', unit: 'Meter', price: 640, age: 4, extra: true },
    { id: 15, sap: 'S-1015', name: 'GRP panel 2×450', cat: 'PANELS', sub: 'GRP', unit: 'm²', price: 280, age: 3 },
    { id: 16, sap: 'S-1016', name: 'Sealant cartridge', cat: 'CONSUMABLES', sub: 'ADHESIVES', unit: 'each', price: 95, age: 8 },
    { id: 17, sap: 'S-1017', name: 'PU foam kit', cat: 'INSULATION', sub: 'PU', unit: 'each', price: 1100, age: 33 },
    { id: 18, sap: 'S-1018', name: 'Hinge set HD', cat: 'DOORS', sub: 'HARDWARE', unit: 'each', price: 640, age: 95 },
    { id: 19, sap: 'S-1019', name: 'Lock bar set', cat: 'DOORS', sub: 'HARDWARE', unit: 'each', price: 950, age: 95 },
    { id: 20, sap: 'S-1020', name: 'Door seal', cat: 'DOORS', sub: 'SEALS', unit: 'metre', price: 45, age: 2 },
    { id: 21, sap: 'S-1021', name: 'Alu angle 50×50', cat: 'ALUMINIUM', sub: 'EXTRUSIONS', unit: 'metre', price: 78, age: 40 },
    { id: 22, sap: 'S-1022', name: 'Reflexite tape', cat: 'CONSUMABLES', sub: 'TAPE', unit: 'metre', price: 38, age: 100 },
    { id: 23, sap: 'S-1023', name: 'Spray paint (touch-up)', cat: 'PAINT', sub: 'FINISH', unit: 'litre', price: 260, age: 18 },
    { id: 24, sap: 'S-1024', name: 'Rivet pack (500)', cat: 'CONSUMABLES', sub: 'FASTENERS', unit: 'pack', price: 310, age: 5 },
    { id: 25, sap: 'S-1025', name: 'Anti-skid coat', cat: 'PAINT', sub: 'FLOOR', unit: 'm²', price: 32, age: 27 },
    { id: 26, sap: 'S-1026', name: 'Floor plate 3CR12', cat: 'STEEL', sub: 'PLATE', unit: 'each', price: null, age: null },
  ];

  const REPAIR_TYPES = ['Panel repair', 'Door re-hang', 'Floor repair', 'Roof leak repair', 'Rear frame repair', 'Other'];

  const CUSTOMERS = [
    { id: 'A', name: 'Customer A', contacts: ['Contact A1', 'Contact A2'] },
    { id: 'B', name: 'Customer B', contacts: ['Contact B1'] },
    { id: 'C', name: 'Customer C', contacts: [] },
  ];

  // Existing costings (drives duplicate detection → the truthful Save button)
  const EXISTING = [
    { customer: 'A', type: 'body', bodyId: 20, quote: 'Q-A101', revs: 2 },
    { customer: 'B', type: 'repair', quote: 'Q-B207', revs: 1 },
  ];

  const CHASSIS = {
    suspension: [{ id: 1, name: 'Air suspension kit', price: 9800 }, { id: 2, name: 'Mechanical suspension kit', price: 6200 }],
    lift: [{ id: 1, name: 'Lift axle kit', price: 7400 }],
    brake: [{ id: 1, name: 'Drum brake kit', price: 3100 }, { id: 2, name: 'Disc brake kit', price: 4400 }],
    tyre: [{ id: 1, name: '385/65 R22.5', price: 3200 }, { id: 2, name: '315/80 R22.5', price: 2900 }],
    rim: [{ id: 1, name: 'Steel rim 22.5', price: 1100 }, { id: 2, name: 'Alloy rim 22.5', price: 2600 }],
    constants: [{ name: 'Chassis rail (per m)', perM: 420, k: 0 }, { name: 'Landing legs', perM: 0, k: 3800 }],
  };

  // Validated references — identity = body + dims + door + insulation + extras + excluded categories.
  // baseline is filled at first load from the mock engine so the demo self-balances.
  const REFS = [
    { id: 1, bodyId: 20, label: 'Std 5.6 m freezer · PU', marked: '11 Aug', identity: { dims: { L: 5.6, W: 2.5, H: 2.4 }, door: 'DRD', ins: { FRONT: 'PU/60', DRD: 'PU/60', SRD: 'PU/60', SIDES: 'PU/60', ROOF: 'PU/100', FLOOR: 'PU/100' }, extras: [], excluded: [] }, baseline: null },
    { id: 2, bodyId: 20, label: '6.0 m freezer · EPS sides', marked: '13 Aug', identity: { dims: { L: 6.0, W: 2.5, H: 2.5 }, door: 'DRD', ins: { FRONT: 'PU/60', DRD: 'PU/60', SRD: 'PU/60', SIDES: 'EPS/60', ROOF: 'PU/100', FLOOR: 'PU/100' }, extras: [], excluded: [] }, baseline: null },
  ];

  return { BODIES, STOCK, REPAIR_TYPES, CUSTOMERS, EXISTING, CHASSIS, REFS, WASTE: 0.05 };
})();
