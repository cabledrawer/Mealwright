// The plan works backwards (M3, F124): the words and the sums behind "Start tonight at 21:00",
// "Done yesterday 21:40" and "Fermented 10 h 20 min · needed 8–12 h".

import { describe, expect, it } from 'vitest';
import type { PlanAhead, PlanItem } from './client/plan';
import {
  doneWords,
  hasToWords,
  isLate,
  neededWords,
  readyAt,
  startOptionWords,
  startsByNow,
  startsOn,
  startWords,
  stepTitle,
  waitedEnough,
  waitedWords,
  waitRange
} from './startWords';
import { recipeItem, samplePlan } from './testing/planViews';

const FERMENT = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };

const AHEAD: PlanAhead = {
  step_id: 7,
  step_text: 'Soak the rice and dal, grind to a batter and leave it. Add salt.',
  wait: FERMENT,
  active_minutes: 30,
  eats_at: '08:00',
  start_day: '2026-10-16',
  start_time: '21:00',
  started_day: null,
  started_time: null,
  waited_minutes: null
};

/** The app keeps a number with its unit by a no-break space: tests read it as a plain one. */
const plain = (text: string) => text.replaceAll('\u00a0', ' ');

describe('the words', () => {
  it('says a range of whole hours the way the mockup does, and anything else as the recipe page', () => {
    expect(waitRange(FERMENT)).toBe('8–12 h');
    expect(waitRange({ ...FERMENT, min_minutes: 240, max_minutes: 1440 })).toBe('4–24 h');
    expect(waitRange({ ...FERMENT, min_minutes: 480, max_minutes: 480 })).toBe('8 h');
    expect(plain(waitRange({ ...FERMENT, min_minutes: 90, max_minutes: 120 }))).toBe(
      '1 h 30 min – 2 h'
    );
    expect(
      plain(waitRange({ ...FERMENT, min_minutes: 480, max_minutes: 720, overnight: true }))
    ).toBe('8 h – overnight');
  });

  it('says a time offered, and what has to happen first', () => {
    expect(startOptionWords('2026-11-13', '21:00')).toBe('Fri 21:00');
    expect(hasToWords('ferment')).toBe('It has to ferment first.');
    expect(hasToWords('marinate')).toBe('It has to marinate first.');
  });

  it('says Start tonight in the evening and just Start at earlier in the day', () => {
    expect(startWords('21:00')).toBe('Start tonight at 21:00');
    expect(startWords('17:00')).toBe('Start tonight at 17:00');
    expect(startWords('07:00')).toBe('Start at 07:00');
  });

  it('cuts a step to its first sentence for a title', () => {
    expect(stepTitle(AHEAD.step_text)).toBe(
      'Soak the rice and dal, grind to a batter and leave it'
    );
    expect(stepTitle('Marinate overnight')).toBe('Marinate overnight');
    expect(stepTitle(`${'word '.repeat(40)}end.`, 30).endsWith('…')).toBe(true);
  });

  it('says when it was done, and how long it waited against what it needed', () => {
    expect(doneWords('2026-11-13', '21:40', '2026-11-14')).toBe('Done yesterday 21:40');
    expect(doneWords('2026-11-14', '08:05', '2026-11-14')).toBe('Done today 08:05');
    expect(doneWords('2026-11-11', '21:40', '2026-11-14')).toBe('Done Wed 21:40');
    expect(waitedWords('ferment', 620)).toBe('Fermented 10 h 20 min');
    expect(waitedWords('soak', 60)).toBe('Soaked 1 h');
    expect(neededWords(FERMENT)).toBe('needed 8–12 h');
    expect(waitedEnough(FERMENT, 479)).toBe(false);
    expect(waitedEnough(FERMENT, 480)).toBe(true);
  });
});

describe('what is to be started', () => {
  const withAhead = (ahead: PlanAhead | null, extra: Partial<PlanItem> = {}) => {
    const plan = samplePlan();
    const meal = plan.meals.find((m) => m.id === 1)!;
    meal.items = [recipeItem(50, 5, 'Masala dosa', { ahead, ...extra })];
    return { plan, meal };
  };

  it('lists a planned recipe on its start day, and not before or after', () => {
    const { plan } = withAhead(AHEAD);
    expect(startsOn(plan, '2026-10-16').map((s) => [s.item.id, s.time])).toEqual([[50, '21:00']]);
    expect(startsOn(plan, '2026-10-15')).toEqual([]);
    expect(startsOn(plan, '2026-10-17')).toEqual([]);
  });

  it('leaves out one that is begun, cooked, without a time, or in a meal that is not planned', () => {
    const begun = { ...AHEAD, started_day: '2026-10-16', started_time: '20:00' };
    expect(startsOn(withAhead(begun).plan, '2026-10-16')).toEqual([]);
    expect(startsOn(withAhead(AHEAD, { cooked: true }).plan, '2026-10-16')).toEqual([]);
    const none = { ...AHEAD, start_day: null, start_time: null };
    expect(startsOn(withAhead(none).plan, '2026-10-16')).toEqual([]);
    const { plan, meal } = withAhead(AHEAD);
    meal.status = 'cooked';
    expect(startsOn(plan, '2026-10-16')).toEqual([]);
    expect(startsOn(null, '2026-10-16')).toEqual([]);
  });

  it('Today lists what is to start today or should have, for a meal still to come', () => {
    const { plan } = withAhead(AHEAD);
    expect(startsByNow(plan, '2026-10-15')).toEqual([]);
    expect(startsByNow(plan, '2026-10-16')).toHaveLength(1);
    expect(startsByNow(plan, '2026-10-17')).toHaveLength(1); // not started in time: still asked
    expect(startsByNow(plan, '2026-10-18')).toEqual([]); // the meal itself has passed
  });

  it('orders them by day and time', () => {
    const { plan, meal } = withAhead(AHEAD);
    meal.items.push(
      recipeItem(51, 6, 'Idli', { ahead: { ...AHEAD, start_time: '19:00' } }),
      recipeItem(52, 7, 'Vada', { ahead: { ...AHEAD, start_time: '20:30' } })
    );
    expect(startsOn(plan, '2026-10-16').map((s) => s.item.id)).toEqual([51, 52, 50]);
  });
});

describe('when a start is ready (F228)', () => {
  it('adds minutes to a day and a time, across midnight', () => {
    expect(readyAt('2026-11-13', '22:50', 8 * 60 + 25)).toEqual({
      day: '2026-11-14',
      time: '07:15'
    });
    expect(readyAt('2026-11-14', '04:05', 505)).toEqual({ day: '2026-11-14', time: '12:30' });
    expect(readyAt('2026-12-31', '23:00', 120)).toEqual({ day: '2027-01-01', time: '01:00' });
  });

  it('is late only when it is ready after the meal', () => {
    const meal = { day: '2026-11-14', time: '12:30' };
    expect(isLate({ day: '2026-11-14', time: '12:30' }, meal)).toBe(false);
    expect(isLate({ day: '2026-11-14', time: '12:31' }, meal)).toBe(true);
    expect(isLate({ day: '2026-11-13', time: '23:59' }, meal)).toBe(false);
  });
});
