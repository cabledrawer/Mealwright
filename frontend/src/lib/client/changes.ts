// Recent changes and Undo (contract 6.5).

import { ApiError, api } from '#lib/api.js';
import { newChangeId } from '#lib/changeId.js';
import { kitchen } from '#lib/freshness.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import type { UndoEntry } from '#lib/undo.svelte.js';
import type { Change, UndoResult } from './types';

export interface ChangeList {
  changes: (Change & { lines?: unknown[] })[];
  next: string | null;
}

export function listChanges(
  options: { mine?: boolean; area?: 'pantry' | 'ingredients'; foodId?: number; limit?: number } = {}
): Promise<ChangeList> {
  const params = new URLSearchParams();
  if (options.limit) params.set('limit', String(options.limit));
  if (options.mine) params.set('mine', 'true');
  if (options.area) params.set('area', options.area);
  if (options.foodId) params.set('food_id', String(options.foodId));
  const query = params.toString();
  return api<ChangeList>('GET', `/changes${query ? `?${query}` : ''}`);
}

export const undoChange = (id: number, idempotencyKey: string) =>
  api<UndoResult>('POST', `/changes/${id}/undo`, undefined, { idempotencyKey });

const afterUndoOf = new Map<string, (() => void)[]>();

/**
 * Run `then` after any successful Undo of a change of this kind, however it was started
 * (a toast, Ctrl+Z, a Recent changes list). A screen's store registers itself here for the
 * changes that reach into it: the Drafts list for an import, whose Undo can bring a draft back.
 */
export function onUndoOf(kind: string, then: () => void): void {
  afterUndoOf.set(kind, [...(afterUndoOf.get(kind) ?? []), then]);
}

/**
 * How to undo a change on the server, for an Undo button. The undo has its own ID, made
 * once, so pressing Try again never undoes twice. Shows the server's message when it
 * could only put back some of it (or nothing) or brought a removed ingredient back;
 * "Undone" otherwise.
 */
export function serverUndo(
  changeId: number,
  after?: (result: UndoResult) => void
): () => Promise<string | void> {
  const idempotencyKey = newChangeId();
  return async () => {
    const result = await undoChange(changeId, idempotencyKey);
    kitchen.changed({ elsewhere: true });
    for (const then of afterUndoOf.get(result.undone?.kind ?? '') ?? []) then();
    after?.(result);
    return result.result === 'done' && !result.brought_back?.length ? undefined : result.message;
  };
}

/**
 * What to tell the person after Undo from the Recent changes list: "Undone: Used about
 * ½ tub Yogurt", plus the server's words when it brought a removed ingredient back
 * ("Yogurt is back in Ingredients, with ½ tub in the Fridge.") or could only put back some.
 */
export function undoToast(summary: string, result: UndoResult | null): string {
  if (!result) return `Undone: ${summary}`;
  if (result.result !== 'done') return result.message;
  if (result.brought_back?.length) return `Undone: ${summary}. ${result.message}`;
  return `Undone: ${summary}`;
}

/** For Ctrl+Z after a reload: your own latest change that can still be undone. */
export async function lastOwnChange(): Promise<UndoEntry | null> {
  const { changes } = await listChanges({ mine: true, limit: 20 });
  const last = changes.find((c) => c.can_undo && !c.undone);
  return last ? { label: last.summary, undo: serverUndo(last.id) } : null;
}

/**
 * Undo from a Recent changes list (Pantry's or Ingredients'): the row loses its Undo at
 * once, the server reverses just that change, and the toast says what happened. If it
 * can't be done the row gets its Undo back and the toast says so.
 */
export async function undoFromList(change: Change, list: { changes: Change[] }): Promise<void> {
  const before = list.changes;
  list.changes = before.map((c) => (c.id === change.id ? { ...c, can_undo: false } : c));
  try {
    let answer: UndoResult | null = null;
    await serverUndo(change.id, (result) => (answer = result))();
    toasts.show(undoToast(change.summary, answer));
  } catch (error) {
    list.changes = before;
    toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t undo. Try again.', {
      tone: 'problem'
    });
  }
}
