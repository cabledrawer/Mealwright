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

/**
 * Where to send someone after signing in: back where they were heading, but only to
 * a page of this app (never another site, never the API).
 */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return '/';
  }
  if (next === '/api' || next.startsWith('/api/')) return '/';
  if (next === SIGN_IN || next.startsWith(SIGN_IN + '?') || next === SETUP) return '/';
  return next;
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
