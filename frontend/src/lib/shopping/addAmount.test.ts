import { describe, expect, it } from 'vitest';
import { splitAmount } from './addAmount';
import { toBaseAmount } from './amountEdit';

describe('splitAmount: an amount in front of a name in the add box (F63)', () => {
  it('reads "1 l milk" as milk, 1 l', () => {
    expect(splitAmount('1 l milk')).toEqual({ amountText: '1 l', name: 'milk' });
  });
  it('reads units written out, with or without a space', () => {
    expect(splitAmount('2 litres milk')).toEqual({ amountText: '2 l', name: 'milk' });
    expect(splitAmount('250g butter')).toEqual({ amountText: '250 g', name: 'butter' });
    expect(splitAmount('1.5 kg flour')).toEqual({ amountText: '1.5 kg', name: 'flour' });
    expect(splitAmount('500 ml cream')).toEqual({ amountText: '500 ml', name: 'cream' });
  });
  it('reads a bare number and fractions', () => {
    expect(splitAmount('3 eggs')).toEqual({ amountText: '3', name: 'eggs' });
    expect(splitAmount('½ cabbage')).toEqual({ amountText: '½', name: 'cabbage' });
    expect(splitAmount('1½ l milk')).toEqual({ amountText: '1½ l', name: 'milk' });
  });
  it('keeps a name that starts like a unit', () => {
    expect(splitAmount('1 lime')).toEqual({ amountText: '1', name: 'lime' });
    expect(splitAmount('2 garlic')).toEqual({ amountText: '2', name: 'garlic' });
  });
  it('finds nothing in a plain name or a number alone', () => {
    expect(splitAmount('milk')).toBeNull();
    expect(splitAmount('250 g')).toBeNull();
    expect(splitAmount('  ')).toBeNull();
  });
  it('hands the amount on in a form the amount reader takes', () => {
    const milk = {
      counted_as: 'volume' as const,
      sizes: [],
      count_word: null,
      count_word_plural: null
    };
    expect(toBaseAmount(splitAmount('1 l milk')!.amountText, milk)).toEqual({
      amount: 1000,
      sizeId: null
    });
  });
});
