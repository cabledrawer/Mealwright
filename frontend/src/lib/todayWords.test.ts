import { describe, expect, it } from 'vitest';
import type { Plan } from './client/plan';
import {
  dayInSentence,
  dayWords,
  mealsWords,
  moreWords,
  spotAt,
  spotWords,
  tubsWords,
  weekRows,
  whenWords
} from './todayWords';

const TODAY = '2026-10-25';

const plan = (meals: Plan['meals']): Plan => ({
  start: '2026-10-18',
  end: '2026-11-01',
  meals,
  batch_cooks: [],
  tubs: []
});

const meal = (
  id: number,
  date: string,
  slot: number,
  status: Plan['meals'][0]['status'],
  name = 'Rasam'
) => ({
  id,
  date,
  slot_id: slot,
  status,
  kcal: null,
  eater_member_ids: [] as number[],
  items: [
    {
      id: id * 10,
      position: 0,
      kind: 'recipe' as const,
      recipe: { id: 1, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
      tub_id: null,
      food: null,
      kept_name: null,
      servings: null,
      note: null,
      eating: null,
      cooked: false
    }
  ]
});

describe('the words on Today', () => {
  it('says when a waiting meal was', () => {
    expect(whenWords('2026-10-24', TODAY)).toBe('Yesterday');
    expect(whenWords('2026-10-23', TODAY)).toBe('Fri 23');
    expect(whenWords(TODAY, TODAY)).toBe('Today');
  });

  it('names days for the next cook and the Move button', () => {
    expect(dayWords(TODAY, TODAY)).toBe('Today');
    expect(dayWords('2026-10-26', TODAY)).toBe('Tomorrow');
    expect(dayWords('2026-10-30', TODAY)).toBe('Friday');
    expect(dayInSentence(TODAY, TODAY)).toBe('today');
    expect(dayInSentence('2026-10-26', TODAY)).toBe('tomorrow');
    expect(dayInSentence('2026-10-28', TODAY)).toBe('Wed 28');
  });

  it('knows what is in a spot: free, alongside, or done', () => {
    const p = plan([meal(1, '2026-10-26', 2, 'planned'), meal(2, '2026-10-27', 2, 'cooked')]);
    expect(spotAt(p, '2026-10-25', 2)).toEqual({ state: 'free' });
    expect(spotAt(p, '2026-10-26', 2)).toEqual({ state: 'alongside', what: 'Rasam' });
    expect(spotAt(p, '2026-10-27', 2)).toEqual({ state: 'done' });
    expect(spotAt(p, '2026-10-26', 3)).toEqual({ state: 'free' });
    expect(spotWords({ state: 'free' })).toBe('free');
    expect(spotWords({ state: 'alongside', what: 'x' })).toBe('adds alongside');
    expect(spotWords({ state: 'done' })).toBe('already done');
  });

  it('names a tub in a spot by its batch', () => {
    const p = plan([
      {
        ...meal(1, '2026-10-26', 2, 'planned'),
        items: [
          {
            id: 5,
            position: 0,
            kind: 'tub',
            recipe: null,
            tub_id: 9,
            food: null,
            kept_name: null,
            servings: null,
            note: null,
            eating: null,
            cooked: false
          }
        ]
      }
    ]);
    p.batch_cooks = [
      {
        id: 3,
        recipe_id: 1,
        recipe_name: 'Rasam',
        cook_meal_id: null,
        cooked_on: '2026-10-24',
        tub_count: 3,
        pattern: 'pick',
        prep_note: null,
        colour: null,
        portions: 1,
        portions_left: 0
      }
    ];
    p.tubs = [
      {
        id: 9,
        batch_id: 3,
        amount_quarters: 4,
        number: 2,
        place_id: null,
        place_kind: 'fridge',
        member_id: null,
        use_by: '2026-10-27'
      }
    ];
    expect(spotAt(p, '2026-10-26', 2)).toEqual({ state: 'alongside', what: 'Rasam · tub 2 of 3' });
  });

  it('counts tubs, meals and meals waiting', () => {
    expect(tubsWords(0)).toBe('None');
    expect(tubsWords(1)).toBe('1 tub');
    expect(tubsWords(4)).toBe('4 tubs');
    expect(mealsWords(0)).toBe('Nothing planned');
    expect(mealsWords(1)).toBe('1 meal');
    expect(mealsWords(3)).toBe('3 meals');
    expect(moreWords(1)).toBe('1 more meal to answer');
    expect(moreWords(3)).toBe('3 more meals to answer');
  });
});

import { partsCooked } from './todayWords';
describe('partsCooked (F160)', () => {
  it('counts the cooked recipes and says when none is left', () => {
    expect(partsCooked(0, 2)).toBe('');
    expect(partsCooked(1, 2)).toBe('1 of 2 cooked');
    expect(partsCooked(2, 2)).toBe('All cooked');
  });
});

describe('This week on Today (F150)', () => {
  const slots = [
    { id: 1, name: 'Breakfast', position: 0, enabled: true },
    { id: 2, name: 'Lunch', position: 1, enabled: true },
    { id: 3, name: 'Dinner', position: 2, enabled: true },
    { id: 4, name: 'Snack', position: 3, enabled: true }
  ];

  it('is seven days from today, today first', () => {
    const rows = weekRows(plan([]), slots, TODAY);
    expect(rows.map((r) => r.day)).toEqual([
      '2026-10-25',
      '2026-10-26',
      '2026-10-27',
      '2026-10-28',
      '2026-10-29',
      '2026-10-30',
      '2026-10-31'
    ]);
    expect(rows[0]!.isToday).toBe(true);
    expect(rows[1]!.isToday).toBe(false);
  });

  it('names the dinner, and counts the day’s meals', () => {
    const rows = weekRows(
      plan([
        meal(1, TODAY, 1, 'planned', 'Upma'),
        meal(2, TODAY, 3, 'planned', 'Sambar'),
        meal(3, TODAY, 2, 'planned', 'Dosa')
      ]),
      slots,
      TODAY
    );
    expect(rows[0]).toMatchObject({ name: 'Sambar', count: '3 meals', cooks: true });
  });

  it('names the last meal of the day when there is no dinner', () => {
    const rows = weekRows(
      plan([
        meal(1, '2026-10-26', 4, 'planned', 'Fruit'),
        meal(2, '2026-10-26', 1, 'planned', 'Upma')
      ]),
      slots,
      TODAY
    );
    expect(rows[1]).toMatchObject({ name: 'Fruit', count: '2 meals' });
  });

  it('says "1 meal", and an empty day has no name or count', () => {
    const rows = weekRows(plan([meal(1, '2026-10-27', 3, 'planned', 'Rasam')]), slots, TODAY);
    expect(rows[2]).toMatchObject({ name: 'Rasam', count: '1 meal' });
    expect(rows[3]).toMatchObject({ name: null, count: null, cooks: false });
  });

  it('names only what is eaten after a session’s Cooked it, not the recipes it cooked (F233)', () => {
    const p = plan([meal(1, '2026-10-26', 3, 'cooked', 'Paneer')]);
    const [cook] = p.meals[0]!.items;
    p.meals[0]!.items = [
      { ...cook!, id: 11, kind: 'tub', recipe: null, tub_id: 9 },
      { ...cook!, id: 12, cooked: true },
      { ...cook!, id: 13, cooked: true, recipe: { ...cook!.recipe!, id: 2, name: 'Dal Tadka' } }
    ];
    p.batch_cooks = [1, 2].map((recipe_id) => ({
      id: recipe_id,
      recipe_id,
      recipe_name: recipe_id === 1 ? 'Paneer' : 'Dal Tadka',
      cook_meal_id: 1,
      cooked_on: '2026-10-26',
      tub_count: 2,
      pattern: 'dinners' as const,
      prep_note: null,
      colour: 'blue',
      portions: 3,
      portions_left: 0,
      session_id: 4
    }));
    p.tubs = [
      {
        id: 9,
        batch_id: 1,
        amount_quarters: 4,
        number: 1,
        place_id: null,
        place_kind: null,
        member_id: null,
        use_by: '2026-10-30'
      }
    ];
    expect(weekRows(p, slots, TODAY)[1]).toMatchObject({ name: 'Paneer', count: 'tub · 1 meal' });
  });

  it('shows a tub as its recipe, with "tub · " before the count', () => {
    const p = plan([meal(1, '2026-10-26', 3, 'planned')]);
    p.meals[0]!.items[0] = { ...p.meals[0]!.items[0]!, kind: 'tub', recipe: null, tub_id: 9 };
    p.batch_cooks = [
      {
        id: 3,
        recipe_id: 1,
        recipe_name: 'Lemon rice',
        cook_meal_id: null,
        cooked_on: '2026-10-25',
        tub_count: 3,
        pattern: 'pick',
        prep_note: null,
        colour: null,
        portions: 1,
        portions_left: 0
      }
    ];
    p.tubs = [
      {
        id: 9,
        batch_id: 3,
        amount_quarters: 4,
        number: 1,
        place_id: null,
        place_kind: 'fridge',
        member_id: null,
        use_by: '2026-10-28'
      }
    ];
    expect(weekRows(p, slots, TODAY)[1]).toMatchObject({
      name: 'Lemon rice',
      count: 'tub · 1 meal'
    });
  });

  it('leaves out a meal that was skipped or moved', () => {
    const rows = weekRows(plan([meal(1, '2026-10-26', 3, 'didnt', 'Rasam')]), slots, TODAY);
    expect(rows[1]!.name).toBeNull();
  });
});
