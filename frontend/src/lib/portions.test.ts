import { describe, expect, it } from 'vitest';
import type { MealSlot, Plan, PlanItem, PlanMeal, Portions } from './client/plan';
import {
  barLabel,
  reached,
  leftoverRows,
  offeredDays,
  planWords,
  portionBar,
  portionsLine,
  rowKey,
  shortRows
} from './portions';

const slots: MealSlot[] = [
  { id: 1, name: 'Breakfast', position: 0, enabled: true },
  { id: 2, name: 'Lunch', position: 1, enabled: true },
  { id: 4, name: 'Dinner', position: 3, enabled: true }
];

// The mockup: cooked Sun 18 Oct at dinner, 6 portions (2 eaten that day, 3 tubs planned, 1 left).
const made: Portions = {
  recipe_name: 'Veg biryani',
  has_batch: true,
  batch_id: 7,
  portions: 6,
  cook_day: 2,
  tubs: 4,
  in_meals: 3,
  left: 1,
  use_by: '2026-10-21',
  spare_use_by: ['2026-10-21']
};

const tubItem = (id: number, tub: number): PlanItem => ({
  id,
  position: 0,
  kind: 'tub',
  recipe: null,
  tub_id: tub,
  ingredient: null,
  kept_name: null,
  servings: null,
  note: null,
  eating: null
});
const meal = (id: number, date: string, slot: number, items: PlanItem[]): PlanMeal => ({
  id,
  date,
  slot_id: slot,
  status: 'planned',
  items,
  kcal: null,
  eater_login_ids: []
});
const plan = (meals: PlanMeal[]): Plan => ({
  start: '2026-10-18',
  end: '2026-10-21',
  meals,
  batch_cooks: [],
  tubs: [1, 2, 3].map((id) => ({
    id,
    batch_id: 7,
    amount_quarters: 4,
    number: id,
    place_id: null,
    place_kind: 'fridge' as const,
    member_login_id: null,
    use_by: '2026-10-21'
  }))
});

describe('which days Leftovers on… offers', () => {
  it('runs from the cook day to the use-by, never into the past', () => {
    expect(offeredDays('2026-10-18', '2026-10-17', '2026-10-21')).toEqual({
      first: '2026-10-18',
      last: '2026-10-21'
    });
    expect(offeredDays('2026-10-18', '2026-10-19', '2026-10-21')).toEqual({
      first: '2026-10-19',
      last: '2026-10-21'
    });
  });

  it('asks for no more than a plan read gives (62 days)', () => {
    const { first, last } = offeredDays('2026-10-18', '2026-10-18', '2027-10-18');
    expect(first).toBe('2026-10-18');
    expect(last).toBe('2026-12-18');
  });
});

describe('the meals Leftovers on… lists', () => {
  const cook = { date: '2026-10-18', slot_id: 4 };
  const rows = (meals: PlanMeal[]) =>
    leftoverRows({
      cook,
      today: '2026-10-18',
      useBy: '2026-10-21',
      slotsOn: slots,
      plan: plan(meals),
      batchId: 7
    });

  it('lists only meals after the cook meal and up to the use-by', () => {
    const list = rows([]);
    expect(list[0]).toMatchObject({ day: '2026-10-19', slotId: 1 }); // nothing on the cook day
    expect(list.at(-1)).toMatchObject({ day: '2026-10-21', slotId: 4, last: true });
    expect(list).toHaveLength(9); // 3 days of 3 meals
    expect(list.filter((r) => r.last)).toHaveLength(3); // the use-by day, each meal
  });

  it('after a lunch cook, offers that day’s dinner', () => {
    const list = leftoverRows({
      cook: { date: '2026-10-18', slot_id: 2 },
      today: '2026-10-18',
      useBy: '2026-10-18',
      slotsOn: slots,
      plan: null,
      batchId: null
    });
    expect(list.map((r) => r.slotId)).toEqual([4]);
  });

  it('shows this batch’s tubs as planned and other food as alongside', () => {
    const list = rows([
      meal(1, '2026-10-19', 2, [tubItem(10, 1)]),
      meal(2, '2026-10-19', 4, [{ ...tubItem(11, 99), tub_id: 99 }]) // a tub of another batch
    ]);
    const at = (day: string, slot: number) => list.find((r) => r.day === day && r.slotId === slot);
    expect(at('2026-10-19', 2)?.state).toBe('planned');
    expect(at('2026-10-19', 4)?.state).toBe('has');
    expect(at('2026-10-19', 4)?.what).toBeTruthy();
    expect(at('2026-10-20', 2)?.state).toBe('free');
  });

  it('works out the meals picked beyond the portions left: the latest ones', () => {
    const list = rows([]);
    const picked = new Set([rowKey(list[3]!), rowKey(list[1]!), rowKey(list[5]!)]);
    const keep = '2026-10-21';
    expect(shortRows(list, picked, [keep]).map(rowKey)).toEqual([
      rowKey(list[3]!),
      rowKey(list[5]!)
    ]);
    expect(shortRows(list, picked, [keep, keep, keep])).toEqual([]);
    expect(shortRows(list, new Set(), [])).toEqual([]);
  });
});

describe('which meals the spare tubs reach (F50: never past a tub’s use-by)', () => {
  it('gives each meal the tub with the earliest use-by that is still good', () => {
    expect(reached(['2026-10-20', '2026-10-30'], ['2026-10-19', '2026-10-25'])).toEqual([
      true,
      true
    ]);
    // The tub that goes off on the 20th cannot be used on the 25th.
    expect(reached(['2026-10-20'], ['2026-10-25'])).toEqual([false]);
    expect(reached(['2026-10-20', '2026-10-30'], ['2026-10-25', '2026-10-26'])).toEqual([
      true,
      false
    ]);
    expect(reached([], ['2026-10-25'])).toEqual([false]);
  });
});

describe('the portions bar and its words (the mockup’s)', () => {
  it('has a part for each portion: cook day, planned, left', () => {
    expect(portionBar(made, 0)).toEqual(['cook', 'cook', 'planned', 'planned', 'planned', 'free']);
  });

  it('turns a free part into a picked one, then adds a part for each pick beyond', () => {
    expect(portionBar(made, 1).at(-1)).toBe('picked');
    expect(portionBar(made, 2)).toEqual([
      'cook',
      'cook',
      'planned',
      'planned',
      'planned',
      'picked',
      'over'
    ]);
  });

  it('says it in words, for the screen reader too', () => {
    expect(barLabel(made)).toBe('6 portions: 2 eaten on the cook day, 3 tubs planned, 1 left');
    expect(portionsLine(made, 0, 'Sun')).toBe('Makes 6 · 2 eaten Sun · 3 tubs planned · 1 left');
    expect(portionsLine(made, 1, 'Sun')).toBe(
      'Makes 6 · 2 eaten Sun · 3 tubs planned · 1 picked, 0 left'
    );
    expect(portionsLine(made, 2, 'Sun')).toBe(
      'Makes 6 · 2 eaten Sun · 3 tubs planned · 2 picked, only 1 left'
    );
    expect(portionsLine({ ...made, left: 0, tubs: 3 }, 1, 'Sun')).toBe(
      'Makes 6 · 2 eaten Sun · 3 tubs planned · 1 picked, none left'
    );
    expect(portionsLine({ ...made, tubs: 2, in_meals: 1, left: 1 }, 0, 'Sun')).toContain(
      '1 tub planned'
    );
  });

  it('names the button by what it plans', () => {
    expect(planWords(1)).toBe('Plan 1 tub');
    expect(planWords(2)).toBe('Plan 2 tubs');
  });
});

describe('the planned rows and the button (the mockup’s words)', () => {
  it('counts tubs only, and meals when there are no tubs', () => {
    expect(planWords(2, 3)).toBe('Plan 2 tubs');
    expect(planWords(0, 1)).toBe('Plan 1 meal');
    expect(planWords(0, 2)).toBe('Plan 2 meals');
  });
});
