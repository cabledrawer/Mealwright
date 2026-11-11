import { describe, expect, it } from 'vitest';
import { eatDays, eatRows, eaterNames } from './planEat';
import { mealOf, noteItem, PEOPLE, recipeItem, samplePlan, SLOTS } from './testing/planViews';

const DAYS = ['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20'];

describe('who is eating', () => {
  it('names the people ticked, and nobody when the meal is for everyone', () => {
    expect(eaterNames(mealOf(1, DAYS[0]!, 1, []), PEOPLE)).toEqual([]);
    expect(eaterNames(mealOf(1, DAYS[0]!, 1, [], { eater_member_ids: [11, 10] }), PEOPLE)).toEqual([
      'Tess',
      'Wren'
    ]);
  });
});

describe('the Eat rows of a meal', () => {
  const plan = samplePlan();
  const meal = (id: number) => plan.meals.find((m) => m.id === id)!;

  it('says a plain recipe is fresh', () => {
    expect(eatRows(plan, meal(1), PEOPLE)).toEqual([
      { key: 'i1', name: 'Pongal', source: null, fresh: true, colour: null, solid: false }
    ]);
  });

  it('says a batch’s cook-day meal is freshly made, for the people ticked', () => {
    const [row] = eatRows(plan, meal(3), PEOPLE);
    expect(row).toMatchObject({
      name: 'Veg biryani',
      source: 'Freshly made · Tess, Wren',
      fresh: false,
      solid: true,
      colour: 3
    });
  });

  it('says where a tub comes from and whose it is', () => {
    const [row] = eatRows(plan, meal(4), PEOPLE);
    expect(row).toMatchObject({
      name: 'Veg biryani',
      source: 'Tub from Sun · Tess',
      solid: false,
      colour: 3
    });
  });

  it('falls back to the people ticked when the tub is nobody’s in particular', () => {
    const [row] = eatRows(plan, meal(5), PEOPLE);
    expect(row?.source).toBe('Tub from Sun · Wren');
  });

  it('joins the tubs of one batch in one meal: "2 tubs from Sun · Tess, Wren"', () => {
    const rows = eatRows(plan, meal(6), PEOPLE);
    expect(rows).toHaveLength(1);
    expect(rows[0]?.source).toBe('2 tubs from Sun · Tess, Wren');
  });

  it('shows a note as it was written and says nothing else', () => {
    const withNote = mealOf(9, DAYS[0]!, 3, [noteItem(9, 'Eating out')]);
    expect(eatRows(plan, withNote, PEOPLE)).toEqual([
      { key: 'i9', name: 'Eating out', source: null, fresh: false, colour: null, solid: false }
    ]);
  });

  it('names the people ticked on a fresh recipe', () => {
    const fresh = mealOf(9, DAYS[0]!, 3, [recipeItem(9, 5, 'Pongal')], { eater_member_ids: [10] });
    expect(eatRows(plan, fresh, PEOPLE)[0]?.source).toBe('Tess');
  });
});

describe('the Eat days', () => {
  const days = eatDays(samplePlan(), SLOTS, PEOPLE, DAYS);

  it('has a day for each date, with every meal that is on', () => {
    expect(days.map((d) => d.day)).toEqual(DAYS);
    expect(days[0]!.meals.map((m) => m.slot.name)).toEqual(['Breakfast', 'Lunch', 'Dinner']);
    expect(days[0]!.meals[1]!.meal).toBeNull();
  });

  it('adds up a day’s kcal, and leaves it out when no meal has any', () => {
    expect(days[0]!.kcal).toBe(400);
    expect(days[2]!.kcal).toBeNull();
  });

  it('marks the days a batch is cooked on', () => {
    expect(days.map((d) => d.cooks)).toEqual([false, true, false, false]);
  });

  it('is empty before the plan has loaded', () => {
    expect(eatDays(null, SLOTS, PEOPLE, DAYS)).toEqual([]);
  });
});
