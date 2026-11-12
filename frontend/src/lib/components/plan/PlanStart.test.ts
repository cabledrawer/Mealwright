// "When will you start it?" sheet (M3 round 1): No time yet, and the note under the times says
// "Start at 07:00" for a morning time (as Today does) and "Start tonight at 21:00" in the evening.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { startAsk } from '#lib/startAsk.svelte.js';
import PlanStart from './PlanStart.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

const WAIT = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };

describe('the start question sheet', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    startAsk.dismiss();
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  function ask(time: string, options: { adding?: boolean } = { adding: true }) {
    fakeApi({
      'GET /plan/start-options': [
        200,
        {
          wait: WAIT,
          eats_at: '12:30',
          options: [{ day: '2026-11-14', time, ready_by: '12:30', ready_by_day: '2026-11-14' }]
        }
      ]
    });
    component = mount(PlanStart, { target: document.body });
    flushSync();
    return startAsk.ask(
      { id: 5, name: 'Masala dosa' },
      { day: '2026-11-14', slotId: 1, slotName: 'Lunch' },
      options
    );
  }

  it('No time yet adds the meal with no start (answers undefined)', async () => {
    const answer = ask('21:00');
    await page.getByRole('button', { name: 'No time yet' }).click();
    expect(await answer).toBeUndefined();
  });

  it('has no No time yet when the time of a planned meal is being changed', async () => {
    void ask('21:00', { adding: false });
    await expect.element(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
    expect(page.getByRole('button', { name: 'No time yet' }).elements()).toHaveLength(0);
  });

  const note = () => document.querySelector('.hint')?.textContent?.replace(/\s+/g, ' ').trim();

  it('says Start tonight in the evening, with the day before', async () => {
    void ask('21:00');
    await vi.waitFor(() =>
      expect(note()).toBe(
        'The day before, Today and the Cook view say “Start tonight at 21:00”. You can change the time from the meal.'
      )
    );
  });

  it('says Start at 07:00 for a morning time', async () => {
    void ask('07:00');
    await vi.waitFor(() =>
      expect(note()).toBe(
        'Today and the Cook view say “Start at 07:00”. You can change the time from the meal.'
      )
    );
  });

  // F228 (cabledrawer 12 Nov): the sheet says so when the chosen start can't be ready by the meal.
  const warning = () =>
    document
      .querySelector('[data-testid="plan-start-late"]')
      ?.textContent?.replace(/\s+/g, ' ')
      .trim();

  function askWith(options: unknown[], active: number | null, adding = true) {
    fakeApi({
      'GET /plan/start-options': [
        200,
        { wait: WAIT, eats_at: '12:30', active_minutes: active, options }
      ]
    });
    component = mount(PlanStart, { target: document.body });
    flushSync();
    return startAsk.ask(
      { id: 5, name: 'Dosa Batter' },
      { day: '2026-11-14', slotId: 1, slotName: 'Lunch' },
      { adding }
    );
  }

  it('says nothing for a start that is ready by the meal', async () => {
    void askWith(
      [{ day: '2026-11-13', time: '21:00', ready_by: '12:30', ready_by_day: '2026-11-14' }],
      25
    );
    await expect.element(page.getByRole('button', { name: 'Add to plan' })).toBeVisible();
    expect(warning()).toBeUndefined();
  });

  it('says so, and when it is ready, for an offered start that cannot be ready by the meal', async () => {
    void askWith(
      [{ day: '2026-11-14', time: '05:05', ready_by: '13:30', ready_by_day: '2026-11-14' }],
      25
    );
    await vi.waitFor(() =>
      expect(warning()).toBe(
        'Started then it won’t be ready by the meal: the earliest is Sat 13:30.'
      )
    );
  });

  it('works out Another time from the wait and the work, 8 h and 25 min here', async () => {
    void askWith([], 25, false);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    await page.getByLabelText('Day').fill('2026-11-14');
    await page.getByLabelText('Time').fill('04:05'); // ready 12:30: just in time
    expect(warning()).toBeUndefined();
    await page.getByLabelText('Time').fill('04:06'); // ready 12:31
    await vi.waitFor(() =>
      expect(warning()).toBe(
        'Started then it won’t be ready by the meal: the earliest is Sat 12:31.'
      )
    );
  });

  it('counts only the wait when the recipe has no Time', async () => {
    void askWith([], null, false);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    await page.getByLabelText('Day').fill('2026-11-14');
    await page.getByLabelText('Time').fill('04:30'); // 8 h: 12:30
    expect(warning()).toBeUndefined();
    await page.getByLabelText('Time').fill('04:31');
    await vi.waitFor(() => expect(warning()).toContain('Sat 12:31'));
  });
});
