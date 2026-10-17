import { describe, expect, it } from 'vitest';
import type { AmountOut } from './client/types';
import { pickFor } from './picks';

const stock = (
  amount: number,
  count: number,
  name: string,
  size: number
): { stock: AmountOut } => ({
  stock: {
    amount,
    display: '',
    as_sold: { count, size: { id: 1, name, plural: `${name}s`, amount: size } }
  }
});

describe('which ¼ · ½ · ¾ · Full pick matches what is left', () => {
  it('eggs: 9 left of a dozen is ¾ (not Full)', () => {
    expect(pickFor(stock(9, 9, 'dozen', 12))).toBe(0.75);
  });

  it('bread: 14 of a 20-slice loaf is ¾', () => {
    expect(pickFor(stock(14, 14, 'loaf', 20))).toBe(0.75);
  });

  it('yoghurt: 250 g of a 500 g tub is ½', () => {
    expect(pickFor(stock(250, 0.5, 'tub', 500))).toBe(0.5);
  });

  it('stays between ¼ and Full, and knows nothing without a size', () => {
    expect(pickFor(stock(20, 0.04, 'packet', 500))).toBe(0.25);
    expect(pickFor(stock(500, 1, 'packet', 500))).toBe(1);
    expect(pickFor({ stock: { amount: 200, display: '200 g', as_sold: null } })).toBeUndefined();
  });
});
