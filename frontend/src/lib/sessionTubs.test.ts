import { describe, expect, it } from 'vitest';
import { tubsLine } from './sessionTubs';

describe('the tubs line of the one Cooked it', () => {
  it('names the places', () => {
    expect(
      tubsLine([
        { place: 'Freezer', count: 2 },
        { place: 'Fridge', count: 2 }
      ])
    ).toBe('4 tubs · 2 Freezer, 2 Fridge');
    expect(tubsLine([{ place: 'Fridge', count: 3 }])).toBe('3 tubs · 3 Fridge');
    expect(tubsLine([{ place: 'Fridge', count: 1 }])).toBe('1 tub · 1 Fridge');
  });

  it('says tubs in meals when they have no place', () => {
    expect(
      tubsLine([
        { place: 'Fridge', count: 1 },
        { place: null, count: 2 }
      ])
    ).toBe('3 tubs · 1 Fridge, 2 in meals');
  });

  it('says nothing for a recipe with no tubs (the "Eaten today · no tubs" line is dropped)', () => {
    expect(tubsLine([])).toBeNull();
    expect(tubsLine([{ place: null, count: 0 }])).toBeNull();
  });
});
