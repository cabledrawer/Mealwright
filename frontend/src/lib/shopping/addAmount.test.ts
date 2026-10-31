import { describe, expect, it } from 'vitest';
import { countedAsFor, MAX_ADD_TEXT, readAs, readForNew, splitAmount } from './addAmount';
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
  it('keeps "00 flour" and "007 tea" whole: a leading zero is part of the name', () => {
    expect(splitAmount('00 flour')).toBeNull();
    expect(splitAmount('007 tea')).toBeNull();
    expect(splitAmount('0.5 l milk')).toEqual({ amountText: '0.5 l', name: 'milk' });
  });
  it('reads "0 g butter" as Butter with an amount of nothing (cabledrawer 29 Oct)', () => {
    expect(splitAmount('0 g butter')).toEqual({ amountText: '0 g', name: 'butter', zero: true });
    expect(splitAmount('0 butter')).toEqual({ amountText: '0', name: 'butter', zero: true });
    expect(splitAmount('0,0 kg rice')).toEqual({ amountText: '0,0 kg', name: 'rice', zero: true });
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
  it('keeps a typed unit, written as the app writes it', () => {
    expect(readAs('1 l', { ...garlic, counted_as: 'volume' })).toBe('1 L');
  });
  it('names a packet size in the plural when there is more than one', () => {
    const packet = { id: 1, name: 'packet', plural: 'packets', amount: 100, usual: true };
    const withPacket = { ...garlic, sizes: [packet] } as never;
    expect(readAs('2', withPacket)).toBe('2 packets');
    expect(readAs('1', withPacket)).toBe('1 packet');
  });
});

describe('splitAmount: the ways an ingredient is sold (cabledrawer 30 Oct: "2 packets milk")', () => {
  it('reads "2 packets milk" as milk, 2 packets, the same as "2 packet milk"', () => {
    const one = splitAmount('2 packets milk');
    expect(one).toEqual({ amountText: '2 packets', name: 'milk' });
    expect(splitAmount('2 packet milk')?.name).toBe(one?.name);
    expect(splitAmount('1 loaf bread')).toEqual({ amountText: '1 loaf', name: 'bread' });
    expect(splitAmount('2 tins chopped tomatoes')).toEqual({
      amountText: '2 tins',
      name: 'chopped tomatoes'
    });
  });
  it('skips an "of" after the way it is sold', () => {
    expect(splitAmount('2 bags of ice')).toEqual({ amountText: '2 bags', name: 'ice' });
    expect(splitAmount('1 l of milk')).toEqual({ amountText: '1 l', name: 'milk' });
  });
  it('keeps a name that starts like a pack word, and a pack word alone is no name', () => {
    expect(splitAmount('2 tinned tomatoes')).toEqual({ amountText: '2', name: 'tinned tomatoes' });
    expect(splitAmount('2 packets')).toBeNull();
  });
  it("is read for the ingredient's own packet size", () => {
    const milk = {
      counted_as: 'volume' as const,
      sizes: [{ name: 'packet', plural: 'packets', usual: false, amount: 568 }],
      count_word: null,
      count_word_plural: null
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    expect(readAs('2 packets', milk as any)).toBe('2 packets');
  });
});

describe('countedAsFor: the typed amount says how a new ingredient is counted (F83)', () => {
  it('is by volume for litres and millilitres, by weight for grams and kilos', () => {
    for (const text of ['1 l orange juice', '250 ml cream', '1½ l milk']) {
      expect(countedAsFor(splitAmount(text)!.amountText), text).toBe('volume');
    }
    for (const text of ['250 g butter', '1.5 kg flour']) {
      expect(countedAsFor(splitAmount(text)!.amountText), text).toBe('weight');
    }
  });
  it('is one by one for a bare number, and says nothing for a packet', () => {
    expect(countedAsFor(splitAmount('3 eggs')!.amountText)).toBe('count');
    expect(countedAsFor(splitAmount('2 packets milk')!.amountText)).toBeNull();
  });
});

describe('readForNew: "2 packets milk" for an ingredient made in the same step', () => {
  const milk = {
    counted_as: 'volume' as const,
    sizes: [{ name: 'packet', amount: 1, unit: 'l' }]
  };
  it('reads the amount against the size just added in the dialog', () => {
    expect(readForNew('2 packets', milk)).toEqual({ amount: 2000, sizeId: null });
    expect(readForNew('1 packet', milk)).toEqual({ amount: 1000, sizeId: null });
  });
  it('still reads plain units', () => {
    expect(readForNew('1 l', { counted_as: 'volume', sizes: [] })).toEqual({
      amount: 1000,
      sizeId: null
    });
  });
  it('says it cannot read a packet there is no size for, so the add carries on without an amount', () => {
    expect('problem' in readForNew('2 packets', { counted_as: 'volume', sizes: [] })).toBe(true);
  });
});
