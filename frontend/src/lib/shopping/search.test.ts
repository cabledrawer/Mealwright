// The add box offline: the phone's copy searched by any name, as the server would (11.1).

import { describe, expect, it } from 'vitest';
import { food, sampleCopy } from '#lib/testing/fakeShopping.js';
import { fold, rankMatches, searchCopy } from './search';

const copy = () => {
  const c = sampleCopy();
  c.foods.push(
    food(8, 'Jalapeño', 'veg_fruit'),
    food(9, 'Pigeon peas', 'dry_goods', { other_names: ['arhar dal'] }),
    food(-1, 'Made offline', 'other')
  );
  c.foods[4]!.other_names = ['thuvaram paruppu', 'arhar dal'];
  return c;
};
const names = (text: string) => searchCopy(copy(), text).map((f) => f.name);

describe('searching the copy (the add box offline)', () => {
  it('finds by the start of the name, then anywhere in it', () => {
    expect(names('pa')).toEqual(['Paneer', 'Toor dal']); // Toor dal: "thuvaram paruppu"
    expect(names('dal')).toEqual(['Toor dal', 'Pigeon peas']);
  });

  it('finds by another name, and says which', () => {
    const found = searchCopy(copy(), 'thuva');
    expect(found.map((f) => [f.name, f.matched_name])).toEqual([['Toor dal', 'thuvaram paruppu']]);
  });

  it('leaves out removed and merged ingredients, as the server does', () => {
    const c = copy();
    c.foods.push(
      food(10, 'Arhar dal (old)', 'dry_goods', { removed: true }),
      food(11, 'Arhar', 'dry_goods', { merged_into_id: 9 })
    );
    expect(searchCopy(c, 'arhar').map((f) => f.name)).toEqual(['Pigeon peas', 'Toor dal']);
  });

  it('ignores case and accents', () => {
    expect(fold('  Jalapeño ')).toBe('jalapeno');
    expect(names('JALAPENO')).toEqual(['Jalapeño']);
  });

  it('gives what the add box needs: ID, name, how it is counted, its place', () => {
    const c = copy();
    c.foods[2]!.place_id = 1;
    expect(searchCopy(c, 'yog')[0]).toMatchObject({
      id: 3,
      name: 'Yoghurt',
      counted_as: 'weight',
      staple: false,
      place: { id: 1, name: 'Fridge' }
    });
  });

  it('leaves out ingredients this phone made that the server has no ID for yet', () => {
    expect(names('made')).toEqual([]);
  });

  it('nothing typed: nothing found; at most 8', () => {
    expect(names('  ')).toEqual([]);
    const c = sampleCopy();
    for (let i = 0; i < 12; i++) c.foods.push(food(100 + i, `Rice ${i}`, 'dry_goods'));
    expect(searchCopy(c, 'rice')).toHaveLength(8);
  });
});

describe('ranking the matches the add box offers (F224)', () => {
  const names = (rows: { name: string }[]) => rows.map((r) => r.name);

  it('puts the name typed first, then its plural, then the rest in their order', () => {
    const rows = [
      { name: 'Onion powder' },
      { name: 'Onion rings' },
      { name: 'Onions' },
      { name: 'Onion' }
    ];
    expect(names(rankMatches(rows, 'onion'))).toEqual([
      'Onion',
      'Onions',
      'Onion powder',
      'Onion rings'
    ]);
  });

  it('finds the singular when the plural is typed, and ignores capitals and accents', () => {
    const rows = [{ name: 'Onion powder' }, { name: 'Onion' }];
    expect(names(rankMatches(rows, 'Onions'))).toEqual(['Onion', 'Onion powder']);
    expect(
      names(rankMatches([{ name: 'Jalapeño chilli' }, { name: 'Jalapeno' }], 'JALAPENO'))
    ).toEqual(['Jalapeno', 'Jalapeño chilli']);
  });

  it('leaves the order alone when nothing is an exact or plural match', () => {
    const rows = [{ name: 'Tahini paste' }, { name: 'Tahini dressing' }];
    expect(rankMatches(rows, 'tahini')).toEqual(rows);
  });
});
