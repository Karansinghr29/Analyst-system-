/*
 * filters.js -- the analyst filter bar.
 *
 * This module holds a selection and turns it into request parameters. It does not filter
 * anything: the narrowing happens in the engine, behind the Trust Gate, and what comes back is
 * rendered as it arrives. There is no arithmetic here at all -- no total, no percentage, no
 * comparison, no re-selection of a value the server did not send.
 *
 * The selection lives in the URL, so a filtered view can be reloaded, bookmarked and shared
 * without a second copy of the state existing anywhere.
 *
 * The comparison month is a CHOICE, always shown in the bar. When a period is picked the bar
 * offers the month before it as the starting selection, visibly, in the control -- the analyst
 * can see and change it. Nothing is substituted behind the answer: if the pair cannot be
 * compared, the engine says so against the months that were asked for.
 */

import { el } from './render.js';

// `range` rides in the route with the filters but is not one: it chooses how much of a recorded
// history a chart draws, and is never sent to the engine, because it narrows a picture rather
// than a question.
const KEYS = ['period', 'compare', 'apartment', 'range'];
const FILTER_KEYS = ['period', 'compare', 'apartment'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

export function monthName(period) {
  const m = String(period || '').match(/^(\d{4})-(\d{2})/);
  if (!m) return String(period || '');
  return MONTHS[Number(m[2]) - 1] + ' ' + m[1];
}

/* The selection carried in the current route, e.g. #/bi/financial?period=2026-08 */
export function readFilters() {
  const hash = location.hash || '';
  const q = hash.indexOf('?');
  const out = { period: '', compare: '', apartment: '', range: '' };
  if (q === -1) return out;
  const params = new URLSearchParams(hash.slice(q + 1));
  KEYS.forEach(function (k) { out[k] = (params.get(k) || '').trim(); });
  return out;
}

export function routeOf(hash) {
  const q = String(hash || '').indexOf('?');
  return q === -1 ? String(hash || '') : String(hash).slice(0, q);
}

export function hrefWith(route, filters) {
  const pairs = [];
  KEYS.forEach(function (k) {
    if (filters && filters[k]) pairs.push(k + '=' + encodeURIComponent(filters[k]));
  });
  return pairs.length ? route + '?' + pairs.join('&') : route;
}

export function anyFilter(filters) {
  return FILTER_KEYS.some(function (k) { return filters && filters[k]; });
}

/* One filter changed, the rest of the route kept. */
export function withFilter(filters, key, value) {
  const next = {};
  KEYS.forEach(function (k) { next[k] = filters ? filters[k] : ''; });
  next[key] = value;
  return next;
}

/*
 * Calendar arithmetic on a month label -- moving a selection in a dropdown, not computing a
 * business figure. Whether the month it lands on exists in the records is decided against the
 * month list the server sent, never assumed.
 */
function shiftMonth(period, back) {
  const m = String(period || '').match(/^(\d{4})-(\d{2})$/);
  if (!m) return '';
  const total = Number(m[1]) * 12 + (Number(m[2]) - 1) - back;
  return Math.floor(total / 12) + '-' + String((total % 12) + 1).padStart(2, '0');
}

/* Which comparison the current selection represents, so the control opens on it. */
function modeFor(filters, modes) {
  if (!filters.compare) return 'none';
  const named = modes.find(function (m) {
    return m.available && m.period && m.period === filters.compare;
  });
  return named ? named.key : 'custom';
}

function select(name, label, options, value) {
  const wrap = el('label', 'filter-field');
  wrap.appendChild(el('span', 'filter-label', label));
  const box = document.createElement('select');
  box.className = 'filter-select';
  box.name = name;
  options.forEach(function (option) {
    const node = document.createElement('option');
    node.value = option.value;
    node.textContent = option.label;
    if (option.disabled) node.disabled = true;
    if (option.value === value) node.selected = true;
    box.appendChild(node);
  });
  wrap.appendChild(box);
  return wrap;
}

/*
 * The bar itself. `options` is the server's own `filter_options` block: the months a comparable
 * series actually has, which of them the export covers in full, and the apartment codes the
 * export contains. Nothing is offered that the engine did not list.
 */
export function filterBar(options, filters, onApply) {
  const opts = options || {};
  const months = (opts.months || []).slice().reverse();
  const partial = new Set(opts.partial_months || []);
  const apartments = opts.apartments || [];

  const bar = el('form', 'filter-bar');
  bar.setAttribute('data-section', 'filters');
  bar.setAttribute('aria-label', 'Analyst filters');

  const monthOptions = [{ value: '', label: 'All recorded months' }].concat(
    months.map(function (m) {
      return { value: m, label: monthName(m) + (partial.has(m) ? ' (part-month)' : '') };
    }));
  const compareOptions = [{ value: '', label: 'No comparison' }].concat(
    months.map(function (m) {
      return { value: m, label: monthName(m) + (partial.has(m) ? ' (part-month)' : '') };
    }));
  const apartmentOptions = [{ value: '', label: 'All apartments' }].concat(
    apartments.map(function (a) { return { value: a, label: a }; }));

  // The comparison is chosen in two visible steps: which KIND of comparison, and then which
  // month it lands on. The kinds come from the server -- a mode whose month is not in the
  // records is offered disabled, with the reason on it, rather than quietly missing.
  const modes = (opts.comparison_modes || []).filter(function (m) {
    return m.key !== 'none';
  });
  const modeOptions = [{ value: 'none', label: 'No comparison' }].concat(
    modes.map(function (m) {
      return {
        value: m.key,
        label: m.label + (m.available ? '' : ' — not recorded'),
        disabled: !m.available,
      };
    }));
  const activeMode = modeFor(filters, modes);

  const period = select('period', 'Period', monthOptions, filters.period);
  const mode = select('mode', 'Compare', modeOptions, activeMode);
  const compare = select('compare', 'Comparison month', compareOptions, filters.compare);
  const apartment = select('apartment', 'Apartment', apartmentOptions, filters.apartment);
  bar.appendChild(period);
  bar.appendChild(mode);
  bar.appendChild(compare);
  bar.appendChild(apartment);

  const periodBox = period.querySelector('select');
  const modeBox = mode.querySelector('select');
  const compareBox = compare.querySelector('select');

  function applyMode() {
    const chosen = modes.find(function (m) { return m.key === modeBox.value; });
    if (modeBox.value === 'none') { compareBox.value = ''; compareBox.disabled = true; return; }
    compareBox.disabled = false;
    // A named mode moves the month box to the month the SERVER said that mode lands on, in
    // full view. "Choose a month" leaves it alone -- that is the whole point of it.
    if (chosen && chosen.period) compareBox.value = chosen.period;
  }
  modeBox.addEventListener('change', applyMode);
  periodBox.addEventListener('change', function () {
    if (modeBox.value === 'none' || modeBox.value === 'custom') return;
    // The named modes are relative to the period, so the month they land on moves with it.
    // Recomputed from the recorded months the server listed, and left blank when the month it
    // would need is not among them.
    const target = shiftMonth(periodBox.value, modeBox.value === 'last_year' ? 12 : 1);
    compareBox.value = (opts.months || []).indexOf(target) === -1 ? '' : target;
  });
  applyMode();

  const actions = el('div', 'filter-actions');
  const apply = el('button', 'filter-apply', 'Apply');
  apply.type = 'submit';
  actions.appendChild(apply);
  const reset = el('button', 'filter-reset', 'Reset');
  reset.type = 'button';
  reset.addEventListener('click', function () {
    onApply({ period: '', compare: '', apartment: '', range: '' });
  });
  actions.appendChild(reset);
  bar.appendChild(actions);

  bar.addEventListener('submit', function (event) {
    event.preventDefault();
    onApply({
      period: periodBox.value,
      compare: compareBox.value,
      apartment: apartment.querySelector('select').value,
      range: filters.range || '',
    });
  });

  const summary = el('p', 'filter-summary');
  summary.setAttribute('data-section', 'filter-summary');
  const parts = [];
  if (filters.period) {
    parts.push(monthName(filters.period) + (partial.has(filters.period) ? ' (part-month)' : ''));
  }
  if (filters.compare) {
    const named = modes.find(function (m) {
      return m.available && m.period === filters.compare && m.key !== 'custom';
    });
    parts.push('compared with ' + monthName(filters.compare)
      + (partial.has(filters.compare) ? ' (part-month)' : '')
      + (named ? ' (' + named.label.toLowerCase() + ')' : ''));
  }
  if (filters.apartment) parts.push(filters.apartment);
  summary.textContent = parts.length
    ? 'Showing: ' + parts.join(' · ')
    : 'Showing: all recorded months · all apartments';
  bar.appendChild(summary);

  // No note about which measures cannot be read per apartment. Those measures are simply not on
  // the page: an owner who chose an apartment is shown what the records hold for it, not an
  // explanation of the ones that could not answer.
  return bar;
}
