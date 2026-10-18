import { describe, expect, it } from 'vitest';
import { food, item, tess, sampleCopy } from '$lib/testing/fakeShopping';
import type { Action, ActionFields } from './actions';
import { applyLocal, localDisplay } from './applyLocal';
import type { ShoppingCopy } from './types';

let n = 0;
const act = <F extends ActionFields>(fields: F) =>
  ({ id: `a${++n}`, made_at: '2026-10-18T09:00:00Z', seen: 40, ...fields }) as Action;

const me = { me: tess };
const row = (copy: ShoppingCopy, id: string) => copy.items.find((i) => i.id === id);

/** A copy with Eggs (by the box of 6) and Toor dal (by the 500 g packet), not on the list. */
function withPacks(): ShoppingCopy {
  const copy = sampleCopy();
  copy.items = copy.items.filter((i) => i.food_id !== 5);
  copy.foods.push(
    food(8, 'Eggs', 'dairy', {
      counted_as: 'count',
      sizes: [{ id: 80, name: 'box', plural: 'boxes', amount: 6, usual: true }]
    })
  );
  const dal = copy.foods.find((f) => f.id === 5)!;
  dal.sizes = [{ id: 50, name: 'packet', plural: 'packets', amount: 500, usual: true }];
  return copy;
}

describe('applyLocal: the copy with the waiting changes on top', () => {
  it('never changes the copy it is given', () => {
    const copy = sampleCopy();
    const before = structuredClone(copy);
    applyLocal(copy, [act({ kind: 'tick', item_id: 'i-onions' })], me);
    expect(copy).toEqual(before);
  });

  it('with nothing waiting it is the copy itself', () => {
    const copy = sampleCopy();
    expect(applyLocal(copy, [], me)).toBe(copy);
  });

  it('tick marks the item ticked by me; a second tick does nothing', () => {
    const t1 = act({ kind: 'tick', item_id: 'i-onions' });
    const t2 = act({ kind: 'tick', item_id: 'i-onions' });
    const shown = applyLocal(sampleCopy(), [t1, t2], me);
    expect(row(shown, 'i-onions')!.ticks).toEqual([
      { id: t1.id, by: tess, at: t1.made_at, place_id: null, bought: null, standing: true }
    ]);
  });

  it('untick, put away, delete, clear ticked, dismiss a note and answer a card', () => {
    const copy = sampleCopy();
    copy.notes = [
      { id: 7, list_id: 'main', item_id: null, food_id: null, text: 'x', undo: null, gone: false }
    ];
    copy.questions = [
      {
        id: 9,
        list_id: 'main',
        item_id: 'i-coriander',
        title: 'Did you buy 2?',
        text: '',
        yes: 'Yes, 2',
        no: 'Just 1',
        open: true
      }
    ];
    const shown = applyLocal(
      copy,
      [
        act({ kind: 'untick', item_id: 'i-coriander', tick_ids: ['t-cor'] }),
        act({ kind: 'put_away', item_id: 'i-paneer', place_id: 2, tick_ids: ['t-pan'] }),
        act({ kind: 'delete', item_id: 'i-yoghurt' }),
        act({ kind: 'clear_ticked', list_id: 'main', item_ids: ['i-roll'] }),
        act({ kind: 'dismiss_note', note_id: 7 }),
        act({ kind: 'answer_double_tick', question_id: 9, answer: 'one' })
      ],
      me
    );
    expect(row(shown, 'i-coriander')!.ticks[0]!.standing).toBe(false);
    expect(row(shown, 'i-paneer')).toMatchObject({ put_away_place_id: 2 });
    expect(row(shown, 'i-paneer')!.ticks[0]!.place_id).toBe(2);
    expect(row(shown, 'i-yoghurt')!.deleted).toBe(true);
    expect(row(shown, 'i-roll')!.deleted).toBe(true);
    expect(shown.notes[0]!.gone).toBe(true);
    expect(shown.questions[0]!.open).toBe(false);
  });

  it('makes, renames and removes lists', () => {
    const shown = applyLocal(
      sampleCopy(),
      [
        act({ kind: 'create_list', list_id: 'l-new', name: 'Diwali' }),
        act({ kind: 'rename_list', list_id: 'l-new', name: 'Diwali sweets' }),
        act({ kind: 'remove_list', list_id: 'party' })
      ],
      me
    );
    expect(shown.lists.find((l) => l.id === 'l-new')).toEqual({
      id: 'l-new',
      name: 'Diwali sweets',
      main: false,
      position: 2,
      removed: false
    });
    expect(shown.lists.find((l) => l.id === 'party')!.removed).toBe(true);
  });

  it('add inserts a line, in the ingredient’s usual shop, added by me', () => {
    const shown = applyLocal(
      sampleCopy(),
      [act({ kind: 'add', list_id: 'main', item_id: 'i-new', food_id: 7, amount: 400 })],
      me
    );
    expect(row(shown, 'i-new')).toMatchObject({
      list_id: 'main',
      food_id: 7,
      shop_id: 1,
      amount: 400,
      display: '400 g',
      added_by: tess,
      ticks: []
    });
  });

  it('a brand-new ingredient shows at once, with a stand-in ID', () => {
    const shown = applyLocal(
      sampleCopy(),
      [
        act({
          kind: 'add',
          list_id: 'main',
          item_id: 'i-new',
          new_food: { name: 'Jaggery', counted_as: 'weight', staple: false }
        })
      ],
      me
    );
    const made = shown.foods.find((f) => f.name === 'Jaggery')!;
    expect(made.id).toBeLessThan(0);
    expect(row(shown, 'i-new')).toMatchObject({ food_id: made.id, shop_id: null, amount: null });
  });

  it('an ingredient from the add box the copy doesn’t have yet shows from the hint', () => {
    const shown = applyLocal(
      sampleCopy(),
      [act({ kind: 'add', list_id: 'main', item_id: 'i-new', food_id: 99 })],
      { me: tess, foods: [food(99, 'Jaggery', 'other', { shop_id: null })] }
    );
    expect(shown.foods.some((f) => f.id === 99)).toBe(true);
    expect(row(shown, 'i-new')).toMatchObject({ food_id: 99, shop_id: null });
  });

  it('SY-65: Eggs 6 + Eggs 6 on this phone is one line of 12, shown as 2 boxes', () => {
    const add = (id: string) =>
      act({ kind: 'add', list_id: 'main', item_id: id, food_id: 8, amount: 6, size_id: 80 });
    const shown = applyLocal(withPacks(), [add('e1'), add('e2')], me);
    const eggs = shown.items.filter((i) => i.food_id === 8);
    expect(eggs).toHaveLength(1);
    expect(eggs[0]).toMatchObject({ id: 'e1', amount: 12, size_id: 80, display: '2 boxes' });
  });

  it('SY-65: toor dal 1 packet + 250 g is 750 g, shown as 1½ packets', () => {
    const shown = applyLocal(
      withPacks(),
      [
        act({ kind: 'add', list_id: 'main', item_id: 'd1', food_id: 5, amount: 500, size_id: 50 }),
        act({ kind: 'add', list_id: 'main', item_id: 'd2', food_id: 5, amount: 250 })
      ],
      me
    );
    const dal = shown.items.filter((i) => i.food_id === 5);
    expect(dal).toHaveLength(1);
    expect(dal[0]).toMatchObject({ amount: 750, size_id: 50, display: '1½ packets' });
  });

  it('joins a line from the copy too, but not a ticked one, another shop or another list', () => {
    const copy = withPacks();
    copy.items.push(
      item('i-dal', 5, { shop_id: 2, amount: 500, size_id: 50, display: '1 packet' })
    );
    const shown = applyLocal(
      copy,
      [
        act({ kind: 'add', list_id: 'main', item_id: 'd1', food_id: 5, amount: 500 }),
        act({ kind: 'add', list_id: 'main', item_id: 'd2', food_id: 5, amount: 500, shop_id: 1 }),
        act({ kind: 'add', list_id: 'party', item_id: 'd3', food_id: 5, amount: 500 }),
        act({ kind: 'add', list_id: 'main', item_id: 'c1', food_id: 2, amount: 1 })
      ],
      me
    );
    expect(row(shown, 'i-dal')).toMatchObject({ amount: 1000, display: '2 packets' });
    expect(row(shown, 'd1')).toBeUndefined();
    expect(row(shown, 'd2')).toMatchObject({ shop_id: 1 });
    expect(row(shown, 'd3')).toMatchObject({ list_id: 'party' });
    // Coriander is in the trolley: a new line.
    expect(row(shown, 'c1')).toMatchObject({ food_id: 2, ticks: [] });
  });

  it('a later change to a joined add goes to the line it joined', () => {
    const copy = withPacks();
    const shown = applyLocal(
      copy,
      [
        act({ kind: 'add', list_id: 'main', item_id: 'd1', food_id: 5, amount: 500, size_id: 50 }),
        act({ kind: 'add', list_id: 'main', item_id: 'd2', food_id: 5 }),
        act({ kind: 'tick', item_id: 'd2' })
      ],
      me
    );
    expect(row(shown, 'd1')!.ticks).toHaveLength(1);
  });

  it('maps an item the server merged into another line', () => {
    const copy = sampleCopy();
    copy.items.push(item('i-old', 3, { merged_into_id: 'i-yoghurt' }));
    const shown = applyLocal(copy, [act({ kind: 'tick', item_id: 'i-old' })], me);
    expect(row(shown, 'i-yoghurt')!.ticks).toHaveLength(1);
    expect(row(shown, 'i-old')!.ticks).toHaveLength(0);
  });

  it('set amount shows a simple local wording until the server’s arrives', () => {
    const shown = applyLocal(
      sampleCopy(),
      [act({ kind: 'set_amount', item_id: 'i-yoghurt', amount: 1500 })],
      me
    );
    expect(row(shown, 'i-yoghurt')).toMatchObject({
      amount: 1500,
      display: '1.5 kg',
      hand_edited: true
    });
  });

  it('an undo of a change still waiting shows neither; of a sent tick, takes the tick back', () => {
    const t = act({ kind: 'tick', item_id: 'i-onions' });
    const both = applyLocal(sampleCopy(), [t, act({ kind: 'undo', undoes: t.id })], me);
    expect(row(both, 'i-onions')!.ticks).toHaveLength(0);
    const sent = applyLocal(sampleCopy(), [act({ kind: 'undo', undoes: 't-cor' })], me);
    expect(row(sent, 'i-coriander')!.ticks[0]!.standing).toBe(false);
  });

  it('fills in packet sizes fetched for an ingredient', () => {
    const copy = sampleCopy();
    copy.foods.find((f) => f.id === 7)!.sizes = null;
    const sizes = [{ id: 70, name: 'jar', plural: 'jars', amount: 300, usual: true }];
    const shown = applyLocal(copy, [], { me: tess, sizes: { 7: sizes } });
    expect(shown.foods.find((f) => f.id === 7)!.sizes).toEqual(sizes);
  });

  it('FE-5: never makes pantry data, whatever the change', () => {
    const copy = withPacks();
    const all: ActionFields[] = [
      { kind: 'create_list', list_id: 'l', name: 'L' },
      { kind: 'rename_list', list_id: 'l', name: 'M' },
      { kind: 'add', list_id: 'main', item_id: 'x', food_id: 8, amount: 6, size_id: 80 },
      { kind: 'set_amount', item_id: 'x', amount: 12 },
      { kind: 'tick', item_id: 'x' },
      { kind: 'different_pack', item_id: 'i-paneer', tick_id: 't-pan', count: 3, pack: 200 },
      { kind: 'put_away', item_id: 'i-paneer', place_id: 1, tick_ids: ['t-pan'] },
      { kind: 'untick', item_id: 'x', tick_ids: [] },
      { kind: 'delete', item_id: 'i-onions' },
      { kind: 'clear_ticked', list_id: 'main', item_ids: ['i-coriander'] },
      { kind: 'answer_double_tick', question_id: 1, answer: 'two' },
      { kind: 'dismiss_note', note_id: 1 },
      { kind: 'undo', undoes: 'nothing' },
      { kind: 'remove_list', list_id: 'l' }
    ];
    const shown = applyLocal(copy, all.map(act), me);
    expect(Object.keys(shown).sort()).toEqual(Object.keys(copy).sort());
    const keys: string[] = [];
    const walk = (value: unknown) => {
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === 'object') {
        for (const [k, v] of Object.entries(value)) {
          keys.push(k);
          walk(v);
        }
      }
    };
    walk(shown);
    expect(keys.filter((k) => /pantry|stock|\blots?\b|left/i.test(k))).toEqual([]);
    // What was bought stays on the tick in the trolley: the list's record, not the pantry's.
    expect(row(shown, 'i-paneer')!.ticks[0]!.bought).toEqual({ amount: 600, display: '600 g' });
  });
});

describe('localDisplay', () => {
  const eggs = food(8, 'Eggs', 'dairy', {
    counted_as: 'count',
    count_word: 'egg',
    count_word_plural: 'eggs',
    sizes: [{ id: 80, name: 'box', plural: 'boxes', amount: 6, usual: true }]
  });

  it('says packs when it is a whole, half or quarter number of them, else the amount', () => {
    expect(localDisplay(6, 80, eggs)).toBe('1 box');
    expect(localDisplay(3, 80, eggs)).toBe('½ box');
    expect(localDisplay(9, 80, eggs)).toBe('1½ boxes');
    expect(localDisplay(7, 80, eggs)).toBe('7 eggs');
    expect(localDisplay(1, null, eggs)).toBe('1 egg');
    expect(localDisplay(null, 80, eggs)).toBeNull();
    expect(localDisplay(400, null, food(1, 'Rice', 'other'))).toBe('400 g');
  });
});
