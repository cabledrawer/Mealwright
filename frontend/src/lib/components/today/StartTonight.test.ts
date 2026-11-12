// Today's "Start tonight" card (M3, F124; F228, cabledrawer 12 Nov): the work time is the server's
// (a saved Time that already holds the wait has it taken off) and "Start by" is the start time.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { PlanAhead } from '#lib/client/plan.js';
import { recipeItem, mealOf, samplePlan } from '#lib/testing/planViews.js';
import type { StartEntry } from '#lib/startWords.js';
import StartTonight from './StartTonight.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function show(active: number | null) {
  const ahead: PlanAhead = {
    step_id: 7,
    step_text: 'Cover the bowl and leave it.',
    wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false },
    active_minutes: active,
    eats_at: '08:00',
    start_day: '2026-11-11',
    start_time: '22:50',
    started_day: null,
    started_time: null,
    waited_minutes: null
  };
  const item = recipeItem(1, 24, 'Dosa Batter Recipe', { ahead });
  const meal = mealOf(1, '2026-11-12', 1, [item]);
  const entry: StartEntry = { key: 'a', meal, item, ahead, day: '2026-11-11', time: '22:50' };
  component = mount(StartTonight, {
    target: document.body,
    props: {
      entry,
      plan: { ...samplePlan(), meals: [meal] },
      today: '2026-11-11',
      slotName: 'Breakfast',
      onchanged: () => {}
    }
  });
  flushSync();
}

describe('Start tonight', () => {
  it('says the work without the wait and when to start by', async () => {
    show(25);
    await expect.element(page.getByText('Start tonight at 22:50')).toBeVisible();
    await expect
      .element(page.getByText('For Thu breakfast · Dosa Batter Recipe · 25 min of work'))
      .toBeVisible();
    await expect.element(page.getByText('Start by 22:50 so it’s ready by 08:00.')).toBeVisible();
    expect(document.body.textContent).not.toContain('12 h 25 min');
  });

  it('leaves the work out when the recipe has no Time', async () => {
    show(null);
    await expect.element(page.getByText('Start tonight at 22:50')).toBeVisible();
    expect(document.body.textContent).not.toContain('of work');
  });
});
