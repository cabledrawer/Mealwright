import { describe, expect, it } from 'vitest';
import { canRemove } from './canRemove';

describe('removing an ingredient', () => {
  it('is offered only when none is in the pantry', () => {
    expect(canRemove({ stock: null })).toBe(true);
    expect(canRemove({ stock: { amount: 0, display: '0 g' } })).toBe(true);
    expect(canRemove({ stock: { amount: 750, display: '1½ packets · about 750 g' } })).toBe(false);
  });
});
