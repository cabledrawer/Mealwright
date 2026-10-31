import { describe, expect, it } from 'vitest';
import type { FoodRow } from './client/types';
import { newNameFor } from './ingredientSearch';

const row = (name: string, other_names: string[] = []) => ({ name, other_names }) as FoodRow;

describe('newNameFor (F97)', () => {
  const found = [row('Chilli powder', ['red chilli powder']), row('Chillies')];

  it('offers the typed name when it is not exactly a name, also beside partial matches', () => {
    expect(newNameFor('chilli flakes', found)).toBe('chilli flakes');
    expect(newNameFor('chilli', found)).toBe('chilli');
    expect(newNameFor('  chilli   flakes ', [])).toBe('chilli flakes');
  });

  it('offers nothing for an exact name or other name, case and spacing ignored', () => {
    expect(newNameFor('Chilli powder', found)).toBeNull();
    expect(newNameFor(' CHILLI  powder ', found)).toBeNull();
    expect(newNameFor('Red Chilli Powder', found)).toBeNull();
  });

  it('offers nothing for empty text', () => {
    expect(newNameFor('', found)).toBeNull();
    expect(newNameFor('   ', [])).toBeNull();
  });
});
