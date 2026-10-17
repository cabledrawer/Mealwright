import { describe, expect, it } from 'vitest';
import { parseAmount } from './amountText';
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
});
