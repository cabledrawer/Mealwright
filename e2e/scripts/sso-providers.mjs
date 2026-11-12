// Single sign-on against real sign-in servers (0.9 O1), by hand, not part of ./check:
//
//   node scripts/sso-providers.mjs
//
// Starts Dex and Keycloak in their dev modes in throwaway Docker containers on a network of their
// own, starts one Mealwright server on 127.0.0.1 with an empty data folder, and signs in through
// each sign-in server the way a browser would (following its redirects and filling in its sign-in
// form), then posts what comes back to /api/v1/sso/finish. It prints one line per check and exits
// 1 if any failed.
//
// The containers are published on this computer's own network address (not localhost, which
// Mealwright never connects to), on two ports next to Mealwright's, for the few minutes the run
// takes. Mealwright may use that address only because the script adds it to Privacy › Your own
// network (as someone with a sign-in server at home would). Every request Mealwright makes to
// them goes through its outbound gate.
//
// It removes only what it started: the containers and the network named with its prefix, and
// its own data folder. Settings, all optional:
//   SSO_TEST_PREFIX    name prefix for the containers and network (default "mw-sso-test-")
//   SSO_TEST_HOST      this computer's own network address (default: the first that
//                      `hostname -I` lists)
//   SSO_TEST_PORT      Mealwright's port on 127.0.0.1 (default 19610); Dex and Keycloak get the
//                      next two
//   SSO_TEST_DEX       the Dex image (default below)
//   SSO_TEST_KEYCLOAK  the Keycloak image (default below)
import { spawn, spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { chmodSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PREFIX = process.env.SSO_TEST_PREFIX ?? 'mw-sso-test-';
const HOST = process.env.SSO_TEST_HOST ?? spawnSync('hostname', ['-I'], { encoding: 'utf8' }).stdout.trim().split(/\s+/)[0];
const PORT = Number(process.env.SSO_TEST_PORT ?? 19610);
const DEX_IMAGE = process.env.SSO_TEST_DEX ?? 'ghcr.io/dexidp/dex:v2.41.1';
const KEYCLOAK_IMAGE = process.env.SSO_TEST_KEYCLOAK ?? 'quay.io/keycloak/keycloak:26.0.7';

const NETWORK = `${PREFIX}net`;
const DEX = { name: `${PREFIX}dex`, port: PORT + 1 };
const KEYCLOAK = { name: `${PREFIX}keycloak`, port: PORT + 2 };
const DEX_ISSUER = `http://${HOST}:${DEX.port}/dex`;
const KEYCLOAK_ISSUER = `http://${HOST}:${KEYCLOAK.port}/realms/mw`;
const BASE = `http://127.0.0.1:${PORT}`;
const API = `${BASE}/api/v1`;
const CALLBACK = `${BASE}/auth/callback`;
const SETUP_CODE = 'TEST-SETU-PCDE';
const ADMIN = { username: 'admin', password: `o1-${randomBytes(12).toString('hex')}` };
const DEX_SECRET = randomBytes(18).toString('hex');
const KEYCLOAK_SECRET = randomBytes(18).toString('hex');
const KEYCLOAK_USERS = {
  trout: `kc-${randomBytes(9).toString('hex')}`,
  boss: `kc-${randomBytes(9).toString('hex')}`,
};

const scratch = mkdtempSync(join(tmpdir(), 'mw-sso-providers-'));
chmodSync(scratch, 0o755); // the containers read their config files from here
let server = null;
const results = [];

function docker(args, { quiet = false } = {}) {
  const run = spawnSync('docker', args, { encoding: 'utf8' });
  if (run.status !== 0 && !quiet) throw new Error(`docker ${args[0]} failed: ${run.stderr.trim()}`);
  return run;
}

/** Remove only the containers and network this script names, and its data folder. */
async function cleanUp() {
  for (const { name } of [DEX, KEYCLOAK]) docker(['rm', '-f', '-v', name], { quiet: true });
  docker(['network', 'rm', NETWORK], { quiet: true });
  if (server && server.exitCode === null && server.signalCode === null) {
    const ended = new Promise((resolve) => server.once('exit', resolve));
    server.kill('SIGTERM');
    await Promise.race([ended, new Promise((resolve) => setTimeout(resolve, 5000))]);
  }
  rmSync(scratch, { recursive: true, force: true });
}

function check(name, ok, detail = '') {
  results.push(ok);
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? `: ${detail}` : ''}`);
}

async function until(what, test, tries = 240) {
  for (let i = 0; i < tries; i++) {
    try {
      if (await test()) return;
    } catch {
      // not ready yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`${what} didn't start`);
}

// --- A tiny browser: cookies per host, redirects followed by hand --------------------------------

class Browser {
  jar = new Map(); // host → Map(name → value)

  cookieFor(url) {
    const cookies = this.jar.get(new URL(url).host);
    return cookies ? [...cookies].map(([k, v]) => `${k}=${v}`).join('; ') : '';
  }

  keep(url, res) {
    const host = new URL(url).host;
    const cookies = this.jar.get(host) ?? new Map();
    for (const line of res.headers.getSetCookie()) {
      const [pair, ...attrs] = line.split(';');
      const at = pair.indexOf('=');
      const name = pair.slice(0, at).trim();
      const value = pair.slice(at + 1).trim();
      const gone = attrs.some((a) => /^\s*max-age=0\s*$/i.test(a)) || value === '';
      if (gone) cookies.delete(name);
      else cookies.set(name, value);
    }
    this.jar.set(host, cookies);
  }

  async go(url, { method = 'GET', body, json, headers = {} } = {}) {
    const sent = { ...headers };
    const cookie = this.cookieFor(url);
    if (cookie) sent.cookie = cookie;
    let payload = body;
    if (json !== undefined) {
      sent['content-type'] = 'application/json';
      payload = JSON.stringify(json);
    }
    const res = await fetch(url, { method, body: payload, headers: sent, redirect: 'manual' });
    this.keep(url, res);
    return res;
  }

  /** Follow redirects until one goes to Mealwright's callback page; give its query. */
  async toCallback(url) {
    let next = url;
    let method = 'GET';
    let body;
    let headers = {};
    for (let hop = 0; hop < 15; hop++) {
      if (next.startsWith(CALLBACK)) return new URL(next).searchParams;
      const res = await this.go(next, { method, body, headers });
      if (res.status >= 300 && res.status < 400) {
        next = new URL(res.headers.get('location'), next).toString();
        method = 'GET';
        body = undefined;
        headers = {};
        continue;
      }
      const page = await res.text();
      const form = this.loginForm(page, next);
      if (!form) throw new Error(`stopped at ${new URL(next).pathname} (${res.status})`);
      ({ next, body } = form);
      method = 'POST';
      headers = { 'content-type': 'application/x-www-form-urlencoded' };
    }
    throw new Error('too many redirects');
  }

  /** Keycloak's sign-in form, filled in with `this.user`. */
  loginForm(page, at) {
    const action = page.match(/<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"/);
    if (!action || !this.user) return null;
    const next = new URL(action[1].replaceAll('&amp;', '&'), at).toString();
    const body = new URLSearchParams({ username: this.user.username, password: this.user.password, credentialId: '' });
    return { next, body: body.toString() };
  }
}

// --- Mealwright -------------------------------------------------------------------------------

async function mealwright(browser, method, path, json) {
  const headers = method === 'GET' ? {} : { origin: BASE };
  const res = await browser.go(`${API}${path}`, { method, json, headers });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  return { status: res.status, data, location: res.headers.get('location') };
}

async function signInWith(browser, path) {
  const started = await mealwright(browser, 'GET', path);
  if (started.status !== 303) throw new Error(`start answered ${started.status}`);
  const query = await browser.toCallback(new URL(started.location, BASE).toString());
  return mealwright(browser, 'POST', '/sso/finish', {
    state: query.get('state'),
    code: query.get('code'),
    error: query.get('error'),
  });
}

function setup(issuer, secret, buttonName, groupRoles) {
  return {
    issuer,
    client_id: 'mealwright',
    client_secret: secret,
    button_name: buttonName,
    redirect_uri: CALLBACK,
    group_claim: 'groups',
    group_roles: groupRoles,
    anyone_else: 'none',
    make_accounts: true,
    password_sign_in: true,
  };
}

// --- The sign-in servers ----------------------------------------------------------------------

function startDex() {
  const config = join(scratch, 'dex.yaml');
  writeFileSync(
    config,
    [
      `issuer: ${DEX_ISSUER}`,
      'storage:',
      '  type: memory',
      'web:',
      '  http: 0.0.0.0:5556',
      'oauth2:',
      '  skipApprovalScreen: true',
      'connectors:',
      // The mock connector signs in "Kilgore Trout" (kilgore), in the group "authors", at once.
      '- type: mockCallback',
      '  id: mock',
      '  name: Example',
      'staticClients:',
      '- id: mealwright',
      `  secret: ${DEX_SECRET}`,
      '  name: Mealwright',
      '  redirectURIs:',
      `  - ${CALLBACK}`,
      '',
    ].join('\n'),
  );
  chmodSync(config, 0o644);
  docker([
    'run', '-d', '--name', DEX.name, '--network', NETWORK, '-p', `${HOST}:${DEX.port}:5556`,
    '-v', `${config}:/etc/dex/mw.yaml:ro`, DEX_IMAGE, 'dex', 'serve', '/etc/dex/mw.yaml',
  ]);
}

function startKeycloak() {
  const user = (username, password, first, groups) => ({
    username,
    enabled: true,
    email: `${username}@example.org`,
    emailVerified: true,
    firstName: first,
    lastName: 'Test',
    credentials: [{ type: 'password', value: password, temporary: false }],
    groups,
  });
  const realm = {
    realm: 'mw',
    enabled: true,
    groups: [{ name: 'mealwright-admins' }, { name: 'family' }],
    clients: [
      {
        clientId: 'mealwright',
        secret: KEYCLOAK_SECRET,
        publicClient: false,
        standardFlowEnabled: true,
        directAccessGrantsEnabled: false,
        redirectUris: [CALLBACK],
        attributes: { 'pkce.code.challenge.method': 'S256' },
        protocolMappers: [
          {
            name: 'groups',
            protocol: 'openid-connect',
            protocolMapper: 'oidc-group-membership-mapper',
            config: {
              'claim.name': 'groups',
              'full.path': 'false',
              'id.token.claim': 'true',
              'access.token.claim': 'true',
              'userinfo.token.claim': 'true',
            },
          },
        ],
      },
    ],
    users: [
      user('trout', KEYCLOAK_USERS.trout, 'Trout', ['/family']),
      user('boss', KEYCLOAK_USERS.boss, 'Boss', ['/mealwright-admins']),
    ],
  };
  const file = join(scratch, 'mw-realm.json');
  writeFileSync(file, JSON.stringify(realm));
  chmodSync(file, 0o644);
  docker([
    'run', '-d', '--name', KEYCLOAK.name, '--network', NETWORK, '-p', `${HOST}:${KEYCLOAK.port}:8080`,
    '-e', 'KC_BOOTSTRAP_ADMIN_USERNAME=kcadmin', '-e', `KC_BOOTSTRAP_ADMIN_PASSWORD=${randomBytes(12).toString('hex')}`,
    '-e', `KC_HOSTNAME=http://${HOST}:${KEYCLOAK.port}`,
    '-v', `${file}:/opt/keycloak/data/import/mw-realm.json:ro`,
    KEYCLOAK_IMAGE, 'start-dev', '--import-realm',
  ]);
}

// --- The run ----------------------------------------------------------------------------------

async function run() {
  if (!HOST) throw new Error('no network address: set SSO_TEST_HOST');
  docker(['network', 'create', NETWORK]);
  startDex();
  startKeycloak();

  server = spawn('uv', ['run', '--frozen', '--project', '../backend', 'python', '../backend/scripts/e2e_server.py'], {
    stdio: ['ignore', 'ignore', 'inherit'],
    env: {
      ...process.env,
      MEALWRIGHT_DATA_DIR: join(scratch, 'data'),
      MEALWRIGHT_HOST: '127.0.0.1',
      MEALWRIGHT_PORT: String(PORT),
      MEALWRIGHT_FRONTEND_DIR: join(scratch, 'no-web-app'),
      MEALWRIGHT_ALLOW_PLAIN_HTTP: 'true',
      E2E_SETUP_CODE: SETUP_CODE,
    },
  });
  await until('Mealwright', async () => (await fetch(`${API}/version`, { signal: AbortSignal.timeout(2000) })).ok);
  await until('Dex', async () => (await fetch(`${DEX_ISSUER}/.well-known/openid-configuration`, { signal: AbortSignal.timeout(2000) })).ok);
  await until('Keycloak', async () => (await fetch(`${KEYCLOAK_ISSUER}/.well-known/openid-configuration`, { signal: AbortSignal.timeout(2000) })).ok, 480);

  const admin = new Browser();
  const made = await mealwright(admin, 'POST', '/setup', { name: 'Admin', ...ADMIN, setup_code: SETUP_CODE });
  if (made.status !== 201) throw new Error(`setup answered ${made.status}`);
  const listed = await mealwright(admin, 'POST', '/privacy/own-network', { value: HOST });
  if (listed.status !== 201) throw new Error(`own network answered ${listed.status}`);

  // The switch off: nothing is sent, the button is gone, and start goes back to sign-in.
  let saved = await mealwright(admin, 'PUT', '/sso/settings', setup(DEX_ISSUER, DEX_SECRET, 'Dex', [{ group: 'authors', role: 'member' }]));
  check('Dex: setup saved, secret not sent back', saved.status === 200 && saved.data.secret_set && !JSON.stringify(saved.data).includes(DEX_SECRET));
  const off = await mealwright(new Browser(), 'GET', '/sso/start');
  check('Switch off: start goes back to sign-in, nothing sent', off.status === 303 && off.location.startsWith('/sign-in?sso='), off.location);
  await mealwright(admin, 'PUT', '/privacy/switches/single_sign_on', { on: true });
  const options = await mealwright(new Browser(), 'GET', '/sign-in-options');
  check('Sign-in page shows "Sign in with Dex"', options.data?.sso_button === 'Dex');

  // Dex: a new person gets an account, a Member from the group "authors".
  const kilgore = new Browser();
  const dex = await signInWith(kilgore, '/sso/start?remember=false');
  check('Dex: signed in, account made on first sign-in', dex.status === 200 && dex.data.done === 'signed_in', `${dex.status} ${dex.data?.me?.username ?? dex.data?.code ?? ''}`);
  check('Dex: role from the group "authors" is Member', dex.data?.me?.role === 'member', dex.data?.me?.role);
  const me = await mealwright(kilgore, 'GET', '/me');
  check('Dex: the session works', me.status === 200 && me.data.username === dex.data?.me?.username);
  const out = await mealwright(kilgore, 'DELETE', '/session');
  check('Dex: signs out', out.status === 204 && (await mealwright(kilgore, 'GET', '/me')).status === 401);
  const again = await signInWith(kilgore, '/sso/start');
  check('Dex: signing in again finds the same account', again.data?.me?.username === dex.data?.me?.username);

  // Keycloak: a sign-in form, groups from a mapper, a confidential client with PKCE.
  saved = await mealwright(
    admin,
    'PUT',
    '/sso/settings',
    setup(KEYCLOAK_ISSUER, KEYCLOAK_SECRET, 'Keycloak', [
      { group: 'mealwright-admins', role: 'admin' },
      { group: 'family', role: 'member' },
    ]),
  );
  check('Keycloak: setup saved', saved.status === 200);
  const trout = new Browser();
  trout.user = { username: 'trout', password: KEYCLOAK_USERS.trout };
  const kc = await signInWith(trout, '/sso/start?remember=true');
  check('Keycloak: signed in through its form, account made', kc.data?.done === 'signed_in', `${kc.status} ${kc.data?.me?.username ?? kc.data?.code ?? ''}`);
  check('Keycloak: role from the group "family" is Member', kc.data?.me?.role === 'member', kc.data?.me?.role);

  // The admin's test sign-in links them, then password sign-in can go off.
  let refused = await mealwright(admin, 'PUT', '/sso/password-sign-in', { on: false });
  check('Passwords stay on before an admin has signed in by SSO', refused.status === 409);
  admin.user = { username: 'boss', password: KEYCLOAK_USERS.boss };
  const tested = await signInWith(admin, '/sso/test');
  check('Keycloak: the setup test passes as Admin', tested.data?.test?.passed === true && tested.data.test.role === 'admin', JSON.stringify(tested.data?.test ?? tested.data));
  refused = await mealwright(admin, 'PUT', '/sso/password-sign-in', { on: false });
  check('Passwords can go off once the admin is linked', refused.status === 200 && refused.data.password_sign_in === false);
  const now = await mealwright(new Browser(), 'GET', '/sign-in-options');
  check('Sign-in page shows only the SSO button', now.data?.password === false && now.data?.sso_button === 'Keycloak');
  const boss = new Browser();
  boss.user = admin.user;
  const bossIn = await signInWith(boss, '/sso/start');
  check('Keycloak: the admin signs in by SSO as themself', bossIn.data?.me?.username === ADMIN.username && bossIn.data.me.role === 'admin');
  const password = await mealwright(new Browser(), 'POST', '/session', { username: ADMIN.username, password: ADMIN.password, remember: false });
  check('Password sign-in is refused while it is off', password.status >= 400, String(password.status));
  await mealwright(boss, 'PUT', '/sso/password-sign-in', { on: true });
}

// Stopped by hand (Ctrl-C): still remove what was started.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => cleanUp().finally(() => process.exit(1)));
}

let failed = false;
try {
  await run();
} catch (error) {
  console.log(`FAIL ${error.message}`);
  failed = true;
} finally {
  await cleanUp();
}
const bad = results.filter((ok) => !ok).length;
console.log(`${results.length - bad} of ${results.length} checks passed${failed ? ', and the run stopped early' : ''}.`);
process.exit(failed || bad ? 1 : 0);
