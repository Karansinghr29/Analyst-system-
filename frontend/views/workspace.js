/*
 * views/workspace.js -- Phase 10 Step 4. Role workspaces and the executive report.
 *
 * Nine workspaces, one engine. What changes between them is which metrics are foregrounded and
 * how much machine vocabulary is surfaced. What does NOT change: the metric definitions, the
 * trust verdicts, the validation status, or whether a headline is permitted.
 *
 * A conflicted measure is conflicted in all nine. The anti-drift validator asserts it by
 * comparing every workspace's rendered tiles against the gate.
 */

import { api } from '../api.js';
import { el, metricTile, section, loading, errorState } from '../render.js';
import { badge } from '../trust.js';
import {
  ownerText, ownerProse, ownerTitle, ownerDecision, ownerView, ownerDefinitionLabels,
} from '../owner_view.js';
import { lineChart } from '../charts.js';

export async function renderRoles(root, ctx) {
  root.replaceChildren(loading('the analyst workspaces'));

  let payload;
  try {
    payload = await api.roles();
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'roles');
  page.appendChild(el('h1', 'dashboard-title', 'Analyst workspaces'));
  page.appendChild(el('p', 'dashboard-asof',
    'Nine lenses over one semantic layer. The lens changes what is foregrounded, never what a ' +
    'measure means or how it is gated.'));

  const grid = el('div', 'role-grid');
  payload.roles.forEach(function (r) {
    const card = el('article', 'role-card');
    card.setAttribute('data-role-id', r.role_id);
    card.setAttribute('tabindex', '0');
    card.appendChild(el('h2', 'role-name', r.display_name));
    card.appendChild(el('p', 'role-focus', r.focus));
    card.appendChild(el('p', 'role-count', r.visible_metric_count + ' measures visible'));
    card.appendChild(el('p', 'role-never', 'Never: ' + r.never_does));
    const open = function () { ctx.openWorkspace(r.analyst_role); };
    card.addEventListener('click', open);
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
    grid.appendChild(card);
  });
  page.appendChild(grid);

  const note = el('section', 'roles-note');
  note.appendChild(el('p', null, payload.roles.length
    ? payload.roles[0].trust_note
    : ''));
  page.appendChild(note);

  root.replaceChildren(page);
}

export async function renderWorkspace(root, roleId, ctx) {
  root.replaceChildren(loading('the workspace'));

  let ws;
  try {
    ws = await api.workspace(roleId);
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'workspace');
  page.setAttribute('data-role-id', roleId);

  const head = el('header', 'workspace-head');
  head.appendChild(el('h1', 'dashboard-title', ws.display_name));
  head.appendChild(el('p', 'dashboard-asof', ws.focus));
  page.appendChild(head);

  // The lens's own boundary, written for the people who maintain it -- it names the gate's
  // postures by their internal names. It is kept verbatim, because it is the policy this lens
  // is held to; it is folded away because an owner opening the page should meet the business,
  // not the machine's vocabulary for it.
  const boundary = el('details', 'workspace-boundary');
  boundary.appendChild(el('summary', 'workspace-boundary-summary', 'What this lens never does'));
  boundary.appendChild(el('p', null, ws.never_does));
  page.appendChild(boundary);

  // The engine's own sentence, when the records could not narrow this lens to measures of
  // its own. Rendered as given; the page adds no judgement of its own.
  if (ws.scope_note) page.appendChild(el('p', 'workspace-note', ws.scope_note));
  buildWorkspaceBody(page, ws, ctx);

  const caps = el('section', 'workspace-caps');
  caps.appendChild(el('h2', 'section-title', 'Capabilities'));
  const ul = el('ul', null);
  (ws.capabilities || []).forEach(function (c) {
    ul.appendChild(el('li', null, c.replace(/_/g, ' ')));
  });
  caps.appendChild(ul);
  page.appendChild(caps);

  root.replaceChildren(page);
}

/* --- the workspace, read in the order an executive reads a business -----------------------------
 *
 * Fifty-six measures in one flat grid is a list, not a briefing: the cash balance and a
 * diagnostic re-run ordering sat at the same size, in registry order, and the reader had to do
 * the sorting. So the same tiles are arranged -- headline measures, then what moved, then what
 * is waiting on a decision, then everything else.
 *
 * WHAT IS ON THE PAGE is decided by the engine, not here. The workspace payload carries only the
 * measures this lens is about -- scoped from links the registry records -- and this page arranges
 * every one of them, carrying the posture, the caveat and the definitions the gate gave it; a
 * conflicted measure is still conflicted, a blocked one still blocked. What leads is selected by
 * id from the engine's `foreground`, and a measure the page does not place explicitly still
 * appears -- it falls through to supporting analysis rather than disappearing.
 */

// What a workspace leads with is the engine's decision, carried as `foreground`. This page
// holds no list of its own: a hardcoded set of "headline" titles was a second, client-side
// answer to which measures matter, and it was a financial answer applied to every lens.

// Occupancy is not four headline numbers. It is one question the records answer several ways,
// so it is shown as one measure carrying its competing readings.
const OCCUPANCY_TITLE = 'Current occupancy';

// Measures that answer only once a period or an apartment is named. They are implemented and
// available -- calling them unavailable would be false -- so they are offered as capabilities
// with the engine's own sentence about what they need.
const CAPABILITY_TITLES = [
  'Rent recorded for a past month',
  'Revenue by month for one apartment',
  'Expenses by month for one apartment',
];

function titleOf(tile) {
  return String((tile && tile.title) || '');
}

function matches(tile, prefix) {
  const title = titleOf(tile).toLowerCase();
  const wanted = String(prefix).toLowerCase();
  return title === wanted || title.indexOf(wanted) === 0;
}

function takeByTitles(pool, prefixes) {
  const taken = [];
  prefixes.forEach(function (prefix) {
    const index = pool.findIndex(function (t) { return matches(t, prefix); });
    if (index !== -1) taken.push(pool.splice(index, 1)[0]);
  });
  return taken;
}

/* The measures the engine says this lens leads with, in the order it gave them.
 *
 * By id, not by title: the engine chose them, and matching its choice by name would be this page
 * guessing at it again. A id the payload does not carry a tile for is simply skipped -- it cannot
 * add a measure the role was not authorized to see, because it only ever removes from `pool`. */
function takeLeading(pool, ids) {
  const taken = [];
  (ids || []).forEach(function (id) {
    const index = pool.findIndex(function (t) { return t && t.metric_id === id; });
    if (index !== -1) taken.push(pool.splice(index, 1)[0]);
  });
  return taken;
}

/* A month-keyed series carried on a value. Same shape the Power BI pages read; the points are
 * the engine's, and nothing here does arithmetic on them. */
function seriesOf(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const keys = Object.keys(value).filter(function (k) { return /^\d{4}-\d{2}/.test(k); });
  if (keys.length === 0) return [];
  return keys.sort().map(function (k) { return [k, value[k]]; });
}

/*
 * Every recorded series a measure carries, with the name each one goes by.
 *
 * A measure with one agreed definition carries its series on the tile. A measure whose evidence
 * carries competing definitions carries one series PER DEFINITION -- historical occupancy holds
 * two, eighty-two months each -- and both are returned, labelled. Choosing between them, or
 * drawing only the first, would be the client deciding a definitional question the gate
 * deliberately left open.
 */
function seriesSetOf(tile) {
  const own = seriesOf(tile && tile.value);
  if (own.length > 0) return [{ label: '', points: own }];

  const definitions = (tile && tile.definitions) || [];
  const labels = ownerDefinitionLabels(definitions);
  const out = [];
  definitions.forEach(function (definition, index) {
    const points = seriesOf(definition.value);
    if (points.length > 0) out.push({ label: labels[index], points: points });
  });
  return out;
}

/*
 * What a measure is waiting to be asked, said as a prompt.
 *
 * Two things are handled here, both of them presentation:
 *
 * The engine closes such a reason with its mandated refusal sentence, because the gate's posture
 * on an unasked measure is genuinely "nothing can be stated yet". On a capability card that
 * sentence contradicts the card: the measure IS implemented, and it answers as soon as a month
 * or an apartment is named. The card's own framing says what the sentence was there to say, so
 * the sentence is dropped -- and only when what remains still explains what is needed. The
 * posture itself is untouched, and the full reason stays on the payload and on the metric page.
 *
 * `ownerProse` is deliberately not used: it drops "see ..." clauses, which is right for a
 * specification reference and wrong for "Name the apartment to see its history".
 */
function capabilityPrompt(tile) {
  const raw = String((tile && tile.unavailable_reason) || '');
  const refusal = 'Not determinable from exported evidence.';
  const trimmed = raw.trim();
  const asked = trimmed.slice(-refusal.length) === refusal
    ? trimmed.slice(0, -refusal.length).trim()
    : trimmed;
  return ownerText(asked || trimmed);
}

function buildWorkspaceBody(page, ws, ctx) {
  // A working copy: every tile leaves this pool into exactly one section, so nothing is
  // rendered twice and nothing is silently dropped.
  const pool = (ws.tiles || []).slice();

  // What this lens leads with, decided by the engine. Nothing is chosen here: a lens the engine
  // could not narrow sends no `foreground`, and then nothing leads.
  const leads = ws.foreground || [];
  // Occupancy is one question the records answer several ways, and the panel below says so. It
  // is used only when the engine leads with occupancy -- the page does not promote a measure the
  // engine did not.
  const occupancy = [];
  const occIndex = pool.findIndex(function (t) { return matches(t, OCCUPANCY_TITLE); });
  if (occIndex !== -1 && leads.indexOf(pool[occIndex].metric_id) !== -1) {
    occupancy.push(pool.splice(occIndex, 1)[0]);
  }
  const headline = takeLeading(pool, leads);
  const capabilities = takeByTitles(pool, CAPABILITY_TITLES);
  // Whatever is left that carries a month series belongs in a chart, not in a tile: rendered as
  // a tile, eighty months arrive as an eighty-part "2019-11: ... ; 2019-12: ..." run-on.
  const trends = [];
  for (let i = pool.length - 1; i >= 0; i -= 1) {
    if (seriesSetOf(pool[i]).length > 0) trends.unshift(pool.splice(i, 1)[0]);
  }

  if (headline.length || occupancy.length) {
    // Not "Executive KPIs": what leads is now this lens's own, and an Operations workspace
    // leading with occupancy is not reporting executive KPIs.
    page.appendChild(section('What this lens leads with',
                             headline.length + occupancy.length));
    // metricTile renders the gate's posture, not a chosen figure: a permitted headline shows its
    // number and its caveat, a conflicted measure shows every competing definition and no
    // headline, a blocked one shows the unavailable statement. Ordering these tiles changes
    // none of that. A lens that holds none of the headline measures -- operations, for one --
    // gets no empty grid.
    if (headline.length) {
      const grid = el('div', 'tile-grid');
      grid.setAttribute('data-section', 'workspace-kpis');
      headline.forEach(function (t) { grid.appendChild(metricTile(t, ctx.openMetric)); });
      page.appendChild(grid);
    }

    // Occupancy is one question with several supported readings. All of them stay -- the tile
    // shows each definition the gate carries -- but they are set apart from the headline row so
    // they do not read as several independent KPIs to be totalled.
    occupancy.forEach(function (t) {
      const wrap = el('section', 'workspace-occupancy');
      wrap.setAttribute('data-section', 'workspace-occupancy');
      wrap.appendChild(el('p', 'workspace-note',
        'Occupancy is one question the records answer in more than one way. The readings below '
        + 'are alternatives to choose between, not separate figures to add together.'));
      wrap.appendChild(metricTile(t, ctx.openMetric));
      page.appendChild(wrap);
    });
  }

  // What moved, from the same comparison engine Owner Home uses -- so a movement stated here
  // cannot disagree with the movement stated there. Only pairs the engine accepted appear;
  // a part-month is never presented as a movement.
  const movements = ws.changes || [];
  if (movements.length) {
    page.appendChild(section('Business movement', movements.length));
    const list = el('div', 'movement-grid');
    list.setAttribute('data-section', 'workspace-movements');
    movements.forEach(function (c) { list.appendChild(movementRow(c)); });
    page.appendChild(list);
  }

  // What actually needs someone, from the engine's own split. The lump this replaced held the
  // standing findings AND the period movements together, so a month in which revenue rose was
  // reported as a month with one more thing needing attention. The movements are rendered above,
  // where they belong; what is left here is work.
  const decisions = ws.decision_queue || [];
  const findings = (ws.needs_attention || []).filter(function (i) {
    return i && i.what_happened;
  });
  if (decisions.length || findings.length) {
    page.appendChild(section('Needs attention', decisions.length + findings.length));

    if (decisions.length) {
      const queue = el('div', 'decision-queue');
      queue.setAttribute('data-section', 'workspace-decisions');
      decisions.forEach(function (d) {
        const view = ownerDecision(d);
        const card = el('article', 'decision');
        card.setAttribute('data-trust', d.trust || '');
        if (view.title) card.appendChild(el('h4', 'decision-title', view.title));
        if (view.posture) card.appendChild(el('p', 'decision-posture', view.posture));
        if (view.decision) card.appendChild(el('p', 'decision-text', view.decision));
        queue.appendChild(card);
      });
      page.appendChild(queue);
    }

    if (findings.length) {
      const list = el('div', 'issue-list');
      list.setAttribute('data-section', 'workspace-findings');
      findings.forEach(function (i) {
        const card = el('article', 'issue');
        card.setAttribute('data-trust', (i.trust || {}).trust_level || '');
        const head = el('div', 'issue-head');
        // What it ASKS FOR, which is what this section is grouped by. The topical label
        // ("Definition Conflict", "Data Quality") stays on the payload for the pages built
        // around subject matter.
        head.appendChild(el('h4', 'issue-title',
          ownerText(i.action_category_label || i.category_label)));
        if (i.trust) head.appendChild(badge(i.trust));
        card.appendChild(head);
        card.appendChild(el('p', 'issue-what', ownerProse(i.what_happened)));
        if (i.why_it_matters) {
          card.appendChild(el('p', 'issue-why', ownerProse(i.why_it_matters)));
        }
        if (i.recommended_action) {
          card.appendChild(el('p', 'issue-action', ownerProse(i.recommended_action)));
        }
        list.appendChild(card);
      });
      page.appendChild(list);
    }

    // The finding register lives on its own page. Repeating all of it here would make this page
    // a second copy of it -- one that can fall out of step with the register itself.
    const more = el('p', 'workspace-note');
    more.appendChild(document.createTextNode(
      'Every recorded finding, with the evidence behind it: '));
    const link = el('a', 'bi-link', 'open the data quality review');
    link.href = '#/data-quality';
    more.appendChild(link);
    page.appendChild(more);
  }

  // Measures that answer once a period or an apartment is named. They are implemented and
  // available: presenting them as empty headline cards would say the records hold nothing,
  // which is not what is true. Each carries the engine's own sentence about what it needs.
  if (capabilities.length) {
    page.appendChild(section('Available on request', capabilities.length));
    // Not `.capability-list`: that class belongs to the analytics capability panel and is
    // written for a list of labels, not for cards.
    const list = el('div', 'workspace-capability-list');
    list.setAttribute('data-section', 'workspace-capabilities');
    capabilities.forEach(function (t) {
      const view = ownerView(t);
      // If the measure did answer without being asked for a period or an apartment, it is shown
      // as what it is. The prompt below is for the case where it is waiting to be asked -- it
      // must never stand in front of a figure the engine actually produced.
      if (view.value || view.definitions.length > 0) {
        list.appendChild(metricTile(t, ctx.openMetric));
        return;
      }
      const card = el('article', 'workspace-capability');
      card.setAttribute('data-metric-id', t.metric_id);
      card.appendChild(el('h4', 'workspace-capability-title', view.title));
      const prompt = capabilityPrompt(t);
      if (prompt) card.appendChild(el('p', 'workspace-capability-prompt', prompt));
      const open = el('button', 'entry-point', 'Open this measure');
      open.type = 'button';
      open.addEventListener('click', function () { ctx.openMetric(t.metric_id); });
      card.appendChild(open);
      list.appendChild(card);
    });
    page.appendChild(list);
  }

  if (trends.length) {
    page.appendChild(section('Over time', trends.length));
    const wrap = el('div', 'workspace-trends');
    wrap.setAttribute('data-section', 'workspace-trends');
    trends.forEach(function (t) { wrap.appendChild(trendCard(t, ctx, ws.as_of)); });
    page.appendChild(wrap);
  }

  // Everything else the lens may see, unchanged. A measure this page does not name explicitly
  // arrives here rather than disappearing, so the semantic layer stays whole.
  if (pool.length) {
    page.appendChild(section('Supporting analysis', pool.length));
    const grid = el('div', 'tile-grid');
    grid.setAttribute('data-section', 'workspace-supporting');
    pool.forEach(function (t) { grid.appendChild(metricTile(t, ctx.openMetric)); });
    page.appendChild(grid);
  }
}

/* One movement, compact: direction, both periods, both figures and the change between them --
 * every string formatted by the engine. The monthly series behind it is not printed here. */
function movementRow(change) {
  const row = el('article', 'movement');
  row.setAttribute('data-direction', change.direction || '');
  row.setAttribute('data-trust', (change.trust || {}).trust_level || '');
  row.appendChild(el('h4', 'movement-title', ownerTitle(change.title)));
  const line = el('p', 'movement-line');
  line.appendChild(el('span', 'movement-direction', change.direction || ''));
  if (change.display_change) {
    line.appendChild(el('span', 'movement-amount', ' by ' + change.display_change));
  }
  row.appendChild(line);
  if (change.previous_period && change.current_period) {
    row.appendChild(el('p', 'movement-periods',
      change.previous_period + ' → ' + change.current_period));
  }
  if (change.current_display && change.previous_display) {
    const figures = el('dl', 'compare-figures');
    [[change.current_period, change.current_display],
     [change.previous_period, change.previous_display],
     ['Change', change.absolute_display
       + (change.percent_display ? ' (' + change.percent_display + ')' : '')]]
      .forEach(function (pair) {
        if (!pair[1]) return;
        figures.appendChild(el('dt', 'compare-label', pair[0]));
        figures.appendChild(el('dd', 'compare-value', pair[1]));
      });
    row.appendChild(figures);
  }
  // One explanation per row: when the engine has said why a comparison cannot be made, its
  // sentence already covers the coverage and part-month state beside it.
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
  if (change.alternative_note) {
    row.appendChild(el('p', 'movement-note', ownerProse(change.alternative_note)));
  }
  return row;
}

/*
 * A recorded series, drawn by the shared chart. Recent months by default because that is what a
 * briefing is about; the full recorded history is one click away, and the toggle only changes how
 * many of the engine's points are drawn. No value here is computed, converted or interpolated,
 * and a month the records do not hold stays absent rather than becoming a zero.
 */
function trendCard(tile, ctx, asOf) {
  // The same owner projection the tiles use, so a measure is named and caveated identically
  // whether it is drawn as a chart or as a tile.
  const view = ownerView(tile);
  const card = el('article', 'trend-card');
  card.setAttribute('data-metric-id', tile.metric_id);
  card.setAttribute('data-trust', (tile.trust || {}).trust_level || '');

  const head = el('div', 'trend-head');
  head.appendChild(el('h4', 'trend-title', view.title));
  if (tile.trust) head.appendChild(badge(tile.trust));
  card.appendChild(head);

  // The gate's own sentence about a measure with no permitted single reading, said above the
  // charts the way the tiles say it above their definitions.
  if (!tile.headline_permitted && tile.trust && tile.trust.owner_label) {
    card.appendChild(el('p', 'tile-refusal', tile.posture_line || tile.trust.owner_label));
  }

  const series = seriesSetOf(tile);
  const longest = series.reduce(function (n, s) { return Math.max(n, s.points.length); }, 0);
  const body = el('div', 'trend-body');
  let full = false;

  // A measure with competing definitions is drawn once per definition, each under its own name.
  // No definition is preferred, averaged, or drawn on top of another.
  function draw() {
    const drawn = [];
    series.forEach(function (s) {
      if (s.label) drawn.push(el('p', 'trend-series-label', s.label));
      drawn.push(lineChart(s.points, {
        label: s.label || view.title,
        recent: full ? 0 : 24,
        // The page's as-at date, which is what the part-month note is about. `tile.as_of` is the
        // measure's TIME SEMANTICS -- "records stop on entry_date, truncated to calendar month;
        // coverage: 53 distinct calendar months..." -- written for an analyst, and reading it
        // into "Records stop on ..." put a column name in front of the owner.
        asOf: asOf || '',
        displays: tile.series_display || {},
      }));
    });
    body.replaceChildren.apply(body, drawn);
  }

  const control = el('div', 'range-control');
  control.appendChild(el('span', 'range-label', 'Range'));
  [[false, 'Recent'], [true, 'Full recorded history']].forEach(function (choice) {
    const button = el('button', 'range-choice', choice[1]);
    button.type = 'button';
    if (choice[0] === full) button.classList.add('active');
    button.addEventListener('click', function () {
      full = choice[0];
      control.querySelectorAll('.range-choice').forEach(function (b) {
        b.classList.remove('active');
      });
      button.classList.add('active');
      draw();
    });
    control.appendChild(button);
  });
  control.appendChild(el('span', 'range-count', longest + ' recorded months available'));
  card.appendChild(control);

  draw();
  card.appendChild(body);

  if (view.caveat) card.appendChild(el('p', 'trend-caveat', view.caveat));

  const open = el('button', 'entry-point', 'Open this measure');
  open.type = 'button';
  open.addEventListener('click', function () { ctx.openMetric(tile.metric_id); });
  card.appendChild(open);
  return card;
}

/* --- executive report --------------------------------------------------------------------- */

export async function renderReport(root, ctx) {
  root.replaceChildren(loading('the management report'));

  let report;
  try {
    report = await api.executiveReport();
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'report');
  page.appendChild(el('h1', 'dashboard-title', 'Management report'));
  page.appendChild(el('p', 'dashboard-asof', 'As at ' + report.as_of));

  const sections = el('p', 'report-sections',
    'Sections: ' + (report.sections || []).join(' · '));
  page.appendChild(sections);

  // The report body is generated by the engine. It is rendered verbatim: a client that
  // reformatted it could drop a caveat or collapse a conflict panel while appearing to
  // reproduce the report faithfully.
  const body = el('pre', 'report-body');
  body.setAttribute('data-role', 'report-body');
  body.textContent = report.text;
  page.appendChild(body);

  if (report.limitations && report.limitations.length) {
    const lim = el('section', 'limitations');
    lim.appendChild(el('h2', 'section-title', 'Limitations'));
    const ul = el('ul', null);
    report.limitations.forEach(function (l) { ul.appendChild(el('li', null, l)); });
    lim.appendChild(ul);
    page.appendChild(lim);
  }

  root.replaceChildren(page);
}

/* --- system / integration status ------------------------------------------------------------ */

export async function renderSystem(root, ctx) {
  root.replaceChildren(loading('system status'));

  let health;
  try {
    health = await api.health();
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'system');
  page.appendChild(el('h1', 'dashboard-title', 'System status'));

  const src = el('section', 'system-block');
  src.setAttribute('data-role', 'data-source');
  src.appendChild(el('h2', 'section-title', 'Data source'));
  src.appendChild(el('p', null, health.data_source.name + ' (' + health.data_source.kind + ')'));
  src.appendChild(el('p', 'system-status', 'Status: ' + health.data_source.status));
  src.appendChild(el('p', null, 'As at ' + health.data_source.as_of));
  src.appendChild(el('p', 'system-note', health.data_source.notes));
  src.appendChild(el('p', 'system-note', health.revalidation.summary));
  page.appendChild(src);

  const llm = el('section', 'system-block');
  llm.setAttribute('data-role', 'llm');
  llm.appendChild(el('h2', 'section-title', 'Language layer'));
  llm.appendChild(el('p', null, 'Mode: ' + health.llm.mode));
  llm.appendChild(el('p', null, 'Status: ' + (health.llm.status || '')));
  llm.appendChild(el('p', null, 'Destination: ' + (health.llm.destination || 'none')));
  llm.appendChild(el('p', null, 'Local loopback: ' +
    ((health.llm.local_loopback) ? 'yes' : 'no')));
  llm.appendChild(el('p', null, 'External network: ' +
    (health.llm.network_access ? 'yes' : 'no')));
  llm.appendChild(el('p', 'system-note', health.llm.note));
  if (health.llm.remaining_requirement) {
    llm.appendChild(el('p', 'system-note', 'Remaining: ' + health.llm.remaining_requirement));
  }
  page.appendChild(llm);

  const auth = el('section', 'system-block');
  auth.setAttribute('data-role', 'auth');
  auth.appendChild(el('h2', 'section-title', 'Authentication'));
  auth.appendChild(el('p', 'system-status', 'Status: ' + (health.auth && health.auth.status)));
  auth.appendChild(el('p', null, 'Mode: ' + (health.auth && health.auth.mode)));
  if (health.auth && health.auth.remaining_requirement) {
    auth.appendChild(el('p', 'system-note', 'Remaining: ' + health.auth.remaining_requirement));
  }
  page.appendChild(auth);

  if (health.live_data) {
    const live = el('section', 'system-block');
    live.setAttribute('data-role', 'live-data');
    live.appendChild(el('h2', 'section-title', 'Live data'));
    live.appendChild(el('p', 'system-status', 'Status: ' + health.live_data.status));
    live.appendChild(el('p', 'system-note', health.live_data.notes || ''));
    if (health.live_data.remaining_requirement) {
      live.appendChild(el('p', 'system-note',
        'Remaining: ' + health.live_data.remaining_requirement));
    }
    page.appendChild(live);
  }

  root.replaceChildren(page);
}
