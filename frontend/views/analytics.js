/*
 * views/analytics.js -- Phase 14. The AI Analyst workspace.
 *
 * Four sections -- Financial, Operations, Risk & Data Quality, Business Insights -- served by
 * `/api/analytics/{section}`. Each is assembled server-side from the SAME owner-home payload the
 * dashboard renders, so a figure here and a figure there cannot disagree. This module adds no
 * second analytics path; it is a lens onto the one that exists.
 *
 * The part of this screen that earns its place is the last one: "What this section can and
 * cannot analyse". The specifications deliberately decline to fix a materiality threshold, an
 * anomaly bound, or a statistical method, so several analyses genuinely do not exist. A product
 * that hid that would look more capable and be less honest, and an owner would eventually ask a
 * question it cannot answer and receive silence rather than a reason.
 */

import { api } from '../api.js';
import {
  el, metricTile, insightCard, changeCard, section, loading, errorState, emptyState,
} from '../render.js';
import { badge } from '../trust.js';

/* --- section navigation -------------------------------------------------------------------- */

function sectionNav(sections, activeKey) {
  const nav = el('nav', 'analytics-nav');
  nav.setAttribute('aria-label', 'Analytics sections');
  sections.forEach(function (s) {
    const a = el('a', 'analytics-tab');
    a.href = '#/analytics/' + encodeURIComponent(s.section);
    a.setAttribute('data-section', s.section);
    a.appendChild(el('span', 'analytics-tab-title', s.title));
    const meta = el('span', 'analytics-tab-meta');
    meta.textContent = s.metric_count > 0
      ? String(s.metric_count) + ' measures'
      : 'Cross-domain';
    a.appendChild(meta);
    if (s.section === activeKey) {
      a.classList.add('active');
      a.setAttribute('aria-current', 'page');
    }
    nav.appendChild(a);
  });
  return nav;
}

/* --- trust posture strip -------------------------------------------------------------------- */

/*
 * How many of this section's measures sit at each posture. Counts come from the payload; this
 * builds no verdict of its own and orders nothing by severity, because an ordering would imply
 * a ranking the trust model does not define.
 */
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
    chip.appendChild(el('span', 'trust-strip-count', String(t.count)));
    chip.appendChild(el('span', 'trust-strip-explain', t.owner_explanation || ''));
    strip.appendChild(chip);
  });
  return strip;
}

/* --- capability disclosure ------------------------------------------------------------------ */

/*
 * Renders what this section can do and, with equal prominence, what it cannot. The limitation
 * sentences are printed exactly as the capability registry states them -- several end with the
 * required NOT_DETERMINABLE phrase, and softening one would turn a refusal into a hedge.
 */
function capabilityPanel(caps) {
  const panel = el('section', 'capability-panel');
  panel.setAttribute('data-section', 'capabilities');
  panel.appendChild(el('h2', 'section-title', 'What this section can and cannot analyse'));

  const supported = caps.supported || [];
  const limited = (caps.partial || []).concat(caps.unsupported || []);

  const can = el('div', 'capability-group');
  can.setAttribute('data-capability-group', 'supported');
  can.appendChild(el('h3', 'capability-group-title', 'Available analysis'));
  if (supported.length === 0) {
    can.appendChild(el('p', 'capability-none', 'No analysis is implemented for this section.'));
  } else {
    const list = el('ul', 'capability-list');
    supported.forEach(function (c) {
      const li = el('li', 'capability');
      li.appendChild(el('span', 'capability-label', c.label));
      list.appendChild(li);
    });
    can.appendChild(list);
  }
  panel.appendChild(can);

  const cannot = el('div', 'capability-group');
  cannot.setAttribute('data-capability-group', 'limited');
  cannot.appendChild(el('h3', 'capability-group-title', 'Not available, and why'));
  if (limited.length === 0) {
    cannot.appendChild(el('p', 'capability-none',
      'Every analysis defined for this section is implemented.'));
  } else {
    const list = el('ul', 'capability-list capability-list-limited');
    limited.forEach(function (c) {
      const li = el('li', 'capability capability-limited');
      li.setAttribute('data-status', c.status);
      li.appendChild(el('span', 'capability-label', c.label));
      li.appendChild(el('span', 'capability-status', c.status));
      if (c.limitation) li.appendChild(el('p', 'capability-limitation', c.limitation));
      list.appendChild(li);
    });
    cannot.appendChild(list);
  }
  panel.appendChild(cannot);
  return panel;
}

/* --- data quality (Risk section) ------------------------------------------------------------- */

function dataQualityPanel(dq) {
  const panel = el('section', 'dq-panel');
  panel.setAttribute('data-section', 'data-quality');
  panel.appendChild(section('Data quality findings', dq.total));
  (dq.severities || []).forEach(function (group) {
    const g = el('section', 'dq-group');
    g.setAttribute('data-severity', group.severity);
    const h = el('h3', 'dq-group-title', group.severity);
    h.appendChild(el('span', 'section-count', String(group.count)));
    g.appendChild(h);
    (group.issues || []).forEach(function (issue) {
      const item = el('article', 'dq-issue');
      item.setAttribute('data-dq-id', issue.dq_id);
      item.appendChild(el('h4', 'dq-issue-title', issue.issue));
      if (issue.business_area) {
        item.appendChild(el('p', 'dq-issue-area', issue.business_area));
      }
      if (issue.root_cause) {
        item.appendChild(el('p', 'dq-issue-cause', issue.root_cause));
      }
      if (issue.affected_metrics && issue.affected_metrics.length) {
        item.appendChild(el('p', 'tile-ids',
          'Affects ' + String(issue.affected_metrics.length) + ' measure(s)'));
      }
      g.appendChild(item);
    });
    panel.appendChild(g);
  });
  return panel;
}

/* --- decision support (Business Insights section) --------------------------------------------- */

function decisionPanel(payload) {
  const wrap = el('div', 'decision-panel');

  wrap.appendChild(section('Needs a decision', (payload.decision_queue || []).length));
  const queue = el('div', 'decision-queue');
  queue.setAttribute('data-section', 'decision-queue');
  if ((payload.decision_queue || []).length === 0) {
    queue.appendChild(emptyState('Nothing is awaiting a decision on the current evidence.'));
  }
  (payload.decision_queue || []).forEach(function (d) {
    const item = el('article', 'decision');
    item.setAttribute('data-insight-id', d.insight_id);
    item.setAttribute('data-trust', d.trust);
    item.appendChild(el('p', 'decision-posture', d.owner_facing));
    item.appendChild(el('p', 'decision-text', d.decision));
    queue.appendChild(item);
  });
  wrap.appendChild(queue);

  wrap.appendChild(section('Suggested next steps', (payload.recommended_actions || []).length));
  const actions = el('div', 'action-list');
  actions.setAttribute('data-section', 'actions');
  (payload.recommended_actions || []).forEach(function (a) {
    const item = el('article', 'action');
    item.setAttribute('data-trust', a.trust);
    item.appendChild(el('p', 'action-text', a.recommendation));
    item.appendChild(el('p', 'action-confidence', 'Confidence: ' + a.confidence));
    actions.appendChild(item);
  });
  wrap.appendChild(actions);
  return wrap;
}

/* --- the section page --------------------------------------------------------------------------- */

export async function renderAnalytics(root, sectionKey, ctx) {
  root.replaceChildren(loading('your analytics'));

  let directory, payload;
  try {
    directory = await api.analytics();
    payload = await api.analyticsSection(sectionKey);
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'analytics-page');
  page.setAttribute('data-analytics-section', sectionKey);

  const head = el('header', 'analytics-head');
  head.appendChild(el('p', 'analytics-eyebrow', 'AI Business Analyst'));
  head.appendChild(el('h1', 'dashboard-title', payload.title || 'Analytics'));
  if (payload.purpose) head.appendChild(el('p', 'analytics-purpose', payload.purpose));
  if (payload.as_of) head.appendChild(el('p', 'dashboard-asof', 'As at ' + payload.as_of));
  page.appendChild(head);

  page.appendChild(sectionNav(directory.sections || [], sectionKey));

  if (!payload.available) {
    page.appendChild(errorState({ message: payload.reason || 'This section is not available.' }));
    root.replaceChildren(page);
    return;
  }

  const strip = trustStrip(payload.trust_summary);
  if (strip) {
    page.appendChild(section('Which of these can I rely on?'));
    page.appendChild(strip);
  }

  // -- measures ------------------------------------------------------------------------------
  if ((payload.tiles || []).length > 0) {
    page.appendChild(section('Measures', payload.metric_count));
    const grid = el('div', 'tile-grid');
    grid.setAttribute('data-section', 'measures');
    payload.tiles.forEach(function (t) { grid.appendChild(metricTile(t, ctx.openMetric)); });
    page.appendChild(grid);
  }

  // -- what changed ---------------------------------------------------------------------------
  page.appendChild(section('What changed', (payload.changes || []).length));
  const changes = el('div', 'change-grid');
  changes.setAttribute('data-section', 'changes');
  if ((payload.changes || []).length === 0) {
    changes.appendChild(emptyState(
      'No period-over-period comparison is available for this section. Only complete months ' +
      'are compared, so a partial month is never shown as a fall.'));
  }
  (payload.changes || []).forEach(function (c) { changes.appendChild(changeCard(c)); });
  page.appendChild(changes);

  // -- findings --------------------------------------------------------------------------------
  page.appendChild(section('Findings', (payload.insights || []).length));
  const feed = el('div', 'insight-feed');
  feed.setAttribute('data-section', 'insights');
  if ((payload.insights || []).length === 0) {
    feed.appendChild(emptyState(
      'No finding in this section is supported by the current evidence. That is the result, ' +
      'not a gap in the view.'));
  }
  (payload.insights || []).forEach(function (i) { feed.appendChild(insightCard(i)); });
  page.appendChild(feed);

  if (payload.data_quality) page.appendChild(dataQualityPanel(payload.data_quality));
  if (payload.decision_queue) page.appendChild(decisionPanel(payload));

  page.appendChild(capabilityPanel(payload.capabilities || {}));

  if ((payload.limitations || []).length) {
    const lim = el('section', 'limitations');
    lim.setAttribute('data-section', 'limitations');
    lim.appendChild(el('h2', 'section-title', 'Limitations that apply to everything above'));
    const ul = el('ul', null);
    payload.limitations.forEach(function (l) { ul.appendChild(el('li', null, l)); });
    lim.appendChild(ul);
    page.appendChild(lim);
  }

  root.replaceChildren(page);
}
