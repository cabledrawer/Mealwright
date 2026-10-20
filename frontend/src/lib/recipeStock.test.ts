import { describe, expect, it } from 'vitest';
import type { LineStock } from './client/recipes';
import { markFor, toAdd } from './recipeStock';

const stock = (id: number, state: LineStock['state'], place: string | null = null): LineStock => ({
  line_id: id,
  food: { id: 100 + id, name: `Food ${id}` },
  state,
  place
});

describe('the mark beside a line', () => {
  it('says where it is, or that it is a staple', () => {
    expect(markFor(stock(1, 'in_stock', 'Freezer'), false)).toEqual({
      kind: 'in',
      label: 'Freezer'
    });
    expect(markFor(stock(1, 'staple'), true)).toEqual({ kind: 'staple', label: 'Staple' });
  });

  it('something in stock stays in stock even when it is on the list too', () => {
    expect(markFor(stock(1, 'in_stock', 'Cupboard'), true)?.kind).toBe('in');
  });

  it('on the list wins over short and missing', () => {
    expect(markFor(stock(1, 'missing'), true)).toEqual({ kind: 'list', label: 'On list' });
    expect(markFor(stock(1, 'short'), true)?.kind).toBe('list');
  });

  it('short says not enough; missing has no words; a line the server skips has no mark', () => {
    expect(markFor(stock(1, 'short'), false)).toEqual({ kind: 'short', label: 'Not enough' });
    expect(markFor(stock(1, 'missing'), false)).toEqual({ kind: 'missing', label: null });
    expect(markFor(undefined, false)).toBeNull();
  });
});

describe('what to add to the shopping list', () => {
  const lines = [
    stock(1, 'in_stock', 'Cupboard'),
    stock(2, 'missing'),
    stock(3, 'short'),
    stock(4, 'staple'),
    stock(5, 'missing'),
    { ...stock(6, 'missing'), food: { id: 102, name: 'Food 2' } } // the same ingredient again
  ];

  it('is the short and missing ones, once each, not already on the list', () => {
    expect(toAdd(lines, () => false).map((f) => f.name)).toEqual(['Food 2', 'Food 3', 'Food 5']);
    expect(toAdd(lines, (id) => id === 105).map((f) => f.name)).toEqual(['Food 2', 'Food 3']);
  });

  it('is empty when everything is in stock or on the list', () => {
    expect(toAdd(lines, () => true)).toEqual([]);
    expect(toAdd([], () => false)).toEqual([]);
  });
});
