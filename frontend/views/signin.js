/*
 * views/signin.js -- Phase 14. Attaching an identity to the session.
 *
 * The Phase 11 API is fail-closed: with no verifier configured it refuses everything, and with
 * one configured it requires a bearer token on every call. That is the correct posture for an
 * application serving one owner's financial records -- but until now nothing in the client could
 * supply a token, so a correctly-secured deployment rendered as an error page.
 *
 * This screen is deliberately NOT a login form. It creates no account, accepts no password, and
 * performs no authentication of its own: the deployment issues a token out of band, and this
 * panel holds it for the session so the API can verify it. Verification stays entirely
 * server-side, where the secret is.
 *
 * The token lives in sessionStorage, so closing the tab ends the session. It is never written to
 * a URL, where it would land in history and server logs.
 */

import { setToken } from '../api.js';
import { el } from '../render.js';

export function renderSignIn(root, onSignedIn) {
  const page = el('div', 'signin');
  page.setAttribute('data-view', 'signin');

  const card = el('section', 'signin-card');
  card.appendChild(el('p', 'analytics-eyebrow', 'Owner Intelligence'));
  card.appendChild(el('h1', 'signin-title', 'This session needs an access token'));
  card.appendChild(el('p', 'signin-lede',
    'The analytics service refuses every request that carries no verified identity. Paste the ' +
    'access token issued by your deployment to continue. It is held for this browser tab only ' +
    'and is never sent anywhere except to this service.'));

  const form = el('form', 'signin-form');
  const label = el('label', 'signin-label', 'Access token');
  label.setAttribute('for', 'signin-token');
  const input = el('input', 'signin-input');
  input.id = 'signin-token';
  input.type = 'password';
  input.setAttribute('autocomplete', 'off');
  input.setAttribute('spellcheck', 'false');
  input.placeholder = 'Paste your access token';
  const submit = el('button', 'primary', 'Continue');
  submit.type = 'submit';

  form.appendChild(label);
  form.appendChild(input);
  form.appendChild(submit);
  card.appendChild(form);

  const problem = el('p', 'signin-problem');
  problem.setAttribute('role', 'alert');
  problem.hidden = true;
  card.appendChild(problem);

  // How an operator produces one. Shown here rather than buried in a README because the person
  // hitting this screen is the person who needs it, and the alternative is a dead end.
  const help = el('details', 'signin-help');
  help.appendChild(el('summary', null, 'How do I get a token?'));
  help.appendChild(el('p', null,
    'A token is minted on the machine running the service, using the same secret the service ' +
    'was started with. It is not issued by this page, and the secret never reaches the browser.'));
  const pre = el('pre', 'signin-code');
  pre.textContent =
    'python -c "import os; from api.auth import mint_token; ' +
    'print(mint_token(os.environ[\'AI_ANALYTICS_AUTH_SECRET\'], \'owner\'))"';
  help.appendChild(pre);
  card.appendChild(help);

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    const token = input.value.trim();
    if (!token) {
      problem.textContent = 'Enter the access token issued by your deployment.';
      problem.hidden = false;
      return;
    }
    problem.hidden = true;
    setToken(token);
    input.value = '';
    onSignedIn();
  });

  page.appendChild(card);
  root.replaceChildren(page);
  input.focus();
}

export function signOut() {
  setToken('');
}
