import { describe, expect, it } from 'vitest';
import type { CookRow } from './client/cook';
import type { Ask } from './client/types';
import {
  amountWords,
  changeCount,
  choicesOf,
  conversionAnswer,
  isUsed,
  listAmountWords,
  newRowState,
  numberWords,
  parseAmountText,
  recipeSays,
  shown,
  sizeAnswer,
  withAnswer,
  roundForScreen
} from './cookRows';

const amount = (n: number, unit: 'g' | 'ml' | 'count' = 'g') => ({
  amount: n,
  unit,
  as_sold: null,
  about: false,
  short: `${n}`,
  display: `${n}`
});

function row(extra: Partial<CookRow> = {}): CookRow {
  return {
    key: 'food:1',
    status: 'take',
    lines: [{ id: 1, words: '200 g toor dal' }],
    food: { id: 1, name: 'Toor dal' },
    recipe: null,
    needed: amount(200),
    takes: [
      {
        food: { id: 1, name: 'Toor dal' },
        stand_in: false,
        amount: amount(200),
        before: amount(800),
        after: amount(600),
        lots: []
      }
    ],
    use: true,
    short: null,
    make_first: false,
    add_to_list: false,
    list_amount: null,
    running_low: false,
    in_freezer: null,
    from_freezer: false,
    ask: null,
    estimate: false,
    ask_need: null,
    half: null,
    count_note: null,
    bought: false,
    unit: 'g',
    ...extra
  };
}

describe('the words', () => {
  it('numbers use ¼ ½ ¾ and units get a no-break space', () => {
    expect(numberWords(1.5)).toBe('1½');
    expect(numberWords(0.5)).toBe('½');
    expect(numberWords(2)).toBe('2');
    expect(numberWords(0.33)).toBe('0.33');
    expect(amountWords(300, 'g')).toBe('300 g');
    expect(amountWords(2, 'count')).toBe('2');
  });

  it('g and ml are rounded for the screen (F132)', () => {
    expect(amountWords(0.63, 'ml')).toBe('0.6\u00a0ml');
    expect(amountWords(149.94, 'g')).toBe('150\u00a0g');
    expect(amountWords(199.98, 'g')).toBe('200\u00a0g');
    expect(amountWords(9.96, 'g')).toBe('10\u00a0g');
    expect(amountWords(2.04, 'ml')).toBe('2\u00a0ml');
    expect(amountWords(0.01, 'g')).toBe('0.1\u00a0g');
    expect(amountWords(0, 'g')).toBe('0\u00a0g');
    expect(numberWords(312.5, 'g')).toBe('313');
    expect(numberWords(1.5)).toBe('1½');
    expect(roundForScreen(0.63, 'ml')).toBe(0.6);
    expect(roundForScreen(149.94, 'g')).toBe(150);
    expect(roundForScreen(1.234, 'count')).toBe(1.23);
  });
});

describe("the recipe's side", () => {
  it('says the amount, the unit and the words as the recipe has them', () => {
    const jaggery = row({
      lines: [
        { id: 1, words: 'jaggery', amount: '1½', unit: 'tbsp' },
        { id: 2, words: 'jaggery, grated' }
      ]
    });
    expect(recipeSays(jaggery)).toBe('1½ tbsp jaggery + jaggery, grated');
  });
});

describe('what a row shows', () => {
  it('is as proposed until touched', () => {
    expect(shown(row(), undefined)).toEqual({ use: true, taken: 200, before: 800, after: 600 });
  });

  it('Use off takes nothing and leaves Before as After', () => {
    const state = { ...newRowState(), use: false };
    expect(shown(row(), state)).toEqual({ use: false, taken: 0, before: 800, after: 800 });
  });

  it('a typed amount used, or left, never goes below zero', () => {
    const used = { ...newRowState(), value: 250 };
    expect(shown(row(), used).after).toBe(550);
    const left = { ...newRowState(), mode: 'left' as const, value: 100 };
    expect(shown(row(), left)).toMatchObject({ taken: 700, after: 100 });
    expect(shown(row(), { ...used, value: 5000 })).toMatchObject({ taken: 800, after: 0 });
  });

  it('a question nobody answered, and a no-amount line, start off', () => {
    expect(isUsed(row({ status: 'ask', use: true }), undefined)).toBe(false);
    expect(isUsed(row({ status: 'no_amount', use: true }), undefined)).toBe(false);
    expect(isUsed(row({ status: 'ask' }), { ...newRowState(), use: true })).toBe(true);
  });

  it('counts the rows that would change the pantry', () => {
    const rows = [row(), row({ key: 'food:2', takes: [], use: false, status: 'none_in_pantry' })];
    expect(changeCount(rows, {})).toBe(1);
    expect(changeCount(rows, { 'food:1': { ...newRowState(), use: false } })).toBe(0);
  });
});

describe('what is sent back', () => {
  it('nothing for rows nobody touched', () => {
    expect(choicesOf([row()], {})).toEqual([]);
    expect(choicesOf([row()], { 'food:1': newRowState() })).toEqual([]);
  });

  it('the switch, a typed amount in the pantry unit, and Bought some', () => {
    const rows = [
      row(),
      row({ key: 'food:2', unit: 'count', status: 'none_in_pantry', use: false })
    ];
    const sent = choicesOf(rows, {
      'food:1': { ...newRowState(), value: 150, mode: 'left' },
      'food:2': { ...newRowState(), bought: true }
    });
    expect(sent).toEqual([
      { key: 'food:1', left: { amount: 150, unit: 'g' } },
      { key: 'food:2', bought: true }
    ]);
    expect(choicesOf([row()], { 'food:1': { ...newRowState(), use: false } })).toEqual([
      { key: 'food:1', use: false }
    ]);
  });

  it('a typed amount is dropped when Use is off', () => {
    const state = { ...newRowState(), use: false, value: 5 };
    expect(choicesOf([row()], { 'food:1': state })).toEqual([{ key: 'food:1', use: false }]);
  });

  it('the shopping-list tick only when it differs from the proposal', () => {
    const state = { ...newRowState(), addToList: true };
    expect(choicesOf([row({ add_to_list: true })], { 'food:1': state })).toEqual([]);
    expect(choicesOf([row({ add_to_list: false })], { 'food:1': state })).toEqual([
      { key: 'food:1', add_to_list: true }
    ]);
  });
});

describe('learning from a typed amount (F106)', () => {
  const cup: Ask = {
    food_id: 1,
    food_name: 'Jaggery',
    kind: 'weight_per_ml',
    question: 'q',
    cup_ml: 250,
    suggested: 200
  };
  const item: Ask = { ...cup, kind: 'item_weight' };

  it('a recipe in ml and a pantry in g: grams in a cup', () => {
    // 25 ml of it weighed 20 g: 200 g in a 250 ml cup.
    expect(conversionAnswer(cup, { amount: 25, unit: 'ml' }, 'g', 20, true)).toEqual({
      kind: 'weight_per_ml',
      food_id: 1,
      grams: 200,
      remember: true
    });
  });

  it('a recipe in g and a pantry in ml', () => {
    // 100 g of it is 125 ml: 0.8 g a ml, 200 g a cup.
    expect(conversionAnswer(cup, { amount: 100, unit: 'g' }, 'ml', 125, false)).toMatchObject({
      grams: 200,
      remember: false
    });
  });

  it('a recipe in items and a pantry in g, and the other way', () => {
    expect(conversionAnswer(item, { amount: 2, unit: 'item' }, 'g', 10, true)).toMatchObject({
      kind: 'item_weight',
      grams: 5
    });
    expect(conversionAnswer(item, { amount: 220, unit: 'g' }, 'count', 2, true)).toMatchObject({
      grams: 110
    });
  });

  it('cups against a count cannot be settled by one number', () => {
    expect(conversionAnswer(cup, { amount: 250, unit: 'ml' }, 'count', 2, true)).toBeNull();
    expect(conversionAnswer(cup, null, 'g', 20, true)).toBeNull();
    expect(conversionAnswer(cup, { amount: 25, unit: 'ml' }, 'g', 0, true)).toBeNull();
    expect(conversionAnswer(cup, { amount: 25, unit: 'ml' }, 'g', 100000, true)).toBeNull();
  });

  it('"2 cloves" typed as 10 g is a clove of 5 g', () => {
    expect(sizeAnswer(1, { count: 2, word: 'clove' }, 10)).toEqual({
      kind: 'size',
      food_id: 1,
      name: 'clove',
      amount: 5
    });
    expect(sizeAnswer(1, { count: 2, word: 'clove' }, 0)).toBeNull();
  });

  it('a new answer replaces the old one for the same question', () => {
    const a = { kind: 'weight_per_ml', food_id: 1, grams: 200, remember: true } as const;
    const b = { ...a, grams: 220 };
    const other = { ...a, food_id: 2 };
    expect(withAnswer([a, other], b)).toEqual([other, b]);
  });
});

describe('at most 20 answers', () => {
  it('never drops one quietly: past 20 the list is left as it is, and a replacement still works', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({
      kind: 'item_weight' as const,
      food_id: i + 1,
      grams: 5,
      remember: true
    }));
    const extra = { kind: 'item_weight' as const, food_id: 99, grams: 5, remember: true };
    expect(withAnswer(many, extra)).toBe(many);
    const again = { ...many[3]!, grams: 6 };
    expect(withAnswer(many, again)).toHaveLength(20);
    expect(withAnswer(many, again).at(-1)).toEqual(again);
  });

  it('typed amounts take fractions', () => {
    expect([
      parseAmountText('¼'),
      parseAmountText('1½'),
      parseAmountText('1/2'),
      parseAmountText('2,5')
    ]).toEqual([0.25, 1.5, 0.5, 2.5]);
    // "10/3" is ten thirds and "11/2" five and a half, as in the other two readers (FE3).
    expect(parseAmountText('10/3')).toBeCloseTo(10 / 3);
    expect(parseAmountText('11/2')).toBe(5.5);
    expect(parseAmountText('2 1/2')).toBe(2.5);
    expect(parseAmountText('⅓')).toBeCloseTo(1 / 3);
    expect(parseAmountText('0')).toBe(0);
    expect(parseAmountText('1/0')).toBeNaN();
    expect(parseAmountText('0/0')).toBeNaN();
    expect(parseAmountText('2 1/0')).toBeNaN();
    expect(parseAmountText('abc')).toBeNaN();
    expect(parseAmountText('')).toBeNaN();
  });
});

describe('the shopping list line says what it adds (F133)', () => {
  it('turns a bare count into the ingredient’s name', () => {
    expect(listAmountWords('2 left', 'Eggs')).toBe('2 eggs');
    expect(listAmountWords('2', 'Eggs')).toBe('2 eggs');
    expect(listAmountWords('1½', 'Bananas')).toBe('1½ bananas');
    expect(listAmountWords('500 g', 'Flour')).toBe('500 g');
    expect(listAmountWords('1 packet', 'Rice')).toBe('1 packet');
  });
});
