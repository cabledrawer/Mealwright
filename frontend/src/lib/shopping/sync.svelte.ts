// The offline queue and the shopping copy (docs/dev/sync-protocol.md sections 11.1 and 11.3).
//
// Every Shopping change goes into the queue in the phone database FIRST, and only then to the
// server. Sending:
//
// - One batch in flight at a time: the oldest (up to 100) waiting changes of the signed-in
//   login, in queue order, gathered for 250 ms after a new change.
// - Sent again on: the browser's `online` event, the app opening or coming to the
//   foreground, the event stream reconnecting, "Try now", and the retry timer.
// - No answer, a network error, a 15 s timeout or a 5xx (a proxy's 502 to 504 too): the SAME
//   batch again after 2, 4, 8, 16 and 30 s, then every 60 s, each ±20%. Repeats are safe:
//   the server never applies a change twice (5.3).
// - 401: stop and keep the queue. 409 other_login: don't send. 413: halve the batch. 422 (or
//   another refusal of the whole batch): stop, keep the queue, and say "Couldn't send your
//   changes" with Try now.
//
// The copy is what the server last said; it is kept in the phone database and only changed
// by the server's answers. On a reset (`reset: true`) only the copy and its cursor are thrown
// away: the queue is kept and sent after the fresh copy has arrived (11.1).

import { api, ApiError } from '#lib/api.js';
import { serverListsHeld } from '#lib/offline/confirmed.js';
import { deviceId } from '#lib/offline/device.js';
import type { QueueEntry } from '#lib/offline/phone.js';
import {
  addToQueue,
  clearCopy,
  countTries,
  dropFromQueue,
  loadCopy,
  nowIso,
  readQueue,
  saveCopy
} from '#lib/offline/store.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { setSendContext, type Action, type ActionResult } from './actions';
import { applyChanges } from './load';
import type { ChangesAnswer, ShoppingCopy } from './types';

export const COULDNT_SEND = 'Couldn’t send your changes';
/** Asked for the list with nobody signed in (just signed out). */
export const NOBODY_SIGNED_IN = 'Please sign in again.';

export interface SyncTiming {
  /** Waits before each resend; the last one repeats. */
  retries: number[];
  /** ±this share of each wait (0.2 = 20%). */
  jitter: number;
  /** How long a batch may take before it counts as "no answer". */
  timeoutMs: number;
  /** How long to gather new changes before sending. */
  gatherMs: number;
  /** The most changes in one batch. */
  maxBatch: number;
  random: () => number;
}

export const TIMING: SyncTiming = {
  retries: [2000, 4000, 8000, 16000, 30000, 60000],
  jitter: 0.2,
  timeoutMs: 15_000,
  gatherMs: 250,
  maxBatch: 100,
  random: Math.random
};

/** The wait before resend number `failures + 1`: 2, 4, 8, 16, 30, then 60 s, each ±20%. */
export function retryDelay(failures: number, timing: SyncTiming = TIMING): number {
  const { retries, jitter, random } = timing;
  const wait = retries[Math.min(failures, retries.length - 1)]!;
  return wait * (1 + (random() * 2 - 1) * jitter);
}

/** Why sending has stopped until something changes. */
export type Stopped = 'signed_out' | 'other_login' | 'refused' | null;

interface Waiter {
  resolve: (result: ActionResult) => void;
  reject: (error: unknown) => void;
}

interface BatchAnswer {
  results?: (ActionResult & { id: string })[];
  changes?: ChangesAnswer;
}

export class ShoppingSync {
  /** What the server last said (kept on this phone). null: never loaded here. */
  copy = $state.raw<ShoppingCopy | null>(null);
  /** Every waiting change on this phone, oldest first (any login). */
  queue = $state.raw<QueueEntry[]>([]);
  /** Sending has stopped, and why. */
  stopped = $state<Stopped>(null);

  /** Waiting changes of the signed-in login, including the batch in flight (11.4). */
  readonly waiting = $derived(this.#mine(this.queue).length);
  /** Those changes, oldest first: what the screen shows on top of the copy (11.2). */
  readonly waitingActions = $derived(this.#mine(this.queue).map((e) => e.action));

  timing: SyncTiming;

  /** Who is waiting for each change's answer, by action ID. */
  #waiters: Record<string, Waiter> = {};
  /** Sends and loads take turns, so the cursor only ever moves forward. */
  #turn: Promise<unknown> = Promise.resolve();
  /** The batch being sent (and sent again, unchanged, until it gets an answer). */
  #batch: QueueEntry[] | null = null;
  #batchSize: number;
  #failures = 0;
  #retryTimer: ReturnType<typeof setTimeout> | null = null;
  #gatherTimer: ReturnType<typeof setTimeout> | null = null;
  #opened: Promise<void> | null = null;
  /** The turn of sending that hasn't started yet, if any. */
  #nextSend: Promise<void> | null = null;
  /** Goes up on forget(): an answer to a request from before then is thrown away unread, so
   * nothing is written back into a wiped phone (sign-out, section 12). With nobody signed
   * in, nothing here opens the phone database either, so a wipe stays wiped. */
  #generation = 0;
  /** The last number given to a change queued in memory only (no IndexedDB): -1, -2, … */
  #memorySeq = 0;

  constructor(timing: SyncTiming = TIMING) {
    this.timing = timing;
    this.#batchSize = timing.maxBatch;
    setSendContext({ cursor: () => this.copy?.cursor ?? 0 });
  }

  #mine(queue: QueueEntry[]): QueueEntry[] {
    const me = session.me?.id;
    return me === undefined ? [] : queue.filter((e) => e.login_id === me);
  }

  #setQueue(queue: QueueEntry[]): void {
    this.queue = queue;
    network.waiting = this.#mine(queue).length;
  }

  /** Read the copy and the queue from the phone database (once). */
  open(): Promise<void> {
    if (!session.me) return Promise.resolve();
    const generation = this.#generation;
    this.#opened ??= (async () => {
      try {
        const [copy, queue] = await Promise.all([loadCopy(), readQueue()]);
        if (generation !== this.#generation) return;
        if (copy && !this.copy) this.copy = copy;
        this.#setQueue(queue);
      } catch {
        // No IndexedDB here: everything still works while connected, in memory.
      }
    })();
    return this.#opened;
  }

  /**
   * Starting the app (or a new version of it, 11.6): read what's on the phone, and start
   * sending what is waiting before anything is asked of the server. Resolves once the copy and
   * the queue are read, without waiting for the send: the list shows from the copy at once,
   * with the queue on top, and a weak signal doesn't hold it back (cabledrawer 20 Oct, hand test).
   */
  async start(): Promise<void> {
    await this.open();
    // A new start tries again: after "Couldn't send your changes" (perhaps with a newer
    // version), and after signing back in as the same login when the sign-in ran out (11.5).
    this.stopped = null;
    if (this.#mine(this.queue).length) void this.send();
  }

  // --- Changes in ---------------------------------------------------------------------------------

  /**
   * Put a change in the queue (stored on the phone before anything else), and send it soon.
   * `queued` runs as soon as it is in the queue (and so on the screen), before any answer:
   * the screens offer Undo then (UX principle 8). Resolves with the server's answer to it;
   * rejects only if the server refuses it.
   */
  async enqueue(action: Action, queued?: () => void): Promise<ActionResult> {
    if (!session.me) throw new ApiError(401, NOBODY_SIGNED_IN);
    // Whoever was signed in when the change was made: theirs, even if the app turns to
    // another login while it's being stored (a late answer at the start, 11.4).
    const me = session.me.id;
    await this.open();
    const plain = $state.snapshot(action) as Action;
    const answered = new Promise<ActionResult>(
      (resolve, reject) => (this.#waiters[plain.id] = { resolve, reject })
    );
    let entry: QueueEntry;
    try {
      entry = await addToQueue(plain, me, deviceId());
    } catch {
      // No IndexedDB: queue it in memory for this visit. Its number is below zero, so it can
      // never be the same as one IndexedDB gives (those start at 1).
      entry = {
        seq: --this.#memorySeq,
        action: plain,
        login_id: me,
        device_id: deviceId(),
        queued_at: nowIso(),
        tries: 0
      };
    }
    this.#setQueue([...this.queue, entry]);
    queued?.();
    this.#gather();
    return answered;
  }

  #gather(): void {
    if (this.#gatherTimer) return;
    this.#gatherTimer = setTimeout(() => {
      this.#gatherTimer = null;
      void this.send();
    }, this.timing.gatherMs);
  }

  // --- Sending ------------------------------------------------------------------------------------

  /** Send what's waiting now (a trigger: online, foreground, reconnect, Try now). */
  send(): Promise<void> {
    if (this.#retryTimer) {
      clearTimeout(this.#retryTimer);
      this.#retryTimer = null;
    }
    return this.#sendNext();
  }

  /** One more turn of sending. Triggers that come before it has started share it: it sends
   * everything waiting when it starts, so a second turn behind it would only wait again for
   * a weak signal's timeout. */
  #sendNext(): Promise<void> {
    this.#nextSend ??= this.#take(() => {
      this.#nextSend = null;
      return this.#sendAll();
    });
    return this.#nextSend;
  }

  /** "Try now" after "Couldn't send your changes": start sending again. */
  tryAgain(): Promise<void> {
    if (this.stopped === 'refused') this.stopped = null;
    return this.send();
  }

  /** The same login signed in again: send what it left waiting (11.5). */
  resume(): Promise<void> {
    this.stopped = null;
    return this.send();
  }

  #take<T>(work: () => Promise<T>): Promise<T> {
    const next = this.#turn.then(work, work);
    this.#turn = next.catch(() => undefined);
    return next;
  }

  async #sendAll(): Promise<void> {
    if (!session.me) return;
    await this.open();
    for (;;) {
      if (this.stopped || !session.me) return;
      const batch = this.#batch ?? this.#nextBatch();
      if (!batch.length) {
        this.#batchSize = this.timing.maxBatch;
        return;
      }
      this.#batch = batch;
      const outcome = await this.#sendBatch(batch);
      if (outcome !== 'next') return;
    }
  }

  #nextBatch(): QueueEntry[] {
    const mine = this.#mine(this.queue);
    const device = mine[0]?.device_id;
    const batch: QueueEntry[] = [];
    for (const entry of mine) {
      if (entry.device_id !== device || batch.length >= this.#batchSize) break;
      batch.push(entry);
    }
    return batch;
  }

  /** Send one batch. 'next': answered, carry on with the rest; 'stop': wait for a trigger. */
  async #sendBatch(batch: QueueEntry[]): Promise<'next' | 'stop'> {
    for (const entry of batch) entry.tries++;
    void countTries(batch).catch(() => undefined);
    const since = this.copy?.cursor ?? 0;
    const generation = this.#generation;
    let answer: BatchAnswer;
    try {
      answer = await api<BatchAnswer>(
        'POST',
        '/shopping/actions',
        {
          protocol: 1,
          device_id: batch[0]!.device_id,
          login_id: batch[0]!.login_id,
          since,
          sent_at: nowIso(),
          actions: batch.map((e) => e.action)
        },
        { timeoutMs: this.timing.timeoutMs }
      );
    } catch (error) {
      if (generation !== this.#generation) return 'stop';
      return this.#failedBatch(error, batch);
    }
    if (generation !== this.#generation) return 'stop';
    this.#failures = 0;
    this.#batch = null;
    await this.#answered(batch, answer);
    return 'next';
  }

  #failedBatch(error: unknown, batch: QueueEntry[]): 'next' | 'stop' {
    const status = error instanceof ApiError ? error.status : 0;
    if (status === 0 || status === 408 || status === 429 || status >= 500) {
      this.#retryLater();
      return 'stop';
    }
    this.#failures = 0;
    this.#batch = null;
    if (status === 413) {
      this.#batchSize = Math.max(1, Math.floor(batch.length / 2));
      return 'next';
    }
    if (status === 401) {
      this.stopped = 'signed_out';
    } else if (status === 409 && error instanceof ApiError && error.code === 'other_login') {
      this.stopped = 'other_login';
    } else {
      // A refusal of the whole batch is a bug: keep everything and say so.
      this.stopped = 'refused';
      toasts.problem(COULDNT_SEND, () => void this.tryAgain());
    }
    return 'stop';
  }

  #retryLater(): void {
    const wait = retryDelay(this.#failures, this.timing);
    this.#failures++;
    if (this.#retryTimer) clearTimeout(this.#retryTimer);
    this.#retryTimer = setTimeout(() => {
      this.#retryTimer = null;
      void this.#sendNext();
    }, wait);
  }

  /** Listen for the browser saying it's online, and the app coming to the foreground. */
  watch(): () => void {
    const onOnline = () => void this.send();
    const onVisible = () => {
      if (document.visibilityState === 'visible') void this.send();
    };
    window.addEventListener('online', onOnline);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', onOnline);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }

  /** The server answered a batch: update the copy, drop what was answered, tell the screens. */
  async #answered(batch: QueueEntry[], answer: BatchAnswer): Promise<void> {
    if (answer.changes) await this.#merge(answer.changes);
    const results = Object.fromEntries((answer.results ?? []).map((r) => [r.id, r]));
    const done = batch.filter((e) => e.action.id in results);
    const doneSeqs = done.map((e) => e.seq!);
    await dropFromQueue(doneSeqs).catch(() => undefined);
    this.#setQueue(this.queue.filter((e) => !doneSeqs.includes(e.seq!)));
    for (const entry of done) {
      const result = { ...results[entry.action.id]!, changes: answer.changes };
      const waiter = this.#waiters[entry.action.id];
      delete this.#waiters[entry.action.id];
      if (result.status === 'refused') {
        const error = new ApiError(
          422,
          result.message || 'That change couldn’t be saved.',
          result.reason ?? null
        );
        if (waiter) waiter.reject(error);
        // Sent from an earlier visit, as below.
        else if (!result.repeat) toasts.problem(error.detail);
      } else if (waiter) {
        waiter.resolve(result);
      } else if (result.status === 'ignored' && result.message && !result.repeat) {
        // Sent from an earlier visit: nobody is waiting, so say it here. Not for an answer
        // marked repeat: the server had it already, so it's not news after a reload (F67).
        toasts.show(result.message);
      }
    }
  }

  // --- Changes from the server --------------------------------------------------------------------

  /** Ask the server what changed since the copy (everything with `full`), and keep it. Not
   * before the server has said who is signed in, when the app opened before it did. */
  refresh(full = false): Promise<ShoppingCopy> {
    const held = serverListsHeld();
    if (held) return held.then(() => this.refresh(full));
    return this.#take(async () => {
      if (!session.me) throw new ApiError(401, NOBODY_SIGNED_IN);
      await this.open();
      const have = full ? null : this.copy;
      const since = have?.cursor ?? 0;
      const generation = this.#generation;
      const answer = await api<ChangesAnswer>(
        'GET',
        `/shopping/sync?since=${since}&device_id=${encodeURIComponent(deviceId())}`
      );
      if (generation !== this.#generation) throw new ApiError(401, NOBODY_SIGNED_IN);
      const reset = await this.#merge(answer, full);
      // After a reset the waiting changes go on top of the fresh copy (11.1).
      if (reset && this.#mine(this.queue).length) void this.send();
      return this.copy!;
    });
  }

  /** Merge an answer into the copy and keep it. True when it was a fresh copy. */
  async #merge(answer: ChangesAnswer, full = false): Promise<boolean> {
    const before = this.copy;
    const fresh = full || !before || answer.reset;
    if (fresh && before) await clearCopy().catch(() => undefined);
    const next = applyChanges(fresh ? null : before, answer);
    this.copy = next;
    await saveCopy(fresh ? null : before, next).catch(() => undefined);
    return fresh;
  }

  // --- Leaving ------------------------------------------------------------------------------------

  /** Forget everything in memory (the phone database has been wiped, or for tests). */
  forget(): void {
    this.#generation++;
    if (this.#retryTimer) clearTimeout(this.#retryTimer);
    if (this.#gatherTimer) clearTimeout(this.#gatherTimer);
    this.#retryTimer = this.#gatherTimer = null;
    this.#waiters = {};
    this.#batch = null;
    this.#failures = 0;
    this.#batchSize = this.timing.maxBatch;
    this.#opened = null;
    this.#nextSend = null;
    this.#turn = Promise.resolve();
    this.copy = null;
    this.stopped = null;
    this.#setQueue([]);
  }
}

export const shoppingSync = new ShoppingSync();

/** Every Shopping write: into the queue, then to the server (sync-protocol 11.3). */
export function sendAction(action: Action, queued?: () => void): Promise<ActionResult> {
  return shoppingSync.enqueue(action, queued);
}
