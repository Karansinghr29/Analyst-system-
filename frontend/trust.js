/*
 * trust.js -- Phase 10. Trust payload -> visual treatment.
 *
 * This module contains NO trust logic. It maps a trust payload the API already produced onto a
 * CSS class and an icon glyph. Every label, explanation, and headline permission is read from
 * the payload; nothing here decides, derives, or overrides a verdict.
 *
 * The reason that matters: a frontend that could compute a trust level could disagree with the
 * gate, and the disagreement would be invisible because the answer would still look
 * authoritative. So the mapping below is presentation only, and the anti-drift validator checks
 * that no trust level is ever hardcoded into a decision.
 *
 * Accessibility rule (design_system_spec.md 7): trust is NEVER conveyed by colour alone. Every
 * treatment carries a text badge and a glyph as well as a tone class.
 */

// tone -> CSS class. The tone itself comes from the payload.
const TONE_CLASS = {
  neutral:     'trust-neutral',
  caution:     'trust-caution',
  conflict:    'trust-conflict',
  unavailable: 'trust-unavailable',
};

// icon name -> glyph. Presentation only.
const ICON_GLYPH = {
  check: '✓',   // ✓
  info:  'ℹ',   // ℹ
  split: '⇄',   // ⇄
  alert: '⚠',   // ⚠
  minus: '—',   // —
};

export function toneClass(trust) {
  if (!trust) return TONE_CLASS.unavailable;
  return TONE_CLASS[trust.tone] || TONE_CLASS.unavailable;
}

export function glyph(trust) {
  if (!trust) return ICON_GLYPH.minus;
  return ICON_GLYPH[trust.icon] || ICON_GLYPH.minus;
}

/*
 * The accessible label for any element carrying a trust posture.
 *
 * A screen reader must hear the posture, not just the number: "Profit — no single reliable
 * figure, definitions conflict" rather than a figure with an unannounced caveat.
 */
export function ariaLabel(title, trust) {
  if (!trust) return title;
  return title + ' — ' + trust.owner_label;
}

// Renders the badge. Text + glyph + tone class: three independent channels, so colour-blind and
// screen-reader users receive the posture through the same element sighted users do.
export function badge(trust) {
  const el = document.createElement('span');
  el.className = 'trust-badge ' + toneClass(trust);
  el.setAttribute('data-trust', trust ? trust.trust_level : 'UNKNOWN');
  el.setAttribute('title', trust ? trust.owner_explanation : '');

  const g = document.createElement('span');
  g.className = 'trust-glyph';
  g.setAttribute('aria-hidden', 'true');
  g.textContent = glyph(trust);

  const t = document.createElement('span');
  t.className = 'trust-text';
  // `owner_status` is the canonical owner-facing phrase for a posture, held in one table in the
  // engine so a tile chip, a finding card, an AI answer and a decision-support section cannot
  // name the same posture four different ways. `badge` is the older per-surface chip text and is
  // still read where an older payload arrives without the canonical field.
  t.textContent = trust ? (trust.owner_status || trust.badge) : 'Cannot be determined';

  el.appendChild(g);
  el.appendChild(t);
  return el;
}

// The one-line owner-facing statement of the posture, used where a badge is too terse.
export function ownerLine(trust) {
  const el = document.createElement('p');
  el.className = 'trust-line ' + toneClass(trust);
  el.textContent = trust ? trust.owner_label : 'Cannot be determined from the available evidence';
  return el;
}
