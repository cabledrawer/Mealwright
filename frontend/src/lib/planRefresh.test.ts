// The Plan refreshes by itself (RF5, H3; cabledrawer 11 Nov): "the Plan refreshes when you come back
// to it, after midnight and after another person's change". Before, it read the household's
// today once and never again, so a Plan left open overnight kept marking yesterday as today.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { network } from './network.svelte';
import { msUntilNextDay } from './planDates';
import { PlanModel } from './plan.svelte';
import { fakeApi } from './testing/fakeApi';

const household = (today: string) => ({
  name: 'Home',
  time_zone: 'Europe/London',
  week_starts_on: 1,
  tub_fridge_days: 0,
  tub_freezer_months: 0,
  today
});
const PLAN = { days: [], meals: [], batch_cooks: [], batch_sessions: [] };

beforeEach(() => network.reset());
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  network.reset();
});

/** A server whose today can be moved on. */
function server() {
  const state = { today: '2026-11-11' };
  const requests = fakeApi({
    'GET /household': () => [200, household(state.today)],
    'GET /meal-slots': [200, []],
    'GET /plan': [200, PLAN],
    'GET /plan/tubs-left': [200, { tubs: [], more: false }],
    'GET /plan/people': [200, []]
  });
  return { state, requests };
}

describe('refresh()', () => {
  it('reads the household’s today again, and a Plan that was on today moves on with it', async () => {
    const { state, requests } = server();
    const model = new PlanModel();
    await model.load();
    expect(model.today).toBe('2026-11-11');
    expect(model.anchor).toBe('2026-11-11');
    state.today = '2026-11-16'; // the next week's Monday: the week on show changes too
    await model.refresh();
    expect(model.today).toBe('2026-11-16');
    expect(model.anchor).toBe('2026-11-16');
    const last = requests.filter((r) => r.path === '/plan').at(-1)!;
    expect(last.url).toContain('from=2026-11-16');
  });

  it('keeps the week someone has moved to', async () => {
    const { state } = server();
    const model = new PlanModel();
    await model.load();
    model.anchor = '2026-12-02';
    state.today = '2026-11-12';
    await model.refresh();
    expect(model.today).toBe('2026-11-12');
    expect(model.anchor).toBe('2026-12-02');
  });

  it('reads the plan again when the day is the same (another person’s change)', async () => {
    const { requests } = server();
    const model = new PlanModel();
    await model.load();
    const before = requests.filter((r) => r.path === '/plan').length;
    await model.refresh();
    expect(requests.filter((r) => r.path === '/plan').length).toBe(before + 1);
  });
});

describe('msUntilNextDay()', () => {
  it('counts to midnight in the household’s zone, not the device’s', () => {
    // In November London is on UTC: 22:30 is 90 minutes before midnight.
    expect(msUntilNextDay(Date.parse('2026-11-11T22:30:00Z'), 'Europe/London')).toBe(90 * 60_000);
    // The same instant in Tokyo (UTC+9) is 07:30 the next morning: 16.5 hours to go.
    expect(msUntilNextDay(Date.parse('2026-11-11T22:30:00Z'), 'Asia/Tokyo')).toBe(16.5 * 3_600_000);
  });

  it('falls back to the device’s zone when the household has none, and never to zero', () => {
    const ms = msUntilNextDay(Date.parse('2026-11-11T12:00:00Z'), null);
    expect(ms).toBeGreaterThan(0);
    expect(ms).toBeLessThanOrEqual(24 * 3_600_000);
  });
});

describe('watchDay()', () => {
  it('refreshes just after midnight in the household’s zone, and arms the next midnight', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    vi.setSystemTime(new Date('2026-11-11T23:30:00Z'));
    const { state, requests } = server();
    const model = new PlanModel();
    await model.load();
    const stop = model.watchDay();
    state.today = '2026-11-12';
    await vi.advanceTimersByTimeAsync(31 * 60_000);
    await vi.waitFor(() => expect(model.today).toBe('2026-11-12'));
    expect(requests.filter((r) => r.path === '/household').length).toBe(2);
    // Another midnight is waiting: a day later it asks again.
    state.today = '2026-11-13';
    await vi.advanceTimersByTimeAsync(24 * 3_600_000);
    await vi.waitFor(() => expect(model.today).toBe('2026-11-13'));
    stop();
    const asked = requests.length;
    await vi.advanceTimersByTimeAsync(48 * 3_600_000);
    expect(requests.length).toBe(asked); // stopped: nothing more is asked
  });
});

describe('refreshSoon() (another person changed the plan)', () => {
  it('reads again once for a burst of events, after a short wait', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    const { requests } = server();
    const model = new PlanModel();
    await model.load();
    const before = requests.filter((r) => r.path === '/plan').length;
    model.refreshSoon(() => false);
    model.refreshSoon(() => false);
    model.refreshSoon(() => false);
    await vi.advanceTimersByTimeAsync(100);
    expect(requests.filter((r) => r.path === '/plan').length).toBe(before); // not yet
    await vi.advanceTimersByTimeAsync(1000);
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.path === '/plan').length).toBe(before + 1)
    );
  });

  it('waits while something is being carried, and reads when it is put down', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'Date'] });
    const { requests } = server();
    const model = new PlanModel();
    await model.load();
    const before = requests.filter((r) => r.path === '/plan').length;
    let busy = true;
    model.refreshSoon(() => busy);
    await vi.advanceTimersByTimeAsync(5000);
    expect(requests.filter((r) => r.path === '/plan').length).toBe(before);
    busy = false;
    await vi.advanceTimersByTimeAsync(2000);
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.path === '/plan').length).toBe(before + 1)
    );
  });
});
