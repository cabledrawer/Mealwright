// Reading and writing the offline copy and the queue in the phone database (phone.ts).
//
// The copy is written from the server's answers only: what this phone did and the server
// hasn't answered yet stays in the queue, and the screen shows it on top (11.2). Rows the
// answer didn't touch are the same objects as before, so only the changed ones are written.

import type { Action } from '$lib/shopping/actions';
import type { Removed, ShoppingCopy } from '$lib/shopping/types';
import {
  ALL_COPY_STORES,
  COPY_STORES,
  copyStore,
  openPhone,
  type CopyStore,
  type QueueEntry
} from './phone';

type Row = Record<string, unknown>;

/** Every kind of the copy as rows keyed by the store's key. */
function rowsOf(copy: ShoppingCopy): Record<CopyStore, Row[]> {
  return {
    lists: copy.lists as unknown as Row[],
    items: copy.items as unknown as Row[],
    notes: copy.notes as unknown as Row[],
    questions: copy.questions as unknown as Row[],
    foods: copy.foods as unknown as Row[],
    shops: copy.shops as unknown as Row[],
    places: copy.places as unknown as Row[],
    people: (copy.people ?? []) as unknown as Row[],
    aisles: (copy.aisles ?? []) as unknown as Row[],
    removed: Object.entries(copy.removed).map(([id, r]) => ({ id, ...r }))
  };
}

/**
 * Keep `next` as the phone's copy. `before` is what was kept until now (null: nothing, or a
 * reset, so every store is emptied first).
 */
export async function saveCopy(before: ShoppingCopy | null, next: ShoppingCopy): Promise<void> {
  const db = await openPhone();
  const tx = db.transaction([...ALL_COPY_STORES, 'meta'], 'readwrite');
  const nextRows = rowsOf(next);
  const beforeRows = before ? rowsOf(before) : null;
  for (const kind of Object.keys(COPY_STORES) as CopyStore[]) {
    const store = tx.objectStore(copyStore(kind));
    const key = COPY_STORES[kind];
    if (!beforeRows) {
      void store.clear();
      for (const row of nextRows[kind]) void store.put(row);
      continue;
    }
    const old = new Map(beforeRows[kind].map((r) => [r[key], r]));
    for (const row of nextRows[kind]) {
      // `removed` rows are made fresh each time; the others are the same object if unchanged.
      if (old.get(row[key]) !== row || kind === 'removed') void store.put(row);
      old.delete(row[key]);
    }
    for (const gone of old.keys()) void store.delete(gone as IDBValidKey);
  }
  void tx.objectStore('meta').put(next.cursor, 'cursor');
  await tx.done;
}

/** The phone's copy, or null when the list has never been loaded on this phone. */
export async function loadCopy(): Promise<ShoppingCopy | null> {
  const db = await openPhone();
  const tx = db.transaction([...ALL_COPY_STORES, 'meta']);
  const cursor = (await tx.objectStore('meta').get('cursor')) as number | undefined;
  if (cursor === undefined) return null;
  const rows = {} as Record<CopyStore, unknown[]>;
  for (const kind of Object.keys(COPY_STORES) as CopyStore[]) {
    rows[kind] = await tx.objectStore(copyStore(kind)).getAll();
  }
  const removed: Record<string, Removed> = {};
  for (const row of rows.removed as (Removed & { id: string })[]) {
    const { id, ...rest } = row;
    removed[id] = rest;
  }
  const copy = { ...(rows as unknown as ShoppingCopy), cursor, removed };
  await tx.done;
  return copy;
}

/** Throw away the copy and its cursor, keeping the queue (a reset, sync-protocol 11.1). */
export async function clearCopy(): Promise<void> {
  const db = await openPhone();
  const tx = db.transaction([...ALL_COPY_STORES, 'meta'], 'readwrite');
  for (const store of ALL_COPY_STORES) void tx.objectStore(store).clear();
  void tx.objectStore('meta').delete('cursor');
  await tx.done;
}

/** Now, as the queue and the batch envelope write it. */
export function nowIso(): string {
  return new Date().toISOString();
}

// --- The queue -----------------------------------------------------------------------------------

/** Put a change at the end of the queue. Resolves once it is stored, with its place. */
export async function addToQueue(
  action: Action,
  login: number,
  device: string
): Promise<QueueEntry> {
  const entry: QueueEntry = {
    action,
    login_id: login,
    device_id: device,
    queued_at: nowIso(),
    tries: 0
  };
  const seq = (await (await openPhone()).add('queue', entry)) as number;
  return { ...entry, seq };
}

/** Every waiting change, oldest first. */
export async function readQueue(): Promise<QueueEntry[]> {
  return (await openPhone()).getAll('queue');
}

/** Take answered changes out of the queue. */
export async function dropFromQueue(seqs: number[]): Promise<void> {
  if (!seqs.length) return;
  const tx = (await openPhone()).transaction('queue', 'readwrite');
  for (const seq of seqs) void tx.store.delete(seq);
  await tx.done;
}

/** Note another try for these changes. */
export async function countTries(entries: QueueEntry[]): Promise<void> {
  const tx = (await openPhone()).transaction('queue', 'readwrite');
  for (const entry of entries) void tx.store.put(entry);
  await tx.done;
}
