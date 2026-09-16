/*
 * api.js -- Phase 10. The ONLY module in the application that performs I/O.
 *
 * Phase 10 constraint: "Use the Phase 9 API as the only application data/analytics boundary."
 *
 * Concentrating every fetch here makes that a one-file property instead of a discipline spread
 * across the codebase: the anti-drift validator asserts that no other frontend module contains
 * the string `fetch(`. A future edit that reached for data elsewhere fails the check.
 *
 * This module also performs NO transformation. It returns exactly what the API returned. Values
 * arrive pre-computed and pre-formatted from the engine; anything this file did to them would be
 * a calculation performed outside the engine.
 */

const BASE = '';
let _token = '';

try {
  if (typeof sessionStorage !== 'undefined') {
    _token = sessionStorage.getItem('aa_token') || '';
  }
} catch (_) { /* storage may be unavailable */ }

export function setToken(token) {
  _token = token || '';
  try {
    if (typeof sessionStorage !== 'undefined') {
      if (_token) sessionStorage.setItem('aa_token', _token);
      else sessionStorage.removeItem('aa_token');
    }
  } catch (_) { /* ignore */ }
}

/*
 * A refused identity is announced once, here, rather than handled at each of the callers'
 * error paths. Views render their own errors, so without this a 401 would surface as a generic
 * failure message with no way for the owner to supply a token.
 */
const UNAUTHORIZED_EVENT = 'aa:unauthorized';

function announceUnauthorized(status) {
  if (status !== 401) return;
  try {
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
  } catch (_) { /* no window: nothing to announce to */ }
}

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function authHeaders() {
  const headers = {};
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  return headers;
}

async function get(path) {
  const headers = authHeaders();
  let response;
  try {
    response = await fetch(BASE + path, { headers });
  } catch (networkError) {
    throw new ApiError('The analytics service could not be reached.', 0, String(networkError));
  }
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail || ''; } catch (_) { /* body not JSON */ }
    announceUnauthorized(response.status);
    throw new ApiError('The analytics service refused the request.', response.status, detail);
  }
  return response.json();
}

async function post(path, body) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, authHeaders());
  let response;
  try {
    response = await fetch(BASE + path, {
      method: 'POST', headers, body: JSON.stringify(body),
    });
  } catch (networkError) {
    throw new ApiError('The analytics service could not be reached.', 0, String(networkError));
  }
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail || ''; } catch (_) { /* body not JSON */ }
    announceUnauthorized(response.status);
    throw new ApiError('The analytics service refused the request.', response.status, detail);
  }
  return response.json();
}

function queryOf(filters) {
  const pairs = [];
  ['period', 'compare', 'apartment'].forEach(function (key) {
    const value = filters && filters[key] ? String(filters[key]).trim() : '';
    if (value) pairs.push(key + '=' + encodeURIComponent(value));
  });
  return pairs.length ? '?' + pairs.join('&') : '';
}

export const api = {
  health:          ()               => get('/health'),
  trust:           ()               => get('/api/trust'),
  ownerHome:       ()               => get('/api/owner/home'),
  analytics:       ()               => get('/api/analytics'),
  // `filters` is the analyst's selection, sent to the server as request parameters. Nothing is
  // filtered here: the browser asks a narrower question and renders whatever the engine answers.
  analyticsSection:(key, filters)   => get('/api/analytics/' + encodeURIComponent(key)
                                           + queryOf(filters)),
  analyticsExport: (key, filters)   => get('/api/analytics/' + encodeURIComponent(key)
                                           + '/export' + queryOf(filters)),
  decisions:       ()               => get('/api/decisions'),
  recordDecision:  (itemKey, status, note) =>
                                       post('/api/decisions',
                                            { item_key: itemKey, status: status,
                                              note: note || '' }),
  metrics:         ()               => get('/api/metrics'),
  metricDetail:    (id)             => get('/api/metrics/' + encodeURIComponent(id)),
  conflict:        (id)             => get('/api/metrics/' + encodeURIComponent(id) + '/conflict'),
  insights:        ()               => get('/api/insights'),
  changes:         ()               => get('/api/changes'),
  dataQuality:     ()               => get('/api/data-quality'),
  roles:           ()               => get('/api/roles'),
  workspace:       (roleId)         => get('/api/roles/' + encodeURIComponent(roleId) + '/workspace'),
  executiveReport: ()               => get('/api/report/executive'),
  llmAdapters:     ()               => get('/api/llm/adapters'),
  conversation:    (id)             => get('/api/conversations/' + encodeURIComponent(id)),
  ask:             (question, conversationId) =>
                      post('/api/ask', { question, conversation_id: conversationId || null }),
  // A metric card action. The metric id identifies the measure; the question is carried only so
  // the answer can be shown beside the sentence the owner clicked.
  metricAction:    (metricId, action, question) =>
                      get('/api/metrics/' + encodeURIComponent(metricId) + '/action?action='
                          + encodeURIComponent(action) + '&question='
                          + encodeURIComponent(question || '')),
  // The background narrative for a card answer that is already on screen.
  metricNarrative: (metricId, action, question) =>
                      get('/api/metrics/' + encodeURIComponent(metricId) + '/narrative?action='
                          + encodeURIComponent(action) + '&question='
                          + encodeURIComponent(question || '')),
};

/* Whether this session already carries an identity. Reports only presence, never the token. */
export function hasToken() {
  return Boolean(_token);
}

export { ApiError, UNAUTHORIZED_EVENT };
