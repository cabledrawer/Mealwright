import { describe, expect, it } from 'vitest';
import { mergeTarget } from './maybeSame';

describe('Maybe the same', () => {
  it('shows the pair once, on the food the server says would go', () => {
    const moringa = {
      id: 40,
      name: 'Drumsticks (moringa)',
      maybe_same: [{ id: 12, name: 'Drumsticks', merge_into: 12, merge_this: true }]
    };
    const sticks = {
      id: 12,
      name: 'Drumsticks',
      maybe_same: [{ id: 40, name: 'Drumsticks (moringa)', merge_into: 12, merge_this: false }]
    };
    expect(mergeTarget(moringa)?.id).toBe(12);
    expect(mergeTarget(sticks)).toBeUndefined();
  });
});
