// Are we connected to the household's own Mealwright server? (UX principle 16, sync
// protocol 11.4.) Shown as a bar on every page, and a toast when the connection comes back.
//
// "Offline" means the last request to our server failed with a network error or timeout, or
// the reverse proxy answered for it (502, 503, 504: proxyGap.ts), or the browser says it is
// offline. A blip shorter than OFFLINE_AFTER_MS shows nothing at all.
// While we think we are offline a small check goes to our own server every few seconds (one at
// a time, and not while the tab is in the background), so the bar goes away by itself; "Try now" does the same check straight away and reconnects
// the live stream (live.svelte.ts).
//
// Only our own server is ever asked (the check is GET /api/v1/version, same origin).
//
// `waiting` is the number of queued changes for the signed-in login (the offline queue,
// lib/shopping/sync.svelte.ts). The bar says "Offline — N changes waiting" (phone) or "N
// changes waiting. They'll save when you're back." (desktop). Once the connection is back
// AND nothing is waiting any more, a short toast says "Back online — all saved" (11.4).

import { isLeaving, whenStaying } from './leaving';
import { endPendingSignOut } from './offline/signOutPending';
import { proxyGap } from './proxyGap';
import { toasts } from './toast.svelte';
import { plural } from './words.js';

/** A failure shorter than this shows nothing. */
export const OFFLINE_AFTER_MS = 3000;
/** How often to check our server while offline. */
export const CHECK_EVERY_MS = 5000;
/** How long a check may take before it counts as failed. */
export const CHECK_TIMEOUT_MS = 8000;

/** The toast when the connection is back and every waiting change has been sent. */
export const BACK_ONLINE = 'Back online — all saved';

const changes = (n: number) => `${n} ${plural(n, 'change', 'changes')}`;

/** The words in the offline bar. `detail` is the second line on desktop, if there is one.
 *  `device`: network.deviceOffline. The word follows the cause, like the page notes (cabledrawer
 *  30 Oct): "Offline" when this device has no network, "Can’t reach server" when it has one
 *  but the server doesn't answer. */
export function offlineText(
  layout: 'phone' | 'desktop',
  waiting: number,
  device: boolean
): { title: string; detail: string | null } {
  const word = device ? 'Offline' : 'Can’t reach server';
  if (waiting <= 0) return { title: word, detail: null };
  if (layout === 'phone') return { title: `${word} — ${changes(waiting)} waiting`, detail: null };
  return {
    title: word,
    detail: `${changes(waiting)} waiting. They’ll save ${device ? 'when you’re back' : 'when it answers again'}.`
  };
}

class Network {
  /** The bar is showing. */
  offline = $state(false);
  /** A request to our server has failed and nothing has answered since (no wait for the bar:
   *  a screen that couldn't load says so at once, and keeps saying it, cabledrawer 30 Oct). */
  failing = $state(false);
  /** The browser says this device has no network. Then the words are "You’re offline…";
   *  with a network but no answer from the server they are "Can’t reach your Mealwright
   *  server…" (downWords.ts, cabledrawer 30 Oct). */
  deviceOffline = $state(false);
  #waiting = $state(0);

  /** Changes waiting to be sent (the signed-in login's queue). */
  get waiting(): number {
    return this.#waiting;
  }

  set waiting(count: number) {
    this.#waiting = count;
    this.#sayBackOnline();
  }
  /** A "Try now" check is running. */
  trying = $state(false);
  /** How many times the connection has come back after a failure. Something that failed
   *  while we were offline (a recipe photo) tries again when this goes up. */
  backAgain = $state(0);

  #failingSince: number | null = null;
  #showTimer: ReturnType<typeof setTimeout> | null = null;
  #checkTimer: ReturnType<typeof setInterval> | null = null;
  #wasShown = false;
  #reconnect: (() => void) | null = null;
  /** The check under way: another one waits for it rather than running alongside (F67). */
  #checking: Promise<void> | null = null;
  /** Numbers the checks; only the newest one's answer counts ("Try now" replaces one under way). */
  #asking = 0;
  /** Stops the check under way, when "Try now" starts a fresh one. */
  #stop: AbortController | null = null;
  /** Bumped by reset(): a check still under way from before then is ignored when it answers. */
  #round = 0;
  /** Reconnect the live stream after the check under way, whatever it finds ("Try now"). */
  #reconnectAfter = false;
  /** The browser said the connection is back while the check was under way. */
  #browserBack = false;
  /** The bar was shown and the connection is back: say so once nothing is waiting. */
  #backOnline = false;

  /** A request to our server got an answer (any answer, even "no"): we are connected.
   *  `sentAt`: when that request went out. One sent before the failures began proves nothing
   *  about now (the server may have finished it on its way down, follow-up 10): it only
   *  makes the online check ask at once. */
  succeeded(sentAt?: number): void {
    // An answer means this device has a network, even if the browser's `online` event was
    // missed (a home-screen app resumed, F67 review).
    this.deviceOffline = false;
    if (this.#failingSince === null && !this.offline) return;
    if (sentAt !== undefined && this.#failingSince !== null && sentAt <= this.#failingSince) {
      void this.#check();
      return;
    }
    this.#failingSince = null;
    this.#clearTimers();
    this.offline = false;
    this.failing = false;
    this.backAgain++;
    if (this.#wasShown) {
      this.#wasShown = false;
      this.#backOnline = true;
      this.#sayBackOnline();
    }
  }

  #sayBackOnline(): void {
    if (!this.#backOnline || this.offline || this.#waiting > 0) return;
    this.#backOnline = false;
    toasts.show(BACK_ONLINE);
  }

  /** A request to our server failed with a network error or timeout. */
  failed(): void {
    // The browser's `offline` event may have been missed. (Writes the state without reading
    // it: start() runs in the layout's $effect.) It clears on an answer, or when the app is
    // looked at again (onVisible).
    if (navigator.onLine === false) this.deviceOffline = true;
    if (this.#failingSince !== null) return;
    this.#failingSince = Date.now();
    this.failing = true;
    this.#showTimer = setTimeout(() => {
      this.#showTimer = null;
      if (this.#failingSince === null) return;
      this.offline = true;
      this.#wasShown = true;
    }, OFFLINE_AFTER_MS);
    this.#checkTimer = setInterval(() => {
      // Not in a background tab: it checks again as soon as it is looked at (start()).
      if (document.visibilityState !== 'hidden') void this.#check();
    }, CHECK_EVERY_MS);
  }

  /** "Try now": ask our server, and reconnect the live stream. */
  async tryNow(): Promise<void> {
    if (this.trying) return;
    this.trying = true;
    try {
      // A fresh check, not the one already under way: that one began before now and may have
      // found the server down when it is back (B3 L4).
      await this.#check(true, false, true);
    } finally {
      this.trying = false;
    }
  }

  /** The bar shows, or a request has failed and nothing has answered since. A screen that
   *  couldn't load shows its note while this is true: from the first failure, so its words
   *  don't change when the bar comes 3 s later (cabledrawer 30 Oct). */
  get down(): boolean {
    return this.offline || this.failing;
  }

  /** Ask our server whether it is there (the live stream dropped, say). Shows the bar only
   *  if it can't be reached; says nothing if it can. */
  check(): Promise<void> {
    return this.#check();
  }

  /** Start watching the browser's own online/offline word. Returns a function that stops. */
  start(reconnect: () => void): () => void {
    this.#reconnect = reconnect;
    const onOnline = () => {
      this.deviceOffline = false;
      void this.#check(false, true);
    };
    const onOffline = () => {
      this.deviceOffline = true;
      this.failed();
    };
    const onVisible = () => {
      // A home-screen app resumed may have missed the browser's online/offline events.
      if (document.visibilityState === 'visible') this.deviceOffline = navigator.onLine === false;
      const failing = this.#failingSince !== null || this.offline;
      if (failing && document.visibilityState === 'visible') void this.#check();
    };
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    document.addEventListener('visibilitychange', onVisible);
    // Not `if (this.deviceOffline)`: start() runs in the layout's $effect, and reading the
    // state here would run that effect again on every offline event, stopping the bar's timer.
    const offlineNow = navigator.onLine === false;
    this.deviceOffline = offlineNow;
    if (offlineNow) this.failed();
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      document.removeEventListener('visibilitychange', onVisible);
      this.#clearTimers();
      this.#reconnect = null;
    };
  }

  /** Ask our server. Reconnect the stream if we were offline (or `always`). `online`: the
   *  browser has just said the connection is back. Only one check at a time: asked while one
   *  is under way, it waits for that one (a slow server never piles checks up). */
  #check(always = false, online = false, fresh = false): Promise<void> {
    if (always) this.#reconnectAfter = true;
    if (online) this.#browserBack = true;
    // `fresh` ("Try now"): the check under way is stopped and forgotten, so there is still
    // only ever one asking, and its old answer can't say "down" about a server that is back.
    if (fresh && this.#checking) {
      this.#stop?.abort();
      this.#checking = null;
    }
    if (!this.#checking) {
      const stop = new AbortController();
      this.#stop = stop;
      const checking: Promise<void> = this.#checkOnce(this.#round, ++this.#asking, stop).finally(
        () => {
          if (this.#checking === checking) this.#checking = null;
          if (this.#stop === stop) this.#stop = null;
        }
      );
      this.#checking = checking;
    }
    return this.#checking;
  }

  async #checkOnce(round: number, asking: number, stop: AbortController): Promise<void> {
    const was = this.#failingSince !== null || this.offline;
    // The page is being left (leaving.ts): ask nothing until it turns out to stay.
    if (isLeaving()) await whenStaying();
    const giveUp = setTimeout(() => stop.abort(), CHECK_TIMEOUT_MS);
    try {
      // Signed out while offline: the server session ends before anything else is sent.
      if (!(await endPendingSignOut())) throw new Error('still unreachable');
      const response = await fetch('/api/v1/version', {
        cache: 'no-store',
        credentials: 'same-origin',
        signal: stop.signal
      });
      // Forgotten (reset()) or replaced by a newer check while it was asking: its answer
      // belongs to before.
      if (round !== this.#round || asking !== this.#asking) return;
      // 502, 503 and 504 are the reverse proxy saying it can't reach Mealwright: still down
      // (F67: counting them as an answer flitted between the page and "You're offline", with
      // "Back online — all saved" while the server was stopped).
      if (proxyGap(response.status)) throw new Error('the proxy can’t reach the server');
    } catch {
      if (round !== this.#round || asking !== this.#asking) return;
      // Cut off by the page being left: that says nothing about the server.
      if (isLeaving()) return;
      this.#reconnectAfter = this.#browserBack = false;
      this.failed();
      return;
    } finally {
      clearTimeout(giveUp);
    }
    const always = this.#reconnectAfter;
    const online = this.#browserBack;
    this.#reconnectAfter = this.#browserBack = false;
    // An answer that came in while we were offline (a late live-stream hello, say) may already
    // have cleared the failure, and then succeeded() doesn't count this: the browser being back
    // still does, so a photo that failed meanwhile tries again.
    if (online && this.#failingSince === null && !this.offline) this.backAgain++;
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
    this.#stop?.abort();
    this.#stop = null;
    this.#checking = null;
    this.#round++;
    this.#reconnectAfter = this.#browserBack = false;
    this.#wasShown = false;
    this.#backOnline = false;
    this.offline = false;
    this.failing = false;
    this.deviceOffline = false;
    this.#waiting = 0;
    this.trying = false;
    this.backAgain = 0;
  }
}

export const network = new Network();
