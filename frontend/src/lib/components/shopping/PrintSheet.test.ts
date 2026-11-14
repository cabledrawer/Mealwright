// The shopping list on paper (mockup Print-ShoppingList095-A4; proposed, for cabledrawer).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import type { ListItem, ShopFood } from '#lib/shopping/types.js';
import type { ShopGroup, ViewItem } from '#lib/shopping/view.js';
import PrintSheet from './PrintSheet.svelte';

const food = (id: number, name: string): ShopFood => ({
  id,
  name,
  other_names: [],
  counted_as: 'count',
  staple: false,
  aisle: 'Fruit & veg',
  shop_id: null,
  place_id: null,
  sizes: []
});

const view = (id: number, name: string, display: string | null): ViewItem => ({
  item: {
    id: `i${id}`,
    list_id: 'l',
    food_id: id,
    shop_id: null,
    amount: null,
    size_id: null,
    display,
    source: 'hand',
    hand_edited: false,
    put_away_place_id: null,
    ticks: [],
    added_by: null,
    deleted: false,
    merged_into_id: null
  } as ListItem,
  food: food(id, name),
  ticks: []
});

const group = (name: string, aisles: [string, ViewItem[]][], trolley: ViewItem[] = []) =>
  ({
    shopId: name === 'Any shop' ? null : name.length,
    name,
    aisles: aisles.map(([n, items]) => ({ key: n, name: n, items })),
    trolley,
    ghosts: [],
    toBuy: aisles.reduce((n, [, items]) => n + items.length, 0)
  }) satisfies ShopGroup;

let shown: { container: HTMLElement; app: object }[] = [];
afterEach(() => {
  for (const s of shown) {
    void unmount(s.app);
    s.container.remove();
  }
  shown = [];
});

function render(props: { groups: ShopGroup[]; builtFrom?: string | null }) {
  const container = document.createElement('div');
  document.body.append(container);
  const app = mount(PrintSheet, { target: container, props });
  flushSync();
  shown.push({ container, app });
  const heads = (level: number) => [...container.querySelectorAll(`h${level}`)] as HTMLElement[];
  return { container, heads };
}

describe('PrintSheet', () => {
  it('one shop: its name is in the title, aisles are headings, every line has an empty box', () => {
    const { container, heads } = render({
      groups: [
        group('Tesco', [
          ['Fruit & veg', [view(1, 'Onions', '1 kg bag'), view(2, 'Lemons', '2')]],
          ['Dairy', [view(3, 'Paneer', '225 g')]]
        ])
      ],
      builtFrom: 'this week’s plan'
    });
    expect(heads(1)[0]!.textContent).toBe('Shopping list · Tesco');
    expect(heads(2).map((h) => h.textContent)).toEqual(['Fruit & veg', 'Dairy']);
    expect(container.querySelectorAll('tr')).toHaveLength(3);
    expect(container.querySelectorAll('td.box span')).toHaveLength(3);
    expect(container.querySelector('.meta')!.textContent).toMatch(
      /^For this week’s plan · 3 things · printed \d{1,2} \w{3}$/
    );
    expect(container.textContent).toContain('1 kg bag');
    expect(container.querySelector('.foot')!.textContent).toContain(
      'Ticks on paper stay on paper: tick things on your phone too, so the pantry knows.'
    );
  });

  it('more shops: each under its own heading, with its aisles under that', () => {
    const { heads } = render({
      groups: [
        group('Tesco', [['Dairy', [view(1, 'Milk', '2')]]]),
        group('Any shop', [['Household', [view(2, 'Soap', '1')]]])
      ]
    });
    expect(heads(2).map((h) => h.textContent)).toEqual(['Tesco', 'Any shop']);
    expect(heads(3).map((h) => h.textContent)).toEqual(['Dairy', 'Household']);
  });

  it('leaves out the trolley and a shop with nothing to buy; says "1 thing"', () => {
    const { container } = render({
      groups: [
        group('Tesco', [['Dairy', [view(1, 'Milk', '2')]]], [view(2, 'Butter', '1')]),
        group('Aldi', [], [view(3, 'Eggs', '6')])
      ]
    });
    expect(container.textContent).not.toContain('Butter');
    expect(container.textContent).not.toContain('Eggs');
    expect(container.textContent).not.toContain('Aldi');
    expect(container.querySelector('.meta')!.textContent).toMatch(/^1 thing · printed /);
  });

  it('with nothing left to buy it prints the page’s own empty words', () => {
    const { container } = render({
      groups: [group('Tesco', [], [view(2, 'Butter', '1')])]
    });
    expect(container.textContent).toContain('Nothing to buy');
    expect(container.textContent).toContain('Add an item above. Ticking it puts it in the pantry.');
    expect(container.querySelectorAll('tr')).toHaveLength(0);
  });
});
