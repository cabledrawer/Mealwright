// The Plan reads past the last day on show as far as a start can reach (RF3, H6): the same number
// of days as Today (the server's `start_ahead.MOST_DAYS_AHEAD`), so a recipe that waits up to ten
// days and is started on the last day shows its Start card in the Cook view.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const calls = vi.hoisted(() => ({
  getPlan: vi.fn(async () => ({ meals: [], tubs: [], batch_cooks: [], batch_sessions: [] })),
  getMealSlots: vi.fn(async () => []),
  getPeople: vi.fn(async () => []),
  getTubsLeft: vi.fn(async () => ({ tubs: [] }))
}));
vi.mock('./client/plan', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client/plan')>()),
  ...calls
}));
vi.mock('./client/household', () => ({
  getHousehold: async () => ({ today: '2026-11-11', week_starts_on: 1 })
}));

import { addDays } from './planDates';
import { PlanModel, START_DAYS_AHEAD } from './plan.svelte';

beforeEach(() => vi.clearAllMocks());

describe('how far the Plan reads past its last day', () => {
  it('is eleven days, the longest wait (ten days) and a day more', () => {
    expect(START_DAYS_AHEAD).toBe(11);
  });

  it('asks for the week and eleven days past it', async () => {
    const model = new PlanModel();
    await model.load();
    const last = model.days.at(-1)!;
    expect(calls.getPlan).toHaveBeenCalledWith(model.days[0], addDays(last, 11));
  });
});
