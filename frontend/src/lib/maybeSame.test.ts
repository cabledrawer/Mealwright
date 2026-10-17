import { describe, expect, it } from 'vitest';
import { goesInto, mergeTarget } from './maybeSame';

const sticks = { id: 12, name: 'Drumsticks' };
const moringa = { id: 40, name: 'Drumsticks (moringa)' };

describe('Maybe the same: which side of a pair merges', () => {
  it('the longer name goes into the shorter, as in the mockup', () => {
    expect(goesInto(moringa, sticks)).toBe(true);
    expect(goesInto(sticks, moringa)).toBe(false);
  });

  it('exactly one side of every pair goes, even with equal lengths', () => {
    const a = { id: 1, name: 'Tomato' };
    const b = { id: 2, name: 'tomato' };
    expect(goesInto(a, b) !== goesInto(b, a)).toBe(true);
    expect(goesInto(b, a)).toBe(true);
  });

  it('shows the pair once, on the food that would go', () => {
    expect(mergeTarget({ ...moringa, maybe_same: [sticks] })).toEqual(sticks);
    expect(mergeTarget({ ...sticks, maybe_same: [moringa] })).toBeUndefined();
  });
});
