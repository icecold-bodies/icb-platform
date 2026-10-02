/* RT3 — body families in the browser.
 *
 * A body's family is DATA: the bodies API returns `family {id, name, colour, ink, sort_order}`
 * on every /api/trailers row, and the server-rendered dropdowns carry the same values as data-fam-* attributes
 * (services/body_family.py is the one source). This file only DRAWS a family: optgroups in the families'
 * order, coloured options, the closed-box bar, chips. Its only colour of its own is FALLBACK's grey, for a
 * row that arrives without a family.
 *
 * The family NAME always travels with the colour (RT3 design rule 6): the optgroup label, the chip's text,
 * the closed box's tooltip.
 */
(function () {
  'use strict';
  var FALLBACK = { id: null, name: 'OTHER', colour: '#7D858C', ink: '#6A7177', sort_order: 1000 };   // = services/body_family.fallback_family()

  function fam(f) { return (f && f.colour) ? f : FALLBACK; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function vars(f) {
    f = fam(f);
    return '--fam:' + f.colour + ';--fam-ink:' + f.ink;
  }
  function chip(f, opts) {
    f = fam(f);
    var t = (opts && opts.title) || ('Family: ' + f.name);
    return '<span class="fam-chip" data-family="' + esc(f.name) + '" style="' + vars(f) + '" title="' + esc(t) + '">' +
      esc(f.name) + '</span>';
  }
  // Paint one <option> (or any element) with its family: colour, data-fam-* for the closed-box bar.
  function paintOption(opt, f) {
    f = fam(f);
    opt.classList.add('fam-ink');
    opt.setAttribute('style', vars(f));
    opt.dataset.famName = f.name;
    opt.dataset.famColour = f.colour;
    opt.dataset.famInk = f.ink;
  }
  // [[family, [items…]], …] — families in (sort_order, name) order; items keep the order they came in.
  function group(items, familyOf) {
    familyOf = familyOf || function (it) { return it.family; };
    var byKey = {}, out = [];
    items.forEach(function (it) {
      var f = fam(familyOf(it));
      var k = (f.id == null ? 'x' : f.id) + '|' + f.name;
      if (!byKey[k]) { byKey[k] = [f, []]; out.push(byKey[k]); }
      byKey[k][1].push(it);
    });
    out.sort(function (a, b) {
      return (a[0].sort_order - b[0].sort_order) || a[0].name.toUpperCase().localeCompare(b[0].name.toUpperCase());
    });
    return out;
  }
  // Fill a <select> with one <optgroup> per family. opts: value(it), label(it), decorate(opt, it) (optional),
  // familyOf(it) (default it.family), head: HTML kept before the groups (e.g. "— Select —").
  function fillSelect(sel, items, opts) {
    opts = opts || {};
    sel.innerHTML = opts.head || '';
    group(items, opts.familyOf).forEach(function (pair) {
      var f = pair[0], og = document.createElement('optgroup');
      og.label = f.name;
      og.dataset.familyId = f.id == null ? '' : String(f.id);
      og.dataset.sortOrder = String(f.sort_order);
      pair[1].forEach(function (it) {
        var o = document.createElement('option');
        o.value = String(opts.value ? opts.value(it) : it.id);
        o.textContent = opts.label ? opts.label(it) : it.name;
        paintOption(o, f);
        if (opts.decorate) opts.decorate(o, it);
        og.appendChild(o);
      });
      sel.appendChild(og);
    });
    refresh(sel);
  }
  // Add ONE option for a body row into its family's optgroup (creating the optgroup in sort order, before any
  // trailing non-family group such as the calculator's REPAIRS divider). Returns the option.
  function addOption(sel, row, label) {
    var f = fam(row.family);
    var groups = Array.prototype.filter.call(sel.querySelectorAll('optgroup'), function (g) { return g.dataset.familyId !== undefined; });
    var og = groups.filter(function (g) { return g.label === f.name; })[0];
    if (!og) {
      og = document.createElement('optgroup');
      og.label = f.name;
      og.dataset.familyId = f.id == null ? '' : String(f.id);
      og.dataset.sortOrder = String(f.sort_order);
      var after = groups.filter(function (g) {
        var so = +g.dataset.sortOrder;
        return so < f.sort_order || (so === f.sort_order && g.label.toUpperCase() < f.name.toUpperCase());
      }).pop();
      var anchor = after ? after.nextSibling : (groups[0] || sel.querySelector('optgroup:not([data-family-id])'));
      sel.insertBefore(og, anchor || null);
    }
    var o = document.createElement('option');
    o.value = String(row.id);
    o.textContent = label || row.name;
    paintOption(o, f);
    og.appendChild(o);
    return o;
  }
  // The closed box: the wrapper's bar takes the SELECTED option's family colour; the tooltip names the family.
  function refresh(sel) {
    if (!sel) return;
    var o = sel.selectedOptions && sel.selectedOptions[0];
    var colour = o && o.dataset.famColour, name = o && o.dataset.famName;
    var wrap = sel.closest('.fam-select-wrap');
    if (wrap) {
      if (colour) wrap.style.setProperty('--fam', colour); else wrap.style.removeProperty('--fam');
      wrap.dataset.family = name || '';
    }
    if (name) sel.title = 'Family: ' + name; else sel.removeAttribute('title');
  }
  function bind(sel) {
    if (!sel || sel.dataset.famBound) return;
    sel.dataset.famBound = '1';
    sel.addEventListener('change', function () { refresh(sel); });
    refresh(sel);
  }
  // The selected option's family as a chip ('' when the option has none).
  function selectedChip(sel) {
    var o = sel && sel.selectedOptions && sel.selectedOptions[0];
    if (!o || !o.dataset.famName) return '';
    return chip({ id: null, name: o.dataset.famName, colour: o.dataset.famColour, ink: o.dataset.famInk, sort_order: 0 });
  }

  window.BodyFamily = { FALLBACK: FALLBACK, chip: chip, vars: vars, group: group, fillSelect: fillSelect,
                        addOption: addOption, paintOption: paintOption, refresh: refresh, bind: bind,
                        selectedChip: selectedChip };
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.fam-select-wrap > select').forEach(bind);
  });
})();
