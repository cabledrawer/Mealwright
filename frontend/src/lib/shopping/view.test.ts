import { describe, expect, it } from 'vitest';
import { groupByShop, listCounts, planWords, subtitle, syncedWith } from './view';
import type { ListItem, ShoppingCopy } from './types';

const wren = { login_id: 2, name: 'Wren' };
const arlo = { login_id: 3, name: 'Arlo' };
const me = { login_id: 1, name: 'Tess' };

function item(id: string, food_id: number, extra: Partial<ListItem> = {}): ListItem {
  return {
    id,
    list_id: 'L',
    food_id,
    shop_id: 1,
    amount: 1,
    size_id: null,
    display: '1',
    source: 'typed',
    hand_edited: false,
    put_away_place_id: null,
    ticks: [],
    added_by: null,
    deleted: false,
    merged_into_id: null,
    ...extra
  };
}

const food = (id: number, name: string, aisle: string) => ({
  id,
  name,
  other_names: [],
  counted_as: 'weight' as const,
  staple: false,
  aisle,
  shop_id: null,
  place_id: null,
  sizes: null
});

const tick = { id: 't', by: me, at: '', place_id: null, bought: null, standing: true };

const copy: ShoppingCopy = {
  cursor: 1,
  lists: [{ id: 'L', name: 'This week', main: true, position: 0, removed: false }],
  foods: [
    food(1, 'Tomatoes', 'veg_fruit'),
    food(2, 'Onions', 'veg_fruit'),
    food(3, 'Yoghurt', 'dairy'),
    food(4, 'Mystery', 'other'),
    food(5, 'Rice', 'dry_goods'),
    food(6, 'Coriander', 'veg_fruit')
  ],
  shops: [
    { id: 2, name: 'Indian grocer', position: 1, aisle_order: null },
    { id: 1, name: 'Supermarket', position: 0, aisle_order: null }
  ],
  items: [
    item('a', 1),
    item('b', 2),
    item('c', 3),
    item('d', 4),
    item('e', 5, { shop_id: null }),
    item('f', 6, { ticks: [tick] }),
    item('g', 2, { shop_id: 2, deleted: true }),
    item('h', 99)
  ],
  notes: [],
  questions: [],
  places: [],
  people: null,
  removed: {}
};

describe('groupByShop', () => {
  const groups = groupByShop(copy, 'L');

  it('puts shops in order and Any shop last', () => {
    expect(groups.map((g) => g.name)).toEqual(['Supermarket', 'Any shop']);
  });

  it('uses the spec aisle names, items by name, Other for no aisle, Other last', () => {
    const shop = groups[0]!;
    expect(shop.aisles.map((a) => a.name)).toEqual(['Veg & fruit', 'Dairy', 'Other']);
    expect(shop.aisles[0]!.items.map((v) => v.food.name)).toEqual(['Onions', 'Tomatoes']);
  });

  it('folds ticked items into the trolley and counts only what is left to buy', () => {
    const shop = groups[0]!;
    expect(shop.trolley.map((v) => v.food.name)).toEqual(['Coriander']);
    expect(shop.toBuy).toBe(4);
  });

  it('skips deleted items and items whose ingredient is gone', () => {
    expect(
      groups.flatMap((g) => g.aisles.flatMap((a) => a.items)).map((v) => v.item.id)
    ).not.toContain('g');
    expect(
      groups.flatMap((g) => g.aisles.flatMap((a) => a.items)).map((v) => v.item.id)
    ).not.toContain('h');
  });

  it('follows a shop’s own aisle order', () => {
    const own = { ...copy, shops: [{ ...copy.shops[1]!, aisle_order: ['dairy'] }] };
    expect(groupByShop(own, 'L')[0]!.aisles.map((a) => a.key)).toEqual([
      'dairy',
      'veg_fruit',
      'other'
    ]);
  });

  it('counts a list', () => {
    expect(listCounts(copy, copy.lists[0]!)).toEqual({ toBuy: 5, ticked: 1 });
  });
});

describe('subtitle', () => {
  it('says the list was built from the plan, in the look-ahead’s words (docs/dev/words.md 21)', () => {
    expect(subtitle(main, 12, [me, wren], 1, false, 'phone', planWords(7))).toBe(
      '12 to buy · built from this week’s plan · synced with Wren'
    );
    expect(subtitle(main, 12, [me, wren], 1, true, 'computer', planWords(7))).toBe(
      '12 to buy · built from this week’s plan · offline, saving on this computer'
    );
    expect(planWords(1)).toBe('today’s plan');
    expect(planWords(10)).toBe('the plan for the next 10 days');
    expect(planWords(null)).toBe('the plan');
    // An extra list is never "built from the plan".
    expect(subtitle({ ...main, main: false }, 5, [me, wren], 1, false, 'phone', planWords(7))).toBe(
      'Extra list · 5 · ticked items still go to the pantry'
    );
  });
  const main = { id: 'L', name: 'This week', main: true, position: 0, removed: false };
  it('says who it is synced with', () => {
    expect(subtitle(main, 12, [me, wren], 1)).toBe('12 to buy · synced with Wren');
    expect(subtitle(main, 12, [me, wren, arlo], 1)).toBe('12 to buy · synced with Wren and Arlo');
    expect(subtitle(main, 12, [me, wren, arlo, { login_id: 4, name: 'Mo' }], 1)).toBe(
      '12 to buy · synced with Wren and 2 others'
    );
  });
  it('FE-2: says offline, saving on this phone (or computer) while offline', () => {
    expect(subtitle(main, 12, [me, wren], 1, true)).toBe(
      '12 to buy · offline, saving on this phone'
    );
    expect(subtitle(main, 12, null, 1, true, 'phone')).toBe(
      '12 to buy · offline, saving on this phone'
    );
    expect(subtitle(main, 12, [me, wren], 1, true, 'computer')).toBe(
      '12 to buy · offline, saving on this computer'
    );
  });
  it('keeps an extra list short while offline (cabledrawer 18 Oct)', () => {
    expect(subtitle({ ...main, main: false }, 5, [me, wren], 1, true)).toBe(
      'Extra list · 5 · offline'
    );
    expect(subtitle({ ...main, main: false }, 5, [me, wren], 1, true, 'computer')).toBe(
      'Extra list · 5 · offline'
    );
    expect(subtitle({ ...main, main: false }, 5, [me, wren], 1)).toBe(
      'Extra list · 5 · ticked items still go to the pantry'
    );
  });
  it('says saved for one login', () => {
    expect(subtitle(main, 12, [me], 1)).toBe('12 to buy · saved');
  });
  it('keeps the mockup line for extra lists', () => {
    expect(subtitle({ ...main, main: false }, 6, [me], 1)).toBe(
      'Extra list · 6 · ticked items still go to the pantry'
    );
  });
  it('leaves the people out when the server cannot say', () => {
    expect(subtitle(main, 3, null, 1)).toBe('3 to buy');
    expect(syncedWith([me], 1)).toBeNull();
  });
});
