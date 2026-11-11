import { describe, expect, it } from 'vitest';
import { MAX_AMOUNT_TEXT, manyOf, parseAmount } from './amountText';
import type { Size } from './client/types';

const packet: Size = {
  id: 12,
  name: 'packet',
  plural: 'packets',
  amount: 500,
  display: 'Packet = 500 g',
  usual: true,
  added_when_shopping: false
};
const dal = {
  counted_as: 'weight' as const,
  sizes: [packet],
  count_word: null,
  count_word_plural: null
};
const bread = {
  counted_as: 'count' as const,
  sizes: [{ ...packet, name: 'loaf', plural: 'loaves', amount: 20 }],
  count_word: 'slice',
  count_word_plural: 'slices'
};

describe('reading a typed amount', () => {
  it('reads fractions and sizes', () => {
    expect(parseAmount('½ packet', dal)).toEqual({ amount: 0.5, unit: 'packet' });
    expect(parseAmount('1½ packets', dal)).toEqual({ amount: 1.5, unit: 'packet' });
    expect(parseAmount('1 1/2 packets', dal)).toEqual({ amount: 1.5, unit: 'packet' });
    expect(parseAmount('0,75 packet', dal)).toEqual({ amount: 0.75, unit: 'packet' });
  });

  it('reads an improper fraction as written: 10/3 is not 1 and 0/3 (RF4)', () => {
    expect(parseAmount('10/3 packets', dal)).toEqual({ amount: 10 / 3, unit: 'packet' });
    expect(parseAmount('15/2', dal)?.amount).toBe(7.5);
    expect(parseAmount('3/4 packet', dal)).toEqual({ amount: 0.75, unit: 'packet' });
    expect(parseAmount('2 3/4 packets', dal)).toEqual({ amount: 2.75, unit: 'packet' });
  });

  it('reads weights and volumes as typed', () => {
    expect(parseAmount('250 g', dal)).toEqual({ amount: 250, unit: 'g' });
    expect(parseAmount('250g', dal)).toEqual({ amount: 250, unit: 'g' });
    expect(parseAmount('1 cup', dal)).toEqual({ amount: 1, unit: 'cup' });
  });

  it('uses the usual size for a bare number, and counts for count foods', () => {
    expect(parseAmount('2', dal)).toEqual({ amount: 2, unit: 'packet' });
    expect(parseAmount('4', bread)).toEqual({ amount: 4, unit: 'count' });
    expect(parseAmount('4 slices', bread)).toEqual({ amount: 4, unit: 'count' });
    expect(parseAmount('1 loaf', bread)).toEqual({ amount: 1, unit: 'loaf' });
  });

  it('says no to things that are not amounts', () => {
    expect(parseAmount('', dal)).toBeNull();
    expect(parseAmount('some', dal)).toBeNull();
    expect(parseAmount('0', dal)).toBeNull();
    expect(parseAmount('1/0 packet', dal)).toBeNull();
  });

  it('reads a number of up to 20 characters, and says no to a longer one', () => {
    expect(MAX_AMOUNT_TEXT).toBe(20);
    expect(parseAmount('0'.repeat(18) + '1½ packets', dal)).toEqual({
      amount: 1.5,
      unit: 'packet'
    });
    expect(parseAmount('0'.repeat(19) + '1½ packets', dal)).toBeNull();
    expect(parseAmount('0'.repeat(15) + '1 1/2', dal)).toEqual({ amount: 1.5, unit: 'packet' });
    expect(parseAmount('0'.repeat(16) + '1 1/2', dal)).toBeNull();
  });

  it('still reads a short number with a long size name', () => {
    const long = { ...packet, name: 'family size packet', plural: 'family size packets' };
    const food = { ...dal, sizes: [long] };
    expect(parseAmount('1½ family size packets', food)).toEqual({
      amount: 1.5,
      unit: 'family size packet'
    });
    expect(parseAmount('2 ' + 'a'.repeat(40), food)).toEqual({ amount: 2, unit: 'a'.repeat(40) });
    expect(parseAmount('2 ' + 'a'.repeat(70), food)).toBeNull();
  });

  it('never gives an endless amount', () => {
    expect(parseAmount('9'.repeat(400), dal)).toBeNull();
    expect(parseAmount('9'.repeat(400) + ' g', dal)).toBeNull();
  });

  it('says no to very long text quickly', () => {
    const started = performance.now();
    expect(parseAmount('1'.repeat(200_000), dal)).toBeNull();
    expect(parseAmount('1 ' + 'a'.repeat(200_000), dal)).toBeNull();
    expect(parseAmount('1' + ' '.repeat(100_000) + 'g', dal)).toBeNull();
    expect(performance.now() - started).toBeLessThan(100);
  });
});

describe('manyOf (F197)', () => {
  it('makes a counted ingredient plural, lower case, like the server', () => {
    expect(manyOf('Lemon')).toBe('lemons');
    expect(manyOf('Mango')).toBe('mangos');
    expect(manyOf('Cherry')).toBe('cherries');
    expect(manyOf('Red onion')).toBe('red onions');
    expect(manyOf('Eggs')).toBe('eggs');
    expect(manyOf('Peach')).toBe('peaches');
  });
});

// The same list is in backend/tests/test_amounts.py (SHARED_PLURALS): the server and the screen
// make the plural of a counted ingredient's name by one rule, so the two lists must not drift.
describe('manyOf, the list shared with the server', () => {
  it.each([
    ['Lemon', 'lemons'],
    ['Potato', 'potatoes'],
    ['Tomato', 'tomatoes'],
    ['Leaf', 'leaves'],
    ['Loaf', 'loaves'],
    ['Fish', 'fish'],
    ['Cherry', 'cherries'],
    ['Peach', 'peaches'],
    ['Glass', 'glasses'],
    ['Red onion', 'red onions'],
    ['Eggs', 'eggs']
  ])('%s → %s', (name, many) => {
    expect(manyOf(name)).toBe(many);
  });
});
