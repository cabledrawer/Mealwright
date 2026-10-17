// Optimistic saving (UX principle 8): a change shows on screen at once, then goes to
// the server. If the server can't take it, the screen goes back to how it was and a
// calm toast says so, with Try again.
//
// Each change gets a client-made ID (changeId.ts), sent as the Idempotency-Key header,
// so the server can tell a retry from a new change and never applies one twice. The
// same ID is used when the server asks a question first ("ask once", contract 4.4)
// and the change is sent again with the answer.
//
// For the 0.3 offline queue: everything goes out through one "sender". Today the
// sender calls the API straight away. The offline queue will replace it (useSender)
// with one that stores the change in IndexedDB and sends it when the server can be
// reached; callers of save() won't change.

import { ApiError, worthRetrying } from './api';
import { askOnce } from './askOnce.svelte';
import { newChangeId } from './changeId';
import type { Answer, Ask } from './client/types';
import { toasts } from './toast.svelte';
import { undoHistory, type UndoEntry } from './undo.svelte';

export { worthRetrying };

export const COULDNT_SAVE = 'Couldn’t save — try again';

/** How many questions one change may ask before giving up (a guard against loops). */
const MAX_QUESTIONS = 3;

/** A change on its way to the server. */
export interface Outgoing<T> {
  changeId: string;
  send: (changeId: string, answers: Answer[]) => Promise<T>;
  answers: Answer[];
}

export type Sender = <T>(change: Outgoing<T>) => Promise<T>;

const sendNow: Sender = (change) => change.send(change.changeId, change.answers);

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
  /** Send it with its change ID, plus any answers to "ask once" questions. */
  send: (changeId: string, answers: Answer[]) => Promise<T>;
  /** Called with the server's answer, e.g. to show the server's version of the thing. */
  saved?: (value: T) => void;
  /** To offer Undo: what happened, and how to take it back once it has saved. */
  undo?: {
    /** Shown at once. */
    label: string;
    /** The server's own words once it answers ("Changed weight of 1 cup to 200 g"). */
    labelFrom?: (saved: T) => string | undefined;
    run: (saved: T) => Promise<string | void | false> | string | void | false;
  };
  /** Deal with a refusal yourself (return true), e.g. "name taken → open that food". */
  refused?: (error: ApiError) => boolean;
}

export type Outcome<T> =
  | { ok: true; value: T }
  | {
      ok: false;
      error: unknown;
      /** The person chose not to answer a question. */
      cancelled?: boolean;
    };

function askOf(error: unknown): Ask | null {
  if (!(error instanceof ApiError) || error.code !== 'ask_once') return null;
  const body = error.body as { ask?: Ask } | null;
  return body?.ask ?? null;
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
  const toastId = entry ? undoHistory.record(entry) : undefined;
  outcome = attempt();
  return outcome;

  async function attempt(): Promise<Outcome<T>> {
    const answers: Answer[] = [];
    for (;;) {
      try {
        const value = await sender({ changeId, send: change.send, answers });
        change.saved?.(value);
        const label = change.undo?.labelFrom?.(value);
        if (entry && label) {
          entry.label = label;
          if (toastId !== undefined) toasts.update(toastId, label);
        }
        return { ok: true, value };
      } catch (error) {
        const ask = askOf(error);
        if (ask && answers.length < MAX_QUESTIONS) {
          const answer = await askOnce.ask(ask);
          if (answer) {
            answers.push(answer);
            continue; // the same change, the same ID, now with the answer
          }
          change.rollback();
          if (entry) undoHistory.forget(entry);
          if (toastId !== undefined) toasts.dismiss(toastId);
          return { ok: false, error, cancelled: true };
        }
        change.rollback();
        if (entry) undoHistory.forget(entry);
        tellProblem(error, change, () => void save(change, changeId));
        return { ok: false, error };
      }
    }
  }
}

function tellProblem<T>(error: unknown, change: Change<T>, retry: () => void): void {
  // A session that has ended goes to sign in (api.ts); no toast needed.
  if (error instanceof ApiError && error.status === 401) return;
  if (error instanceof ApiError && change.refused?.(error)) return;
  if (worthRetrying(error)) {
    toasts.show(COULDNT_SAVE, { tone: 'problem', action: { label: 'Try again', run: retry } });
  } else {
    // The server said no, with its reason in plain English; trying again won't help.
    toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
  }
}
