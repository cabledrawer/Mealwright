// Live updates (sync protocol section 10): one EventSource to our own server's
// /api/v1/events, opened by the app shell while someone is signed in.
//
// The stream carries numbers only. `shopping {cursor}` says the household's lists changed up
// to that counter; Shopping asks GET /shopping/changes?since= when it is above its own.
// `pantry {change_id}` says stock changed; an open Pantry fetches again. `signed_out` means
// the sign-in ran out: go to the sign-in page, exactly as a 401 does.
//
// The browser reconnects by itself after a drop (the server asks for 5 seconds). Coming
// back to the foreground, the screens fetch again on their own (visibilitychange).
//
// `replaced` means this sign-in opened more than 10 streams (more than 10 tabs) and this,
// the oldest, was closed (security audit, 0.4). It closes quietly: no offline bar, and no
// reconnecting until this tab next comes to the foreground or is reloaded. Reconnecting
// at once would close another tab's stream, and that tab would do the same, in turns.
//
// On `signed_out` this calls sessionEnded(), the same as a 401. Neither is a sign-out: the
// offline queue stays on the phone, and the sign-in page says "Please sign in again. Your N
// changes are kept on this phone." when changes are waiting (sync protocol 11.5).

import { api, sessionEnded } from './api';
import { network } from './network.svelte';

/** The server asks the browser for the same wait (`retry: 5000`). */
const RETRY_MS = 5000;

export const EVENTS_URL = '/api/v1/events';

function numberIn(event: Event, key: string): number | null {
  try {
    const data: unknown = JSON.parse((event as MessageEvent<string>).data);
    const value = data && typeof data === 'object' ? (data as Record<string, unknown>)[key] : null;
    return typeof value === 'number' ? value : null;
  } catch {
    return null;
  }
}

class Live {
  /** The highest shopping counter heard (hello or shopping). */
  shopping = $state(0);
  /** Moves on every time the pantry's stock changed somewhere. */
  pantry = $state(0);

  #source: EventSource | null = null;
  #onHello: (() => void) | null = null;
  /** Closed by the server for a newer tab (`replaced`): wait until this tab is looked at. */
  #replaced = false;

  /**
   * Open the stream. `onHello` runs each time it (re)connects: the offline queue sends then.
   * Returns a function that closes it.
   */
  start(onHello: (() => void) | null = null): () => void {
    this.#onHello = onHello;
    this.#open();
    const onVisible = () => {
      // A phone may have dropped the stream while the app was in the background, or a newer
      // tab took this one's place.
      if (document.visibilityState !== 'visible') return;
      if (this.#replaced || this.#source?.readyState === 2) this.#open();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      this.#onHello = null;
      this.#replaced = false;
      this.#close();
    };
  }

  /**
   * Close and open again ("Try now", or the connection came back). Not after `replaced`:
   * every tab hears that the connection came back, and they would take turns closing
   * each other's streams.
   */
  reconnect(): void {
    if (this.#replaced) return;
    this.#close();
    this.#open();
  }

  #open(): void {
    if (typeof EventSource === 'undefined') return;
    this.#close();
    this.#replaced = false;
    const source = new EventSource(EVENTS_URL, { withCredentials: true });
    this.#source = source;
    source.addEventListener('hello', (event) => {
      network.succeeded();
      this.#shopping(numberIn(event, 'cursor'));
      this.#onHello?.();
    });
    source.addEventListener('shopping', (event) => this.#shopping(numberIn(event, 'cursor')));
    source.addEventListener('pantry', () => this.pantry++);
    source.addEventListener('signed_out', () => {
      this.#close();
      sessionEnded();
    });
    source.addEventListener('replaced', () => {
      if (this.#source !== source) return;
      this.#close();
      this.#replaced = true;
    });
    // The browser tries again by itself; the offline bar waits 3 seconds before showing.
    source.addEventListener('error', () => {
      if (this.#source !== source) return;
      if (source.readyState === EventSource.CLOSED) void this.#refused(source);
      else network.failed();
    });
  }

  /**
   * The browser gave up on the stream (the server answered with an error, not a dropped
   * connection). Ask who we are: a 401 sends the person to sign in; a network failure
   * shows the offline bar; otherwise try the stream again shortly.
   */
  async #refused(source: EventSource): Promise<void> {
    try {
      await api('GET', '/me');
    } catch {
      // api() has already told the connection store, or handled a 401
    }
    setTimeout(() => {
      if (this.#source === source) this.#open();
    }, RETRY_MS);
  }

  #shopping(cursor: number | null): void {
    if (cursor !== null && cursor > this.shopping) this.shopping = cursor;
  }

  #close(): void {
    this.#source?.close();
    this.#source = null;
  }
}

export const live = new Live();
