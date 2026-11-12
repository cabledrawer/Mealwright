// Single sign-on (backend api/v1/sso.py, 0.9 O1). Signing in starts with a plain link to
// /api/v1/sso/start (the server answers with a redirect to the sign-in server); the sign-in
// server sends the browser back to /auth/callback, which posts what it brought to /sso/finish.
// The setup screen's test starts with a POST (never a link), and links nothing: the admin
// who tested confirms the link afterwards with another POST (O1 review r1 H1).
// The setup is for admins only, and never carries the client secret back ("set" only).

import { api, type Me } from '#lib/api.js';

export interface SignInOptions {
  /** False when an admin turned password sign-in off: only the button shows. */
  password: boolean;
  /** The button's name ("Authentik"), or null for no button. */
  sso_button: string | null;
}

export interface TestResult {
  passed: boolean;
  /** Who the sign-in server said it was: its user name, name and email address for them. */
  username: string | null;
  name?: string | null;
  email?: string | null;
  groups: string[];
  role: 'admin' | 'member' | null;
  /** 'can': the admin who tested may link this person to their own login, by confirming.
   *  'linked': they already are. */
  link?: 'can' | 'linked' | 'no';
  message: string | null;
  code: string | null;
}

export interface FinishOut {
  /** 'again': the sign-in server refused the sign-in for asking to stay signed in while
   *  away; the browser goes to `url` to try once more without (the server allows one). */
  done: 'signed_in' | 'tested' | 'again';
  me: Me | null;
  test: TestResult | null;
  url?: string | null;
}

export interface GroupRole {
  group: string;
  role: 'admin' | 'member';
}

export interface SsoSetup {
  issuer: string;
  client_id: string;
  /** Whether a client secret is saved. The secret itself never comes back. */
  secret_set: boolean;
  button_name: string;
  redirect_uri: string | null;
  group_claim: string;
  group_roles: GroupRole[];
  anyone_else: 'none' | 'member';
  make_accounts: boolean;
  password_sign_in: boolean;
  /** An admin has signed in with single sign-on (or passed the test). */
  admin_linked: boolean;
  /** The Single sign-on switch in Settings → Privacy. */
  switch_on: boolean;
  test: TestResult | null;
  /** After a save: password sign-in was off and is on again, because the save changed who
   *  gets in. `notice` is the server's sentence to show. */
  passwords_back_on?: boolean;
  notice?: string | null;
}

export interface SsoSetupIn {
  issuer: string;
  client_id: string;
  /** Blank keeps the saved one. */
  client_secret: string;
  button_name: string;
  redirect_uri: string;
  group_claim: string;
  group_roles: GroupRole[];
  anyone_else: 'none' | 'member';
  make_accounts: boolean;
  password_sign_in: boolean;
}

/** The address the sign-in server sends people back to, on this server's own address. */
export const CALLBACK_PATH = '/auth/callback';

export const callbackAddress = (origin: string = location.origin): string =>
  `${origin}${CALLBACK_PATH}`;

/** Where the "Sign in with …" button goes (a link: the server redirects). */
export const startAddress = (remember: boolean): string =>
  `/api/v1/sso/start?remember=${remember ? 'true' : 'false'}`;

/** "Test sign-in": the sign-in server's address, to open in a new tab. */
export const startTest = () => api<{ url: string }>('POST', '/sso/test');

/** "Link tess to …?", confirmed: links the admin's own login to who the test found. */
export const linkTested = () => api<SsoSetup>('POST', '/sso/link');

/** "Not now": nothing is linked. */
export const dropTestedLink = () => api<SsoSetup>('DELETE', '/sso/link');

/** Send this tab to the sign-in server (off this site). On its own so tests can stand in. */
export const goToSignInServer = (url: string, keepHistory = false): void => {
  if (keepHistory) location.assign(url);
  else location.replace(url);
};

export const getSignInOptions = (fetcher?: typeof fetch) =>
  api<SignInOptions>('GET', '/sign-in-options', undefined, fetcher ? { fetch: fetcher } : {});

export const finishSignIn = (state: string, code: string | null, error: string | null) =>
  api<FinishOut>('POST', '/sso/finish', { state, code, error }, { signingIn: true });

export const getSsoSetup = () => api<SsoSetup>('GET', '/sso/settings');

export const putSsoSetup = (setup: SsoSetupIn) => api<SsoSetup>('PUT', '/sso/settings', setup);

export const putPasswordSignIn = (on: boolean) =>
  api<SsoSetup>('PUT', '/sso/password-sign-in', { on });
