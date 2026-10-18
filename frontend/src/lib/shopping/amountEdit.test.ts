import { describe, expect, it } from 'vitest';
import { toBaseAmount, type EditFood } from './amountEdit';

const dal: EditFood = {
  counted_as: 'weight',
  count_word: null,
  count_word_plural: null,
  sizes: [{ id: 12, name: 'packet', plural: 'packets', amount: 500, usual: true }]
};

describe('toBaseAmount', () => {
  it('reads grams, kilos and its own sizes', () => {
    expect(toBaseAmount('250 g', dal)).toEqual({ amount: 250, sizeId: null });
    expect(toBaseAmount('2 kg', dal)).toEqual({ amount: 2000, sizeId: null });
    expect(toBaseAmount('1½ packets', dal)).toEqual({ amount: 750, sizeId: 12 });
  });
  it('uses the usual size when only a number is typed', () => {
    expect(toBaseAmount('2', dal)).toEqual({ amount: 1000, sizeId: 12 });
  });
  it('turns down units a phone cannot convert offline', () => {
    expect(toBaseAmount('2 cups', dal)).toMatchObject({
      problem: expect.stringContaining('g, kg')
    });
    expect(toBaseAmount('', dal)).toMatchObject({ problem: expect.any(String) });
  });
  it('counts items', () => {
    const eggs: EditFood = {
      counted_as: 'count',
      count_word: null,
      count_word_plural: null,
      sizes: []
    };
    expect(toBaseAmount('6', eggs)).toEqual({ amount: 6, sizeId: null });
  });
});
