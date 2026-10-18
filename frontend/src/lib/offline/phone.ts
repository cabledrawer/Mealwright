// What this phone (or computer) keeps for working offline: one IndexedDB database,
// `mealwright`, through `idb` (docs/dev/sync-protocol.md section 11.1).
//
// - `meta`: small facts about the device and who is signed in (device ID, login, cursor).
// - the offline copy, one store per kind, each keyed by ID: what "changes since" sent.
// - `queue`: changes made here that the server hasn't answered yet, oldest first.
//
// There is no pantry store: only the server works out the pantry (FE-5).
//
// The upgrade code only ever adds stores. It never deletes or rewrites `queue` or `meta`,
// so a newer version of the app opens an older version's database with every waiting
// change still there, and sends it (section 11.6, FE-4).

import { deleteDB, openDB, type IDBPDatabase } from 'idb';
import type { Action } from '$lib/shopping/actions';

export const DB_NAME = 'mealwright';
/** Raise this (and only add stores) when the stores change. */
export const DB_VERSION = 1;

/** The offline copy's stores, one per kind, with the field each is keyed by. */
export const COPY_STORES = {
  lists: 'id',
  items: 'id',
  notes: 'id',
  questions: 'id',
  foods: 'id',
  shops: 'id',
  places: 'id',
  people: 'login_id',
  aisles: 'key',
  /** Items taken off the list (from the server's tombstones), keyed by item ID. */
  removed: 'id'
} as const;
export type CopyStore = keyof typeof COPY_STORES;

/** One waiting change. `device_id` and `login_id` are the ones it was made under. */
export interface QueueEntry {
  /** Given by IndexedDB, rising: the queue's order. */
  seq?: number;
  action: Action;
  login_id: number;
  device_id: string;
  queued_at: string;
  tries: number;
}

/** What `meta` holds (sync-protocol 11.1), plus `role` for opening offline. */
export interface Meta {
  device_id: string;
  login_id: number;
  login_name: string;
  username: string;
  role: string;
  cursor: number;
  protocol: number;
}

// Tests give each file its own database, as every test file shares one origin.
let name = DB_NAME;
let opening: Promise<IDBPDatabase> | null = null;

/** For tests only: use a database of this name instead of `mealwright`. */
export function usePhoneDatabase(testName: string): void {
  closePhone();
  name = testName;
}

/** The database's name: `mealwright`, except in tests. */
export function phoneDatabaseName(): string {
  return name;
}

/** Open the database at `version`. The version is for tests of a later upgrade only. */
export function openPhoneAt(version: number): Promise<IDBPDatabase> {
  return openDB(name, version, {
    upgrade(db) {
      // Only add what's missing. Never touch `queue` or `meta`.
      if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta');
      if (!db.objectStoreNames.contains('queue')) {
        db.createObjectStore('queue', { keyPath: 'seq', autoIncrement: true });
      }
      for (const [store, keyPath] of Object.entries(COPY_STORES)) {
        const full = copyStore(store as CopyStore);
        if (!db.objectStoreNames.contains(full)) db.createObjectStore(full, { keyPath });
      }
    },
    // Another tab wants to upgrade or delete the database (signing out): let it.
    blocking() {
      closePhone();
    },
    terminated() {
      opening = null;
    }
  });
}

/** The open database, opened once. */
export function openPhone(): Promise<IDBPDatabase> {
  if (!opening) {
    opening = openPhoneAt(DB_VERSION);
    opening.catch(() => (opening = null));
  }
  return opening;
}

/**
 * Is there a phone database here at all? Asked before reading one on the sign-in page, so
 * looking doesn't make a new, empty database right after a wipe.
 */
export async function phoneExists(): Promise<boolean> {
  if (opening) return true;
  try {
    if (typeof indexedDB.databases !== 'function') return true;
    return (await indexedDB.databases()).some((db) => db.name === name);
  } catch {
    return false;
  }
}

/** Close the connection, so the database can be deleted or upgraded. */
export function closePhone(): void {
  const was = opening;
  opening = null;
  void was?.then((db) => db.close()).catch(() => undefined);
}

/** Delete the whole database (signing out, section 12). */
export async function deletePhone(): Promise<void> {
  const was = opening;
  opening = null;
  if (was) await was.then((db) => db.close()).catch(() => undefined);
  await deleteDB(name);
}

/** The store name of a kind of the offline copy. */
export function copyStore(kind: CopyStore): string {
  return `copy.${kind}`;
}

export const ALL_COPY_STORES = Object.keys(COPY_STORES).map((k) => copyStore(k as CopyStore));

// --- meta ------------------------------------------------------------------------------------

export async function getMeta<K extends keyof Meta>(key: K): Promise<Meta[K] | undefined> {
  return (await openPhone()).get('meta', key);
}

export async function setMeta(values: Partial<Meta>): Promise<void> {
  const tx = (await openPhone()).transaction('meta', 'readwrite');
  for (const [key, value] of Object.entries(values)) void tx.store.put(value, key);
  await tx.done;
}
