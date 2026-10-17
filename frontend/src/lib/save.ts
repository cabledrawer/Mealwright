// Optimistic saving (UX principle 8): a change shows on screen at once, then goes to
// the server. If the server can't take it, the screen goes back to how it was and a
// calm toast says so, with Try again.
//
// Each change gets a client-made ID (changeId.ts) that travels with it, so the server
// can tell a retry from a new change and never applies one twice.
//
// For the 0.3 offline queue: everything goes out through one "sender". Today the
// sender calls the API straight away. The offline queue will replace it (useSender)
// with one that stores the change in IndexedDB and sends it when the server can be
// reached; callers of save() won't change.

import { ApiError } from './api';
import { newChangeId } from './changeId';
import { toasts } from './toast.svelte';
import { undoHistory, type UndoEntry } from './undo.svelte';

export const COULDNT_SAVE = 'Couldn’t save — try again';

/** A change on its way to the server. */
export interface Outgoing<T> {
  changeId: string;
  send: (changeId: string) => Promise<T>;
}

export type Sender = <T>(change: Outgoing<T>) => Promise<T>;

const sendNow: Sender = (change) => change.send(change.changeId);

let sender: Sender = sendNow;

/** Replace how changes go out (the 0.3 offline queue). null goes back to sending at once. */
export function useSender(replacement: Sender | null): void {
  sender = replacement ?? sendNow;
}

export interface Change<T> {
  /** Show the change on screen. Must set values, not add to them: a retry runs it again. */
  apply: () => void;
  /** Put the screen back as it was before apply(). */
  rollback: () => void;
  /** Send it to the server, with its change ID (header or body, as the API asks). */
  send: (changeId: string) => Promise<T>;
  /** To offer Undo: what happened, and how to take it back once it has saved. */
  undo?: {
    label: string;
    run: (saved: T) => Promise<string | void | false> | string | void | false;
  };
}

export type Outcome<T> = { ok: true; value: T } | { ok: false; error: unknown };

/** Whether trying the same change again might work (no connection, or a server hiccup). */
export function worthRetrying(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 0 || error.status === 408 || error.status === 429 || error.status >= 500;
}

/**
 * Make a change: apply it at once, send it, and roll it back if it fails.
 * Pass `changeId` only to retry a change that was already sent once.
 */
export function save<T>(change: Change<T>, changeId: string = newChangeId()): Promise<Outcome<T>> {
  // eslint-disable-next-line prefer-const -- the Undo entry reads it later
  let outcome: Promise<Outcome<T>>;
  let entry: UndoEntry | undefined;
  if (change.undo) {
    const { label, run } = change.undo;
    entry = {
      label,
      undo: async () => {
        const result = await outcome;
        // It didn't save, so it has already been rolled back and the toast said so.
        return result.ok ? run(result.value) : false;
      }
    };
  }

  change.apply();
  if (entry) undoHistory.record(entry);
  outcome = attempt();
  return outcome;

  async function attempt(): Promise<Outcome<T>> {
    try {
      const value = await sender({ changeId, send: change.send });
      return { ok: true, value };
    } catch (error) {
      change.rollback();
      if (entry) undoHistory.forget(entry);
      tellProblem(error, () => void save(change, changeId));
      return { ok: false, error };
    }
  }
}

function tellProblem(error: unknown, retry: () => void): void {
  // A session that has ended goes to sign in (api.ts); no toast needed.
  if (error instanceof ApiError && error.status === 401) return;
  if (worthRetrying(error)) {
    toasts.show(COULDNT_SAVE, { tone: 'problem', action: { label: 'Try again', run: retry } });
  } else {
    // The server said no, with its reason in plain English; trying again won't help.
    toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
  }
}
