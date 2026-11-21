// Who is signed in, and where people go when they aren't (spec: Sign in, Onboarding).

import type { Me, SetupState } from './api';

class Session {
  me = $state<Me | null>(null);
  setup = $state<SetupState | null>(null);
}

export const session = new Session();

/** Pages that work without signing in. */
export const SIGN_IN = '/sign-in';
export const SETUP = '/setup';

// Control characters (tab, newline, CR, anything below a space, DEL) and backslashes: a browser
// drops or turns them into "/" while reading an address, so "/\t/evil.example" or "/\\evil"
// would leave the site (release security pass, open redirect).
// eslint-disable-next-line no-control-regex -- matching control characters is the point
const UNSAFE = /[\u0000-\u001f\u007f\\]/;

/**
 * Where to send someone after signing in: back where they were heading, but only to
 * a page of this app (never another site, never the API). The address is read as the
 * browser would read it, and only the checked page (path, search, hash) is given back,
 * never the raw text.
 */
export function safeNext(
  next: string | null | undefined,
  origin: string = globalThis.location?.origin ?? 'http://mealwright.invalid'
): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || UNSAFE.test(next)) return '/';
  let decoded: string;
  try {
    decoded = decodeURIComponent(next);
  } catch {
    return '/'; // a broken %-form: not an address we made
  }
  // The same characters written as %09, %5C…, or "/%2F" (two slashes once read).
  if (UNSAFE.test(decoded) || decoded.startsWith('//')) return '/';
  let url: URL;
  let own: string;
  try {
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- read once here, never state
    url = new URL(next, origin);
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- read once here, never state
    own = new URL(origin).origin;
  } catch {
    return '/';
  }
  if (url.origin !== own) return '/';
  const path = decodeURIComponent(url.pathname);
  if (!path.startsWith('/') || path.startsWith('//')) return '/';
  if (path === '/api' || path.startsWith('/api/')) return '/';
  if (path === SIGN_IN || path === SETUP) return '/';
  return url.pathname + url.search + url.hash;
}

/** The sign-in page's address, remembering where the person was heading. */
export function signInPath(heading: string): string {
  const next = safeNext(heading);
  return next === '/' ? SIGN_IN : `${SIGN_IN}?next=${encodeURIComponent(next)}`;
}

/** The first letter of someone's name, for their round avatar. */
export function initial(name: string): string {
  const first = [...name.trim()][0];
  return first ? first.toLocaleUpperCase() : '?';
}

/**
 * Whether this page can send a password safely. Browsers count https:// and
 * localhost as secure; a plain http:// address on the network is not.
 */
export type Connection = 'secure' | 'plain-allowed' | 'plain-refused';

export function connection(isSecureContext: boolean, plainHttpAllowed: boolean): Connection {
  if (isSecureContext) return 'secure';
  return plainHttpAllowed ? 'plain-allowed' : 'plain-refused';
}
