// The web app talks to the server only through the public API, /api/v1 (CLAUDE.md:
// API-first). Same origin only: the session cookie goes along automatically.

import { cantReachText } from './downWords';
import { isLeaving, whenStaying } from './leaving';
import { network } from './network.svelte';
import { endPendingSignOut } from './offline/signOutPending';
import { forgetOnWipe } from './offline/wipeHooks';
import { PROXY_GAP, proxyGap } from './proxyGap';

export { PROXY_GAP };

export type ThemeChoice = 'auto' | 'light' | 'dark';

export interface Me {
  id: number;
  name: string;
  username: string;
  role: 'admin' | 'member';
  theme: ThemeChoice;
  /** This login's own person in Settings → Household (0.9 A1). */
  member_id?: number | null;
  /** A login the household shares (a kitchen tablet): it may ask "Who's this?". */
  shared?: boolean;
}

export interface SetupState {
  needs_setup: boolean;
  /** The admin allowed signing in over plain http:// (for testing only). */
  plain_http_allowed: boolean;
}

/** A refusal from the server, with its plain-English reason. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** What the app must react to: "ask_once", "name_taken", "already_undone"… */
    readonly code: string | null = null,
    /** The whole answer, for extra fields (`ask`, `food_id`). */
    readonly body: unknown = null
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

/** The machine-readable `code` of an error answer, if it has one. */
export function codeOf(body: unknown): string | null {
  if (body && typeof body === 'object' && 'code' in body) {
    const code = (body as { code: unknown }).code;
    if (typeof code === 'string' && code) return code;
  }
  return null;
}

/** Whether trying the same request again might work (no connection, or a server hiccup). */
export function worthRetrying(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status === 408 || error.status === 429 || error.status >= 500;
}

/** The server couldn't be reached: no connection, or the reverse proxy couldn't reach it. */
export function cantReach(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || proxyGap(error.status));
}

/** The words for "the server can't be reached", the same on every page and chosen by the cause
 *  (word list, section 7; downWords.ts, cabledrawer 30 Oct). */
export const cantReachWords = (): string => cantReachText(network.deviceOffline);

type Fetch = typeof fetch;

let onUnauthorized: (() => void) | null = null;

/** What to do when the session has ended (a 401 from anything but sign-in itself). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

const FALLBACK = 'Something went wrong. Try again.';

/** The server's reason, as a sentence a person can read. */
export function detailOf(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail) return detail;
    // Validation errors (422) come as a list; show the first one's message.
    if (Array.isArray(detail) && detail.length) {
      const msg = (detail[0] as { msg?: unknown }).msg;
      if (typeof msg === 'string' && msg) return msg.replace(/^Value error, /, '');
    }
  }
  return FALLBACK;
}

export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface ApiOptions {
  fetch?: Fetch;
  signingIn?: boolean;
  /**
   * The change's client-made ID (save.ts). Sent as the Idempotency-Key header, so the
   * server never applies the same change twice.
   */
  idempotencyKey?: string;
  /** How long it may take before it counts as "no connection" (default 30 s). */
  timeoutMs?: number;
}

/** How long a request may take before it counts as "no connection". */
const REQUEST_TIMEOUT_MS = 30_000;

/** What else to forget when the session ends (things held in memory for the household). */
const onEnded = new Set<() => void>();

/** Run `forget` whenever the session ends, before the app goes to the sign-in page. */
export function forgetWhenSessionEnds(forget: () => void): void {
  onEnded.add(forget);
}

/** Run what is forgotten when a session ends. */
export function runSessionEndHooks(): void {
  for (const forget of onEnded) forget();
}

/** Forget at BOTH ends of a person's time here: when a session ends and when the browser is
 * wiped (what one person's screen holds must not be there for the next). */
export function forgetAtSignOut(forget: () => void): void {
  onEnded.add(forget);
  forgetOnWipe(forget);
}

/** The session ended (a 401, or the live stream's signed_out): go to the sign-in page. */
export function sessionEnded(): void {
  runSessionEndHooks();
  onUnauthorized?.();
}

export async function api<T>(
  method: Method,
  path: string,
  body?: unknown,
  options: ApiOptions = {}
): Promise<T> {
  const doFetch = options.fetch ?? fetch;
  // The page is being left (leaving.ts): send nothing new until it turns out to stay.
  if (isLeaving()) await whenStaying();
  /** Cut off by the page being left: not a failure, so nothing is said. If the page stays after
   *  all, a read (or a change with its key, which the server never applies twice) is asked
   *  again; any other change gets the usual "can't reach". */
  const cutOff = async (): Promise<{ again: Promise<T> } | null> => {
    if (!isLeaving()) return null;
    await whenStaying();
    return method === 'GET' || options.idempotencyKey
      ? { again: api<T>(method, path, body, options) }
      : null;
  };
  // Signed out while offline: end that session on the server before anything else is sent.
  if (!(await endPendingSignOut(doFetch))) {
    const left = await cutOff();
    if (left) return left.again;
    network.failed();
    throw new ApiError(0, cantReachWords());
  }
  const headers: Record<string, string> = {};
  // A file (a recipe photo) goes as it is; everything else is JSON.
  const file = body instanceof Blob ? body : null;
  if (body !== undefined)
    headers['content-type'] = file ? file.type || 'image/jpeg' : 'application/json';
  if (options.idempotencyKey) headers['idempotency-key'] = options.idempotencyKey;
  let response: Response;
  const sentAt = Date.now();
  try {
    response = await doFetch(`/api/v1${path}`, {
      method,
      credentials: 'same-origin',
      headers: Object.keys(headers).length ? headers : undefined,
      body: file ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal: AbortSignal.timeout(options.timeoutMs ?? REQUEST_TIMEOUT_MS)
    });
  } catch {
    const left = await cutOff();
    if (left) return left.again;
    network.failed();
    throw new ApiError(0, cantReachWords());
  }
  // Any answer from our server means it is there. But 502, 503 and 504 come from the
  // reverse proxy when it can't reach Mealwright (spec UX principle 16).
  if (proxyGap(response.status)) network.failed();
  else network.succeeded(sentAt);
  if (response.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // No JSON (an error page), or the answer was cut off by the page being left.
    const left = await cutOff();
    if (left) return left.again;
  }
  if (!response.ok) {
    if (response.status === 401 && !options.signingIn) sessionEnded();
    throw new ApiError(response.status, detailOf(data), codeOf(data), data);
  }
  return data as T;
}

export const getSetup = (fetch?: Fetch) => api<SetupState>('GET', '/setup', undefined, { fetch });

/** The signed-in person, or null when nobody is signed in. */
export async function getMe(fetch?: Fetch): Promise<Me | null> {
  try {
    return await api<Me>('GET', '/me', undefined, { fetch, signingIn: true });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export const createAdmin = (code: string, name: string, username: string, password: string) =>
  api<Me>('POST', '/setup', { setup_code: code, name, username, password }, { signingIn: true });

export const signIn = (username: string, password: string, remember: boolean) =>
  api<Me>('POST', '/session', { username, password, remember }, { signingIn: true });

export const signOut = () => api<void>('DELETE', '/session', undefined, { signingIn: true });

export const saveTheme = (theme: ThemeChoice) => api<Me>('PUT', '/me/preferences', { theme });
