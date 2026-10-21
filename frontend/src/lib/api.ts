// The web app talks to the server only through the public API, /api/v1 (CLAUDE.md:
// API-first). Same origin only: the session cookie goes along automatically.

import { network } from './network.svelte';
import { endPendingSignOut } from './offline/signOutPending';

export type ThemeChoice = 'auto' | 'light' | 'dark';

export interface Me {
  id: number;
  name: string;
  username: string;
  role: 'admin' | 'member';
  theme: ThemeChoice;
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

const PROXY_GAP = new Set([502, 503, 504]);

/** The server couldn't be reached: no connection, or the reverse proxy couldn't reach it. */
export function cantReach(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || PROXY_GAP.has(error.status));
}

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

/** The session ended (a 401, or the live stream's signed_out): go to the sign-in page. */
export function sessionEnded(): void {
  for (const forget of onEnded) forget();
  onUnauthorized?.();
}

export async function api<T>(
  method: Method,
  path: string,
  body?: unknown,
  options: ApiOptions = {}
): Promise<T> {
  const doFetch = options.fetch ?? fetch;
  // Signed out while offline: end that session on the server before anything else is sent.
  if (!(await endPendingSignOut(doFetch))) {
    network.failed();
    throw new ApiError(0, 'Can’t reach your Mealwright server. Check your connection.');
  }
  const headers: Record<string, string> = {};
  // A file (a recipe photo) goes as it is; everything else is JSON.
  const file = body instanceof Blob ? body : null;
  if (body !== undefined)
    headers['content-type'] = file ? file.type || 'image/jpeg' : 'application/json';
  if (options.idempotencyKey) headers['idempotency-key'] = options.idempotencyKey;
  let response: Response;
  try {
    response = await doFetch(`/api/v1${path}`, {
      method,
      credentials: 'same-origin',
      headers: Object.keys(headers).length ? headers : undefined,
      body: file ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal: AbortSignal.timeout(options.timeoutMs ?? REQUEST_TIMEOUT_MS)
    });
  } catch {
    network.failed();
    throw new ApiError(0, 'Can’t reach your Mealwright server. Check your connection.');
  }
  // Any answer from our server means it is there. But 502, 503 and 504 come from the
  // reverse proxy when it can't reach Mealwright (spec UX principle 16).
  if (PROXY_GAP.has(response.status)) network.failed();
  else network.succeeded();
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
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

export const createAdmin = (name: string, username: string, password: string) =>
  api<Me>('POST', '/setup', { name, username, password }, { signingIn: true });

export const signIn = (username: string, password: string, remember: boolean) =>
  api<Me>('POST', '/session', { username, password, remember }, { signingIn: true });

export const signOut = () => api<void>('DELETE', '/session', undefined, { signingIn: true });

export const saveTheme = (theme: ThemeChoice) => api<Me>('PUT', '/me/preferences', { theme });
