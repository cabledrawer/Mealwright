// The web app talks to the server only through the public API, /api/v1 (CLAUDE.md:
// API-first). Same origin only: the session cookie goes along automatically.

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
    readonly detail: string
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

type Fetch = typeof fetch;

let onUnauthorized: (() => void) | null = null;

/** What to do when the session has ended (a 401 from anything but sign-in itself). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

const FALLBACK = 'Something went wrong. Please try again.';

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

export async function api<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
  options: { fetch?: Fetch; signingIn?: boolean } = {}
): Promise<T> {
  const doFetch = options.fetch ?? fetch;
  let response: Response;
  try {
    response = await doFetch(`/api/v1${path}`, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch {
    throw new ApiError(0, "Can't reach your Mealwright server. Check your connection.");
  }
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !options.signingIn) onUnauthorized?.();
    throw new ApiError(response.status, detailOf(data));
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
