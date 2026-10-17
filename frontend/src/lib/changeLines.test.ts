import { describe, expect, it } from 'vitest';
import { changeLines } from './changeLines';
import type { ChangeLine } from './client/types';

const fridge = { id: 1, name: 'Fridge' };
const line = (before: string, after: string, extra: Partial<ChangeLine> = {}): ChangeLine => ({
  food: { id: 21, name: 'Paneer' },
  lot_id: 1,
  before: { amount: 0, display: before },
  after: { amount: 0, display: after },
  place_before: fridge,
  place_after: fridge,
  ...extra
});

describe('lines under a change', () => {
  it('says identical lines once, with how many times', () => {
    expect(changeLines([line('0 g', '1 pack · 200 g'), line('0 g', '1 pack · 200 g')])).toEqual([
      'Paneer: 0 g → 1 pack · 200 g, twice'
    ]);
    const four = Array.from({ length: 4 }, () => line('0 g', '1 pack · 200 g'));
    expect(changeLines(four)).toEqual(['Paneer: 0 g → 1 pack · 200 g, 4 times']);
  });

  it('keeps different lines apart, and says moves and dates', () => {
    expect(
      changeLines([
        line('1 pack · 200 g', '0 g'),
        line('1 pack · 200 g', '1 pack · 200 g', {
          place_after: { id: 2, name: 'Freezer' },
          use_by_after: '2027-01-17'
        })
      ])
    ).toEqual(['Paneer: 1 pack · 200 g → 0 g', 'Paneer: Fridge → Freezer · use by 17 Jan']);
  });
});
