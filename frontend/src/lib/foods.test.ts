import { describe, expect, it } from 'vitest';
import { countedAs, describeSaleUnit, listFoods, matchesSearch, type Food } from './foods';

function food(overrides: Partial<Food>): Food {
  return {
    id: 1,
    name: 'Toor dal',
    otherNames: ['thuvaram paruppu', 'arhar dal'],
    base: 'g',
    saleUnits: [{ name: 'packet', amount: 500, usual: true }],
    cupWeight: '',
    runningLow: '',
    placeId: null,
    shopId: null,
    staple: false,
    standInIds: [],
    ...overrides
  };
}

describe('search by any name', () => {
  const dal = food({});

  it('finds a food by its own name or any other name, ignoring case', () => {
    expect(matchesSearch(dal, 'toor')).toBe(true);
    expect(matchesSearch(dal, 'ARHAR')).toBe(true);
    expect(matchesSearch(dal, 'thuvaram  paruppu')).toBe(true);
    expect(matchesSearch(dal, 'moong')).toBe(false);
  });

  it('ignores accents and spare spaces, and an empty search finds everything', () => {
    expect(matchesSearch(food({ name: 'Crème fraîche' }), 'creme')).toBe(true);
    expect(matchesSearch(dal, '   ')).toBe(true);
  });
});

describe('listFoods', () => {
  const foods = [
    food({ id: 1, name: 'Turmeric', otherNames: [], staple: true }),
    food({ id: 2, name: 'Drumsticks', otherNames: [], maybeSameAsId: 3 }),
    food({ id: 3, name: 'Bread', otherNames: [] })
  ];
  const names = (list: Food[]) => list.map((f) => f.name);

  it('lists in name order and filters', () => {
    expect(names(listFoods(foods, '', 'all'))).toEqual(['Bread', 'Drumsticks', 'Turmeric']);
    expect(names(listFoods(foods, '', 'staples'))).toEqual(['Turmeric']);
    expect(names(listFoods(foods, '', 'maybe'))).toEqual(['Drumsticks']);
    expect(names(listFoods(foods, 'bre', 'all'))).toEqual(['Bread']);
  });
});

describe('how a food is counted, in plain words', () => {
  it('matches the mockups', () => {
    expect(countedAs(food({}))).toBe('Packets · 500 g');
    expect(countedAs(food({ base: 'count', saleUnits: [] }))).toBe('Count');
    expect(countedAs(food({ base: 'count', countName: 'slice' }))).toBe('Slices');
    expect(countedAs(food({ staple: true }))).toBe('Staple');
  });

  it('describes each size it is sold in', () => {
    const dal = food({});
    expect(describeSaleUnit({ name: 'packet', amount: 500, usual: true }, dal)).toBe(
      'Packet = 500 g'
    );
    expect(describeSaleUnit({ name: 'bag', amount: 1000, usual: false }, dal)).toBe('Bag = 1 kg');
    const bread = food({ base: 'count', countName: 'slice' });
    expect(describeSaleUnit({ name: 'loaf', amount: 20, usual: true }, bread)).toBe(
      'Loaf = 20 slices'
    );
    const eggs = food({ name: 'Egg', base: 'count' });
    expect(describeSaleUnit({ name: 'dozen', amount: 12, usual: true }, eggs)).toBe(
      'Dozen = 12 eggs'
    );
  });
});
