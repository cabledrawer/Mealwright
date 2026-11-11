import { describe, expect, it } from 'vitest';
import { applyChanges, EMPTY_COPY } from './load';
import type { ChangesAnswer } from './types';
import { item, sampleCopy } from '#lib/testing/fakeShopping.js';

const answer = (extra: Partial<ChangesAnswer>): ChangesAnswer => {
  const copy = sampleCopy();
  return {
    cursor: 50,
    reset: false,
    lists: [],
    items: [],
    notes: [],
    questions: [],
    foods: [],
    shops: copy.shops,
    places: copy.places,
    people: copy.people!,
    ...extra
  };
};

describe('applyChanges', () => {
  const start = applyChanges(null, {
    ...answer({}),
    reset: true,
    items: [item('a', 1), item('b', 2)]
  });

  it('a full copy replaces everything', () => {
    expect(start.items.map((i) => i.id)).toEqual(['a', 'b']);
    expect(start.cursor).toBe(50);
    const again = applyChanges(start, {
      ...answer({ cursor: 60 }),
      reset: true,
      items: [item('c', 3)]
    });
    expect(again.items.map((i) => i.id)).toEqual(['c']);
  });

  it('later answers change only the rows they name', () => {
    const next = applyChanges(start, answer({ cursor: 55, items: [item('b', 2, { amount: 9 })] }));
    expect(next.items.map((i) => [i.id, i.amount])).toEqual([
      ['a', 500],
      ['b', 9]
    ]);
    expect(next.cursor).toBe(55);
  });

  it('a tombstone takes the item off and remembers who removed it', () => {
    const next = applyChanges(
      start,
      answer({
        items: [
          {
            id: 'a',
            list_id: 'main',
            deleted: true,
            version: 3,
            food_id: 1,
            shop_id: 1,
            removed_by: 'Remy'
          }
        ]
      })
    );
    expect(next.items.map((i) => i.id)).toEqual(['b']);
    expect(next.removed['a']).toEqual({ food_id: 1, shop_id: 1, removed_by: 'Remy' });
    // Brought back by an Undo: no longer removed.
    expect(applyChanges(next, answer({ items: [item('a', 1)] })).removed['a']).toBeUndefined();
  });

  it('notes and cards are replaced in full, as the server sends them', () => {
    const withNote = applyChanges(
      start,
      answer({
        notes: [
          { id: 1, list_id: 'main', item_id: 'a', food_id: 1, text: 'x', undo: null, gone: false }
        ]
      })
    );
    expect(withNote.notes).toHaveLength(1);
    expect(applyChanges(withNote, answer({})).notes).toEqual([]);
  });

  it('starts from the empty copy', () => {
    expect(EMPTY_COPY.items).toEqual([]);
  });
});
