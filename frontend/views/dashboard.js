/*
 * views/dashboard.js -- the Owner Home.
 *
 * Answers "How is my business doing?" without the owner asking. Every tile, insight, change and
 * decision comes from `/api/owner/home` in one payload; this module assembles them and adds
 * nothing -- no figure, no threshold, no ordering that implies a judgement the engine did not
 * make.
 *
 * Phase 14 reorganised this screen into three blocks, in the order an owner actually reads a
 * business: what the numbers are, what needs a decision, what the evidence suggests. Previously
 * the attention queue sat BELOW the full insight feed, so the items most needing a decision were
 * the ones furthest down the page.
 *
 * The behaviour that matters most is still what this screen REFUSES to show. Several of the
 * headline measures carry no figure at all, because profit, receivables and occupancy each have
 * competing evidence-backed definitions. A cockpit's whole idiom is one number per tile, so
 * resisting it is the point rather than an edge case.
 */

import { api } from '../api.js';
import { el, metricTile, insightCard, changeCard, section, loading, errorState, emptyState }
  from '../render.js';
import { badge } from '../trust.js';
import { ownerInsight, ownerAction, ownerProse } from '../owner_view.js';

// Insight categories that represent something the owner may need to act on, and those that
// report a state worth knowing. The split is presentational: both lists are rendered in full,
// and no insight is dropped by either.
function tileGrid(tiles, name, openMetric) {
  const grid = el('div', 'tile-grid');
  grid.setAttribute('data-section', name);
  tiles.forEach(function (t) { grid.appendChild(metricTile(t, openMetric)); });
  return grid;
}

/*
 * The feed, grouped by what each item ASKS OF THE OWNER.
 *
 * The grouping and its labels are the engine's: each card carries the action category the
 * deterministic layer assigned it and the label that goes with it, so this function knows of no
 * categories at all. It used to hold two hardcoded lists of topical names, which meant the page
 * decided what counted as "attention" -- and it counted a validated revenue rise as one.
 *
 * Order within a block is the order the engine handed over; nothing is re-ranked here.
 */
function actionGroups(cards) {
  const feed = el('div', 'insight-feed');
  const order = [];
  const byAction = {};
  (cards || []).forEach(function (card) {
    const key = card.action_category || '';
    if (!byAction[key]) { byAction[key] = []; order.push(key); }
    byAction[key].push(card);
  });
  order.forEach(function (key) {
    const items = byAction[key];
    const group = el('section', 'insight-group');
    group.setAttribute('data-action-category', key);
    group.setAttribute('data-category', items[0].category || '');
    const h = el('h3', 'insight-group-title', items[0].action_category_label || '');
    h.appendChild(el('span', 'section-count', String(items.length)));
    group.appendChild(h);
    items.forEach(function (i) { group.appendChild(insightCard(i)); });
    feed.appendChild(group);
  });
  return feed;
}

/* An empty block says so, and says that it is the evidence's answer rather than a missing view. */
function feedOrEmpty(cards, emptyMessage) {
  if ((cards || []).length === 0) return emptyState(emptyMessage);
  return actionGroups(cards);
}

/*
 * "4 need a decision · 11 need a review" -- the headline count broken down by what the subjects
 * ask for. Counted from the groups themselves and labelled with the engine's own category
 * labels, so no list of categories is written here and none can fall out of step.
 */
function attentionBreakdown(subjects) {
  const counts = [];
  const seen = {};
  (subjects || []).forEach(function (group) {
    const key = group.action_category || '';
    if (!(key in seen)) { seen[key] = counts.length; counts.push({ label: group.action_category_label || key, n: 0 }); }
    counts[seen[key]].n += 1;
  });
  if (counts.length < 2) return '';
  return counts.map(function (c) { return c.n + ' × ' + String(c.label).toLowerCase(); })
    .join(' · ');
}

/*
 * One business subject: what it is, what it asks for, and the findings behind it.
 *
 * The findings are listed by their own owner sentences rather than summarised, so grouping hides
 * nothing -- it only stops the same subject being counted and shown several times over.
 */
function subjectCard(group) {
  const card = el('article', 'decision');
  card.setAttribute('data-action-category', group.action_category || '');
  card.setAttribute('data-subject', group.subject || '');

  const head = el('div', 'decision-head');
  head.appendChild(el('h4', 'decision-title', group.subject || ''));
  head.appendChild(el('span', 'decision-status', group.action_category_label || ''));
  card.appendChild(head);

  // A subject holding both a conflict and a recording problem asks for both. The card says so
  // rather than reporting only the stronger of the two.
  const also = (group.categories || []).filter(function (c) {
    return c !== group.action_category;
  });
  if (also.length) {
    const others = (group.items || []).filter(function (i) {
      return also.indexOf(i.action_category) !== -1;
    }).map(function (i) { return i.action_category_label; });
    card.appendChild(el('p', 'decision-posture',
      'Also needs: ' + [...new Set(others)].join(', ').toLowerCase()));
  }

  const list = el('ul', 'subject-findings');
  (group.items || []).forEach(function (item) {
    const view = ownerInsight(item);
    const li = el('li', 'subject-finding');
    if (view.finding) li.appendChild(el('p', 'subject-finding-what', view.finding));
    if (view.action) li.appendChild(el('p', 'subject-finding-action', view.action));
    list.appendChild(li);
  });
  card.appendChild(list);
  return card;
}

export async function renderDashboard(root, ctx) {
  root.replaceChildren(loading('your business summary'));

  let home;
  try {
    home = await api.ownerHome(ctx.role);
  } catch (err) {
    root.replaceChildren(errorState(err));
    return;
  }

  const page = el('div', 'dashboard');

  // -- header ------------------------------------------------------------------------------
  const head = el('header', 'dashboard-head');
  head.appendChild(el('h1', 'dashboard-title', 'How is my business doing?'));
  head.appendChild(el('p', 'dashboard-asof', 'As at ' + home.as_of));
  const toBi = el('a', 'bi-link bi-link-subtle', 'Open in Power BI');
  toBi.href = '#/bi/executive';
  toBi.setAttribute('data-role', 'open-bi');
  head.appendChild(toBi);
  page.appendChild(head);

  const asks = el('nav', 'quick-asks');
  asks.setAttribute('aria-label', 'Suggested questions');
  (home.ai_entry_points || []).forEach(function (ep) {
    const b = el('button', 'quick-ask entry-point', ep.label);
    b.setAttribute('data-action', ep.action);
    b.setAttribute('data-question', ep.question);
    asks.appendChild(b);
  });
  page.appendChild(asks);

  /* ===== 1. Executive snapshot =========================================================== */

  const snapshot = el('section', 'home-block');
  snapshot.setAttribute('data-block', 'executive-snapshot');
  snapshot.appendChild(el('h2', 'home-block-title', 'Executive snapshot'));

  snapshot.appendChild(section('Business health'));
  snapshot.appendChild(tileGrid(home.business_health, 'business-health', ctx.openMetric));

  snapshot.appendChild(section('Operations'));
  snapshot.appendChild(tileGrid(home.operations, 'operations', ctx.openMetric));

  snapshot.appendChild(section('Risk indicators'));
  snapshot.appendChild(tileGrid(home.risks, 'risks', ctx.openMetric));

  // Which of these can be relied on, stated up front rather than discovered per tile.
  snapshot.appendChild(section('Which numbers can I trust?'));
  const trust = el('div', 'trust-summary');
  trust.setAttribute('data-section', 'trust-summary');
  Object.keys(home.trust_summary || {}).forEach(function (level) {
    const t = home.trust_summary[level];
    const row = el('div', 'trust-row');
    row.setAttribute('data-trust', level);
    row.appendChild(badge(t));
    row.appendChild(el('span', 'trust-count', String(t.count) + ' measures'));
    row.appendChild(el('span', 'trust-explain', t.owner_explanation));
    trust.appendChild(row);
  });
  snapshot.appendChild(trust);
  page.appendChild(snapshot);

  /* ===== 2. What needs attention ========================================================= */

  const attention = el('section', 'home-block home-block-attention');
  attention.setAttribute('data-block', 'needs-attention');
  attention.appendChild(el('h2', 'home-block-title', 'What needs my attention'));

  /*
   * One entry per business subject, which is what the owner is actually dealing with.
   *
   * The headline counts what this list shows. It used to count the underlying findings -- twenty
   * over a list of five subjects -- and the same subject then appeared again in the feed below,
   * so tenant dues was on the page four times. The grouping and the count are the engine's; this
   * renders them.
   */
  const subjects = home.attention_subjects || [];
  attention.appendChild(section('Business subjects', subjects.length));
  const breakdown = attentionBreakdown(subjects);
  if (breakdown) attention.appendChild(el('p', 'home-block-note', breakdown));

  const queue = el('div', 'decision-queue');
  queue.setAttribute('data-section', 'attention-subjects');
  if (subjects.length === 0) {
    queue.appendChild(emptyState(
      'Nothing in the records is waiting on a decision or a review. This is what the evidence '
      + 'says, not an empty view.'));
  }
  subjects.forEach(function (group) { queue.appendChild(subjectCard(group)); });
  attention.appendChild(queue);
  page.appendChild(attention);

  /* ===== 3. Business movements ============================================================
   *
   * What the business DID, kept apart from what needs doing about it. Both blocks are built
   * from the engine's own action categories, so a figure that rose is reported as a figure that
   * rose and counted nowhere near the work list.
   */

  const moved = el('section', 'home-block');
  moved.setAttribute('data-block', 'business-movements');
  moved.appendChild(el('h2', 'home-block-title', 'What the business did'));
  moved.appendChild(el('p', 'home-block-note',
    'Complete periods only, so a part-month is never shown as a movement. Direction only: your '
    + 'records set no threshold for what counts as a significant move, so none is applied.'));

  moved.appendChild(section('Movements', (home.movements || []).length));
  const movementFeed = feedOrEmpty(home.movements,
    'No period-over-period movement is established on the current evidence.');
  movementFeed.setAttribute('data-section', 'movements');
  moved.appendChild(movementFeed);

  // The same movements with both figures and the change between them.
  moved.appendChild(section('Compared side by side', (home.changes || []).length));
  const changes = el('div', 'change-grid');
  changes.setAttribute('data-section', 'changes');
  if ((home.changes || []).length === 0) {
    changes.appendChild(emptyState(
      'No period-over-period comparison is available on the current evidence.'));
  }
  (home.changes || []).forEach(function (c) { changes.appendChild(changeCard(c)); });
  moved.appendChild(changes);
  page.appendChild(moved);

  /* ===== 4. Worth knowing ================================================================= */

  const insights = el('section', 'home-block');
  insights.setAttribute('data-block', 'key-insights');
  insights.appendChild(el('h2', 'home-block-title', 'Worth knowing'));
  insights.appendChild(el('p', 'home-block-note',
    'Recorded because the records show it. Nothing here asks anything of you.'));

  const standingFeed = feedOrEmpty(home.findings,
    'Nothing else is recorded about the current evidence.');
  standingFeed.setAttribute('data-section', 'standing-insights');
  insights.appendChild(standingFeed);

  // Anything the engine classed as supporting information. Rendered only when there is some:
  // an empty block here would say nothing, where the monitor block above says something by
  // being empty.
  if ((home.supporting || []).length) {
    insights.appendChild(section('Supporting information', home.supporting.length));
    const supportingFeed = actionGroups(home.supporting);
    supportingFeed.setAttribute('data-section', 'supporting');
    insights.appendChild(supportingFeed);
  }

  insights.appendChild(section('Suggested next steps', (home.recommended_actions || []).length));
  const actions = el('div', 'action-list');
  actions.setAttribute('data-section', 'actions');
  if ((home.recommended_actions || []).length === 0) {
    actions.appendChild(emptyState('No recommendation is supported by the current evidence.'));
  }
  (home.recommended_actions || []).forEach(function (a) {
    const view = ownerAction(a);
    const item = el('article', 'action');
    item.setAttribute('data-trust', a.trust);
    if (view.recommendation) item.appendChild(el('p', 'action-text', view.recommendation));
    if (view.confidence) {
      item.appendChild(el('p', 'action-confidence', 'Confidence: ' + view.confidence));
    }
    actions.appendChild(item);
  });
  insights.appendChild(actions);
  page.appendChild(insights);

  /* ===== limitations ===================================================================== */

  const lim = el('section', 'limitations');
  lim.setAttribute('data-section', 'limitations');
  lim.appendChild(el('h2', 'section-title', 'Limitations'));
  const ul = el('ul', null);
  (home.limitations || []).forEach(function (l) {
    const cleaned = ownerProse(l);
    if (cleaned) ul.appendChild(el('li', null, cleaned));
  });
  lim.appendChild(ul);
  page.appendChild(lim);

  root.replaceChildren(page);
}
