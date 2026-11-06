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
  eater_login_ids: [] as number[],
  items: [
    {
      id: id * 10,
      position: 0,
      kind: 'recipe' as const,
      recipe: { id: 1, name, removed: false, photo_url: null, time_minutes: null, kcal: null },
      tub_id: null,
      ingredient: null,
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
            ingredient: null,
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
        member_login_id: null,
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
