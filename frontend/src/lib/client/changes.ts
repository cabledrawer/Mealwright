// Recent changes and Undo (contract 6.5).

import { api } from '$lib/api';
import { newChangeId } from '$lib/changeId';
import { kitchen } from '$lib/freshness.svelte';
import type { UndoEntry } from '$lib/undo.svelte';
import type { Change, UndoResult } from './types';

export interface ChangeList {
  changes: (Change & { lines?: unknown[] })[];
  next: string | null;
}

export function listChanges(
  options: { mine?: boolean; area?: 'pantry'; foodId?: number; limit?: number } = {}
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

/**
 * How to undo a change on the server, for an Undo button. The undo has its own ID, made
 * once, so pressing Try again never undoes twice. Shows the server's message when it
 * could only put back some of it (or nothing); "Undone" otherwise.
 */
export function serverUndo(
  changeId: number,
  after?: (result: UndoResult) => void
): () => Promise<string | void> {
  const idempotencyKey = newChangeId();
  return async () => {
    const result = await undoChange(changeId, idempotencyKey);
    kitchen.changed();
    after?.(result);
    return result.result === 'done' ? undefined : result.message;
  };
}

/** For Ctrl+Z after a reload: your own latest change that can still be undone. */
export async function lastOwnChange(): Promise<UndoEntry | null> {
  const { changes } = await listChanges({ mine: true, limit: 20 });
  const last = changes.find((c) => c.can_undo && !c.undone);
  return last ? { label: last.summary, undo: serverUndo(last.id) } : null;
}
