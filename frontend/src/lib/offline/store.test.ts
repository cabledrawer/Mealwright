import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { applyChanges } from '#lib/shopping/load.js';
import type { ChangesAnswer } from '#lib/shopping/types.js';
import { sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { addToQueue, clearCopy, loadCopy, readQueue, saveCopy } from './store';

const answer = (extra: Partial<ChangesAnswer> = {}): ChangesAnswer => ({
  ...structuredClone(sampleCopy()),
  people: sampleCopy().people ?? [],
  reset: true,
  aisles: [{ key: 'dairy', name: 'Dairy' }],
  ...extra
});

beforeEach(() => freshPhone());
afterEach(() => dropPhone());

describe('the offline copy on the phone', () => {
  it('is empty until the list has been loaded once', async () => {
    expect(await loadCopy()).toBeNull();
  });

  it('keeps a copy, every kind', async () => {
    const copy = applyChanges(null, answer());
    await saveCopy(null, copy);
    const kept = await loadCopy();
    expect(kept).not.toBeNull();
    const sorted = <T extends { id: string | number }>(rows: T[]) =>
      [...rows].sort((a, b) => String(a.id).localeCompare(String(b.id)));
    expect(kept!.cursor).toBe(copy.cursor);
    expect(sorted(kept!.items)).toEqual(sorted(copy.items));
    expect(sorted(kept!.lists)).toEqual(sorted(copy.lists));
    expect(kept!.aisles).toEqual([{ key: 'dairy', name: 'Dairy' }]);
    expect(kept!.people).toEqual(copy.people);
  });

  it('writes what changed: an item gone from the list goes from the phone too', async () => {
    const first = applyChanges(null, answer());
    await saveCopy(null, first);
    const gone = first.items[0]!;
    const next = applyChanges(first, {
      ...answer({ reset: false, cursor: first.cursor + 1 }),
      items: [
        {
          id: gone.id,
          list_id: gone.list_id,
          deleted: true,
          version: 41,
          food_id: gone.food_id,
          shop_id: gone.shop_id,
          removed_by: 'Alex'
        }
      ]
    });
    await saveCopy(first, next);
    const kept = (await loadCopy())!;
    expect(kept.cursor).toBe(first.cursor + 1);
    expect(kept.items.some((i) => i.id === gone.id)).toBe(false);
    expect(kept.items).toHaveLength(first.items.length - 1);
    expect(kept.removed[gone.id]).toMatchObject({ removed_by: 'Alex' });
  });

  it('a reset throws away the copy and cursor only', async () => {
    await saveCopy(null, applyChanges(null, answer()));
    const waiting = await addToQueue(
      { id: 'a1', made_at: '2026-10-18T09:00:00Z', seen: 40, kind: 'tick', item_id: 'i-onions' },
      1,
      '11111111-2222-4333-8444-555555555555'
    );
    await clearCopy();
    expect(await loadCopy()).toBeNull();
    expect(await readQueue()).toEqual([waiting]);
  });
});
