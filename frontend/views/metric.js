/*
 * views/metric.js -- Phase 10 Step 2. Metric detail and the conflict experience.
 *
 * The conflict view is the sharpest surface in the application. Its job is to present several
 * evidence-backed answers that disagree, WITHOUT choosing between them -- not by default, not by
 * ordering, not by styling one more prominently, and not by offering an average.
 *
 * "Which definition should we use?" is answered with a statement about who owns that decision,
 * never with a number.
 */

import { api } from '../api.js';
import { el, section, loading, errorState, unavailableState } from '../render.js';
import { badge, ariaLabel, toneClass } from '../trust.js';
import { ownerView } from '../owner_view.js';
import { biHref, biKeyForMetricId } from '../bi_nav.js';

export async function renderMetric(root, metricId, ctx) {
  root.replaceChildren(loading(metricId));

  let detail;
  try {
    detail = await api.metricDetail(metricId, ctx.role);
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  if (!detail.available) {
    root.replaceChildren(unavailableState(
      detail.unavailable_reason || detail.reason || 'This measure is not available.'));
    return;
  }

  const tile = detail.tile;
  // The measure's semantic contract. Everything the page says ABOUT the measure -- its name, the
  // question it answers, what it may be used for -- is read from here rather than derived, so
  // this page cannot describe a measure differently from the tile that led to it.
  const contract = detail.contract || {};
  const ownerSafe = contract.owner_safe_fields || [];
  const isSafe = function (field) { return ownerSafe.indexOf(field) !== -1; };

  const page = el('div', 'metric-detail');
  page.setAttribute('data-metric-id', metricId);
  page.setAttribute('data-trust', tile.trust.trust_level);

  // -- header --------------------------------------------------------------------------------
  const title = contract.business_name || detail.name;
  const head = el('header', 'metric-head ' + toneClass(tile.trust));
  head.setAttribute('aria-label', ariaLabel(title, tile.trust));
  head.appendChild(el('h1', 'metric-title', title));
  // The question this measure answers, where the registry states it in words an owner can read.
  if (isSafe('business_question')) {
    head.appendChild(el('p', 'metric-question', contract.business_question));
  }
  head.appendChild(badge(tile.trust));
  page.appendChild(head);

  // -- value, or the refusal ------------------------------------------------------------------
  const valueBlock = el('section', 'metric-value-block');
  if (tile.headline_permitted) {
    const v = el('p', 'metric-value', tile.display_value);
    v.setAttribute('data-role', 'headline');
    valueBlock.appendChild(v);
  } else {
    valueBlock.appendChild(el('p', 'metric-refusal',
      tile.posture_line || tile.trust.owner_label));
    valueBlock.appendChild(el('p', 'metric-refusal-why', tile.trust.owner_explanation));
    if (tile.definitions && tile.definitions.length) {
      const list = el('ul', 'definition-list');
      list.setAttribute('data-role', 'definitions');
      // The same owner projection every other surface uses. Rendered raw, these labels are the
      // registry's -- "Tenant dues -- Def A: v_outstanding_receivables (reversals excluded)" --
      // which names the record rather than the distinction the owner is being asked to choose
      // between. Every definition still appears, in the engine's order, with its own figure.
      ownerView(tile).definitions.forEach(function (d) {
        const li = el('li', 'definition');
        li.appendChild(el('span', 'definition-label', d.label));
        li.appendChild(el('span', 'definition-value', d.value));
        if (d.secondary && d.secondary.length) {
          const parts = el('ul', 'value-parts');
          d.secondary.forEach(function (part) {
            const item = el('li', 'value-part');
            if (part.label) item.appendChild(el('span', 'value-part-label', part.label + ': '));
            item.appendChild(el('span', 'value-part-figure', part.value));
            parts.appendChild(item);
          });
          li.appendChild(parts);
        }
        list.appendChild(li);
      });
      valueBlock.appendChild(list);
      const open = el('button', 'primary', 'View all definitions');
      open.setAttribute('data-action', 'conflict');
      open.addEventListener('click', function () { ctx.openConflict(metricId); });
      valueBlock.appendChild(open);
    } else if (tile.unavailable_reason) {
      valueBlock.appendChild(el('p', 'metric-unavailable', tile.unavailable_reason));
    }
  }
  // The caveat as every other surface states it. Rendered raw it was the registry's own note --
  // the posture in machine form, a policy instruction to the engine, and the conflict records
  // behind it. The projection keeps the limitation and drops the vocabulary; the raw column is
  // under the technical record below.
  const ownerCaveatText = ownerView(tile).caveat;
  if (ownerCaveatText) {
    const c = el('p', 'metric-caveat', ownerCaveatText);
    c.setAttribute('data-role', 'caveat');
    valueBlock.appendChild(c);
  }
  const toBi = el('a', 'bi-link', 'View in Power BI');
  toBi.href = biHref(biKeyForMetricId(metricId));
  toBi.setAttribute('data-role', 'open-bi');
  valueBlock.appendChild(toBi);
  page.appendChild(valueBlock);

  // -- the analytical record --------------------------------------------------------------------
  function block(title, body) {
    if (!body) return;
    const s = el('section', 'metric-block');
    s.appendChild(el('h2', 'metric-block-title', title));
    s.appendChild(el('p', 'metric-block-body', body));
    page.appendChild(s);
  }
  function listBlock(title, items, dataRole) {
    if (!items || !items.length) return;
    const s = el('section', 'metric-block');
    if (dataRole) s.setAttribute('data-role', dataRole);
    s.appendChild(el('h2', 'metric-block-title', title));
    const ul = el('ul', null);
    items.forEach(function (i) { ul.appendChild(el('li', null, String(i))); });
    s.appendChild(ul);
    page.appendChild(s);
  }

  /*
   * What this measure means, in the owner's language.
   *
   * Every line is a contract field the CONTRACT ITSELF marks owner-safe. A definition that names
   * an application function and a grain written as column names are the right words for the
   * audit trail and the wrong ones here, so they are not shown here -- they are below, whole and
   * unedited, under the technical record. The page makes no judgement of its own about which is
   * which; it asks the contract.
   */
  const about = el('section', 'metric-block');
  about.setAttribute('data-role', 'contract');
  about.appendChild(el('h2', 'metric-block-title', 'What this measure means'));
  const facts = el('dl', 'contract-facts');
  function fact(label, field, value) {
    if (field && !isSafe(field)) return;
    const text = value === undefined ? contract[field] : value;
    if (!text) return;
    facts.appendChild(el('dt', 'contract-label', label));
    facts.appendChild(el('dd', 'contract-value', String(text)));
  }
  fact('Status', null, contract.owner_status);
  fact('What it is', 'definition');
  fact('One row of it is', 'grain');
  fact('Periods it covers', 'supported_period');
  fact('It can be split by', 'supported_dimensions');
  fact('Limitations', 'limitations');
  fact('When definitions compete', 'conflict_behaviour');
  fact('What this asks of you', 'owner_action');
  fact('Using it in a decision', null, contract.usable_for_decisions_note);
  fact('Comparing it over time', null, contract.comparable_over_time_note);
  about.appendChild(facts);
  page.appendChild(about);

  // -- the technical record, one click away -----------------------------------------------------
  const technical = document.createElement('details');
  technical.className = 'metric-technical';
  const techSummary = document.createElement('summary');
  techSummary.textContent = 'Evidence & technical details';
  technical.appendChild(techSummary);
  const techBody = el('div', 'metric-technical-body');

  block('Reference', metricId);
  // Where the owner is shown a different but equally real count of the same thing, the
  // calculator's own figure belongs here rather than nowhere.
  if (tile.recorded_value && typeof tile.recorded_value === 'object') {
    block('As originally recorded', Object.keys(tile.recorded_value).map(function (k) {
      return k + ': ' + tile.recorded_value[k];
    }).join('; '));
  }
  block('Business definition', detail.business_definition);
  block('Calculation', detail.calculation);
  block('Filters', detail.filters);
  block('Reversal policy', detail.reversal_policy);
  block('Soft-delete policy', detail.soft_delete_policy);
  block('Date basis', detail.date_field);
  block('Period', detail.period);
  listBlock('Dimensions', detail.dimensions);
  listBlock('Evidence', detail.evidence, 'evidence');

  const val = el('section', 'metric-block');
  val.setAttribute('data-role', 'validation');
  val.appendChild(el('h2', 'metric-block-title', 'Validation'));
  val.appendChild(el('p', null, detail.validation.status +
    (detail.validation.reference ? ' — ' + detail.validation.reference : '')));
  page.appendChild(val);

  listBlock('Related measures', detail.related_metrics);
  listBlock('Conflicts', detail.conflicts);
  listBlock('Data-quality findings', detail.dq_issues);
  listBlock('Insights touching this measure', detail.insights);

  // Everything the two helpers appended after the contract block belongs behind the fold.
  Array.from(page.querySelectorAll(':scope > .metric-block')).forEach(function (node) {
    if (node.getAttribute('data-role') === 'contract') return;
    techBody.appendChild(node);
  });
  technical.appendChild(techBody);
  page.appendChild(technical);

  // -- next questions -------------------------------------------------------------------------------
  const next = el('section', 'metric-block');
  next.appendChild(el('h2', 'metric-block-title', 'Ask about this'));
  const asks = el('div', 'quick-asks');
  (detail.recommended_questions || []).forEach(function (q) {
    const b = el('button', 'entry-point', q);
    b.setAttribute('data-action', 'ask');
    b.setAttribute('data-question', q);
    asks.appendChild(b);
  });
  (tile.ai_entry_points || []).forEach(function (ep) {
    const b = el('button', 'entry-point', ep.label);
    b.setAttribute('data-action', ep.action);
    b.setAttribute('data-question', ep.question);
    asks.appendChild(b);
  });
  next.appendChild(asks);
  page.appendChild(next);

  root.replaceChildren(page);
}

/* --- conflict view -------------------------------------------------------------------------- */

export async function renderConflict(root, metricId, ctx) {
  root.replaceChildren(loading('the competing definitions'));

  let cv;
  try {
    cv = await api.conflict(metricId, ctx.role);
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  if (cv.available === false) {
    root.replaceChildren(unavailableState(cv.reason));
    return;
  }

  const page = el('div', 'conflict-view');
  page.setAttribute('data-metric-id', metricId);
  page.setAttribute('data-trust', cv.trust.trust_level);
  page.setAttribute('data-headline-permitted', 'false');

  const head = el('header', 'conflict-head ' + toneClass(cv.trust));
  head.appendChild(el('h1', 'conflict-title', cv.name));
  head.appendChild(badge(cv.trust));
  head.appendChild(el('p', 'conflict-posture', cv.trust.owner_label));
  page.appendChild(head);

  page.appendChild(el('p', 'conflict-explain', cv.trust.owner_explanation));

  if (!cv.definitions_computable) {
    // The conflict is real; its figures are not computable. Showing the conflict WITHOUT numbers
    // is the only honest option: hiding the measure would imply no conflict exists, and showing
    // invented figures would be worse.
    page.appendChild(unavailableState(cv.note));
  }

  // Definitions. Rendered in the order the engine returned them, with identical styling: any
  // visual weight or "primary" placement would be a soft endorsement.
  const list = el('div', 'definition-cards');
  list.setAttribute('data-role', 'definitions');
  (cv.definitions || []).forEach(function (d) {
    const card = el('article', 'definition-card');
    card.appendChild(el('h2', 'definition-card-label', d.label));
    card.appendChild(el('p', 'definition-card-value', d.display_value));
    function row(term, value) {
      if (!value) return;
      const r = el('div', 'definition-row');
      r.appendChild(el('span', 'definition-term', term));
      r.appendChild(el('span', 'definition-detail', String(value)));
      card.appendChild(r);
    }
    row('Source', d.source);
    row('Time semantics', d.time_semantics);
    row('Calculation', d.calculation);
    row('Validation', d.validation_status);
    row('Limitations', d.limitations);
    list.appendChild(card);
  });
  page.appendChild(list);

  if (cv.numeric_difference) {
    const spread = el('section', 'conflict-spread');
    spread.appendChild(el('h2', 'section-title', 'How far apart they are'));
    Object.keys(cv.numeric_difference).forEach(function (pair) {
      const diff = cv.numeric_difference[pair];
      const line = diff.percentage_difference !== null && diff.percentage_difference !== undefined
        ? pair + ': ' + diff.absolute_difference + ' (' + diff.percentage_difference + '%)'
        : pair + ': ' + diff.absolute_difference;
      spread.appendChild(el('p', 'spread-line', line));
    });
    page.appendChild(spread);
  }

  // "Which should we use?" -- answered with the decision owner, never with a number.
  const decision = el('section', 'conflict-decision');
  decision.setAttribute('data-role', 'which-definition');
  decision.appendChild(el('h2', 'section-title', 'Which definition should we use?'));
  decision.appendChild(el('p', 'decision-answer', cv.which_should_we_use));
  decision.appendChild(el('p', 'decision-owner', 'Decision owner: ' + cv.resolution_owner));
  page.appendChild(decision);

  const ids = el('p', 'tile-ids');
  ids.textContent = 'Conflicts: ' + (cv.conflict_ids || []).join(', ') +
    ((cv.dq_ids && cv.dq_ids.length) ? '  ·  Data quality: ' + cv.dq_ids.join(', ') : '');
  page.appendChild(ids);

  root.replaceChildren(page);
}

/* --- data quality centre -------------------------------------------------------------------- */

export async function renderDataQuality(root, ctx) {
  root.replaceChildren(loading('the data-quality register'));

  let dq;
  try {
    dq = await api.dataQuality();
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'dq-center');
  page.appendChild(el('h1', 'dashboard-title', 'Data Quality'));
  page.appendChild(el('p', 'dashboard-asof',
    'What the records say about themselves. This page covers the whole business: it is not ' +
    'narrowed by a filter chosen elsewhere.'));

  // The tally, counted from the payload rather than stated here, so it cannot drift from the
  // findings listed below it.
  const summary = el('div', 'dq-summary');
  summary.setAttribute('data-section', 'dq-summary');
  const totalCard = el('div', 'dq-total');
  totalCard.appendChild(el('span', 'dq-total-count', String(dq.total)));
  totalCard.appendChild(el('span', 'dq-total-label',
    dq.total === 1 ? 'finding' : 'findings'));
  summary.appendChild(totalCard);
  (dq.severities || []).forEach(function (group) {
    const chip = el('a', 'dq-count');
    chip.href = '#dq-' + String(group.severity).toLowerCase();
    chip.setAttribute('data-severity', group.severity);
    chip.appendChild(el('span', 'dq-count-value', String(group.count)));
    chip.appendChild(el('span', 'dq-count-label', SEVERITY_LABELS[group.severity]
      || titleCase(group.severity)));
    summary.appendChild(chip);
  });
  page.appendChild(summary);

  (dq.severities || []).forEach(function (group) {
    const s = el('section', 'dq-group');
    s.setAttribute('data-severity', group.severity);
    s.id = 'dq-' + String(group.severity).toLowerCase();
    const h = el('h2', 'section-title',
      SEVERITY_LABELS[group.severity] || titleCase(group.severity));
    h.appendChild(el('span', 'section-count', String(group.count)));
    s.appendChild(h);
    group.issues.forEach(function (issue) { s.appendChild(dqCard(issue)); });
    page.appendChild(s);
  });

  root.replaceChildren(page);
}

// The engine's severity words, capitalised for reading. The ORDER is the engine's and is not
// touched here: no priority is invented, and nothing is re-ranked.
const SEVERITY_LABELS = {
  CRITICAL: 'Critical', HIGH: 'High', MEDIUM: 'Medium',
  LOW: 'Low', INFORMATIONAL: 'Informational', UNVERIFIED: 'Not yet verified',
};

function titleCase(text) {
  const word = String(text || '').toLowerCase();
  return word ? word.charAt(0).toUpperCase() + word.slice(1) : '';
}

/*
 * One finding, in the order an owner reads it: what it is, why it matters, what to do. The
 * technical record is not removed -- it is one click away, complete, and unchanged. Nothing in
 * the default view is an identifier, a table, a view or a formula.
 */
function dqCard(issue) {
  const card = el('article', 'dq-issue');
  card.setAttribute('data-dq-id', issue.dq_id);

  card.setAttribute('data-action-category', issue.owner_action_category || '');
  card.setAttribute('data-action-kind', issue.owner_action_kind || '');

  const head = el('div', 'dq-head');
  head.appendChild(el('h3', 'dq-title', issue.owner_what || issue.owner_issue || issue.issue));
  // What this finding asks for, from the engine's classification of the finding itself -- the
  // same category Owner Home groups by, so the two pages describe it identically.
  if (issue.owner_category_label) {
    head.appendChild(el('span', 'dq-posture', issue.owner_category_label));
  }
  card.appendChild(head);

  if (issue.owner_why) card.appendChild(el('p', 'dq-why', issue.owner_why));
  if (issue.owner_action) {
    const action = el('p', 'dq-action');
    action.appendChild(el('span', 'dq-action-label', 'Action'));
    action.appendChild(el('span', 'dq-action-text', issue.owner_action));
    card.appendChild(action);
  }

  const details = document.createElement('details');
  details.className = 'dq-details';
  const summary = document.createElement('summary');
  summary.textContent = 'Evidence & technical details';
  details.appendChild(summary);

  const meta = el('dl', 'dq-meta');
  function pair(term, value) {
    if (!value && value !== 0) return;
    meta.appendChild(el('dt', null, term));
    meta.appendChild(el('dd', null, String(value)));
  }
  pair('Finding reference', issue.dq_id);
  // The record's own sentence, unedited, so nothing the register says is lost to the page.
  if ((issue.owner_what || issue.owner_issue) !== issue.issue) {
    pair('Recorded wording', issue.issue);
  }
  pair('Kind of finding', String(issue.owner_action_kind || '').replace(/_/g, ' '));
  pair('Gate handling of affected measures', issue.owner_posture);
  pair('Business area', issue.business_area);
  pair('Affected rows', issue.affected_rows);
  pair('Affected amount', issue.affected_amount);
  pair('Affected measures', (issue.owner_measure_names || []).join(', '));
  pair('Measure references', (issue.affected_metrics || []).join(', '));
  pair('Trust levels affected', (issue.affected_trust_levels || []).join(', '));
  pair('Root cause', issue.root_cause);
  pair('Root-cause confidence', issue.root_cause_confidence);
  pair('Status', issue.status);
  pair('Evidence', (issue.evidence || []).join(', '));
  // The register's own handling column, under its own name. Labelled "Recommended
  // investigation" it read as advice, and its value is a posture -- so the row said the
  // recommended investigation was "BLOCK".
  pair('Recorded handling', issue.recommended_investigation);
  details.appendChild(meta);
  card.appendChild(details);
  return card;
}
