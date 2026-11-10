// Cook mode on day two (M3, F124, mockup CookDay2-08): the steps up to the one that waited are
// folded, and Cook mode says how long it waited against how long it needed.

import { describe, expect, it } from 'vitest';
import type { PlanAhead } from './client/plan';
import { aheadView } from './cookAhead';
import { cookSteps } from './cookSteps';

const FERMENT = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };
const STEPS = cookSteps([
  { id: 1, kind: 'step', text: 'Wash the rice.' },
  { id: 2, kind: 'step', text: 'Soak the rice and dal.' },
  { id: 3, kind: 'step', text: 'Grind and leave the batter. It ferments.', wait: FERMENT },
  { id: 4, kind: 'step', text: 'Stir the batter. Add salt.' },
  { id: 5, kind: 'step', text: 'Heat the pan.' },
  { id: 6, kind: 'step', text: 'Make the dosas.' }
]);

const ahead = (extra: Partial<PlanAhead> = {}): PlanAhead => ({
  step_id: 3,
  step_text: 'Grind and leave the batter. It ferments.',
  wait: FERMENT,
  active_minutes: 30,
  eats_at: '08:00',
  start_day: '2026-11-13',
  start_time: '21:00',
  started_day: '2026-11-13',
  started_time: '21:40',
  waited_minutes: 620,
  ...extra
});

describe('Cook mode on day two', () => {
  it('folds the steps up to the one that waited, says when it was done and how long it waited', () => {
    const view = aheadView(ahead(), STEPS, '2026-11-14')!;
    expect(view).toMatchObject({
      index: 2,
      begun: true,
      range: '1–3',
      title: 'Grind and leave the batter',
      done: 'Done yesterday 21:40',
      needed: 'needed 8–12 h',
      enough: true,
      day: 2
    });
    expect(view.waited).toBe('Fermented 10 h 20 min');
  });

  it('says it has not waited long enough when it is under the shortest', () => {
    const view = aheadView(ahead({ waited_minutes: 300 }), STEPS, '2026-11-14')!;
    expect(view.enough).toBe(false);
    expect(view.waited).toBe('Fermented 5 h');
  });

  it('is not day two on the day it was begun', () => {
    const view = aheadView(
      ahead({ waited_minutes: 20, started_time: '21:40' }),
      STEPS,
      '2026-11-13'
    )!;
    expect(view.day).toBeNull();
    expect(view.done).toBe('Done today 21:40');
  });

  it('counts the days after a longer wait (a marinade of three nights)', () => {
    expect(aheadView(ahead(), STEPS, '2026-11-16')!.day).toBe(4);
  });

  it('knows where the step is before it is begun, and shows nothing folded', () => {
    const view = aheadView(
      ahead({ started_day: null, started_time: null, waited_minutes: null }),
      STEPS,
      '2026-11-13'
    )!;
    expect(view).toMatchObject({ index: 2, begun: false, done: null, waited: null, day: null });
  });

  it('says a first step that waits is step 1', () => {
    const view = aheadView(ahead({ step_id: 1 }), STEPS, '2026-11-14')!;
    expect(view.range).toBe('1');
  });

  it('shows nothing when the step that waited is not in the steps (another way, or an edit)', () => {
    expect(aheadView(ahead({ step_id: 99 }), STEPS, '2026-11-14')).toBeNull();
  });
});
