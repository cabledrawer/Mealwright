import { describe, expect, it } from 'vitest';
import type { RecipeRow } from './client/recipes';
import { recipeLine, recipeParts, stockWords, useSoonWords } from './recipeLine';

const recipe = (extra: Partial<RecipeRow> = {}): RecipeRow => ({
  id: 1,
  name: 'Sambar',
  description: null,
  makes: null,
  version: 1,
  time_minutes: 50,
  serves: 4,
  tags: [],
  ingredient_count: 7,
  kcal: 320,
  stock: { counted: 7, missing: 1, can_cook_now: false },
  use_soon: null,
  stock_unchecked: false,
  ...extra
});

const spinach = { id: 3, name: 'Spinach' };

describe('the line under a recipe', () => {
  it('says the time, the calories and what is in stock, as in the mockup', () => {
    expect(recipeLine(recipe())).toBe('50 min · 320 kcal · all in stock but 1');
  });

  it('leaves out the time when it is not known', () => {
    expect(recipeLine(recipe({ time_minutes: null }))).toBe('320 kcal · all in stock but 1');
  });

  it('says nutrition unknown, never 0, when there are no calories', () => {
    expect(recipeLine(recipe({ kcal: null, stock: null }))).toBe('50 min · nutrition unknown');
    expect(recipeLine(recipe({ kcal: null, stock: null, time_minutes: null }))).toBe(
      'nutrition unknown'
    );
  });

  it('shows a real zero as 0 kcal and rounds the rest', () => {
    expect(recipeLine(recipe({ kcal: 0, stock: null }))).toContain('0 kcal');
    expect(recipeLine(recipe({ kcal: 320.6, stock: null }))).toContain('321 kcal');
  });

  it('puts what is about to go off in orange', () => {
    const row = recipe({
      time_minutes: null,
      kcal: null,
      stock: { counted: 3, missing: 0, can_cook_now: true },
      use_soon: { foods: [spinach], use_by: '2026-10-20', days_left: 0 }
    });
    expect(recipeLine(row)).toBe('nutrition unknown · Uses spinach (today)');
    expect(recipeParts(row).map((p) => !!p.soon)).toEqual([false, true]);
  });

  it('still says what is missing next to what is about to go off', () => {
    const row = recipe({
      use_soon: { foods: [spinach], use_by: '2026-10-21', days_left: 1 }
    });
    expect(recipeLine(row)).toBe(
      '50 min · 320 kcal · Uses spinach (tomorrow) · all in stock but 1'
    );
  });
});

describe('a recipe that uses a recipe that is not checked', () => {
  // cabledrawer 20 Oct: never "all in stock" nor "all in stock but 1"; "N missing" if something
  // checked is missing, otherwise no stock words.
  const unchecked = (counted: number, missing: number) =>
    recipe({ stock: { counted, missing, can_cook_now: false }, stock_unchecked: true });

  it('never says all in stock, with or without one missing', () => {
    expect(recipeLine(unchecked(7, 0))).toBe('50 min · 320 kcal');
    expect(recipeLine(unchecked(7, 1))).toBe('50 min · 320 kcal · 1 missing');
    expect(recipeLine(unchecked(7, 3))).toBe('50 min · 320 kcal · 3 missing');
  });

  it('says no stock words when nothing was checked', () => {
    expect(recipeLine(recipe({ stock: null, stock_unchecked: true }))).toBe('50 min · 320 kcal');
  });

  it('still says what is about to go off', () => {
    const row = {
      ...unchecked(7, 0),
      use_soon: { foods: [spinach], use_by: '2026-10-20', days_left: 0 }
    };
    expect(recipeLine(row)).toBe('50 min · 320 kcal · Uses spinach (today)');
  });
});

describe('stock words', () => {
  const stock = (counted: number, missing: number) => ({
    counted,
    missing,
    can_cook_now: missing === 0
  });

  it('counts what is missing', () => {
    expect(stockWords(stock(5, 0))).toBe('all in stock');
    expect(stockWords(stock(5, 1))).toBe('all in stock but 1');
    expect(stockWords(stock(5, 2))).toBe('2 missing');
    expect(stockWords(stock(1, 1))).toBe('1 missing'); // nothing at all is in stock
  });

  it('leaves out "all in stock" when some line is not checked', () => {
    expect(stockWords(stock(5, 0), true)).toBe('');
    expect(stockWords(stock(5, 1), true)).toBe('1 missing');
    expect(stockWords(stock(5, 2), true)).toBe('2 missing');
  });

  it('says nothing when no ingredient counts', () => {
    expect(stockWords(null)).toBe('');
    expect(stockWords(stock(0, 0))).toBe('');
  });
});

describe('use soon words', () => {
  const soon = (names: string[], days_left: number, use_by: string) => ({
    foods: names.map((name, id) => ({ id, name })),
    use_by,
    days_left
  });

  it('names one, two, or several ingredients, and the day', () => {
    expect(useSoonWords(soon(['Spinach'], 0, '2026-10-20'))).toBe('Uses spinach (today)');
    expect(useSoonWords(soon(['Spinach', 'Toor dal'], 1, '2026-10-21'))).toBe(
      'Uses spinach and toor dal (tomorrow)'
    );
    expect(useSoonWords(soon(['Paneer', 'Milk', 'Spinach'], 2, '2026-10-22'))).toBe(
      'Uses paneer and 2 more (Thu)'
    );
  });

  it('keeps a name that starts with capitals as it is', () => {
    expect(useSoonWords(soon(['TVP'], 0, '2026-10-20'))).toBe('Uses TVP (today)');
  });
});
