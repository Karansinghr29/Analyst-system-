/*
 * app.js -- Phase 10. Application shell: routing and view assembly.
 *
 * Holds no business state. The only client-side state is the current route, the selected role,
 * and a conversation_id -- the conversation itself (including any open clarification and any
 * explicit definition selection) lives server-side, so a reload cannot lose a pending ambiguity.
 *
 * Dashboard → chat continuity: any element carrying `data-question` opens the analyst with that
 * question. The dashboard and the chat therefore reach the identical pipeline; there is no
 * second analytics path in the client.
 */

import { renderDashboard } from './views/dashboard.js';
import { renderMetric, renderConflict, renderDataQuality } from './views/metric.js';
import { renderChat } from './views/chat.js';
import { renderAnalytics } from './views/analytics.js';
import { renderPowerBi } from './views/powerbi.js';
import { routeOf } from './filters.js';
import { renderRoles, renderWorkspace, renderReport, renderSystem } from './views/workspace.js';
import { UNAUTHORIZED_EVENT, setToken, hasToken } from './api.js';
import { renderSignIn, signOut } from './views/signin.js';
import { el, errorState } from './render.js';

// Owner-facing navigation. Ordered the way an owner actually reads the business: what is
// happening, then the detail behind it, then the analyst to interrogate it. "Analytics" opens on
// Financial and carries its own section tabs, so the top bar stays short enough to scan.
const ROUTES = [
  ['#/', 'Overview'],
  ['#/analytics/financial', 'Analytics'],
  ['#/bi/executive', 'Power BI'],
  ['#/ask', 'AI Analyst'],
  ['#/data-quality', 'Data Quality'],
  ['#/roles', 'Workspaces'],
  ['#/report', 'Report'],
  ['#/system', 'System'],
];

const ctx = {
  role: 'owner',
  subject: 'owner',
  conversationId: null,
  ask: null,
  openMetric(id) { location.hash = '#/metric/' + encodeURIComponent(id); },
  openConflict(id) { location.hash = '#/conflict/' + encodeURIComponent(id); },
  openWorkspace(id) { location.hash = '#/workspace/' + encodeURIComponent(id); },
};

function buildShell() {
  const shell = el('div', 'shell');

  const header = el('header', 'app-header');
  const brand = el('div', 'brand');
  brand.appendChild(el('span', 'brand-mark', '◆'));
  brand.appendChild(el('span', 'brand-name', 'Analyst System'));
  header.appendChild(brand);

  const nav = el('nav', 'app-nav');
  nav.setAttribute('aria-label', 'Main');
  ROUTES.forEach(function (r) {
    const a = el('a', 'nav-link', r[1]);
    a.href = r[0];
    a.setAttribute('data-route', r[0]);
    nav.appendChild(a);
  });
  header.appendChild(nav);

  const askBox = el('form', 'global-ask');
  const label = el('label', 'sr-only', 'Ask anything about your business');
  label.setAttribute('for', 'global-ask-input');
  const input = el('input', 'global-ask-input');
  input.id = 'global-ask-input';
  input.type = 'search';
  input.placeholder = 'Ask anything about your business…';
  askBox.appendChild(label);
  askBox.appendChild(input);
  askBox.addEventListener('submit', function (e) {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = '';
    askAndShow(q);
  });
  header.appendChild(askBox);

  const out = el('button', 'sign-out', 'Sign out');
  out.type = 'button';
  out.addEventListener('click', function () {
    signOut();
    // `main` is not in scope yet while the header is being built, so it is looked up at click
    // time from the element this same function assigns the id to below.
    const target = document.getElementById('main');
    if (target) route(target);
  });
  header.appendChild(out);

  shell.appendChild(header);

  const main = el('main', 'app-main');
  main.id = 'main';
  main.setAttribute('tabindex', '-1');
  shell.appendChild(main);

  const footer = el('footer', 'app-footer');
  footer.appendChild(el('p', 'footer-note',
    'Every figure comes from the deterministic analytics engine. Where the evidence carries ' +
    'competing definitions, all of them are shown and none is chosen.'));
  shell.appendChild(footer);

  return { shell, main };
}

async function askAndShow(question) {
  if (!location.hash.startsWith('#/ask')) {
    location.hash = '#/ask';
    await new Promise(function (r) { setTimeout(r, 0); });
  }
  if (ctx.ask) {
    ctx.ask(question);
  }
}

function markActive(hash) {
  document.querySelectorAll('.nav-link').forEach(function (a) {
    const route = a.getAttribute('data-route');
    const active = route === hash ||
      (hash.startsWith('#/metric') && route === '#/') ||
      (hash.startsWith('#/conflict') && route === '#/') ||
      (hash.startsWith('#/analytics') && route.startsWith('#/analytics')) ||
      (hash.startsWith('#/bi') && route.startsWith('#/bi')) ||
      (hash === '#/insights' && route.startsWith('#/analytics')) ||
      (hash.startsWith('#/workspace') && route === '#/roles');
    a.classList.toggle('active', active);
    if (active) { a.setAttribute('aria-current', 'page'); }
    else { a.removeAttribute('aria-current'); }
  });
}

async function route(main) {
  const hash = location.hash || '#/';
  markActive(hash);

  try {
    if (hash.startsWith('#/metric/')) {
      return renderMetric(main, decodeURIComponent(hash.slice('#/metric/'.length)), ctx);
    }
    if (hash.startsWith('#/conflict/')) {
      return renderConflict(main, decodeURIComponent(hash.slice('#/conflict/'.length)), ctx);
    }
    if (hash.startsWith('#/workspace/')) {
      return renderWorkspace(main, decodeURIComponent(hash.slice('#/workspace/'.length)), ctx);
    }
    if (hash.startsWith('#/analytics/')) {
      return renderAnalytics(main, decodeURIComponent(hash.slice('#/analytics/'.length)), ctx);
    }
    if (hash === '#/analytics') return renderAnalytics(main, 'financial', ctx);
    if (hash.startsWith('#/bi/')) {
      // The analyst's filter selection travels in the route's query, so the page key is the
      // part before it. Reading the whole tail as the key looked up a page called
      // "financial?period=2026-08" and fell back to Executive on every filtered request.
      const tail = routeOf(hash).slice('#/bi/'.length);
      return renderPowerBi(main, decodeURIComponent(tail), ctx);
    }
    if (routeOf(hash) === '#/bi') return renderPowerBi(main, 'executive', ctx);
    // The standalone insights feed is now the Business Insights analytics section. The old
    // route still resolves so an existing bookmark does not land on the dashboard silently.
    if (hash === '#/insights') return renderAnalytics(main, 'insights', ctx);
    if (hash === '#/data-quality') return renderDataQuality(main, ctx);
    if (hash === '#/ask') return renderChat(main, ctx);
    if (hash === '#/roles') return renderRoles(main, ctx);
    if (hash === '#/report') return renderReport(main, ctx);
    if (hash === '#/system') return renderSystem(main, ctx);
    return renderDashboard(main, ctx);
  } catch (err) {
    // A refused identity is not a failure of the analytics; it is the fail-closed API doing
    // its job. Sending the owner to a generic error page would leave them with no way forward.
    if (err && err.status === 401) {
      return renderSignIn(main, function () { route(main); });
    }
    main.replaceChildren(errorState(err));
  }
}

// Any element carrying data-question opens the analyst with that question. This is what makes
// "click Why? on a card" and "type the question" the same operation.
function wireEntryPoints() {
  document.addEventListener('click', function (event) {
    const btn = event.target.closest('[data-question]');
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    askAndShow(btn.getAttribute('data-question'));
  });
}

/*
 * Ask the service for a session token before deciding the owner needs to paste one.
 *
 * A deployment serving one owner at a private address issues the token itself, so the owner
 * opens the URL and is in. `/session` answers only where that deployment explicitly asked for
 * it; anywhere else it is a 404 and this resolves to nothing, leaving the paste-a-token panel
 * exactly as it was. No secret is involved on this side -- what comes back is the same bearer
 * token the API has always verified.
 */
async function adoptOwnerSession() {
  if (hasToken()) return;
  try {
    const response = await fetch('/session', { headers: { Accept: 'application/json' } });
    if (!response.ok) return;
    const body = await response.json();
    if (body && body.token) setToken(body.token);
  } catch (_) { /* offline, or no such endpoint: the sign-in panel still works */ }
}

export function start(root) {
  const built = buildShell();
  root.replaceChildren(built.shell);
  wireEntryPoints();
  // Deferred by one task on purpose: the view that triggered the refusal renders its own error
  // first, and the sign-in panel must replace it rather than be replaced by it.
  window.addEventListener(UNAUTHORIZED_EVENT, function () {
    setTimeout(function () {
      renderSignIn(built.main, function () { route(built.main); });
    }, 0);
  });
  window.addEventListener('hashchange', function () { route(built.main); });
  // The first route waits for the session attempt, so a deployment that issues its own token
  // never flashes the sign-in panel on the way in.
  adoptOwnerSession().then(function () { route(built.main); });
}

document.addEventListener('DOMContentLoaded', function () {
  start(document.getElementById('app'));
});
