import { describe, expect, it } from 'vitest';
import { packLine, wholePacks } from './packLine';
import type { ShopFood } from './types';

const NBSP = ' ';

function food(counted_as: ShopFood['counted_as'], sizes: ShopFood['sizes'], staple = false) {
  return { id: 1, name: 'Ghee', counted_as, staple, sizes } as ShopFood;
}
const size = (name: string, plural: string, amount: number, usual = true) => ({
  id: 1,
  name,
  plural,
  amount,
  usual
});

describe('what to buy in whole packs', () => {
  it('holds the need without a spare pack', () => {
    for (const pack of [1, 7, 200, 400, 500, 1000]) {
      for (let need = 1; need <= 3000; need += 7) {
        const packs = wholePacks(need, pack);
        expect(packs * pack).toBeGreaterThanOrEqual(need);
        expect((packs - 1) * pack).toBeLessThan(need);
      }
    }
  });

  // The same lines the server gives (backend/tests/test_buying.py).
  it('says the packs and the need, as the server does', () => {
    const ghee = food('weight', [size('jar', 'jars', 500)]);
    expect(packLine(ghee, 120)).toBe(`1${NBSP}jar (500${NBSP}g) · 120${NBSP}g needed`);
    const dal = food('weight', [size('bag', 'bags', 1000)]);
    expect(packLine(dal, 1200)).toBe(`2${NBSP}bags (1${NBSP}kg) · 1.2${NBSP}kg needed`);
    const coconut = food('volume', [size('tin', 'tins', 400)]);
    expect(packLine(coconut, 600)).toBe(`2${NBSP}tins (400${NBSP}ml) · 600${NBSP}ml needed`);
  });

  it('an exact fit is one pack, not two', () => {
    expect(packLine(food('weight', [size('tub', 'tubs', 750)]), 750)).toContain(`1${NBSP}tub`);
  });

  it('uses the Usual size, else the only one (F122, review r1 L4)', () => {
    const both = food('weight', [size('tin', 'tins', 1000, false), size('jar', 'jars', 500)]);
    expect(packLine(both, 100)).toContain('jar');
    const one = food('weight', [size('tin', 'tins', 1000, false)]);
    expect(packLine(one, 100)).toContain('tin');
    const several = food('weight', [
      size('tin', 'tins', 1000, false),
      size('jar', 'jars', 500, false)
    ]);
    expect(packLine(several, 100)).toBeNull();
  });

  // Review r1 M1: the same rounding and words as the server's amounts.exact_text / count_text.
  it('rounds and words the amounts as the server does', () => {
    const jar = food('weight', [size('jar', 'jars', 500)]);
    expect(packLine(jar, 123.4)).toBe(`1${NBSP}jar (500${NBSP}g) · 123${NBSP}g needed`);
    expect(packLine(jar, 7.25)).toBe(`1${NBSP}jar (500${NBSP}g) · 7.3${NBSP}g needed`);
    expect(packLine(jar, 0.02)).toBe(`1${NBSP}jar (500${NBSP}g) · under 0.1${NBSP}g needed`);
    const bag = food('weight', [size('bag', 'bags', 5000)]);
    expect(packLine(bag, 1234.5)).toBe(`1${NBSP}bag (5${NBSP}kg) · 1.235${NBSP}kg needed`);
    const eggs = {
      ...food('count', [size('box', 'boxes', 6)]),
      count_word: 'egg',
      count_word_plural: 'eggs'
    } as ShopFood;
    expect(packLine(eggs, 5)).toBe(`1${NBSP}box (6${NBSP}eggs) · 5${NBSP}eggs needed`);
    expect(packLine(eggs, 1.5)).toBe(`1${NBSP}box (6${NBSP}eggs) · 1½${NBSP}eggs needed`);
    const plain = food('count', [size('box', 'boxes', 6)]);
    expect(packLine(plain, 8)).toBe(`2${NBSP}boxes (6) · 8 needed`);
  });

  it('says nothing with no size, no amount or a staple', () => {
    expect(packLine(food('weight', []), 120)).toBeNull();
    expect(packLine(food('weight', [size('jar', 'jars', 500)]), null)).toBeNull();
    expect(packLine(food('weight', [size('jar', 'jars', 500)], true), 120)).toBeNull();
    expect(packLine(undefined, 120)).toBeNull();
  });
});
