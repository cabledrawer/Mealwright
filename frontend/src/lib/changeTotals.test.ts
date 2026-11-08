import { describe, expect, it } from 'vitest';
import { totalWords } from './changeTotals';
import type { ChangeTotal } from './client/types';

const fridge = { id: 1, name: 'Fridge' };
const freezer = { id: 2, name: 'Freezer' };
const total = (before: string, after: string, extra: Partial<ChangeTotal> = {}): ChangeTotal => ({
  food_id: 21,
  name: 'Paneer',
  place_before: fridge,
  place_after: fridge,
  before: { amount: 0, display: before },
  after: { amount: 0, display: after },
  ...extra
});

describe('what a change did, per ingredient', () => {
  it('reads before → after, as the server words the amounts', () => {
    expect(totalWords(total('0 g', '400 g · 2 packs', { place_before: null }))).toBe(
      'Paneer: 0 g → 400 g · 2 packs'
    );
  });

  it('says a move, and only the move when the amount is the same', () => {
    expect(totalWords(total('200 g · 1 pack', '200 g · 1 pack', { place_after: freezer }))).toBe(
      'Paneer: Fridge → Freezer'
    );
    expect(totalWords(total('400 g · 2 packs', '200 g · 1 pack', { place_after: freezer }))).toBe(
      'Paneer: 400 g · 2 packs → 200 g · 1 pack · Fridge → Freezer'
    );
  });
});
