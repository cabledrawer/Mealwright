// "Sign-out pending" (docs/dev/sync-protocol.md section 12): signing out while the server
// can't be reached wipes this browser at once and shows the sign-in page, but the session
// cookie can only be ended by the server. This flag remembers that it still has to be, and
// the app ends the server session first thing once it's back, before any other request can
// use the old cookie (api.ts and the connection check call endPendingSignOut first).
//
// It lives in localStorage, OUTSIDE the phone database, on purpose: the wipe deletes that
// database, and the flag has to outlast it (cabledrawer 18 Oct). It says nothing about the
// household: only "1".

import { signOutState } from './unfinished.svelte';

export const SIGN_OUT_PENDING_KEY = 'mealwright.sign-out-pending';

/** How long the server sign-out may take before it counts as "can't reach". */
const SIGN_OUT_TIMEOUT_MS = 8000;

export function signOutPending(): boolean {
  try {
    return localStorage.getItem(SIGN_OUT_PENDING_KEY) === '1';
  } catch {
    return false;
  }
}

export function markSignOutPending(): void {
  try {
    localStorage.setItem(SIGN_OUT_PENDING_KEY, '1');
  } catch {
    // Storage blocked: the sign-out is tried now only.
  }
}

function clearSignOutPending(): void {
  try {
    localStorage.removeItem(SIGN_OUT_PENDING_KEY);
  } catch {
    // Nothing kept there.
  }
}

let ending: Promise<boolean> | null = null;

/**
 * If a sign-out is pending, end the server session now. True when nothing is pending any
 * more; false when the server still can't be reached (then nothing else should be sent).
 */
export function endPendingSignOut(doFetch: typeof fetch = fetch): Promise<boolean> {
  if (!signOutPending()) return Promise.resolve(true);
  ending ??= (async () => {
    try {
      const response = await doFetch('/api/v1/session', {
        method: 'DELETE',
        credentials: 'same-origin',
        signal: AbortSignal.timeout(SIGN_OUT_TIMEOUT_MS)
      });
      // 204: ended. 401: there was no session left to end.
      if (response.ok || response.status === 401) {
        clearSignOutPending();
        signOutState.unfinished = false;
        return true;
      }
      // The server answered but didn't end it (502, 503 and 504 are the reverse proxy saying
      // it can't reach the server: that's only "offline").
      if (![502, 503, 504].includes(response.status)) signOutState.unfinished = true;
      return false;
    } catch {
      return false;
    } finally {
      ending = null;
    }
  })();
  return ending;
}

/**
 * End a pending sign-out as soon as the browser says it's online again (the sign-in page
 * sends nothing by itself). Returns a function that stops listening.
 */
export function endPendingSignOutWhenOnline(): () => void {
  const end = () => void endPendingSignOut();
  window.addEventListener('online', end);
  return () => window.removeEventListener('online', end);
}
