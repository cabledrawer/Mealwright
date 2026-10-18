// Are we connected to the household's own Mealwright server? (UX principle 16, sync
// protocol 11.4.) Shown as a bar on every page, and a toast when the connection comes back.
//
// "Offline" means the last request to our server failed with a network error or timeout, or
// the browser says it is offline. A blip shorter than OFFLINE_AFTER_MS shows nothing at all.
// While we think we are offline a small check goes to our own server every few seconds, so
// the bar goes away by itself; "Try now" does the same check straight away and reconnects
// the live stream (live.svelte.ts).
//
// Only our own server is ever asked (the check is GET /api/v1/version, same origin).
//
// FOR PR 6 (offline queue): `waiting` is the number of queued changes for the signed-in
// login. Nothing sets it above 0 in PR 5. When it is above 0 the bar says "Offline — N
// changes waiting" (phone) or "N changes waiting. They'll save when you're back." (desktop),
// and the "Back online" toast must grow "— all saved" once the queue has emptied (spec
// section 6, "Offline wording grows with PR 6"). PR 6 must also keep the queue when the
// session ends and show the sync-protocol 11.5 message ("Please sign in again. Your N
// changes are kept on this phone.") instead of simply going to the sign-in page.

import { toasts } from './toast.svelte';

/** A failure shorter than this shows nothing. */
export const OFFLINE_AFTER_MS = 3000;
/** How often to check our server while offline. */
export const CHECK_EVERY_MS = 5000;
/** How long a check may take before it counts as failed. */
export const CHECK_TIMEOUT_MS = 8000;

/** The toast when the connection comes back. PR 6 adds " — all saved" once that is true. */
export const BACK_ONLINE = 'Back online';

const changes = (n: number) => `${n} ${n === 1 ? 'change' : 'changes'}`;

/** The words in the offline bar. `detail` is the second line on desktop, if there is one. */
export function offlineText(
  layout: 'phone' | 'desktop',
  waiting: number
): { title: string; detail: string | null } {
  if (waiting <= 0) return { title: 'Offline', detail: null };
  if (layout === 'phone') return { title: `Offline — ${changes(waiting)} waiting`, detail: null };
  return {
    title: 'Offline',
    detail: `${changes(waiting)} waiting. They'll save when you're back.`
  };
}

class Network {
  /** The bar is showing. */
  offline = $state(false);
  /** Changes waiting to be sent. PR 6 fills this in; always 0 in PR 5. */
  waiting = $state(0);
  /** A "Try now" check is running. */
  trying = $state(false);

  #failingSince: number | null = null;
  #showTimer: ReturnType<typeof setTimeout> | null = null;
  #checkTimer: ReturnType<typeof setInterval> | null = null;
  #wasShown = false;
  #reconnect: (() => void) | null = null;

  /** A request to our server got an answer (any answer, even "no"): we are connected. */
  succeeded(): void {
    if (this.#failingSince === null && !this.offline) return;
    this.#failingSince = null;
    this.#clearTimers();
    if (this.#wasShown) {
      this.#wasShown = false;
      toasts.show(BACK_ONLINE);
    }
    this.offline = false;
  }

  /** A request to our server failed with a network error or timeout. */
  failed(): void {
    if (this.#failingSince !== null) return;
    this.#failingSince = Date.now();
    this.#showTimer = setTimeout(() => {
      this.#showTimer = null;
      if (this.#failingSince === null) return;
      this.offline = true;
      this.#wasShown = true;
    }, OFFLINE_AFTER_MS);
    this.#checkTimer = setInterval(() => void this.#check(), CHECK_EVERY_MS);
  }

  /** "Try now": ask our server, and reconnect the live stream. */
  async tryNow(): Promise<void> {
    if (this.trying) return;
    this.trying = true;
    try {
      await this.#check(true);
    } finally {
      this.trying = false;
    }
  }

  /** Start watching the browser's own online/offline word. Returns a function that stops. */
  start(reconnect: () => void): () => void {
    this.#reconnect = reconnect;
    const onOnline = () => void this.#check();
    const onOffline = () => this.failed();
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    if (navigator.onLine === false) this.failed();
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      this.#clearTimers();
      this.#reconnect = null;
    };
  }

  /** Ask our server. Reconnect the stream if we were offline (or `always`). */
  async #check(always = false): Promise<void> {
    const was = this.#failingSince !== null || this.offline;
    try {
      await fetch('/api/v1/version', {
        cache: 'no-store',
        credentials: 'same-origin',
        signal: AbortSignal.timeout(CHECK_TIMEOUT_MS)
      });
    } catch {
      this.failed();
      return;
    }
    this.succeeded();
    if (was || always) this.#reconnect?.();
  }

  #clearTimers(): void {
    if (this.#showTimer) clearTimeout(this.#showTimer);
    if (this.#checkTimer) clearInterval(this.#checkTimer);
    this.#showTimer = this.#checkTimer = null;
  }

  /** For tests: forget everything. */
  reset(): void {
    this.#clearTimers();
    this.#failingSince = null;
    this.#wasShown = false;
    this.offline = false;
    this.waiting = 0;
    this.trying = false;
  }
}

export const network = new Network();
