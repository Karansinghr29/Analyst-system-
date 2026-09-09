/*
 * render.js -- Phase 10. Payload -> DOM.
 *
 * The rule this module exists to make unbreakable:
 *
 *     A tile renders `display_value` ONLY when `headline_permitted` is true.
 *
 * The payload for a headline-forbidden metric carries no `value` field at all, so there is
 * nothing to render even if a future edit tried. `metricTile()` still checks the flag
 * explicitly, because two independent barriers are worth more than one.
 *
 * There is no arithmetic anywhere in this file. Values arrive pre-computed and pre-formatted
 * from the engine. A frontend that formatted its own numbers could round or unit-convert a
 * figure away from what the engine computed, and the divergence would be invisible because both
 * sides would look correct.
 */

import { badge, ariaLabel, toneClass } from './trust.js';
import { ownerView, ownerInsight } from './owner_view.js';

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function section(title, count) {
  const h = el('h2', 'section-title', title);
  if (count !== undefined) {
    h.appendChild(el('span', 'section-count', String(count)));
  }
  return h;
}

/* --- metric tile ------------------------------------------------------------------------- */

export function metricTile(tile, onOpen) {
  const card = el('article', 'tile ' + toneClass(tile.trust));
  card.setAttribute('data-metric-id', tile.metric_id);
  card.setAttribute('data-trust', tile.trust ? tile.trust.trust_level : 'UNKNOWN');
  card.setAttribute('data-widget', tile.widget);
  card.setAttribute('data-headline-permitted', String(tile.headline_permitted));
  card.setAttribute('tabindex', '0');
  card.setAttribute('role', 'group');

  // Everything below renders the owner PROJECTION of the payload, not the payload itself. The
  // payload's record identifiers, database object names and policy text stay available to the
  // metric detail view and the evidence chain; they are not the Overview's language.
  const view = ownerView(tile);
  card.setAttribute('aria-label', ariaLabel(view.title, tile.trust));

  const head = el('header', 'tile-head');
  head.appendChild(el('h3', 'tile-title', view.title));
  head.appendChild(badge(tile.trust));
  card.appendChild(head);

  if (view.value || (view.secondary && view.secondary.length > 0)) {
    // SAFE / DISCLOSE: the single figure, exactly as the engine formatted it. A composite whose
    // payload names no total has parts but no headline, and an empty paragraph above them would
    // read as a missing figure.
    if (view.value) {
      const v = el('p', 'tile-value', view.value);
      v.setAttribute('data-role', 'headline');
      card.appendChild(v);
    }
    // A composite measure reads as one figure with its parts beneath, rather than as a run-on
    // of "key: value" pairs. Every part is the engine's own string.
    if (view.secondary.length > 0) {
      const parts = el('ul', 'value-parts');
      parts.setAttribute('data-role', 'value-parts');
      view.secondary.forEach(function (part) {
        const li = el('li', 'value-part');
        if (part.label) li.appendChild(el('span', 'value-part-label', part.label + ': '));
        li.appendChild(el('span', 'value-part-figure', part.value));
        parts.appendChild(li);
      });
      card.appendChild(parts);
    }
  } else if (view.definitions.length > 0) {
    // SHOW_BOTH: every competing definition, labelled in plain language. No default, no
    // average, no ordering that implies precedence. The posture line is the engine's, said for
    // the number of readings this measure actually holds -- "review both" is wrong above five.
    card.appendChild(el('p', 'tile-refusal', tile.posture_line || tile.trust.owner_label));
    const list = el('ul', 'definition-list');
    list.setAttribute('data-role', 'definitions');
    view.definitions.forEach(function (d) {
      const li = el('li', 'definition');
      li.appendChild(el('span', 'definition-label', d.label));
      if (d.value) li.appendChild(el('span', 'definition-value', d.value));
      // A multi-part definition reads as its named parts, the same way the headline branch
      // above renders a composite. Dropping them left the raw "key: value; key: value" string
      // as the only thing with anywhere to go.
      if (d.secondary && d.secondary.length > 0) {
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
    card.appendChild(list);
  } else {
    // BLOCK / NOT_DETERMINABLE: explicit unavailable statement, no chart, no zero.
    card.appendChild(el('p', 'tile-refusal', tile.trust.owner_label));
    if (view.unavailable) {
      card.appendChild(el('p', 'tile-unavailable', view.unavailable));
    }
  }

  if (view.caveat) {
    // DISCLOSE caveats render WITH the number, never behind a tooltip the owner may not open.
    const c = el('p', 'tile-caveat', view.caveat);
    c.setAttribute('data-role', 'caveat');
    card.appendChild(c);
  }

  // Conflict and data-quality record ids are deliberately not rendered here. They identify the
  // rows an analyst would open, not anything an owner can act on, and they remain on the
  // payload for the metric detail view. Per-tile Power BI links are not repeated here;
  // Overview exposes one Open-in-Power-BI action in the page header.

  const foot = el('footer', 'tile-foot');
  (view.actions || []).forEach(function (ep) {
    const b = el('button', 'entry-point', ep.label);
    b.setAttribute('data-action', ep.action);
    b.setAttribute('data-question', ep.question);
    foot.appendChild(b);
  });
  if (foot.childNodes.length) card.appendChild(foot);

  if (onOpen) {
    card.addEventListener('click', function (event) {
      if (event.target.closest('.entry-point, .bi-link')) return;
      onOpen(tile.metric_id);
    });
    card.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onOpen(tile.metric_id); }
    });
  }
  return card;
}

/* --- insight card ------------------------------------------------------------------------ */

const CATEGORY_LABEL_CLASS = {
  critical: 'cat-critical',
  attention: 'cat-attention',
  positive: 'cat-positive',
  opportunity: 'cat-opportunity',
  data_quality: 'cat-dq',
  definition_conflict: 'cat-conflict',
};

export function insightCard(insight) {
  const view = ownerInsight(insight);
  const card = el('article', 'insight ' + (CATEGORY_LABEL_CLASS[insight.category] || ''));
  card.setAttribute('data-insight-id', insight.insight_id);
  card.setAttribute('data-category', insight.category);
  card.setAttribute('data-trust', insight.trust ? insight.trust.trust_level : 'UNKNOWN');
  card.setAttribute('role', 'group');
  card.setAttribute('aria-label', (view.category || 'Insight') + ': ' + (view.finding || view.action));

  const head = el('header', 'insight-head');
  if (view.category) head.appendChild(el('span', 'insight-category', view.category));
  head.appendChild(badge(insight.trust));
  card.appendChild(head);

  // The owner's three questions, in the order they are asked: what is happening, why it matters,
  // what to do. The middle one was projected and then not rendered, so a card said what had
  // happened and what to do about it without ever saying why it mattered -- which is the one an
  // owner needs to decide whether to care. Evidence ids, rationale and specification filenames
  // stay on the payload for technical surfaces.
  if (view.finding) card.appendChild(el('p', 'insight-what', view.finding));
  if (view.why) card.appendChild(el('p', 'insight-why', view.why));
  if (view.action) {
    const act = el('p', 'insight-action', view.action);
    act.setAttribute('data-role', 'owner-action');
    card.appendChild(act);
  }

  const foot = el('footer', 'insight-foot');
  (view.actions || []).forEach(function (ep) {
    const b = el('button', 'entry-point', ep.label);
    b.setAttribute('data-action', ep.action);
    b.setAttribute('data-question', ep.question);
    foot.appendChild(b);
  });
  if (foot.childNodes.length) card.appendChild(foot);
  return card;
}

/* --- change card ------------------------------------------------------------------------- */

export function changeCard(change) {
  const card = el('article', 'change');
  card.setAttribute('data-metric-id', change.metric_id);
  card.setAttribute('data-direction', change.direction);

  card.appendChild(el('h3', 'change-title', change.title));

  if (change.direction === 'UNAVAILABLE') {
    card.appendChild(el('p', 'change-unavailable', change.unavailable_reason));
  } else {
    const line = el('p', 'change-value');
    line.appendChild(el('span', 'change-direction', change.direction));
    line.appendChild(el('span', 'change-amount', change.display_change));
    card.appendChild(line);
    card.appendChild(el('p', 'change-period',
      change.previous_period + ' → ' + change.current_period));
    // Materiality is undefined; the note says so on every change, never a threshold colour.
    card.appendChild(el('p', 'change-materiality', change.materiality_note));
  }
  if (change.coverage_note) {
    card.appendChild(el('p', 'change-coverage', change.coverage_note));
  }
  const foot = el('footer', 'change-foot');
  (change.ai_entry_points || []).forEach(function (ep) {
    const b = el('button', 'entry-point', ep.label);
    b.setAttribute('data-action', ep.action);
    b.setAttribute('data-question', ep.question);
    foot.appendChild(b);
  });
  card.appendChild(foot);
  return card;
}

/* --- states ------------------------------------------------------------------------------ */
/*
 * Six distinct terminal states (ui_state_model.md 1). Collapsing any two is a correctness
 * failure: "no data" and "not determinable" rendered identically would tell the owner a
 * measured zero where the truth is an unmeasurable quantity.
 */

export function loading(what) {
  const d = el('div', 'state state-loading');
  d.setAttribute('role', 'status');
  d.setAttribute('aria-live', 'polite');
  d.appendChild(el('p', null, 'Loading ' + (what || '') + '…'));
  return d;
}

export function emptyState(message) {
  const d = el('div', 'state state-empty');
  d.appendChild(el('p', null, message));
  return d;
}

export function unavailableState(message) {
  const d = el('div', 'state state-unavailable');
  d.setAttribute('data-state', 'unavailable');
  d.appendChild(el('p', null, message));
  return d;
}

export function errorState(err) {
  const d = el('div', 'state state-error');
  d.setAttribute('role', 'alert');
  d.setAttribute('data-state', 'error');
  d.appendChild(el('p', null, err && err.message
    ? err.message
    : 'Something went wrong. No figure is shown.'));
  if (err && err.detail) d.appendChild(el('p', 'state-detail', err.detail));
  return d;
}

export { section };
