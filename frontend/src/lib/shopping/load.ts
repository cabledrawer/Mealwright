// Getting the shopping copy: GET /shopping/sync (sync-protocol 5.5). The first time (and
// whenever the server says `reset`) it is a full copy; after that only what changed since the
// copy's cursor, which applyChanges() merges in. The same function takes the `changes` that
// come back with a batch of actions.

import { api } from '#lib/api.js';
import { deviceId } from './actions';
import type { ChangesAnswer, ShoppingCopy, Tombstone } from './types';

export const EMPTY_COPY: ShoppingCopy = {
  cursor: 0,
  lists: [],
  items: [],
  notes: [],
  questions: [],
  foods: [],
  shops: [],
  places: [],
  people: null,
  removed: {},
  aisles: []
};

/** Ask the server what changed since `copy` (everything, when there is no copy yet). */
export async function loadChanges(copy: ShoppingCopy | null): Promise<ChangesAnswer> {
  const since = copy?.cursor ?? 0;
  return api<ChangesAnswer>(
    'GET',
    `/shopping/sync?since=${since}&device_id=${encodeURIComponent(deviceId())}`
  );
}

const isTombstone = (row: ChangesAnswer['items'][number]): row is Tombstone =>
  (row as { deleted?: boolean }).deleted === true;

function upsert<T extends { id: string | number }>(rows: T[], news: T[]): T[] {
  const byId = new Map(rows.map((r) => [r.id, r]));
  for (const row of news) byId.set(row.id, row);
  return [...byId.values()];
}

/** Merge an answer into a copy, or start a fresh copy (a reset, or no copy yet). */
export function applyChanges(copy: ShoppingCopy | null, answer: ChangesAnswer): ShoppingCopy {
  const fresh = !copy || answer.reset;
  const base = fresh ? EMPTY_COPY : copy;
  let items = fresh ? [] : base.items;
  const removed = fresh ? {} : { ...base.removed };
  const live = [];
  for (const row of answer.items) {
    if (isTombstone(row)) {
      items = items.filter((i) => i.id !== row.id);
      removed[row.id] = {
        food_id: row.food_id,
        shop_id: row.shop_id,
        removed_by: row.removed_by
      };
    } else {
      live.push(row as ShoppingCopy['items'][number]);
      delete removed[row.id];
    }
  }
  items = upsert(items, live);
  return {
    cursor: answer.cursor,
    lists: fresh ? answer.lists : upsert(base.lists, answer.lists),
    items,
    notes: answer.notes ?? [],
    questions: answer.questions ?? [],
    // A provisional ingredient (negative ID, made while an add is in flight) goes.
    foods: (fresh ? answer.foods : upsert(base.foods, answer.foods)).filter((f) => f.id >= 0),
    shops: answer.shops,
    places: answer.places,
    people: answer.people,
    removed,
    aisles: answer.aisles ?? base.aisles ?? []
  };
}
