import { describe, expect, it } from 'vitest';
import { readAmount } from './importAmount';

describe('the amount typed on a Check line', () => {
  it('reads whole numbers, decimals, fractions and mixed numbers', () => {
    expect(readAmount('2')).toEqual({ amount: 2 });
    expect(readAmount(' 0,5 ')).toEqual({ amount: 0.5 });
    expect(readAmount('½')).toEqual({ amount: 0.5 });
    expect(readAmount('1½')).toEqual({ amount: 1.5 });
    expect(readAmount('1 1/2')).toEqual({ amount: 1.5 });
    expect(readAmount('3/4')).toEqual({ amount: 0.75 });
    expect(readAmount('⅓')).toEqual({ amount: 0.333 });
  });

  it('reads an improper fraction as it is written, never as a whole number and a fraction (RF4)', () => {
    expect(readAmount('10/3')).toEqual({ amount: 3.333 });
    expect(readAmount('15/2')).toEqual({ amount: 7.5 });
    expect(readAmount('20/3')).toEqual({ amount: 6.667 });
    expect(readAmount('11/4')).toEqual({ amount: 2.75 });
    expect(readAmount('2 3/4')).toEqual({ amount: 2.75 });
    expect(readAmount('12 1/2')).toEqual({ amount: 12.5 });
    expect(readAmount('2 ¾')).toEqual({ amount: 2.75 });
    expect(readAmount('1 2')).toBeNull();
  });

  it('takes an empty box as no amount', () => {
    expect(readAmount('')).toEqual({ amount: null });
    expect(readAmount('   ')).toEqual({ amount: null });
  });

  it('refuses what is not a number above nothing', () => {
    for (const text of ['abc', '0', '-2', '2 cups', '1/0', '1e5', '999999', '1.2.3']) {
      expect(readAmount(text), text).toBeNull();
    }
  });
});
