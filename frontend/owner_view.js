/*
 * owner_view.js -- the Owner Overview presentation projection.
 *
 * The API payload is a diagnostic object: it carries the registry's own display strings, the
 * conflict and data-quality record ids, the evidence list, and the policy text that tells the
 * SYSTEM how to handle a measure. All of that is correct, and none of it is written for an
 * owner. Rendering it directly is what put "Tenant dues -- Def A: v_outstanding_receivables
 * (reversals excluded)" and "Conflicts: C.002" on the Overview.
 *
 * This module is a pure projection over that payload. It:
 *
 *   * computes nothing -- every figure it returns is a string the engine already formatted;
 *   * decides no trust posture -- it reads `headline_permitted`, `definitions` and the trust
 *     payload the gate already produced, and branches on nothing else;
 *   * drops no disclosure -- a conflicted measure still shows every competing definition when
 *     the gate permits figures, and a caveat still travels beside its number.
 *
 * What it removes is only the vocabulary: record identifiers, database object names,
 * specification filenames, and instructions addressed to the engine. Those remain in the
 * payload for the metric detail view and the evidence chain, which is where they belong.
 */

const UNAVAILABLE = 'Not determinable from exported evidence.';

/* --- internal vocabulary that must not reach the Overview --------------------------------- */

const INTERNAL_TOKENS = [
  /\bM\.[A-Z]{2,12}\.\d{3}[A-Za-z]?\b/g,        // metric records
  /\b(?:DQ|C|FN|H|D)\.\d{3}[A-Za-z]?\b/g,       // data-quality, conflict, finding records
  /\bINS\.[A-Z0-9._-]+\b/g,                     // insight records
  /\b[\w.-]+\.(?:md|csv|py|json)\b/gi,          // specification filenames
  /\b(?:v_|vw_)[a-z0-9_]+\b/gi,                 // database views
  /\bget_universal[a-z0-9_]*\b/gi,              // database functions
  /\bget_[a-z0-9_]{3,}\b/gi,
  /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\.[a-z][a-z0-9_]*\b/g,   // table.column references
];

// Policy text addressed to the engine, not to the owner. The behaviour it mandates is already
// carried out -- a blocked measure shows no figure -- so restating the instruction adds nothing
// and reads as the machine talking to itself.
const DIRECTIVE_MARKERS = [
  'present every definition',
  'present all definitions',
  'never silently pick',
  'do not state a single',
  'must not state',
  'never pick a winner',
  'do not pick',
  'required_disclosure',
  'routing',
  'status=measured',
  'ai_handling',
  'answer, but state the known limitation',
  'state the known limitation',
];

/*
 * Definition labels written in implementation vocabulary. Each names a real, distinct
 * definition, so none may be dropped -- but "V1, bed.status=Live" tells an owner nothing about
 * how it differs from the one above it, and "NOT COMPUTED IN PHASE 1" is a note to the people
 * building the system. The distinction each label draws is restated in business terms.
 */
const IMPLEMENTATION_LABELS = [
  [/not computed in phase\s*\d*/i, 'Not currently available from the exported evidence'],
  [/v1.*bed\.status\s*=\s*live/i, 'Active-bed definition'],
  [/bed\.status\s*=\s*live/i, 'Active-bed definition'],
  // Owner rent and profit are each defined three ways, and what separates them is how owner
  // rent is treated. The engine names that in its own terms -- "EXCLUDED entirely",
  // "owner-rent-inclusive", a ledger account pattern -- and each of those is a real, distinct
  // definition that must keep its own row. What the owner needs is the distinction itself,
  // which is what these say. They come first because the generic rules below would collapse
  // three different definitions into one repeated label.
  [/get_universal_metrics[^)]*excluded/i, 'Application definition, owner rent left out'],
  [/get_universal_metrics[^)]*inclusive/i, 'Application definition, owner rent counted'],
  [/get_universal_metrics[^)]*substituted/i, 'Application definition, owner rent substituted'],
  [/ledger raw[^)]*bucket/i, 'Ledger definition, from the owner-rent account'],
  [/get_universal_metrics(?:\s*v?\d)?/i, 'Application definition'],
  [/tenant_transactions/i, 'Legacy ledger definition'],
  [/\bledger\b/i, 'Ledger definition'],
  [/^(?:def\s+[a-z0-9]+\s*[(:]\s*)?v1(?![a-z0-9])/i, 'Application definition'],
  // Occupancy's definitions differ over who counts as resident and which beds count as
  // available. "Staying+On-Notice, Live+Live" states that in the engine's shorthand; the owner
  // needs the distinction itself, which is what each of these says.
  [/staying\s*\+\s*on-?notice.*all beds/i, 'Residents and those on notice, all beds'],
  [/staying\s*\+\s*on-?notice/i, 'Residents and those on notice, active beds'],
  [/staying only/i, 'Residents only, active beds'],
  [/day-?weighted/i, 'Day-weighted over time'],
];

const POSTURE_PREFIX =
  /^\s*(?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\s*:\s*/i;

// The same posture, written as a clause inside an engine sentence rather than as a prefix:
// "This metric's trust level is NOT_DETERMINABLE: ...". The badge beside the text already says
// this in the owner's words, so the clause is removed and the reason that follows it kept.
const POSTURE_CLAUSE =
  /\bThis metric's trust level is (?:SAFE|DISCLOSE|SHOW_BOTH|BLOCK|NOT_DETERMINABLE)\s*:\s*/gi;

const SEE_SPEC = /\bsee\b[^.;]*/gi;

const COMPOSITE_LABELS = {
  total: 'Total',
  'total amount': 'Total',
  deposit_collections: 'Deposits',
  deposits: 'Deposits',
  deposit: 'Deposits',
  non_deposit: 'Rent and other',
  'non deposit': 'Rent and other',
  rent_and_other: 'Rent and other',
  // Field names an owner would never use for the thing they name. Humanising the key generically
  // turns "ar_balance" into "Ar balance", which is not English either.
  'ar balance': 'Outstanding',
  'deposit held': 'Held as deposits',
  'booking advance': 'Booking advances',
  unclipped: 'As recorded',
  'floored at zero': 'With negatives treated as zero',
  'total bill amount': 'Billed',
  'total units consumed': 'Units consumed',
  'total tenant eb charge': 'Charged to tenants',
  'path a total': 'First recorded path',
  'path b total': 'Second recorded path',
  'row count': 'Records',
  'allotment count': 'Allotments affected',
  'amount at risk': 'Amount involved',
  'duplicate groups': 'Allotment-months with more than one invoice',
  'excess rows': 'Additional invoices in those groups',
  'legacy amount': 'Source system',
  'je net amount': 'Ledger',
  diff: 'Difference',
  'unposted source amount': 'Recorded but never posted',
  verdict: 'Assessment',
  occupied: 'Occupied beds',
  'occupancy pct': 'Occupancy',
};

/*
 * Strip internal vocabulary from a string meant for the owner.
 *
 * Removal only. Nothing is added, no claim is softened, and no number is touched.
 */
export function ownerText(text) {
  let out = String(text === undefined || text === null ? '' : text);
  out = out.replace(POSTURE_PREFIX, '');
  out = out.replace(POSTURE_CLAUSE, '');
  // Mid-sentence registry definition tags: "Tenant dues -- Def A: (reversals excluded)".
  out = out.replace(/\s*(?:--|—)\s*Def\s+[A-Za-z0-9]+\s*[:.]?\s*/gi, ' — ');
  out = out.replace(/\bDef\s+[A-Za-z0-9]+\s*[:.]?\s*/gi, '');
  INTERNAL_TOKENS.forEach(function (pattern) { out = out.replace(pattern, ''); });

  out = out.replace(/\(\s*[,;]\s*/g, '(');
  out = out.replace(/\s*[,;]\s*\)/g, ')');
  out = out.replace(/\(\s*[,;\s]*\)/g, '');
  out = out.replace(/\s+([,.;:])/g, '$1');
  out = out.replace(/([,;])\s*[,;]+/g, '$1');
  out = out.replace(/\s*(?:--|—)\s*(?:--|—)+/g, ' — ');
  out = out.replace(/\s{2,}/g, ' ');
  out = out.replace(/^[\s,;:—–-]+/, '');
  out = out.replace(/[\s,;:—–-]+$/, '');
  return out.trim();
}

/*
 * Drop sentences that instruct the engine rather than inform the owner. A sentence that states
 * a fact or a limitation is always kept -- that is what a caveat is for.
 */
export function ownerProse(text) {
  const sentences = String(text || '').split(/(?<=[.;])\s+/);
  const kept = sentences.filter(function (sentence) {
    const low = sentence.toLowerCase();
    if (!sentence.trim()) return false;
    if (DIRECTIVE_MARKERS.some(function (m) { return low.includes(m); })) return false;
    if (/^\s*see\b/i.test(sentence.trim())) return false;
    return true;
  });
  return ownerText(kept.join(' ').replace(SEE_SPEC, ' '));
}

/* --- titles and definition labels ----------------------------------------------------------- */

/*
 * The owner-facing name of a measure.
 *
 * Some family members are registered as the family name plus that member's own definition
 * ("Tenant dues -- Def A: ..."). On a tile heading that reads as one definition standing in for
 * the whole measure, so the family name alone is used and the definitions are listed below it.
 */
export function ownerTitle(title) {
  let text = String(title || '').trim();
  const marker = text.search(/\s+(?:--|—)\s+Def\b/i);
  if (marker !== -1) text = text.slice(0, marker);
  // "(3 definitions)", "(ledger bucket, 3 definitions)" and "(2 paths)" describe how the measure
  // is stored, not what it is. The definitions themselves are listed underneath either way.
  text = text.replace(/\s*\([^()]*\d+\+?\s*(?:definitions?|paths?)\)/i, '');
  text = text.replace(/\s*\(\d+\+?\s*definitions?\)/i, '');
  text = text.replace(/\s*\((?:total,\s*)?ledger-derived\)/i, '');
  text = text.replace(/\s*\(application-level\)/i, '');
  text = text.replace(/\s*\(source total\)/i, '');
  text = ownerText(text);
  if (/^tenant dues$/i.test(text)) return 'Tenant dues outstanding';
  if (/^gross\/net profit$/i.test(text)) return 'Profit';
  if (/^current occupancy$/i.test(text)) return 'Occupancy';
  // The detector's name states a conclusion its own rule does not reach: it finds repeated
  // invoices in an allotment-month, which a proration or a room change produces just as
  // readily as a double-billing. The heading says what was found; the finding's own text says
  // what the evidence does and does not establish about it.
  if (/^duplicate invoices$/i.test(text)) return 'Repeated invoice groups';
  return text || ownerText(title);
}

/*
 * One competing definition, named in plain language.
 *
 * "Def A" is a registry label, not something an owner can act on; what distinguishes the
 * definitions is the description beside it ("reversals excluded"). That description becomes the
 * label. Uniqueness is enforced afterwards, because two definitions that read alike would
 * collapse a conflict disclosure into an apparent duplicate.
 */
export function ownerDefinitionLabel(label) {
  let text = String(label || '').trim();
  for (let i = 0; i < IMPLEMENTATION_LABELS.length; i += 1) {
    if (IMPLEMENTATION_LABELS[i][0].test(text)) return IMPLEMENTATION_LABELS[i][1];
  }
  const marker = text.search(/\s+(?:--|—)\s+/);
  if (marker !== -1) text = text.slice(marker).replace(/^\s*(?:--|—)\s*/, '');
  text = text.replace(/^\s*Def\s+[A-Za-z0-9]+\s*[:.]?\s*/i, '');
  text = ownerText(text);
  text = text.replace(/^\(\s*/, '').replace(/\s*\)$/, '');
  if (text) return text.charAt(0).toUpperCase() + text.slice(1);
  return '';
}

export function ownerDefinitionLabels(definitions) {
  const used = Object.create(null);
  return (definitions || []).map(function (definition, index) {
    let label = ownerDefinitionLabel(definitionLabel(definition));
    if (!label || used[label.toLowerCase()]) {
      label = 'Definition ' + String(index + 1);
    }
    used[label.toLowerCase()] = true;
    return label;
  });
}

/* --- values ---------------------------------------------------------------------------------- */

function definitionLabel(definition) {
  if (!definition) return '';
  if (Array.isArray(definition)) return definition[0] || '';
  return definition.label || '';
}

function definitionDisplay(definition) {
  if (!definition) return '';
  if (Array.isArray(definition)) return definition[2] || '';
  return definition.display_value || '';
}

// Verdict tokens the reconciliation figure carries. They are the engine's own words for the
// outcome of a comparison; an owner reads the outcome, not the token.
const PART_VALUES = {
  PERFECT: 'Matches',
  INVESTIGATE: 'Needs investigation',
  MISMATCH: 'Does not match',
  UNKNOWN: 'Not established',
  // The comparison balances once the records that were never posted are taken into account.
  // That is a different finding from "needs investigation", and it must not read as one.
  EXPLAINED_UNPOSTED: 'Matches, apart from records never posted',
};

function friendlyPartValue(raw) {
  const key = String(raw === undefined || raw === null ? '' : raw).trim();
  return PART_VALUES[key.toUpperCase()] || key;
}

function friendlyPartLabel(raw) {
  const key = String(raw || '').trim().toLowerCase().replace(/_/g, ' ');
  if (COMPOSITE_LABELS[key]) return COMPOSITE_LABELS[key];
  if (COMPOSITE_LABELS[String(raw || '').trim().toLowerCase()]) {
    return COMPOSITE_LABELS[String(raw || '').trim().toLowerCase()];
  }
  const spaced = String(raw || '').trim().replace(/_/g, ' ');
  if (!spaced) return '';
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/*
 * A composite figure, split for reading.
 *
 * The engine formats a multi-part measure as "total: X; deposits: Y; non deposit: Z". That is a
 * rendering of one already-computed value, so splitting it back apart is presentation and not
 * arithmetic: the parts are shown exactly as the engine wrote them, and none is summed,
 * compared, or dropped.
 */
export function splitComposite(displayValue) {
  const text = String(displayValue || '').trim();
  if (!text || !text.includes(':')) return { main: text, secondary: [] };

  // A composite can be nested: the reconciliation figure arrives as
  // "deposit_settlements: legacy_amount: X; je_net_amount: Y; ...; expenses: legacy_amount: ..."
  // -- groups of rows, flattened into one string. A part whose VALUE still contains a
  // "key: value" pair is the start of a new group, and its own label names that group.
  const parts = [];
  let group = '';
  text.split(';').forEach(function (chunk) {
    const piece = chunk.trim();
    if (!piece) return;
    const at = piece.indexOf(':');
    if (at === -1) { parts.push({ label: '', value: piece, group: group }); return; }
    let label = piece.slice(0, at).trim();
    let value = piece.slice(at + 1).trim();
    const nested = value.indexOf(':');
    if (nested !== -1) {
      group = label;
      label = value.slice(0, nested).trim();
      value = value.slice(nested + 1).trim();
    }
    parts.push({ label: label, value: value, group: group });
  });

  if (parts.length === 0) return { main: text, secondary: [] };
  if (parts.length === 1 && !parts[0].label) return { main: parts[0].value, secondary: [] };

  // Which part, if any, speaks for the whole. A rate summarises a composite; a denominator
  // does not, so "occupancy_pct" outranks "total" -- otherwise an occupancy tile headlined the
  // bed count and read as though 195 beds were occupied.
  const rateOf = function (label) { return /(?:^|\s)(pct|percent|percentage|rate|ratio)(?:\s|$)/.test(label); };
  const totalOf = function (label) { return label === 'total' || label === 'total amount'; };

  // Which part speaks for the whole is decided BEFORE any is promoted: the parts arrive in the
  // engine's order, and the denominator precedes the rate that summarises it. Promoting the
  // first eligible part headlined the occupancy tile with 195, its bed count.
  const norm = function (part) { return part.label.toLowerCase().replace(/_/g, ' '); };
  let headline = parts.find(function (part) { return rateOf(norm(part)); });
  if (!headline) headline = parts.find(function (part) { return totalOf(norm(part)); });

  let main = '';
  const secondary = [];
  parts.forEach(function (part) {
    if (part === headline) {
      main = (rateOf(norm(part)) && !/%\s*$/.test(part.value))
        ? part.value + '%'
        : part.value;
      return;
    }
    secondary.push({
      label: (part.group ? friendlyPartLabel(part.group) + ' — ' : '')
        + friendlyPartLabel(part.label),
      value: friendlyPartValue(part.value),
    });
  });

  // Promoting a part would assert a relationship the payload does not state, so none is
  // promoted -- but keeping the engine's raw string instead put "ar_balance: X; deposit_held:
  // Y" on the tile, which is the shape this function exists to prevent. The parts are returned
  // named, with no headline above them.
  return { main: main, secondary: secondary };
}

function trustLevel(tile) {
  return (tile && tile.trust && tile.trust.trust_level) || '';
}

function ownerCaveat(tile) {
  // The engine's own owner-facing caveat, where the payload carries one. It applies the same
  // test this function used to apply alone, in the one place both this frontend and the
  // Streamlit application can read it -- so a measure's limitation is worded once.
  if (tile && tile.owner_caveat) return tile.owner_caveat;
  const cleaned = ownerProse(tile && tile.caveat);
  if (cleaned) return cleaned;
  // Policy-only caveats leave nothing after cleaning. Fall back to the gate's owner sentence,
  // which is already business language and carries no registry ids.
  if (tile && tile.headline_permitted && tile.trust && tile.trust.owner_explanation) {
    return ownerProse(tile.trust.owner_explanation);
  }
  return '';
}

/* --- the projection ---------------------------------------------------------------------------- */

/*
 * Project one tile payload onto what the Overview shows.
 *
 * Returns { title, value, secondary, definitions, badge, caveat, unavailable, actions }.
 *
 * `value` is present ONLY when the payload permits a headline. The trust decision is the gate's
 * and is read, never recomputed: this function branches on `headline_permitted` and on whether
 * definitions were supplied, and on nothing else for posture.
 */
export function ownerView(tile) {
  const source = tile || {};
  const level = trustLevel(source);
  const view = {
    // The engine's own business name for the measure, from the semantic contract on the tile.
    // `ownerTitle` re-derived one here from the registry display name, which made this file a
    // second authority on what a measure is called -- the same rules in two languages, free to
    // drift apart. It stays as the fallback for a payload that predates the contract.
    title: source.business_name || ownerTitle(source.title),
    value: '',
    secondary: [],
    definitions: [],
    badge: source.trust || null,
    caveat: '',
    unavailable: '',
    actions: source.ai_entry_points || [],
  };

  // Overview: a blocked measure shows the unavailable statement and no figure at all — even
  // competing definition values stay off this surface. They remain on the metric detail view.
  if (level === 'BLOCK') {
    view.unavailable = UNAVAILABLE;
    view.caveat = '';
    return view;
  }

  if (source.headline_permitted) {
    const split = splitComposite(source.display_value);
    view.value = split.main;
    view.secondary = split.secondary;
    view.caveat = ownerCaveat(source);
    return view;
  }

  const definitions = source.definitions || [];
  if (definitions.length > 0) {
    const labels = ownerDefinitionLabels(definitions);
    view.definitions = definitions.map(function (definition, index) {
      const split = splitComposite(definitionDisplay(definition));
      return {
        label: labels[index],
        value: split.main,
        secondary: split.secondary,
      };
    });
    view.caveat = '';
    return view;
  }

  // Nothing can be stated. Prefer the engine's own sentence when it is already the required
  // phrase; otherwise use that phrase so Overview never invents a zero.
  const reason = ownerText(source.unavailable_reason);
  view.unavailable = reason || UNAVAILABLE;
  return view;
}

/*
 * Project one insight onto a short finding and the action it implies.
 *
 * The rationale, the evidence list and the specification references stay in the payload for the
 * detail view; what the Overview shows is the finding in the owner's own language.
 */
export function ownerInsight(insight) {
  const source = insight || {};
  return {
    // What the item ASKS FOR, which is what the owner needs from a heading. The topical label
    // beside it is the feed's subject grouping and reads wrongly here: a validated fall in
    // collections is a movement, and its topical label -- "Attention Required" -- said the
    // opposite of the category that put it in the movements block. Direction words never claim
    // the movement is good or bad.
    category: source.action_category_label || source.category_label || '',
    badge: source.trust || null,
    finding: ownerProse(source.what_happened),
    why: ownerProse(source.why_it_matters),
    action: ownerProse(source.recommended_action),
    actions: source.ai_entry_points || [],
    guidance: ownerGuidance(source.guidance),
  };
}

/*
 * The five-part guidance on an item that asks something of the owner: what is happening, why it
 * is flagged, what to do, the decision needed (absent where none is), and how the figures are
 * treated until it is resolved. Scrubbed like any other owner text; null when the item has none.
 */
export const GUIDANCE_PARTS = [
  ['what', 'What is happening'],
  ['why', 'Why this is flagged'],
  ['do', 'What you should do'],
  ['decision', 'Decision needed'],
  ['until', 'Until resolved'],
];

export function ownerGuidance(guidance) {
  if (!guidance || !guidance.what) return null;
  const out = {};
  GUIDANCE_PARTS.forEach(function (part) {
    const text = ownerProse(guidance[part[0]]);
    if (text) out[part[0]] = text;
  });
  return out;
}

/*
 * Decision-queue and recommended-action copy, scrubbed the same way as insight text.
 */
export function ownerDecision(item) {
  const source = item || {};
  return {
    // The business issue this card is about. Grouped rows carry one; a row that was not
    // grouped does not, and renders exactly as it always did.
    title: ownerText(source.title),
    posture: ownerProse(source.owner_facing),
    decision: ownerProse(source.decision),
  };
}

export function ownerAction(item) {
  const source = item || {};
  return {
    recommendation: ownerProse(source.recommendation),
    confidence: ownerText(source.confidence),
    guidance: ownerGuidance(source.guidance),
  };
}

/**
 * Serialize an Overview projection to plain text for regression checks.
 * Technical tokens must not appear in this string.
 */
export function overviewOwnerText(tile) {
  const view = ownerView(tile);
  const parts = [view.title, view.value, view.caveat, view.unavailable];
  (view.secondary || []).forEach(function (p) {
    parts.push(p.label, p.value);
  });
  (view.definitions || []).forEach(function (d) {
    parts.push(d.label, d.value);
  });
  return parts.filter(Boolean).join('\n');
}
