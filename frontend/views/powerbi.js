/*
 * views/powerbi.js -- the Power BI Analyst workspace.
 *
 * An analyst reads a business in a fixed order: what the figures are, how they moved, what they
 * break down into, what changed, what needs a decision, and what the definitions and caveats
 * are. Every page here follows that order, and each section is drawn from a payload the engine
 * already produced.
 *
 * This layer computes NOTHING. It selects which authorized measure belongs in which section,
 * reads the series and breakdowns the engine put on the tile, and draws them. The only
 * arithmetic is chart geometry -- turning a value into a pixel. A figure that is not in the
 * payload does not appear, and a definition the gate refused to collapse stays uncollapsed.
 *
 * The trust posture is read, never decided: SAFE renders a figure, DISCLOSE renders it with its
 * caveat beside it, SHOW_BOTH renders every competing definition, BLOCK renders no headline at
 * all, and NOT_DETERMINABLE says so. The workspace cannot soften any of them, because it has no
 * code path that writes one.
 */

import { api } from '../api.js';
import { el, section, loading, errorState, emptyState, changeCard } from '../render.js';
import { badge } from '../trust.js';
import { ownerView, ownerTitle, ownerProse, ownerText, ownerDecision, splitComposite,
  ownerDefinitionLabels } from '../owner_view.js';
import { lineChart, barChart, kpi, monthLabel, fmtMoney } from '../charts.js';
import { BI_PAGES, biHref } from '../bi_nav.js';
import { filterBar, readFilters, hrefWith, anyFilter, withFilter, monthName }
  from '../filters.js';

/* --- the shared page context -----------------------------------------------------------------
 *
 * Set once per render so the pieces below can move the route without each being handed the
 * filters, the page key and the re-render function separately.
 */
let VIEW = { key: 'executive', filters: {}, rerender: function () {} };

// Which render is the live one. See `renderPowerBi`.
let RENDER_TICKET = 0;

function goWith(key, value) {
  location.hash = hrefWith(biHref(VIEW.key), withFilter(VIEW.filters, key, value));
  VIEW.rerender();
}

/*
 * A trend, with the interactions an analyst needs on one: what a point is worth, and the
 * ability to look at that month. Selecting a point moves the SHARED period filter, so the
 * chart, the bar and the comparison are always describing the same question.
 */
function trend(tile, label) {
  const wrap = el('div', 'trend');
  // The measure is not on this page at all -- omitted because it could not answer the narrowed
  // question. There is nothing to say about a chart that was never offered, so not even the
  // range control is drawn.
  if (!tile) return wrap;
  const points = seriesOf(tile);
  const full = (VIEW.filters.range || '') === 'full';

  // A series that came back empty because the engine REFUSED the request is not an empty
  // series. Drawing a blank chart under "0 recorded months available" says the records hold
  // nothing, when what happened is that this measure is not kept per apartment and declined to
  // pretend otherwise. The engine's own sentence is shown instead of a chart.
  if (points.length === 0 && tile && tile.unavailable_reason) {
    wrap.appendChild(emptyState(ownerProse(tile.unavailable_reason)));
    return wrap;
  }

  wrap.appendChild(rangeControl(points.length, full));
  wrap.appendChild(lineChart(points, {
    label: label,
    recent: full ? 0 : 24,
    asOf: VIEW.asOf,
    displays: (tile && tile.series_display) || {},
    selected: VIEW.filters.period,
    onSelect: function (period) { goWith('period', period); },
  }));
  return wrap;
}

function rangeControl(count, full) {
  const nav = el('div', 'range-control');
  nav.appendChild(el('span', 'range-label', 'Range'));
  [['', 'Recent'], ['full', 'Full recorded history']].forEach(function (choice) {
    const button = el('button', 'range-choice', choice[1]);
    button.type = 'button';
    if ((choice[0] === 'full') === full) button.classList.add('active');
    button.addEventListener('click', function () { goWith('range', choice[0]); });
    nav.appendChild(button);
  });
  nav.appendChild(el('span', 'range-count', count + ' recorded months available'));
  return nav;
}

/* --- selecting from the payload ------------------------------------------------------------ */
//
// Measures are found by the name the registry gives them, never by a record identifier: the
// frontend has no business knowing one, and a hardcoded id here would be a second place where
// the semantic layer is defined.

function pickTile(tiles, name) {
  const wanted = String(name).toLowerCase();
  const titled = (tiles || []).map(function (t) {
    return [String(t.title || '').toLowerCase(), t];
  });
  // An exact title wins over a prefix. Two measures can share an opening: "Revenue by month" is
  // the estate series, and "Revenue by month for one apartment" is a different measure whose
  // title begins with it. Prefix-first would hand whichever the registry happened to list
  // earlier -- a lookup that depends on row order is a lookup waiting to break.
  const exact = titled.find(function (pair) { return pair[0] === wanted; });
  if (exact) return exact[1];
  // A prefix may only pick up the QUALIFIER the registry appends to a measure's own name --
  // "Owner rent (ledger bucket…)", "Tenant dues -- Def A…". It must never run on into a
  // different measure whose name happens to begin the same way: with the estate series absent
  // under an apartment filter, "Revenue by month" would otherwise match "Revenue by month for
  // one apartment" and show one apartment's figures under the estate's heading.
  const partialQualifier = wanted.indexOf('(') !== -1;
  const prefixed = titled.find(function (pair) {
    if (pair[0].indexOf(wanted) !== 0) return false;
    const rest = pair[0].slice(wanted.length);
    // Already inside the qualifier ("Revenue (total" -> "Revenue (total, ledger-derived)"), or
    // stopping exactly where the qualifier begins.
    return partialQualifier || rest === ''
      || rest.indexOf(' (') === 0 || rest.indexOf(' --') === 0;
  });
  return prefixed ? prefixed[1] : null;
}

function pickAll(tiles, names) {
  return names.map(function (n) { return pickTile(tiles, n); }).filter(Boolean);
}

/* A month-keyed dict as ordered [period, value] pairs. Ordering only -- no value is touched. */
function monthPairs(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.keys(value)
    .filter(function (k) { return /^\d{4}-\d{2}/.test(k); })
    .sort()
    .map(function (k) { return [k, value[k]]; });
}

/* A monthly series the engine put on the tile, in its own order. */
function seriesOf(tile) {
  const value = tile && tile.value;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const keys = Object.keys(value).filter(function (k) { return /^\d{4}-\d{2}/.test(k); });
  if (keys.length === 0) return [];
  return keys.sort().map(function (k) { return [k, value[k]]; });
}

/* A flat category breakdown, labelled the way the rest of the product labels parts. */
function breakdownOf(tile) {
  const value = tile && tile.value;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  return Object.keys(value)
    .filter(function (k) { return !/^\d{4}-\d{2}/.test(k) && typeof value[k] === 'number'; })
    .map(function (k) {
      const label = k.replace(/_/g, ' ');
      return [label.charAt(0).toUpperCase() + label.slice(1), value[k]];
    });
}

function findChange(changes, name) {
  const wanted = String(name).toLowerCase();
  return (changes || []).find(function (c) {
    return String(c.title || '').toLowerCase().indexOf(wanted) === 0;
  }) || null;
}

/* --- small presentational pieces ------------------------------------------------------------ */

function block(title, note) {
  const wrap = el('section', 'bi-block');
  wrap.setAttribute('data-block', String(title).toLowerCase().replace(/[^a-z]+/g, '-'));
  wrap.appendChild(el('h2', 'bi-block-title', title));
  if (note) wrap.appendChild(el('p', 'bi-block-note', note));
  return wrap;
}

function sub(title) {
  return el('h3', 'bi-sub-title', title);
}

/*
 * One measure as a KPI. The trust posture decides the shape, exactly as it does on Owner Home:
 * a measure with no permitted headline shows its definitions instead of a number.
 */
function kpiFor(tile, label) {
  if (!tile) return null;
  // A month-by-month series is a chart, not a headline. Rendered as a KPI it leads with
  // whichever month happens to sort first -- a real figure standing for the wrong thing.
  if (seriesOf(tile).length > 0) return null;
  const view = ownerView(tile);
  const trust = (tile.trust || {}).trust_level || '';
  // `view.title` is the engine's business name for the measure, from the semantic contract the
  // tile carries. An explicit `label` still wins: a page section that names a measure its own
  // way is naming the SLOT, not the measure.
  const title = label || view.title;
  // A measure whose recorded value is several quantities at once -- electricity is a bill and a
  // number of units -- has no single headline to lead with. The parts are what it is, so the
  // first one leads and the rest follow, instead of the card falling through to a card with no
  // figure on it at all.
  const parts = view.secondary || [];
  if (!view.value && parts.length > 0) {
    const card = kpi(title + ' — ' + parts[0].label, parts[0].value,
      { trust: trust, note: view.caveat ? ownerProse(view.caveat) : '' });
    parts.slice(1).forEach(function (p) {
      card.appendChild(el('p', 'kpi-part', p.label + ': ' + p.value));
    });
    return card;
  }
  if (view.value) {
    const card = kpi(title, view.value,
      { trust: trust, note: view.caveat ? ownerProse(view.caveat) : '' });
    parts.forEach(function (p) {
      card.appendChild(el('p', 'kpi-part', p.label + ': ' + p.value));
    });
    return card;
  }
  const card = kpi(title, '', { trust: trust });
  card.querySelector('.kpi-value').textContent = (tile.trust || {}).owner_label || '—';
  card.querySelector('.kpi-value').classList.add('kpi-value-refused');
  if (view.unavailable) card.appendChild(el('p', 'kpi-note', view.unavailable));
  return card;
}

/*
 * A row of KPI cards. An entry is a tile, or a { tile, label } pair where the registry's own
 * name would leave two cards side by side reading identically -- two definitions of collections
 * are two different measures to an owner, and a row that calls both "Collections" hides that.
 */
function kpiRow(entries) {
  const row = el('div', 'kpi-row');
  row.setAttribute('data-section', 'kpi-summary');
  let any = false;
  entries.forEach(function (entry) {
    const tile = entry && entry.tile !== undefined ? entry.tile : entry;
    const card = kpiFor(tile, entry && entry.label);
    if (card) { row.appendChild(card); any = true; }
  });
  if (!any) row.appendChild(emptyState('No measure in this group is visible to your role.'));
  return row;
}

/*
 * The competing definitions of a BLOCKED measure.
 *
 * Owner Home deliberately shows none of them: a blocked measure is stated as unavailable there
 * and the definitions live on the detail view. An analyst workspace is that detail view, and the
 * brief for it is explicit -- show the competing definitions, the conflict, and why no single
 * number is given. BLOCK forbids a HEADLINE, which is what stays withheld: `kpiFor` still
 * refuses one for this tile. Nothing is computed here; each label and figure is the string the
 * engine already formatted, projected through the same naming the rest of the product uses.
 */
function blockedDefinitions(tile) {
  const raw = (tile && tile.definitions) || [];
  if (raw.length === 0) return [];
  const labels = ownerDefinitionLabels(raw);
  return raw.map(function (definition, index) {
    const split = splitComposite(definition.display_value || '');
    return { label: labels[index], value: split.main, secondary: split.secondary };
  });
}

/* Every competing definition, named in business terms. Never collapsed, never ordered by
 * preference -- the gate refused to choose and so does this. */
function definitionPanel(tile) {
  if (!tile) return null;
  const view = ownerView(tile);
  const projected = (view.definitions && view.definitions.length > 0)
    ? view.definitions : blockedDefinitions(tile);
  // A narrowed request can leave a conflicted measure with no computable figures. The conflict
  // has not gone away and must not look as though it has: the panel keeps its posture and says
  // why there are no numbers under it, instead of vanishing from the page.
  if (projected.length === 0 && !tile.unavailable_reason) return null;
  const panel = el('section', 'definition-panel');
  panel.setAttribute('data-section', 'definitions');
  panel.setAttribute('data-trust', (tile.trust || {}).trust_level || '');
  const head = el('div', 'definition-head');
  head.appendChild(el('h4', 'definition-measure', view.title));
  if (tile.trust) head.appendChild(badge(tile.trust));
  panel.appendChild(head);
  panel.appendChild(el('p', 'definition-why', (tile.trust || {}).owner_explanation || ''));
  if (projected.length === 0) {
    panel.appendChild(el('p', 'definition-unavailable', ownerProse(tile.unavailable_reason)));
    return panel;
  }
  const list = el('ul', 'definition-list');
  projected.forEach(function (d) {
    const li = el('li', 'definition');
    li.appendChild(el('span', 'definition-label', d.label));
    if (d.value) li.appendChild(el('span', 'definition-value', d.value));
    (d.secondary || []).forEach(function (p) {
      li.appendChild(el('span', 'definition-part', p.label + ': ' + p.value));
    });
    list.appendChild(li);
  });
  panel.appendChild(list);
  return panel;
}

/*
 * What drove a movement.
 *
 * Every figure here was computed and reconciled in the engine: the labels, the signed amounts
 * and the sentence about how the parts relate to the whole all arrive finished. This draws
 * them. The only arithmetic is the bar's width, which is the geometry of a chart, and even the
 * number printed beside each bar is the engine's own string rather than one formatted here.
 *
 * When the engine could not reconcile a split, `components` is empty and the note says a
 * component-level explanation is not available. That note is shown as the answer, because it
 * is one.
 */
function contributions(change) {
  const rows = change.components || [];
  if (rows.length === 0 && !change.component_note) return null;

  const box = el('div', 'contributions');
  box.setAttribute('data-section', 'contributions');
  if (rows.length === 0) {
    box.appendChild(el('p', 'contribution-none', ownerProse(change.component_note)));
    return box;
  }
  box.appendChild(el('h5', 'contribution-title', 'What drove the change'));
  const display = {};
  rows.forEach(function (r) { display[r.label] = r.display_change; });
  box.appendChild(barChart(rows.map(function (r) { return [r.label, r.value]; }),
    { display: display }));
  box.appendChild(el('p', 'contribution-note', ownerProse(change.component_note)));
  return box;
}

/*
 * What an analyst can do with a movement. Each action goes somewhere that already exists: the
 * drivers are the decomposition already on the card, another comparison is the shared filter
 * bar, and the question goes to the AI Analyst through the same route every other question
 * uses. Nothing here is a placeholder.
 */
function movementActions(change, drivers) {
  const nav = el('nav', 'movement-actions');
  nav.setAttribute('aria-label', 'Actions for this movement');

  if (drivers && (change.components || []).length) {
    const toggle = el('button', 'movement-action', 'Hide drivers');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.addEventListener('click', function () {
      const hidden = drivers.hasAttribute('hidden');
      if (hidden) drivers.removeAttribute('hidden'); else drivers.setAttribute('hidden', '');
      toggle.textContent = hidden ? 'Hide drivers' : 'View drivers';
      toggle.setAttribute('aria-expanded', hidden ? 'true' : 'false');
    });
    nav.appendChild(toggle);
  }

  const compare = el('button', 'movement-action', 'Compare another period');
  compare.type = 'button';
  compare.addEventListener('click', function () {
    const bar = document.querySelector('.filter-bar select[name="period"]');
    if (bar) { bar.focus(); bar.scrollIntoView({ block: 'center' }); }
  });
  nav.appendChild(compare);

  const ask = el('a', 'movement-action', 'Ask the AI Analyst');
  const question = (change.ai_entry_points || [])[0];
  ask.href = askHref((question && question.question)
    || ('Why did ' + change.title + ' change?'));
  nav.appendChild(ask);
  return nav;
}

/*
 * The selected month's figure, read out beside the chart.
 *
 * The value printed is the engine's own formatted string for that month -- this picks a key out
 * of a map the server already produced and prints it. A month the series does not contain is
 * said to be absent, never rendered as zero: the records state no zero for it, and showing one
 * would be a figure the evidence does not hold.
 */
function selectedMonthValue(tile, series) {
  const line = el('p', 'selected-month');
  const wanted = String(VIEW.filters.period || '').slice(0, 7);
  if (!wanted) {
    line.textContent = 'Select a month on the chart, or in the filter bar, to read its figure.';
    return line;
  }
  const displays = tile.series_display || {};
  const key = Object.keys(displays).find(function (k) { return k.slice(0, 7) === wanted; });
  if (key) {
    line.appendChild(el('span', 'selected-month-label', monthName(wanted)));
    line.appendChild(el('span', 'selected-month-value', displays[key]));
    return line;
  }
  const present = (series || []).some(function (p) { return String(p[0]).slice(0, 7) === wanted; });
  line.textContent = present
    ? monthName(wanted) + ' is in the records but carries no figure to show.'
    : 'No revenue is recorded against this apartment for ' + monthName(wanted)
      + '. That month is absent from the records, which is not the same as a recorded zero.';
  return line;
}

/* A movement the engine validated. Direction, both periods, size and share -- and the note
 * saying which months were left out, because a part-month is not a fall. */
function movementRow(change) {
  const row = el('article', 'movement');
  row.setAttribute('data-direction', change.direction || '');
  row.setAttribute('data-trust', (change.trust || {}).trust_level || '');
  row.appendChild(el('h4', 'movement-title', ownerTitle(change.title)));
  const line = el('p', 'movement-line');
  line.appendChild(el('span', 'movement-direction', change.direction || ''));
  if (change.display_change) {
    // "rose" and "35,384.03 (1.07%)" are two payload fields; read together they are one
    // sentence, and they need the word and the space that make them one.
    line.appendChild(el('span', 'movement-amount', ' by ' + change.display_change));
  }
  row.appendChild(line);
  if (change.previous_period && change.current_period) {
    row.appendChild(el('p', 'movement-periods',
      change.previous_period + ' → ' + change.current_period));
  }
  // The two figures the comparison is between, beside the movement between them. Every string
  // here was formatted by the engine; this only lays them out against their labels.
  if (change.current_display && change.previous_display) {
    const table = el('dl', 'compare-figures');
    [[change.current_period, change.current_display],
     [change.previous_period, change.previous_display],
     ['Change', change.absolute_display
       + (change.percent_display ? ' (' + change.percent_display + ')' : '')]]
      .forEach(function (pair) {
        if (!pair[1]) return;
        table.appendChild(el('dt', 'compare-label', pair[0]));
        table.appendChild(el('dd', 'compare-value', pair[1]));
      });
    row.appendChild(table);
  }
  // One explanation per row, not four. When the engine has said why the requested comparison
  // cannot be made, its sentence covers the part-month state as well -- the coverage note and
  // the part-month note beside it would restate the same fact twice more under the same card.
  if (change.unavailable_reason) {
    row.appendChild(el('p', 'movement-note', ownerProse(change.unavailable_reason)));
  } else {
    if (change.coverage_note) {
      row.appendChild(el('p', 'movement-note', ownerProse(change.coverage_note)));
    }
    if (change.partial_note) {
      row.appendChild(el('p', 'movement-partial', ownerProse(change.partial_note)));
    }
  }
  // The whole-month pair the engine offers instead. It is a different question, said as one,
  // and it is never rendered in place of the comparison that was asked for.
  if (change.alternative_note) {
    row.appendChild(el('p', 'movement-note', ownerProse(change.alternative_note)));
  }
  const drivers = contributions(change);
  if (drivers) row.appendChild(drivers);
  row.appendChild(movementActions(change, drivers));
  return row;
}

function movements(changes, names) {
  const wrap = el('div', 'movement-grid');
  wrap.setAttribute('data-section', 'movement');
  const rows = names
    ? names.map(function (n) { return findChange(changes, n); }).filter(Boolean)
    : (changes || []);
  if (rows.length === 0) {
    wrap.appendChild(emptyState(
      'No month-to-month comparison is supported here. Only complete months are compared, ' +
      'so a part-month is never presented as a movement.'));
  } else {
    rows.forEach(function (c) { wrap.appendChild(movementRow(c)); });
  }
  return wrap;
}

/* The grouped owner issues, exactly as Owner Home states them. No ranking is added: the
 * evidence defines no priority score, so the order here is the order the engine gave. */
function attention(queue) {
  const wrap = el('div', 'decision-queue');
  wrap.setAttribute('data-section', 'decision-queue');
  if (!queue || queue.length === 0) {
    wrap.appendChild(emptyState('Nothing is awaiting a decision on the current evidence.'));
    return wrap;
  }
  queue.forEach(function (d) {
    const view = ownerDecision(d);
    const item = el('article', 'decision');
    item.setAttribute('data-trust', d.trust || '');
    if (view.title) item.appendChild(el('h4', 'decision-title', view.title));
    if (view.posture) item.appendChild(el('p', 'decision-posture', view.posture));
    if (view.decision) item.appendChild(el('p', 'decision-text', view.decision));
    wrap.appendChild(item);
  });
  return wrap;
}

/* An issue, in the four parts an owner needs: what, how much, why, what to do. */
function issueCard(insight) {
  const card = el('article', 'issue');
  card.setAttribute('data-trust', (insight.trust || {}).trust_level || '');
  const head = el('div', 'issue-head');
  head.appendChild(el('h4', 'issue-title', ownerText(insight.category_label)));
  if (insight.trust) head.appendChild(badge(insight.trust));
  card.appendChild(head);
  card.appendChild(el('p', 'issue-what', ownerProse(insight.what_happened)));
  if (insight.why_it_matters) {
    card.appendChild(el('p', 'issue-why', ownerProse(insight.why_it_matters)));
  }
  if (insight.recommended_action) {
    card.appendChild(el('p', 'issue-action', ownerProse(insight.recommended_action)));
  }
  if (insight.what_would_change_it) {
    card.appendChild(el('p', 'issue-caveat', ownerProse(insight.what_would_change_it)));
  }
  return card;
}

/*
 * The findings of one kind.
 *
 * `families` names the kinds of finding a page is responsible for -- a recording problem belongs
 * on the Risk page, a definition conflict and a period movement belong with the analysis they
 * affect. Without the split, both pages printed the same twenty cards and neither page was about
 * anything. The finding itself is unchanged; only which page it appears on is decided here.
 */
function familyOf(insight) {
  const parts = String((insight && insight.insight_id) || '').split('.');
  return parts.length > 1 ? parts[1] : '';
}

function issueList(insights, families) {
  const wrap = el('div', 'issue-list');
  wrap.setAttribute('data-section', 'issues');
  const rows = (insights || []).filter(function (i) {
    return !families || families.indexOf(familyOf(i)) !== -1;
  });
  if (rows.length === 0) {
    wrap.appendChild(emptyState('No finding of this kind on the current evidence.'));
  } else {
    rows.forEach(function (i) { wrap.appendChild(issueCard(i)); });
  }
  return wrap;
}

function caveats(limitations) {
  const wrap = el('ul', 'caveat-list');
  wrap.setAttribute('data-section', 'caveats');
  (limitations || []).forEach(function (l) {
    wrap.appendChild(el('li', 'caveat', ownerProse(l)));
  });
  return wrap;
}

/* --- analyst actions ------------------------------------------------------------------------ */
//
// Every action opens a surface that already exists. Nothing here is a placeholder: an action
// that had nowhere to go would be a promise the workspace cannot keep.

function actions(items) {
  const nav = el('nav', 'bi-actions');
  nav.setAttribute('data-section', 'actions');
  nav.setAttribute('aria-label', 'Analyst actions');
  items.forEach(function (item) {
    const a = el('a', 'bi-action', item.label);
    a.href = item.href;
    a.setAttribute('data-action', item.action || '');
    nav.appendChild(a);
  });
  return nav;
}

function askHref(question) {
  return '#/ask?q=' + encodeURIComponent(question);
}

/* --- the five analyst pages ------------------------------------------------------------------ */

function executivePage(page, data) {
  // Unfiltered, the snapshot is the fixed set of measures the whole business is read by.
  // Narrowed to an apartment, that set is the wrong question -- most of it is not held per
  // apartment -- so the snapshot becomes whatever the engine could answer at that grain. The
  // server has already dropped everything it could not, so this shows what survived rather
  // than a list of names chosen here.
  const snapshot = block('Business snapshot',
    VIEW.filters.apartment
      ? 'What the records hold for ' + VIEW.filters.apartment + ', each with the posture its '
        + 'own evidence carries.'
      : 'The measures the business is read by, each with the posture its own evidence carries.');
  snapshot.appendChild(kpiRow(VIEW.filters.apartment
    ? (data.tiles || [])
    : pickAll(data.tiles, [
      'Revenue (total', 'Collections (application', 'Expenses (total',
      'Deposit held', 'Owner payments', 'Cash balance',
    ])));
  page.appendChild(snapshot);

  const movement = block('Business movement',
    'Complete months only. A month still in progress is excluded rather than compared.');
  movement.appendChild(movements(data.changes));
  page.appendChild(movement);

  const attn = block('Business attention',
    'Grouped by the business subject each one is about. No priority is implied: the records ' +
    'define no ranking, so none is applied.');
  attn.appendChild(decisionList(data));
  page.appendChild(attn);

  page.appendChild(actions([
    { label: 'Financial analysis', href: biHref('financial'), action: 'financial' },
    { label: 'Operations analysis', href: biHref('operations'), action: 'operations' },
    { label: 'Risk & data quality', href: biHref('risk'), action: 'risk' },
    { label: 'Ask the AI Analyst', href: askHref('How is my business doing?'), action: 'ask' },
  ]));
}

function financialPage(page, data) {
  const tiles = data.tiles;

  const summary = block('Financial summary');
  summary.appendChild(kpiRow(pickAll(tiles, [
    'Revenue (total', 'Collections (application', 'Expenses (total', 'Cash balance',
  ])));
  page.appendChild(summary);

  // --- revenue ---------------------------------------------------------------------------
  const revenue = block('Revenue');
  const revSeries = pickTile(tiles, 'Revenue by month');
  revenue.appendChild(sub('Monthly trend'));
  revenue.appendChild(trend(revSeries, 'Revenue by month'));
  revenue.appendChild(sub('Recent movement'));
  revenue.appendChild(movements(data.changes, ['Revenue']));
  // The forecast is estate-wide and no apartment forecast exists. Under an apartment filter it
  // is simply not shown -- an owner asking about one apartment is not told which measures
  // declined to answer, and none is projected for the apartment in its place.
  if (data.forecast && !VIEW.filters.apartment) {
    revenue.appendChild(sub('Projected — not recorded'));
    const box = el('article', 'forecast');
    box.setAttribute('data-trust', data.forecast.trust_level || '');
    box.appendChild(el('p', 'forecast-flag',
      'The figures below are a projection of the recorded trend. They are not recorded ' +
      'revenue, and no month in them has happened yet.'));
    (data.forecast.answer || '').split('\n').forEach(function (line) {
      if (line.trim()) box.appendChild(el('p', 'forecast-line', line.trim()));
    });
    revenue.appendChild(box);
  }
  revenue.appendChild(actions([
    { label: 'Compare periods', href: askHref('How did revenue change?'), action: 'compare' },
    { label: 'View trend', href: askHref('How is revenue doing?'), action: 'trend' },
    { label: 'Ask the AI Analyst', href: askHref('Why did revenue change?'), action: 'ask' },
  ]));
  page.appendChild(revenue);

  // --- collections ------------------------------------------------------------------------
  const collections = block('Collections',
    'Two evidence-backed definitions of collections exist. The application-level figure is ' +
    'shown here; the ledger-derived one is listed with the definitions below.');
  collections.appendChild(kpiRow([
    { tile: pickTile(tiles, 'Collections (application'),
      label: 'Collections — as recorded in the application' },
    { tile: pickTile(tiles, 'Collections (ledger'),
      label: 'Collections — as derived from the accounting ledger' },
  ]));
  collections.appendChild(sub('Monthly trend'));
  collections.appendChild(trend(pickTile(tiles, 'Collections by month'),
    'Collections by month'));
  collections.appendChild(sub('Recent movement'));
  collections.appendChild(movements(data.changes, ['Collections']));
  collections.appendChild(actions([
    { label: 'View definitions', href: askHref('How much have we collected?'),
      action: 'definitions' },
    { label: 'Compare periods', href: askHref('How did collections change?'),
      action: 'compare' },
  ]));
  page.appendChild(collections);

  // --- expenses ---------------------------------------------------------------------------
  const expenses = block('Expenses');
  expenses.appendChild(kpiRow(pickAll(tiles, ['Expenses (total'])));
  expenses.appendChild(sub('By category'));
  const byCategory = pickTile(tiles, 'Expenses by category');
  expenses.appendChild(barChart(breakdownOf(byCategory), {
    caption: byCategory && byCategory.caveat ? ownerProse(byCategory.caveat) : '',
  }));
  expenses.appendChild(sub('Recent movement'));
  expenses.appendChild(movements(data.changes, ['P&L']));
  page.appendChild(expenses);

  // --- by apartment -------------------------------------------------------------------------
  //
  // The apartment is on the journal line itself, so this is the same revenue and the same
  // expenses read one level finer. The part of each that carries no apartment is a row in its
  // own right and is never divided across the others.
  const byApartment = block('By apartment',
    VIEW.filters.apartment
      ? 'Read from the apartment recorded on each posting, narrowed to ' +
        VIEW.filters.apartment + '. The estate-wide unattributed amount is not shown here and ' +
        'no part of it belongs to this apartment.'
      : 'Read from the apartment recorded on each posting. The part that carries no apartment ' +
        'is shown as its own row and is not divided among the others.');
  [['Revenue by apartment', 'Revenue'], ['Expenses by apartment', 'Expenses']]
    .forEach(function (pair) {
      const tile = pickTile(tiles, pair[0]);
      if (!tile) return;
      byApartment.appendChild(sub(pair[1]));
      const rows = breakdownOf(tile);
      if (rows.length === 0) {
        byApartment.appendChild(emptyState(ownerProse(
          tile.unavailable_reason || 'No apartment breakdown is recorded for this.')));
        return;
      }
      byApartment.appendChild(barChart(rows, { display: tile.series_display || {} }));
      if (tile.caveat) {
        byApartment.appendChild(el('p', 'bi-block-note', ownerProse(tile.caveat)));
      }
    });

  // One apartment's revenue over time. The measure needs the apartment named, so it is rendered
  // here where the apartment is chosen: with a filter it draws that apartment's months, and
  // without one it states the requirement rather than picking an apartment or widening to the
  // estate. A month with nothing posted is absent from the series, never drawn as a zero.
  const apartmentMonths = pickTile(tiles, 'Revenue by month for one apartment');
  if (apartmentMonths) {
    byApartment.appendChild(sub(VIEW.filters.apartment
      ? 'Revenue by month — ' + VIEW.filters.apartment
      : 'Revenue by month for one apartment'));
    const series = seriesOf(apartmentMonths);
    if (series.length === 0) {
      byApartment.appendChild(emptyState(ownerProse(
        apartmentMonths.unavailable_reason
        || 'Choose an apartment to see its revenue month by month.')));
    } else {
      // The chart draws the whole recorded series -- one apartment's history is short enough to
      // read at once, and trimming it would hide months the records do hold. The series itself
      // never appears as text: a month-by-month dictionary printed into a KPI line is a data
      // dump, not a figure.
      byApartment.appendChild(lineChart(series, {
        label: 'Revenue by month for ' + VIEW.filters.apartment,
        recent: 0,
        displays: apartmentMonths.series_display || {},
        selected: VIEW.filters.period,
        onSelect: function (period) { goWith('period', period); },
      }));
      byApartment.appendChild(selectedMonthValue(apartmentMonths, series));
      if (apartmentMonths.caveat) {
        byApartment.appendChild(el('p', 'bi-block-note',
          ownerProse(apartmentMonths.caveat)));
      }
    }
  }

  byApartment.appendChild(actions([
    { label: 'Operations detail', href: hrefWith(biHref('operations'), VIEW.filters),
      action: 'operations' },
    { label: 'Ask the AI Analyst', action: 'ask',
      href: askHref('Which apartment generated the most revenue?') },
  ]));
  page.appendChild(byApartment);

  // --- profit -----------------------------------------------------------------------------
  const profitTile = pickTile(tiles, 'Gross/net profit');
  const profit = block('Profit',
    'No single profit figure is stated. The definitions in your records disagree, and ' +
    'choosing between them is a business decision rather than an analytical one.');
  const panel = definitionPanel(profitTile);
  if (panel) profit.appendChild(panel);
  profit.appendChild(actions([
    { label: 'View definitions', href: askHref('What is profit?'), action: 'definitions' },
    { label: 'Ask the AI Analyst', href: askHref('Why is there no single profit figure?'),
      action: 'ask' },
  ]));
  page.appendChild(profit);

  // --- reconciliation ---------------------------------------------------------------------
  const recTile = pickTile(data.riskTiles || [], 'Ledger/source reconciliation');
  if (recTile) {
    const rec = block('Source and ledger comparison',
      'Each figure is compared between the system it was entered in and the accounting ' +
      'ledger. Where they differ, the difference is shown rather than reconciled away.');
    const view = ownerView(recTile);
    const list = el('div', 'reconciliation');
    list.setAttribute('data-section', 'reconciliation');
    (view.secondary || []).forEach(function (p) {
      const row = el('div', 'reconciliation-row');
      row.appendChild(el('span', 'reconciliation-label', p.label));
      row.appendChild(el('span', 'reconciliation-value', p.value));
      list.appendChild(row);
    });
    if ((view.secondary || []).length === 0) {
      list.appendChild(emptyState('No comparison is recorded for this.'));
    }
    rec.appendChild(list);
    if (view.caveat) rec.appendChild(el('p', 'bi-block-note', ownerProse(view.caveat)));
    page.appendChild(rec);
  }

  const defs = block('Definitions and caveats');
  ['Tenant dues', 'Owner rent'].forEach(function (name) {
    const p = definitionPanel(pickTile(tiles, name));
    if (p) defs.appendChild(p);
  });
  defs.appendChild(caveats(data.limitations));
  page.appendChild(defs);
}

/*
 * Apartments, and the beds inside one.
 *
 * The only dimension below the estate that this export carries with figures attached is the bed,
 * and the only figure on it is the rent recorded on the allotment occupying it. So this shows
 * beds and their rents -- not an apartment revenue, not an apartment occupancy rate, and not an
 * apartment rent, because several different rents sit inside one apartment and choosing between
 * them would be an aggregation decision rather than a reading of the records.
 *
 * Selecting an apartment sets the SHARED apartment filter, so the drill-down and the rest of the
 * page are always looking at the same thing.
 */
function apartmentSection(data) {
  const breakdown = data.apartment_breakdown || {};
  const wrap = block('Apartments and beds',
    breakdown.basis || 'Beds recorded as currently occupied, with the rent recorded on each.');

  if (!breakdown.available) {
    wrap.appendChild(emptyState(ownerProse(breakdown.unavailable_reason
      || 'No apartment detail is available from the exported records.')));
    if (VIEW.filters.apartment) {
      const back = el('button', 'bi-action', 'Show all apartments');
      back.type = 'button';
      back.addEventListener('click', function () { goWith('apartment', ''); });
      wrap.appendChild(back);
    }
    return wrap;
  }

  const rows = breakdown.apartments || [];
  if (VIEW.filters.apartment && rows.length === 1) {
    // Drilled in: one apartment, its beds and their rents.
    const only = rows[0];
    wrap.appendChild(sub(only.apartment + ' — ' + only.bed_count_display));
    const list = el('dl', 'bed-list');
    list.setAttribute('data-section', 'beds');
    (only.beds || []).forEach(function (bed) {
      list.appendChild(el('dt', 'bed-code', bed.bed));
      list.appendChild(el('dd', 'bed-rent', bed.rent_display || bed.note));
    });
    wrap.appendChild(list);
    if (only.note) wrap.appendChild(el('p', 'bi-block-note', only.note));
    const back = el('button', 'bi-action', 'Show all apartments');
    back.type = 'button';
    back.addEventListener('click', function () { goWith('apartment', ''); });
    wrap.appendChild(back);
    wrap.appendChild(actions([
      { label: 'Ask the AI Analyst', action: 'ask',
        href: askHref('What rent is recorded for apartment ' + only.apartment + '?') },
    ]));
    return wrap;
  }

  const table = el('div', 'apartment-table');
  table.setAttribute('data-section', 'apartments');
  rows.forEach(function (row) {
    const item = el('div', 'apartment-row');
    if (!row.comparable) item.setAttribute('data-sparse', 'true');
    const open = el('button', 'apartment-code', row.apartment);
    open.type = 'button';
    open.addEventListener('click', function () { goWith('apartment', row.apartment); });
    item.appendChild(open);
    item.appendChild(el('span', 'apartment-beds', row.bed_count_display));
    item.appendChild(el('span', 'apartment-rents', row.rent_range_display));
    const view = el('button', 'apartment-drill', 'View beds');
    view.type = 'button';
    view.addEventListener('click', function () { goWith('apartment', row.apartment); });
    item.appendChild(view);
    if (row.note) item.appendChild(el('p', 'apartment-note', row.note));
    table.appendChild(item);
  });
  wrap.appendChild(table);
  return wrap;
}

function operationsPage(page, data) {
  const tiles = data.tiles;

  const occTile = pickTile(tiles, 'Current occupancy');
  const occupancy = block('Occupancy',
    'More than one supported definition exists, and they differ over who counts as resident ' +
    'and which beds count as available. Every one is shown.');
  const panel = definitionPanel(occTile);
  if (panel) occupancy.appendChild(panel);
  occupancy.appendChild(actions([
    { label: 'View definitions', href: askHref('What is current occupancy?'),
      action: 'definitions' },
    { label: 'Ask the AI Analyst', href: askHref('Which occupancy definition should I use?'),
      action: 'ask' },
  ]));
  page.appendChild(occupancy);

  const tenants = block('Tenants');
  tenants.appendChild(kpiRow(pickAll(tiles, [
    'Staying tenants', 'On-Notice tenants', 'Booked beds', 'Move-ins', 'Move-outs',
  ])));
  page.appendChild(tenants);

  const rentTile = pickTile(data.financialTiles || [], 'Current rent per bed');
  if (rentTile) {
    const rent = block('Rent',
      'Rent is recorded per bed. The beds inside one apartment routinely carry different ' +
      'rents, so there is no single apartment rent to state.');
    const view = ownerView(rentTile);
    const rows = breakdownOf(rentTile);
    rent.appendChild(sub('Current rent by bed'));
    rent.appendChild(barChart(rows.slice(0, 12), {
      // The engine's own strings, so a rent reads identically here and in the bed list below.
      display: rentTile.series_display || {},
      caption: rows.length > 12
        ? 'Showing 12 of ' + rows.length + ' currently occupied beds.'
        : rows.length + ' currently occupied beds.',
    }));
    if (view.caveat) rent.appendChild(el('p', 'bi-block-note', ownerProse(view.caveat)));
    rent.appendChild(actions([
      { label: 'Ask the AI Analyst', href: askHref('What is our typical rent?'),
        action: 'ask' },
    ]));
    page.appendChild(rent);
  }

  // Occupancy month by month, on both readings the records support. Neither is chosen: the
  // tile keeps its posture and both series are drawn under their own names.
  const history = pickTile(tiles, 'Historical occupancy');
  if (history) {
    const occHistory = block('Occupancy over time',
      'Two supported readings of what "occupied in a month" means. Both are shown; the ' +
      'records do not settle which one the business uses.');
    const view = ownerView(history);
    const raw = history.definitions || [];
    if (raw.length === 0) {
      occHistory.appendChild(emptyState(ownerProse(
        history.unavailable_reason || 'No occupancy history is available.')));
    } else {
      raw.forEach(function (definition, index) {
        const label = (view.definitions[index] || {}).label || definition.label;
        occHistory.appendChild(sub(label));
        occHistory.appendChild(lineChart(monthPairs(definition.value), {
          label: label, unit: 'count',
          recent: (VIEW.filters.range || '') === 'full' ? 0 : 24,
          selected: VIEW.filters.period,
          onSelect: function (period) { goWith('period', period); },
        }));
      });
      occHistory.appendChild(rangeControl(Object.keys(raw[0].value || {}).length,
        (VIEW.filters.range || '') === 'full'));
    }
    if (history.caveat) {
      occHistory.appendChild(el('p', 'bi-block-note', ownerProse(history.caveat)));
    }
    occHistory.appendChild(actions([
      { label: 'Ask the AI Analyst', action: 'ask',
        href: askHref('How did occupancy change over the last 6 months?') },
    ]));
    page.appendChild(occHistory);
  }

  page.appendChild(apartmentSection(data));

  const maintenance = block('Maintenance');
  maintenance.appendChild(kpiRow(pickAll(tiles, ['Maintenance volume', 'Maintenance cost'])));
  maintenance.appendChild(movements(data.changes, ['Maintenance']));
  page.appendChild(maintenance);

  const electricity = block('Electricity');
  electricity.appendChild(kpiRow(pickAll(tiles, ['EB/electricity', 'EB tenant allocation'])));
  page.appendChild(electricity);

  const defs = block('Definitions and caveats');
  defs.appendChild(caveats(data.limitations));
  page.appendChild(defs);
}

function riskPage(page, data) {
  const tiles = data.tiles;

  const financial = block('Financial recording issues',
    'What the money records say twice, or say differently in two places.');
  financial.appendChild(sub('How much is affected'));
  financial.appendChild(kpiRow(pickAll(tiles, [
    'Duplicate receipts', 'Phantom deposits',
  ])));
  const recTile = pickTile(tiles, 'Ledger/source reconciliation');
  if (recTile) {
    financial.appendChild(sub('Source system compared with the accounting ledger'));
    const view = ownerView(recTile);
    const list = el('div', 'reconciliation');
    list.setAttribute('data-section', 'reconciliation');
    (view.secondary || []).forEach(function (p) {
      const row = el('div', 'reconciliation-row');
      row.appendChild(el('span', 'reconciliation-label', p.label));
      row.appendChild(el('span', 'reconciliation-value', p.value));
      list.appendChild(row);
    });
    financial.appendChild(list);
    if (view.caveat) financial.appendChild(el('p', 'bi-block-note', ownerProse(view.caveat)));
  }
  page.appendChild(financial);

  const operational = block('Operational recording issues',
    'The same, in the records of who is staying where.');
  operational.appendChild(sub('How much is affected'));
  operational.appendChild(kpiRow(pickAll(tiles, ['Overlapping allotments'])));
  page.appendChild(operational);

  // Kept out of the two blocks above on purpose. Those hold differences the evidence proves;
  // this one holds a pattern the evidence only shows, and grouping them would lend it a
  // certainty the records do not support.
  const observed = block('Repeated invoice groups — review needed',
    'The records contain multiple invoices for some allotment-month combinations. The ' +
    'exported evidence does not establish whether these represent duplicate billing or ' +
    'legitimate proration/room changes.');
  observed.appendChild(sub('How much is affected'));
  observed.appendChild(kpiRow(pickAll(tiles, ['Duplicate invoices'])));
  observed.appendChild(actions([
    { label: 'View affected records', href: '#/data-quality', action: 'records' },
    { label: 'Ask the AI Analyst',
      href: askHref('Why are there multiple invoices for the same allotment month?'),
      action: 'ask' },
  ]));
  page.appendChild(observed);

  const issues = block('What each issue is, and what to review',
    'Each states what is happening, how much it covers, why it matters, and what to review.');
  issues.appendChild(issueList(data.insights, ['DQ', 'RISK']));
  issues.appendChild(actions([
    { label: 'View affected records', href: '#/data-quality', action: 'records' },
    { label: 'Ask the AI Analyst', href: askHref('What are my biggest risks?'), action: 'ask' },
    { label: 'Return to Executive', href: biHref('executive'), action: 'executive' },
  ]));
  page.appendChild(issues);

  const defs = block('Definitions and caveats');
  ['Outstanding dues'].forEach(function (name) {
    const p = definitionPanel(pickTile(tiles, name));
    if (p) defs.appendChild(p);
  });
  defs.appendChild(caveats(data.limitations));
  page.appendChild(defs);
}

/*
 * Exceptions -- things worth a look, sorted by what the evidence actually establishes.
 *
 * This is not an anomaly detector and does not claim to be one. Calling a movement anomalous
 * needs a threshold that says what normal is, and no such threshold exists in these records;
 * the earlier investigation established that and it has not changed. So the two headings here
 * are about the STATUS OF THE EVIDENCE, not about severity: one holds findings the records
 * establish, the other holds patterns the records show without explaining. A reader must never
 * have to guess which kind they are looking at.
 */
function exceptionsSection(data) {
  const insights = data.insights || [];
  const established = insights.filter(function (i) {
    return i.evidence_status !== 'observed' && familyOf(i) !== 'CHANGE';
  });
  const observed = insights.filter(function (i) { return i.evidence_status === 'observed'; });
  const movements = insights.filter(function (i) { return familyOf(i) === 'CHANGE'; });

  const wrap = block('Exceptions worth a look',
    'Sorted by what the records establish, not by severity. No threshold for "unusual" exists ' +
    'in your records, so nothing here is called an anomaly.');

  if (movements.length) {
    wrap.appendChild(sub('Movements large enough to state'));
    wrap.appendChild(issueList(movements, ['CHANGE']));
  }
  if (established.length) {
    wrap.appendChild(sub('Established by the records'));
    const list = el('div', 'issue-list');
    established.forEach(function (i) { list.appendChild(issueCard(i)); });
    wrap.appendChild(list);
  }
  if (observed.length) {
    wrap.appendChild(sub('Observed, but not established'));
    wrap.appendChild(el('p', 'bi-block-note',
      'The records show these patterns. They do not say what causes them, so nothing below is ' +
      'stated as a confirmed problem.'));
    const list = el('div', 'issue-list');
    observed.forEach(function (i) { list.appendChild(issueCard(i)); });
    wrap.appendChild(list);
  }
  if (!movements.length && !established.length && !observed.length) {
    wrap.appendChild(emptyState('Nothing stands out in the current records.'));
  }
  return wrap;
}

/*
 * The decision queue as a worklist. The status is the owner's note about what they are doing;
 * it is stored beside the finding and never inside it. Recording "management selected a
 * definition" does not select one in the engine -- every definition stays visible and the
 * measure keeps the posture its evidence carries, because the disagreement in the records is a
 * fact and the choice is a policy sitting next to it.
 */
function decisionList(data) {
  const wrap = el('div', 'decision-queue');
  wrap.setAttribute('data-section', 'decision-queue');
  const items = data.decisions || [];
  if (items.length === 0) return attention(data.decision_queue);

  // Said once, above the list: a status records what management is doing about a disagreement,
  // and changes nothing about the records it concerns.
  wrap.appendChild(el('p', 'decision-scope-note',
    'Marking an item records your review of it. It does not change any figure, remove any ' +
    'competing definition, or alter what the records say — every definition stays visible and ' +
    'each measure keeps the posture its own evidence carries.'));

  items.forEach(function (item) {
    const card = el('article', 'decision');
    card.setAttribute('data-trust', item.trust || '');
    card.setAttribute('data-status', item.status || 'open');
    const head = el('div', 'decision-head');
    if (item.title) head.appendChild(el('h4', 'decision-title', item.title));
    head.appendChild(el('span', 'decision-status', item.status_label || 'Open'));
    card.appendChild(head);
    if (item.posture) card.appendChild(el('p', 'decision-posture', item.posture));
    if (item.decision) card.appendChild(el('p', 'decision-text', item.decision));
    if (item.note) card.appendChild(el('p', 'decision-note', item.note));

    const controls = el('div', 'decision-controls');
    (data.decision_statuses || []).forEach(function (status) {
      const button = el('button', 'decision-set', status.label);
      button.type = 'button';
      if (status.key === (item.status || 'open')) button.classList.add('active');
      button.addEventListener('click', function () {
        recordDecision(item.item_key, status.key);
      });
      controls.appendChild(button);
    });
    const ask = el('a', 'decision-set', 'Ask the AI Analyst');
    ask.href = askHref('Explain the ' + String(item.title || 'issue').split('—')[0].trim()
      + ' decision I need to make');
    controls.appendChild(ask);
    card.appendChild(controls);
    wrap.appendChild(card);
  });
  return wrap;
}

async function recordDecision(itemKey, status) {
  try {
    await api.recordDecision(itemKey, status);
  } catch (_) { /* the page below is unchanged; the status simply did not save */ }
  VIEW.rerender();
}

function insightsPage(page, data) {
  // Narrowed to an apartment, this page leads with what the records actually hold for it. The
  // section carries no metric domain of its own, so without this an apartment whose series
  // cannot support the requested comparison would show nothing at all.
  if (VIEW.filters.apartment && (data.tiles || []).length) {
    const held = block('What the records hold for ' + VIEW.filters.apartment);
    held.appendChild(kpiRow(data.tiles));
    page.appendChild(held);
  }

  const changed = block('What changed',
    'Supported period comparisons only, between complete months.');
  changed.appendChild(movements(data.changes));
  page.appendChild(changed);

  // Estate-wide, exactly as on the Financial page: omitted under an apartment filter.
  if (data.forecast && !VIEW.filters.apartment) {
    const fc = block('What is projected',
      'A projection of the recorded trend. Nothing below has happened yet, and none of it is ' +
      'a recorded figure.');
    const box = el('article', 'forecast');
    box.setAttribute('data-trust', data.forecast.trust_level || '');
    (data.forecast.answer || '').split('\n').forEach(function (line) {
      if (line.trim()) box.appendChild(el('p', 'forecast-line', line.trim()));
    });
    fc.appendChild(box);
    page.appendChild(fc);
  }

  // The findings appear once, under the exceptions heading. They used to appear twice -- a
  // "What stands out" list of conflicts and movements, and then the same cards again grouped by
  // what the evidence establishes -- which made the page longer without making it say more.
  page.appendChild(exceptionsSection(data));

  const look = block('What management should look at',
    'Grouped by business subject. No priority score exists in the records, so none is applied.');
  look.appendChild(decisionList(data));
  page.appendChild(look);

  page.appendChild(actions([
    { label: 'Return to Executive', href: biHref('executive'), action: 'executive' },
    { label: 'Ask the AI Analyst', href: askHref('What should I focus on today?'),
      action: 'ask' },
  ]));

  const defs = block('Caveats');
  defs.appendChild(caveats(data.limitations));
  page.appendChild(defs);
}

/* --- loading --------------------------------------------------------------------------------- */

async function loadPage(key, filters) {
  const home = await api.ownerHome();
  const base = {
    as_of: home.as_of,
    trust_summary: home.trust_summary,
    decision_queue: home.decision_queue,
    changes: home.changes,
    insights: home.insights,
    limitations: home.limitations,
    filters: filters,
  };

  // The executive view reads the same measures the whole business is read by, and the section
  // endpoint is where a narrowed request is answered. Asking it for the financial section gives
  // this page a filtered payload from the same engine path the other four use, rather than a
  // second, unfiltered one.
  const sectionKey = key === 'executive' ? 'financial' : key;
  const payload = await api.analyticsSection(sectionKey, filters);

  if (key === 'executive') {
    return Object.assign({}, base, {
      title: 'Executive Analyst',
      filter_options: payload.filter_options,
      applied_filters: payload.applied_filters,
      tiles: anyFilter(filters)
        ? [].concat(payload.tiles || [], (await api.analyticsSection('operations', filters)).tiles || [])
        : [].concat(home.business_health || [], home.operations || [], home.risks || []),
      // Same rule as every other page: under a narrowing filter the section's answer is
      // authoritative even when empty, so the estate-wide movements are not shown beneath an
      // apartment heading.
      changes: anyFilter(filters)
        ? (payload.changes || [])
        : (payload.changes && payload.changes.length ? payload.changes : home.changes),
      decision_queue: anyFilter(filters) ? [] : home.decision_queue,
    });
  }

  const data = Object.assign({}, base, {
    title: payload.title || 'Analyst',
    available: payload.available,
    reason: payload.reason,
    tiles: payload.tiles || [],
    limitations: payload.limitations || home.limitations,
    filter_options: payload.filter_options,
    applied_filters: payload.applied_filters,
  });
  // Under a narrowing filter the section's own answer is authoritative even when it is EMPTY:
  // falling back to the dashboard's estate-wide movements and findings would put wider figures
  // on a page the owner narrowed. Without a filter the fallback is still right, because an
  // empty section list there just means this section carries none of them.
  const scoped = anyFilter(filters);
  if (scoped || (payload.changes && payload.changes.length)) {
    data.changes = payload.changes || [];
  }
  if (scoped || (payload.insights && payload.insights.length)) {
    data.insights = payload.insights || [];
  }
  if (payload.decision_queue) data.decision_queue = payload.decision_queue;
  if (scoped) data.decision_queue = payload.decision_queue || [];
  if (payload.apartment_breakdown) data.apartment_breakdown = payload.apartment_breakdown;

  // A page that reads a measure belonging to another section asks that section for it rather
  // than re-deriving it here. The reconciliation figure is a risk measure the financial page
  // reports on; rent is a financial measure the operations page reports on. Both carry the same
  // filter, so a narrowed page is narrowed throughout.
  if (key === 'financial') {
    const risk = await api.analyticsSection('risk', filters);
    data.riskTiles = risk.tiles || [];
  }
  if (key === 'operations') {
    const financial = await api.analyticsSection('financial', filters);
    data.financialTiles = financial.tiles || [];
  }
  return data;
}

/* The owner's recorded decisions, attached to the queue they are about. Optional: a page is
 * complete without them, and a store that will not answer must not take the page down. */
async function loadDecisions(data, filters) {
  // The queue is drawn from estate-wide findings and carries no apartment attribution. Under an
  // apartment filter it is not fetched at all, so it cannot be rendered beneath an apartment
  // heading as though those decisions were about that apartment.
  if (filters && filters.apartment) {
    data.decisions = [];
    data.decision_statuses = [];
    return data;
  }
  try {
    const log = await api.decisions();
    data.decisions = log.items || [];
    data.decision_statuses = log.statuses || [];
  } catch (_) {
    data.decisions = [];
    data.decision_statuses = [];
  }
  return data;
}

/*
 * The revenue forecast, from the engine's own validated model. It is fetched through the same
 * question pipeline every other surface uses, so the figures, the interval and the tested error
 * are the ones the forecaster produced -- this page neither projects nor re-labels anything.
 */
async function loadForecast() {
  try {
    const result = await api.ask('Forecast revenue for the next 3 months');
    if (!result || !result.answer) return null;
    if ((result.trust_level || '') === 'NOT_DETERMINABLE') return null;
    return result;
  } catch (_) {
    return null;                       // the page is complete without it
  }
}

/*
 * Export of what is on screen.
 *
 * The rows come from the server, built from the same authorized payload the page renders --
 * after the role filter and after the gate. So a measure with no permitted headline exports its
 * posture and its competing definitions and no number, exactly as it appears here. This function
 * turns those finished rows into a file; it reads no figure and computes none.
 */
function exportControl(key, filters) {
  const nav = el('nav', 'export-control');
  nav.setAttribute('aria-label', 'Export');
  const button = el('button', 'bi-action', 'Export this view (CSV)');
  button.type = 'button';
  const status = el('span', 'export-status');

  button.addEventListener('click', async function () {
    status.textContent = 'Preparing…';
    let payload;
    try {
      payload = await api.analyticsExport(key, filters);
    } catch (err) {
      status.textContent = 'The export could not be prepared.';
      return;
    }
    if (!payload.available) {
      status.textContent = payload.reason || 'Nothing to export for this view.';
      return;
    }
    const quote = function (value) {
      return '"' + String(value === undefined || value === null ? '' : value)
        .replace(/"/g, '""') + '"';
    };
    const lines = [['Section', 'Item', 'Value', 'Trust', 'Note'].map(quote).join(',')];
    (payload.rows || []).forEach(function (row) {
      lines.push([row.section, row.item, row.value, row.trust, row.note].map(quote).join(','));
    });
    const blob = new Blob(['﻿' + lines.join('\r\n')],
      { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = key + '-analysis.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    status.textContent = (payload.rows || []).length + ' rows exported, as shown on this page.';
  });

  nav.appendChild(button);
  nav.appendChild(status);
  return nav;
}

/*
 * What an apartment-scoped page shows: what it can answer, and nothing about what it cannot.
 *
 * The server already omits every measure that produced no answer for the selected apartment, so
 * a block built around one of those measures comes out holding only its heading and, at most, an
 * empty state. Left on the page those read as a list of apologies -- the owner asked about one
 * apartment and got a screen explaining which measures declined. So a block with no figure in it
 * is removed entirely while a filter is active.
 *
 * It runs ONLY under a filter: the unfiltered dashboard is untouched, empty states there still
 * mean something (a section with genuinely nothing in it is itself a finding). And it removes
 * only presentation -- no figure, posture or caveat on a surviving block is altered, and an
 * omitted measure is never replaced by a wider one.
 */
const ANSWER_BEARING = [
  '.kpi', '.bar-row', '.chart-svg', '.definition', '.movement', '.issue', '.decision',
  '.reconciliation-row', '.bed-list', '.apartment-row', '.selected-month-value',
  '.forecast-line', '.caveat', '.trust-strip-item',
].join(', ');

function pruneUnscopedSections(page, filters) {
  if (!filters || !filters.apartment) return;

  // A placeholder saying there is nothing here is the same apology in shorter words, so the
  // placeholders go first.
  page.querySelectorAll('.empty-state, .chart-empty').forEach(function (node) {
    node.remove();
  });
  // A sub-heading whose content has just been removed is a label over nothing.
  page.querySelectorAll('.bi-sub-title').forEach(function (heading) {
    let next = heading.nextElementSibling;
    while (next && next.classList.contains('bi-block-note')) next = next.nextElementSibling;
    if (!next || next.classList.contains('bi-sub-title')
        || !next.querySelector(ANSWER_BEARING)) {
      heading.remove();
    }
  });
  page.querySelectorAll('.bi-block').forEach(function (blockNode) {
    if (!blockNode.querySelector(ANSWER_BEARING)) blockNode.remove();
  });
}

function pageNav(activeKey, filters) {
  const nav = el('nav', 'analytics-nav');
  nav.setAttribute('aria-label', 'Analyst views');
  BI_PAGES.forEach(function (p) {
    const a = el('a', 'analytics-tab');
    // The selection is part of the route, so moving between views keeps the question the
    // analyst is asking instead of silently widening it back to the whole estate.
    a.href = hrefWith(biHref(p.key), filters);
    a.setAttribute('data-bi-page', p.key);
    a.appendChild(el('span', 'analytics-tab-title', p.title));
    if (p.key === activeKey) {
      a.classList.add('active');
      a.setAttribute('aria-current', 'page');
    }
    nav.appendChild(a);
  });
  return nav;
}

function trustStrip(trustSummary) {
  const keys = Object.keys(trustSummary || {});
  if (keys.length === 0) return null;
  const strip = el('div', 'trust-strip');
  strip.setAttribute('data-section', 'trust-strip');
  keys.forEach(function (level) {
    const t = trustSummary[level];
    const chip = el('div', 'trust-strip-item');
    chip.setAttribute('data-trust', level);
    chip.appendChild(badge(t));
    chip.appendChild(el('span', 'trust-strip-count', String(t.count) + ' measures'));
    chip.appendChild(el('span', 'trust-strip-explain', t.owner_explanation || ''));
    strip.appendChild(chip);
  });
  return strip;
}

const PAGE_BUILDERS = {
  executive: executivePage,
  financial: financialPage,
  operations: operationsPage,
  risk: riskPage,
  insights: insightsPage,
};

const PAGE_PURPOSE = {
  executive: 'The whole business at a glance: what the figures are, how they moved, and what ' +
    'is waiting on a decision.',
  financial: 'Revenue, collections, expenses and profit, with the trends and the definitions ' +
    'behind each.',
  operations: 'Occupancy, tenants, rent, maintenance and electricity, as the records hold them.',
  risk: 'Where the records disagree with themselves, and what to review before relying on the ' +
    'figures they affect.',
  insights: 'What changed, what is projected, what stands out, and what management should ' +
    'look at.',
};

export async function renderPowerBi(root, pageKey, ctx) {
  const key = PAGE_BUILDERS[pageKey] ? pageKey : 'executive';
  root.replaceChildren(loading('the analyst workspace'));
  const filters = readFilters();

  // Every render takes a ticket. A render whose ticket is no longer the current one has been
  // overtaken -- the analyst has moved on, or changed a filter -- and it must not write to the
  // page. Without this, a slow request finishing after a faster one replaced the whole view
  // with the OLDER page's content, so the heading said one thing and the figures another.
  //
  // Errors are not swallowed by this: a stale render stays silent because nothing is waiting
  // for it, while the render that IS current still reports its own failure.
  RENDER_TICKET += 1;
  const ticket = RENDER_TICKET;
  const current = function () { return ticket === RENDER_TICKET; };

  VIEW = {
    key: key, filters: filters, asOf: '',
    rerender: function () { renderPowerBi(root, key, ctx); },
  };

  let data;
  try {
    data = await loadPage(key, filters);
  } catch (err) {
    if (current()) root.replaceChildren(errorState(err));
    return;
  }
  if (!current()) return;
  VIEW.asOf = data.as_of || '';
  await loadDecisions(data, filters);
  if (!current()) return;
  if (key === 'financial' || key === 'insights') {
    data.forecast = await loadForecast();
    if (!current()) return;
  }

  const page = el('div', 'analytics-page bi-page bi-analyst');
  page.setAttribute('data-bi-workspace', 'true');
  page.setAttribute('data-bi-page', key);

  const head = el('header', 'analytics-head');
  head.appendChild(el('p', 'analytics-eyebrow', 'Power BI Analyst'));
  head.appendChild(el('h1', 'dashboard-title', data.title));
  head.appendChild(el('p', 'analytics-purpose', PAGE_PURPOSE[key] || ''));
  if (data.as_of) head.appendChild(el('p', 'dashboard-asof', 'As at ' + data.as_of));
  page.appendChild(head);
  page.appendChild(pageNav(key, filters));

  // One bar, the same on all five pages, and the selection travels with the route -- so moving
  // between Executive and Operations keeps the analyst's question rather than resetting it.
  page.appendChild(filterBar(data.filter_options, filters, function (next) {
    location.hash = hrefWith(biHref(key), next);
    renderPowerBi(root, key, ctx);
  }));
  page.appendChild(exportControl(key, filters));

  if (data.available === false) {
    page.appendChild(errorState({ message: data.reason || 'This view is not available.' }));
    if (current()) root.replaceChildren(page);
    return;
  }

  // The legend is reference material, not a finding. It stays one click away rather than
  // occupying the top of all five pages with the same five paragraphs.
  const strip = trustStrip(data.trust_summary);
  if (strip) {
    const reliance = document.createElement('details');
    reliance.className = 'bi-block trust-legend';
    const summary = document.createElement('summary');
    summary.className = 'bi-block-title';
    summary.textContent = 'Which of these can I rely on?';
    reliance.appendChild(summary);
    reliance.appendChild(strip);
    page.appendChild(reliance);
  }

  PAGE_BUILDERS[key](page, data, ctx);
  pruneUnscopedSections(page, filters);

  const foot = el('footer', 'bi-foot');
  foot.appendChild(el('p', 'bi-foot-note',
    'Every figure and every posture on this page comes from the analytics engine. This ' +
    'workspace selects and draws them; it calculates nothing of its own.'));
  const back = el('nav', 'bi-cross-nav');
  const home = el('a', 'bi-link', 'Owner Home');
  home.href = '#/';
  const ask = el('a', 'bi-link', 'Ask the AI Business Analyst');
  ask.href = '#/ask';
  back.appendChild(home);
  back.appendChild(ask);
  foot.appendChild(back);
  page.appendChild(foot);

  if (current()) root.replaceChildren(page);
}
