import { describe, expect, it } from 'vitest';
import type { RecipeStock } from './client/recipes';
import { cookDays, cookDayTotal, scaleWords, stillToBuy } from './planCook';
import { mealOf, recipeItem, samplePlan, SLOTS } from './testing/planViews';

const DAYS = ['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20'];

describe('cook scale', () => {
  it('writes up to two decimals and no trailing zeros', () => {
    expect(scaleWords(1)).toBe('1');
    expect(scaleWords(1.5)).toBe('1.5');
    expect(scaleWords(0.75)).toBe('0.75');
    expect(scaleWords(1.3333)).toBe('1.33');
  });
});

describe('cooking by day', () => {
  const plan = samplePlan();
  const days = cookDays(plan, SLOTS, DAYS);

  it('lists only the days with something to cook; tubs are not cooked', () => {
    expect(days.map((d) => d.day)).toEqual(['2026-10-17', '2026-10-18']);
  });

  it('describes a fresh meal: how many it is for and how long', () => {
    const [pongal] = days[0]!.entries;
    expect(pongal).toMatchObject({
      name: 'Pongal',
      slotName: 'Breakfast',
      batch: null,
      serves: 2,
      minutes: 30,
      recipeId: 5
    });
    expect(days[0]!.minutes).toBe(30);
  });

  it('describes a batch: × scale, makes N, eat N now, where each tub goes, spare tubs, prep', () => {
    const [biryani] = days[1]!.entries;
    expect(biryani).toMatchObject({
      name: 'Veg biryani',
      scale: '3',
      makes: 6,
      eatNow: 2,
      tubs: ['Mon lunch', 'Mon dinner', 'Tue lunch', 'Tue lunch'],
      spare: 2,
      prep: 'Soak the rice',
      serves: null,
      cooked: false
    });
  });

  it('leaves the scale out when the recipe has no Serves', () => {
    const odd = samplePlan();
    odd.meals[1]!.items[0]!.recipe!.serves = null;
    expect(cookDays(odd, SLOTS, DAYS)[1]!.entries[0]!.scale).toBeNull();
  });

  it('carries the way of cooking it the meal uses, so its stock is read for that way (M2)', () => {
    const two = samplePlan();
    two.meals[0]!.items[0]!.method_id = 11;
    expect(cookDays(two, SLOTS, DAYS)[0]!.entries[0]!.methodId).toBe(11);
    expect(days[0]!.entries[0]!.methodId).toBeNull();
  });

  it('leaves a deleted recipe nothing to start', () => {
    const gone = samplePlan();
    gone.meals[0]!.items[0] = recipeItem(1, 5, 'Pongal', { recipe: null, kept_name: 'Pongal' });
    expect(cookDays(gone, SLOTS, DAYS)[0]!.entries[0]!.recipeId).toBeNull();
  });

  it('shows a meal already cooked as cooked, and skips one that was not cooked or moved', () => {
    const done = samplePlan();
    // As the server reads a cooked meal: every item of it is cooked.
    const was = done.meals[0]!;
    done.meals[0] = {
      ...was,
      status: 'cooked',
      items: was.items.map((i) => ({ ...i, cooked: true }))
    };
    done.meals.push(mealOf(20, '2026-10-19', 1, [recipeItem(20, 6, 'Upma')], { status: 'didnt' }));
    const out = cookDays(done, SLOTS, DAYS);
    expect(out[0]!.entries[0]!.cooked).toBe(true);
    expect(out.map((d) => d.day)).toEqual(['2026-10-17', '2026-10-18']);
  });

  it('shows Cooked on the recipe that was cooked, not on the others of its meal (F157)', () => {
    const part = samplePlan();
    const meal = part.meals[0]!;
    meal.items = [
      recipeItem(31, 5, 'Khichdi'),
      { ...recipeItem(32, 6, 'Lentil soup'), cooked: true }
    ];
    const entries = cookDays(part, SLOTS, DAYS)[0]!.entries.filter((e) => e.meal.id === meal.id);
    expect(entries.map((e) => [e.name, e.cooked])).toEqual([
      ['Khichdi', false],
      ['Lentil soup', true]
    ]);
  });

  it('skips a meal that is switched off', () => {
    expect(
      cookDays(
        plan,
        SLOTS.filter((s) => s.id !== 1),
        DAYS
      ).map((d) => d.day)
    ).toEqual(['2026-10-18']);
  });
});

describe('still to buy', () => {
  const line = (id: number, name: string, state: RecipeStock['lines'][number]['state']) => ({
    line_id: id,
    food: { id, name },
    state,
    place: null
  });

  it('names what is short or missing, once each', () => {
    const stock: RecipeStock = {
      lines: [
        line(1, 'Saffron', 'missing'),
        line(2, 'Rice', 'in_stock'),
        line(3, 'Mint', 'short'),
        line(4, 'Salt', 'staple'),
        line(5, 'Saffron', 'missing')
      ],
      counted: 5,
      missing: 3,
      stock_unchecked: false
    };
    expect(stillToBuy(stock)).toEqual(['Saffron', 'Mint']);
  });
});

describe('the day header counts only what is not cooked (F164)', () => {
  const plan = samplePlan();
  const [day] = cookDays(plan, SLOTS, DAYS);
  const words = (m: number) => `${m} min`;

  it('counts what is left and its time', () => {
    expect(cookDayTotal(day!, words)).toBe('1 thing to cook · 30 min');
  });

  it('says All cooked when nothing is left, and leaves cooked time out', () => {
    const done = { ...day!, entries: day!.entries.map((e) => ({ ...e, cooked: true })) };
    expect(cookDayTotal(done, words)).toBe('All cooked');
    // The time of a cooked thing is left out of the day's time.
    const cooked = samplePlan();
    for (const meal of cooked.meals) for (const item of meal.items) item.cooked = true;
    const [first] = cookDays(cooked, SLOTS, DAYS);
    expect(first!.minutes).toBeNull();
    expect(cookDayTotal(first!, words)).toBe('All cooked');
  });
});

describe('long waits to start (M3)', () => {
  const ahead = {
    step_id: 3,
    step_text: 'Soak and grind the batter.',
    wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false },
    active_minutes: 30,
    eats_at: '08:00',
    start_day: '2026-10-16',
    start_time: '21:00',
    started_day: null,
    started_time: null,
    waited_minutes: null
  };

  it('shows the start on its day, even when nothing else is cooked then, with no cooking total', () => {
    const plan = samplePlan();
    plan.meals[0]!.items = [recipeItem(9, 5, 'Masala dosa', { ahead })];
    const days = cookDays(plan, SLOTS, ['2026-10-16', '2026-10-17']);
    const eve = days.find((d) => d.day === '2026-10-16')!;
    expect(eve.entries).toEqual([]);
    expect(eve.starts.map((s) => [s.item.id, s.time])).toEqual([[9, '21:00']]);
    expect(cookDayTotal(eve, (m) => `${m} min`)).toBe('');
    // The meal's own day is cooked as before, and has no start.
    expect(days.find((d) => d.day === '2026-10-17')!.starts).toEqual([]);
  });

  it('shows nothing for a start that is begun', () => {
    const plan = samplePlan();
    plan.meals[0]!.items = [
      recipeItem(9, 5, 'Masala dosa', {
        ahead: { ...ahead, started_day: '2026-10-16', started_time: '21:05' }
      })
    ];
    expect(cookDays(plan, SLOTS, ['2026-10-16'])).toEqual([]);
  });
});
