/*
 * views/chat.js -- Phase 10 Step 3. The conversational AI Business Analyst.
 *
 * Every answer here comes from `/api/ask`, which runs the identical pipeline the dashboard uses.
 * There is no second analytics path: a typed question and a clicked tile reach the same engine,
 * so the chat and the cockpit cannot disagree.
 *
 * Two things this view must always show, because they are what make an answer trustworthy rather
 * than merely fluent:
 *
 *   1. The evidence chain -- question → interpretation → analyst lens → metric → calculation →
 *      evidence → validation → trust decision → reasoning → recommendation. Collapsed by
 *      default, one click away, never absent.
 *   2. Guard violations -- when the language layer produced something the guard rejected, the
 *      user sees that the deterministic text was substituted. Hiding it would present a
 *      fallback as if it were the model's answer.
 *
 * Conversation continuity is server-side. The client holds only a conversation_id; the
 * clarification lifecycle and any explicit definition selection live in the Phase 9 store, so a
 * reload cannot lose a pending ambiguity.
 */

import { api } from '../api.js';
import { el, loading, errorState } from '../render.js';
import { badge, toneClass } from '../trust.js';
import { biHref, biKeyForAsk, biNavLabel } from '../bi_nav.js';

const SUGGESTIONS = [
  'How is my business doing?',
  'What changed this month?',
  'What should I focus on?',
  'What are my biggest risks?',
  'How much revenue did we make?',
  'How much do tenants owe?',
  'What is our occupancy?',
  'Which numbers should I trust?',
];

/*
 * Follow-ups offered after an answer. Every one of these is a question the pipeline actually
 * supports: the first two resolve against the previous turn through conversation context, and
 * the rest are deterministic workflows that run whether or not the language layer is reachable.
 * Offering a follow-up that cannot be answered would train the owner to distrust the buttons.
 */
const FOLLOW_UPS = [
  'Why?',
  'Explain this.',
  'What changed?',
  'What should I do?',
  'Which area should I look at first?',
];

export function renderChat(root, ctx) {
  const page = el('div', 'chat');

  const head = el('header', 'chat-head');
  head.appendChild(el('p', 'analytics-eyebrow', 'AI Business Analyst'));
  head.appendChild(el('h1', 'dashboard-title', 'Ask about your business'));
  head.appendChild(el('p', 'dashboard-asof',
    'Answers come from the same deterministic engine the dashboard uses.'));
  page.appendChild(head);

  // What this analyst is, stated plainly. It matters because the interface looks like a
  // general-purpose chatbot and is not one: it answers from this business's own records only,
  // and it declines rather than estimating.
  const identity = el('section', 'analyst-identity');
  identity.setAttribute('data-section', 'analyst-identity');
  const traits = el('ul', 'analyst-traits');
  [
    'Answers only from your own records — never from general knowledge.',
    'Every figure is computed by the analytics engine, never written by the language model.',
    'Where your records disagree, it shows every definition rather than picking one.',
    'Where the evidence cannot answer, it says so instead of estimating.',
  ].forEach(function (t) { traits.appendChild(el('li', null, t)); });
  identity.appendChild(traits);
  page.appendChild(identity);

  const thread = el('div', 'chat-thread');
  thread.setAttribute('role', 'log');
  thread.setAttribute('aria-live', 'polite');
  thread.setAttribute('aria-label', 'Conversation');
  const welcome = el('div', 'chat-welcome');
  welcome.setAttribute('data-state', 'empty');
  welcome.appendChild(el('p', null,
    'Ask a question below, or start with one of the suggestions.'));
  thread.appendChild(welcome);
  page.appendChild(thread);

  // -- suggestions ---------------------------------------------------------------------------
  const asks = el('nav', 'quick-asks');
  asks.setAttribute('aria-label', 'Suggested questions');
  SUGGESTIONS.forEach(function (q) {
    const b = el('button', 'quick-ask entry-point', q);
    b.setAttribute('data-action', 'ask');
    b.setAttribute('data-question', q);
    asks.appendChild(b);
  });
  page.appendChild(asks);

  // -- input ----------------------------------------------------------------------------------
  const form = el('form', 'chat-form');
  const label = el('label', 'sr-only', 'Ask anything about your business');
  label.setAttribute('for', 'chat-input');
  const input = el('input', 'chat-input');
  input.id = 'chat-input';
  input.type = 'text';
  input.placeholder = 'Ask anything about your business…';
  input.setAttribute('autocomplete', 'off');
  const send = el('button', 'primary', 'Ask');
  send.type = 'submit';
  form.appendChild(label);
  form.appendChild(input);
  form.appendChild(send);
  page.appendChild(form);

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    ask(q);
  });

  async function ask(question) {
    if (welcome.parentNode) welcome.remove();
    thread.appendChild(userBubble(question));
    const pending = loading('an answer');
    thread.appendChild(pending);
    thread.scrollTop = thread.scrollHeight;
    send.disabled = true;

    let result;
    try {
      result = await api.ask(question, ctx.conversationId, ctx.role, ctx.subject);
    } catch (err) {
      pending.replaceWith(errorState(err));
      send.disabled = false;
      return;
    } finally {
      send.disabled = false;
    }
    ctx.conversationId = result.conversation_id;
    const panel = answerPanel(result, ctx);
    pending.replaceWith(panel);
    panel.appendChild(followUpBar());
    thread.scrollTop = thread.scrollHeight;
  }

  /* A metric card action: answered for the metric id the card carries, shown in the same panel
   * as any other answer. Nothing about the free-text path changes. */
  async function askMetric(metricId, action, question) {
    if (welcome.parentNode) welcome.remove();
    thread.appendChild(userBubble(question));
    const pending = loading('an answer');
    thread.appendChild(pending);
    thread.scrollTop = thread.scrollHeight;

    let result;
    try {
      result = await api.metricAction(metricId, action, question);
    } catch (err) {
      pending.replaceWith(errorState(err));
      return;
    }
    pending.replaceWith(answerPanel(result, ctx));
    thread.scrollTop = thread.scrollHeight;
  }

  ctx.ask = ask;
  ctx.askMetric = askMetric;
  root.replaceChildren(page);
}

/*
 * The follow-up bar. These reuse the global `data-question` entry point, so a clicked follow-up
 * travels the identical path as a typed one and inherits the same conversation.
 */
function followUpBar() {
  const bar = el('nav', 'follow-ups');
  bar.setAttribute('aria-label', 'Follow-up questions');
  bar.appendChild(el('span', 'follow-ups-label', 'Ask next'));
  FOLLOW_UPS.forEach(function (q) {
    const b = el('button', 'follow-up entry-point', q);
    b.setAttribute('data-action', 'follow-up');
    b.setAttribute('data-question', q);
    bar.appendChild(b);
  });
  return bar;
}

function userBubble(question) {
  const b = el('div', 'bubble bubble-user');
  b.setAttribute('data-role', 'question');
  b.appendChild(el('p', null, question));
  return b;
}

/*
 * The answer panel. Nine parts, per ai_chat_experience_spec.md 2 -- the caveat and the evidence
 * chain are not optional extras, they are what distinguishes an answer from an assertion.
 */
export function answerPanel(result, ctx) {
  const panel = el('article', 'bubble bubble-answer ' + toneClass(result.trust));
  panel.setAttribute('data-role', 'answer');
  panel.setAttribute('data-trust', result.trust_level || 'WORKFLOW');
  panel.setAttribute('data-headline-permitted', String(!!result.headline_permitted));
  panel.setAttribute('data-status', result.status || '');

  const head = el('header', 'answer-head');
  if (result.trust) head.appendChild(badge(result.trust));
  if (result.analyst_lenses && result.analyst_lenses.length) {
    head.appendChild(el('span', 'answer-lens-chip',
      result.analyst_lenses.join(', ').replace(/_/g, ' ')));
  }
  panel.appendChild(head);

  // The language layer was unreachable or its wording was rejected. The owner is told, because
  // a deterministic fallback presented silently reads as the analyst's own considered phrasing.
  if (result.llm_fallback) {
    const note = el('p', 'answer-fallback');
    note.setAttribute('data-role', 'llm-fallback');
    note.textContent =
      'The wording layer did not contribute to this answer. The figures and the posture below ' +
      'are unaffected — they are computed by the analytics engine, not written by the model.';
    panel.appendChild(note);
  }

  // The answer text is owner-facing business English. Internal identifiers stay in the
  // evidence chain, not in this body. Newlines are preserved so the briefing sections remain
  // readable; the client does not reformat the engine's wording.
  const body = el('div', 'answer-text');
  body.setAttribute('data-role', 'answer-text');
  body.textContent = result.answer;
  panel.appendChild(body);

  const biNav = el('nav', 'bi-cross-nav');
  biNav.setAttribute('data-role', 'bi-navigation');
  const biKey = biKeyForAsk(result);
  const bi = el('a', 'bi-link', biNavLabel(biKey));
  bi.href = biHref(biKey);
  bi.setAttribute('data-bi-target', biKey);
  biNav.appendChild(bi);
  panel.appendChild(biNav);


  if (result.limitations && result.limitations.length) {
    const lim = el('section', 'answer-limitations');
    lim.setAttribute('data-role', 'limitations');
    lim.appendChild(el('h3', null, 'Limitations'));
    const ul = el('ul', null);
    result.limitations.forEach(function (l) { ul.appendChild(el('li', null, l)); });
    lim.appendChild(ul);
    panel.appendChild(lim);
  }

  // Guard violations are surfaced, not hidden. If the language layer produced something the
  // guard rejected, the user is told the deterministic text was used instead -- presenting the
  // fallback silently would misrepresent whose words these are.
  if (result.guard_violations && result.guard_violations.length) {
    const g = el('section', 'answer-guard');
    g.setAttribute('data-role', 'guard-violations');
    g.appendChild(el('h3', null, 'The wording layer was overridden'));
    g.appendChild(el('p', null,
      'The language model produced a restatement that failed verification, so the ' +
      'deterministic answer above was shown instead.'));
    const ul = el('ul', null);
    result.guard_violations.forEach(function (v) { ul.appendChild(el('li', null, v)); });
    g.appendChild(ul);
    panel.appendChild(g);
  }

  /*
   * "Why are you saying this?" -- the OWNER's reason, not the audit record.
   *
   * This used to render `evidence_chain` directly. That chain is the audit trail and is
   * correct as it stands: it names measure IDs, source objects, specification sections and
   * engine modules, because an auditor needs to retrace exactly what ran. Shown to a business
   * owner it answers a question they did not ask, in a vocabulary that is not theirs.
   *
   * `owner_explanation` is a projection of that same chain, produced server-side and keyed on
   * the trust posture. The chain itself still travels in the payload for developer and audit
   * tooling; it is simply not what this panel shows.
   */
  const why = result.owner_explanation;
  if (why && why.paragraphs && why.paragraphs.length) {
    const details = el('details', 'evidence-chain');
    details.setAttribute('data-role', 'owner-explanation');
    details.appendChild(el('summary', null, 'Why are you saying this?'));
    const body = el('div', 'owner-why');
    if (why.heading) body.appendChild(el('h4', 'owner-why-heading', why.heading));
    why.paragraphs.forEach(function (p) {
      body.appendChild(el('p', 'owner-why-text', p));
    });
    details.appendChild(body);
    panel.appendChild(details);
  }

  return panel;
}
