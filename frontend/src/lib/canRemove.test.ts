import { describe, expect, it } from 'vitest';
import { canRemove } from './canRemove';

describe('removing an ingredient', () => {
  it('is offered only when none is in the pantry', () => {
    expect(canRemove({ stock: null })).toBe(true);
    expect(canRemove({ stock: { amount: 0, display: '0 g' } })).toBe(true);
    expect(canRemove({ stock: { amount: 750, display: 'about 750 g · 1½ packets' } })).toBe(false);
  });

  it('is not blocked by the recipes that use it (cabledrawer 19 Oct)', () => {
    expect(canRemove({ stock: null, made_by: null })).toBe(true);
  });

  it('is not offered for a recipe’s own made-ahead ingredient', () => {
    expect(canRemove({ stock: null, made_by: { id: 3, name: 'Dosa batter' } })).toBe(false);
  });
});
