import { describe, expect, it } from 'vitest';
import { MAX_ADD_TEXT, readAs, splitAmount } from './addAmount';
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

describe('splitAmount: a name that starts with a number (review round 1)', () => {
  it('keeps "00 flour", "007 tea" and "0 g butter" whole: a leading zero is part of the name', () => {
    expect(splitAmount('00 flour')).toBeNull();
    expect(splitAmount('007 tea')).toBeNull();
    expect(splitAmount('0 g butter')).toBeNull();
    expect(splitAmount('0.5 l milk')).toEqual({ amountText: '0.5 l', name: 'milk' });
  });
  it('refuses text longer than a name and its amount can be', () => {
    expect(splitAmount(`1 ${'a'.repeat(MAX_ADD_TEXT)}`)).toBeNull();
  });
});

describe('readAs: the amount as it will be read, for the match row', () => {
  const garlic = {
    counted_as: 'weight' as const,
    sizes: [],
    count_word: null,
    count_word_plural: null
  };
  it('says the unit a bare number gets', () => {
    expect(readAs('2', garlic)).toBe('2 g');
    expect(readAs('2', { ...garlic, counted_as: 'volume' })).toBe('2 ml');
    expect(readAs('2', { ...garlic, counted_as: 'count' })).toBe('2');
  });
  it('keeps a typed unit', () => {
    expect(readAs('1 l', { ...garlic, counted_as: 'volume' })).toBe('1 l');
  });
});
