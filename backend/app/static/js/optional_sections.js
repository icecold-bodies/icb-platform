// Shared opt-in section state for EXTRAS / OPTIONAL EXTRAS (any
// bom_sections row with is_optional = 1). Loaded by both calculator.js
// (Costings 1) and calculator2.js (Costings 2) so the two pages share
// the same per-trailer state shape:
//
//   optsec_enabled_<tid>       — Set of bom_section_id that the user
//                                has ticked ON. Optional sections not in
//                                this set are greyed out + contribute 0.
//   optsec_row_excl_<page>_<tid> — Set of bom_id that the user has
//                                individually ticked OFF inside an
//                                enabled optional section. page = 'c1'
//                                or 'c2'. Costings 2 also keeps its
//                                existing _calc2Excl set for non-
//                                optional rows — the two are merged at
//                                payload time.

(function () {
  function _key(tid)             { return `optsec_enabled_${tid}`; }
  function _rowKey(tid, page)    { return `optsec_row_excl_${page}_${tid}`; }

  function loadEnabled(tid) {
    if (!tid) return new Set();
    try {
      const raw = localStorage.getItem(_key(tid));
      return new Set((raw ? JSON.parse(raw) : []).map(Number).filter(Number.isFinite));
    } catch (_) { return new Set(); }
  }
  function saveEnabled(tid, set) {
    if (!tid) return;
    try { localStorage.setItem(_key(tid), JSON.stringify([...set])); } catch (_) {}
  }
  function loadRowExcl(tid, page) {
    if (!tid) return new Set();
    try {
      const raw = localStorage.getItem(_rowKey(tid, page));
      return new Set((raw ? JSON.parse(raw) : []).map(Number).filter(Number.isFinite));
    } catch (_) { return new Set(); }
  }
  function saveRowExcl(tid, page, set) {
    if (!tid) return;
    try { localStorage.setItem(_rowKey(tid, page), JSON.stringify([...set])); } catch (_) {}
  }

  // Walk the items list and return every bom_id that should be treated as
  // excluded because of the optional-section layer — either the section is
  // not enabled, or the section is enabled but the row is individually
  // ticked off. Items in non-optional sections are never added.
  function compute(items, tid, page) {
    const enabled = loadEnabled(tid);
    const rowExcl = loadRowExcl(tid, page);
    const out = new Set();
    (items || []).forEach(it => {
      if (!it || !it.section_is_optional) return;
      const sid = it.bom_section_id;
      if (sid == null) return;
      if (!enabled.has(+sid)) {
        if (it.bom_id != null) out.add(+it.bom_id);
        return;
      }
      if (it.bom_id != null && rowExcl.has(+it.bom_id)) {
        out.add(+it.bom_id);
      }
    });
    return out;
  }

  // Master header toggle: it turns the SECTION on or off, and nothing more.
  //
  // v1.47 (Michael, 18 Aug): turning a section ON no longer selects its rows.
  // An OPTIONAL EXTRAS section can hold hundreds of items, so the old behaviour
  // ("on" = include every row) made the only route to costing ONE extra
  // "include all ~300, then untick 299". Now:
  //
  //   ON  -> section enabled, EVERY row left excluded. The user then ticks the
  //          few items they actually want, one by one.
  //   OFF -> section disabled, every row excluded (unchanged).
  //
  // "Select all" is still one click away on the header pill for the rare case
  // where the whole section really is wanted — the two actions are now distinct
  // instead of the master tick silently doing both.
  function toggleSection(tid, page, sectionId, allBomIdsInSection, enabled) {
    if (!tid || sectionId == null) return;
    const enSet = loadEnabled(tid);
    const exSet = loadRowExcl(tid, page);
    const ids = Array.isArray(allBomIdsInSection) ? allBomIdsInSection.map(Number).filter(Number.isFinite) : [];
    if (enabled) enSet.add(+sectionId);
    else         enSet.delete(+sectionId);
    // Either way the rows start excluded: switching a section on is an
    // invitation to choose, not a bulk selection.
    ids.forEach(id => exSet.add(+id));
    saveEnabled(tid, enSet);
    saveRowExcl(tid, page, exSet);
  }

  function toggleRow(tid, page, sectionId, allBomIdsInSection, bomId, excluded) {
    if (!tid || bomId == null) return;
    const ids = Array.isArray(allBomIdsInSection) ? allBomIdsInSection.map(Number).filter(Number.isFinite) : [];
    const exSet = loadRowExcl(tid, page);
    const enSet = loadEnabled(tid);
    const sid = sectionId != null ? +sectionId : null;
    const wasEnabled = sid != null && enSet.has(sid);
    // Fresh disabled sections historically persisted as:
    //   enabled = false, rowExcl = []
    // Seed every row as excluded before including the clicked one so the
    // first untick produces a partial state instead of waking the whole section.
    if (!excluded && sid != null && !wasEnabled && ids.length) {
      ids.forEach(id => exSet.add(+id));
    }
    if (excluded) exSet.add(+bomId);
    else          exSet.delete(+bomId);
    if (sid != null) {
      if (!excluded) {
        enSet.add(sid);
      }
      if (ids.length) {
        const allExcluded = ids.every(id => exSet.has(+id));
        if (allExcluded) enSet.delete(sid);
        else             enSet.add(sid);
      }
    }
    saveEnabled(tid, enSet);
    saveRowExcl(tid, page, exSet);
  }

  // Bulk select/deselect every row in an optional section.
  // selectAll=true  → clear all matching bom_ids from the excl set (= included)
  // selectAll=false → add all matching bom_ids to the excl set    (= excluded)
  //
  // v1.47 (Michael, 18 Aug): "Deselect all" clears the ROWS and leaves the
  // SECTION ON. It used to switch the section off as well, which made
  // "deselect all, then pick the two I want" impossible — the section went
  // dark and every row with it, so the only way back was Select all. The
  // master tick is the control for the section; this pill is the control for
  // the rows, and it no longer reaches across.
  function bulkRows(tid, page, sectionId, bomIds, selectAll) {
    if (!tid || !Array.isArray(bomIds)) return;
    const exSet = loadRowExcl(tid, page);
    const enSet = loadEnabled(tid);
    bomIds.forEach(id => {
      if (selectAll) exSet.delete(+id);
      else           exSet.add(+id);
    });
    // Both directions leave the section ENABLED: after either bulk action the
    // user is still working inside the section.
    if (sectionId != null) enSet.add(+sectionId);
    saveEnabled(tid, enSet);
    saveRowExcl(tid, page, exSet);
  }

  window.OptionalSections = {
    loadEnabled, saveEnabled,
    loadRowExcl, saveRowExcl,
    compute, toggleSection, toggleRow, bulkRows,
  };
})();
