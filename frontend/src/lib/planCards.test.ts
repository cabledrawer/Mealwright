import { describe, expect, it } from 'vitest';
import { beforeCook, cookPlace, makesWords, weekCards } from './planCards';
import { timeWords } from './timeWords';
import { cookedOn, cookDayOf } from './planMeals';
import { PEOPLE, SLOTS, samplePlan } from './testing/planViews';

const plan = samplePlan();
const meal = (id: number) => plan.meals.find((m) => m.id === id)!;

describe('COOK and EAT are separate cards', () => {
  it('a batch’s cook-day meal is a COOK card plus an EAT card', () => {
    const cards = weekCards(plan, meal(3), PEOPLE, SLOTS);
    expect(cards.map((c) => [c.role, c.eyebrow])).toEqual([
      ['cook', `Cook · ${timeWords(30)}`],
      ['eat', 'Eat']
    ]);
    expect(cards[0]!.meta).toBe('Makes 6 · 4 tubs');
    expect(cards[0]!.prep).toBe('Soak the rice');
    expect(cards[1]!.who).toEqual(['Tess', 'Wren']);
    // The COOK card carries the batch colour as its dot; the EAT card wears it.
    expect(cards[0]!.colour).toBe(3);
    expect(cards[1]!.colour).toBe(3);
  });

  it('a tub is an EAT card that says which tub, and the last one says so', () => {
    const cards = weekCards(plan, meal(5), PEOPLE, SLOTS);
    expect(cards).toHaveLength(1);
    expect(cards[0]).toMatchObject({
      role: 'eat',
      eyebrow: 'Eat · tub 2 of 4',
      shown: 'Veg biryani'
    });
    expect(cards[0]!.name).toBe('Veg biryani tub');
    const last = weekCards(plan, meal(6), PEOPLE, SLOTS);
    expect(last.map((c) => c.eyebrow)).toEqual(['Eat · tub 3 of 4', 'Eat · last tub']);
    expect(last[0]!.who).toEqual(['Tess']);
  });

  it('a fresh recipe has no eyebrow; the pan comes with its small line', () => {
    const [card] = weekCards(plan, meal(1), PEOPLE, SLOTS);
    expect(card).toMatchObject({ role: 'fresh', eyebrow: null, colour: null, before: false });
    expect(card!.meta).toContain(timeWords(30));
  });
});

describe('tubs before the cook day', () => {
  const cook = { date: '2026-10-18', slot_id: 3 };

  it('compares the day, then the meal', () => {
    expect(beforeCook('2026-10-17', 3, cook, SLOTS)).toBe(true);
    expect(beforeCook('2026-10-18', 2, cook, SLOTS)).toBe(true);
    expect(beforeCook('2026-10-18', 3, cook, SLOTS)).toBe(true); // the cook meal itself
    expect(beforeCook('2026-10-19', 1, cook, SLOTS)).toBe(false);
  });

  it('does not judge a day whose cook meal is not known', () => {
    expect(beforeCook('2026-10-18', 1, { date: '2026-10-18', slot_id: null }, SLOTS)).toBe(false);
    expect(beforeCook('2026-10-17', 1, { date: '2026-10-18', slot_id: null }, SLOTS)).toBe(true);
  });

  it('flags the tub cards once the cook meal has moved past them', () => {
    const moved = samplePlan();
    const cookMeal = moved.meals.find((m) => m.id === 3)!;
    cookMeal.date = '2026-10-20'; // dragged to Tuesday dinner
    const flags = moved.meals
      .filter((m) => [4, 5, 6].includes(m.id))
      .flatMap((m) => weekCards(moved, m, PEOPLE, SLOTS).map((c) => [m.id, c.before]));
    // Mon lunch, Mon dinner and Tue lunch (two tubs) are all before Tue dinner.
    expect(flags).toEqual([
      [4, true],
      [5, true],
      [6, true],
      [6, true]
    ]);
    expect(weekCards(moved, cookMeal, PEOPLE, SLOTS)[0]!.before).toBe(false);
  });

  it('the cook day follows the cook meal, not the batch’s old cooked_on', () => {
    const moved = samplePlan();
    moved.meals.find((m) => m.id === 3)!.date = '2026-10-21';
    expect(cookPlace(moved, moved.batch_cooks[0]!)).toEqual({ date: '2026-10-21', slot_id: 3 });
    expect(cookDayOf(moved, moved.batch_cooks[0]!)).toBe('2026-10-21');
    expect(cookedOn(moved, '2026-10-21')).toHaveLength(1);
    expect(cookedOn(moved, '2026-10-18')).toHaveLength(0);
  });
});

describe('makesWords', () => {
  it('says portions and tubs', () => {
    expect(makesWords({ ...plan.batch_cooks[0]!, portions: 2, tub_count: 1 })).toBe(
      'Makes 2 · 1 tub'
    );
  });
});
