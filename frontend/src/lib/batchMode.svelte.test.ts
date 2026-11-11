import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api';
import type { Schedule, ScheduleTask } from './client/batchMode';

const calls = vi.hoisted(() => ({
  start: vi.fn(),
  get: vi.fn(),
  done: vi.fn(),
  undo: vi.fn(),
  timer: vi.fn()
}));
vi.mock('./client/batchMode', () => ({
  startSchedule: calls.start,
  getSchedule: calls.get,
  markTaskDone: calls.done,
  undoTaskDone: calls.undo,
  startTaskTimer: calls.timer
}));
vi.mock('./chime', () => ({ primeChime: vi.fn(), playChime: vi.fn() }));

import { BatchModeModel } from './batchMode.svelte';

function task(over: Partial<ScheduleTask> & { id: string }): ScheduleTask {
  return {
    kind: 'step',
    title: `Do ${over.id}`,
    recipe_ids: [1],
    step_ids: [],
    start: 0,
    end: 5,
    minutes: 5,
    hands: 'hands',
    equipment: 'none',
    slot: null,
    lacks: false,
    state: 'ready',
    started_at: null,
    done_at: null,
    ends_at: null,
    ...over
  };
}

function schedule(tasks: ScheduleTask[]): Schedule {
  return {
    session_id: 7,
    cook_day: '2026-11-15',
    made_at: new Date().toISOString(),
    stale: false,
    total_minutes: 30,
    minutes_left: 10,
    kitchen: { hob_rings: 4, pressure_cookers: 1, oven: true },
    recipes: [
      {
        batch_id: 1,
        recipe_id: 1,
        recipe_name: 'Sambar',
        tub_count: 2,
        pattern: 'pick',
        colour: null
      }
    ],
    tasks,
    before: [],
    now_id: 't1',
    next_id: null,
    in_use: { hob: 0, pressure: 0, oven: 0 },
    done_count: 0,
    server_time: new Date().toISOString()
  };
}

const two = () => schedule([task({ id: 't1' }), task({ id: 't2', start: 5, end: 10 })]);
const offline = () => new ApiError(0, 'Couldn’t reach the server', 'network');

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});
afterEach(() => localStorage.clear());

describe('Batch cook mode model', () => {
  it('starts the mode and shows Now and Next', async () => {
    calls.start.mockResolvedValue(two());
    const model = new BatchModeModel(7);
    await model.load();
    expect(model.worked?.now?.id).toBe('t1');
    expect(model.worked?.next?.id).toBe('t2');
    expect(model.loading).toBe(false);
  });

  it('Done, next marks the task at once and sends it', async () => {
    calls.start.mockResolvedValue(two());
    const after = two();
    after.tasks[0] = { ...after.tasks[0]!, done_at: new Date().toISOString() };
    calls.done.mockResolvedValue(after);
    const model = new BatchModeModel(7);
    await model.load();
    model.mark('done', 't1');
    expect(model.worked?.now?.id).toBe('t2'); // before the server answers
    await model.flush();
    expect(calls.done).toHaveBeenCalledWith(7, 't1', expect.any(String));
    expect(model.pending).toEqual([]);
    expect(model.lastDone).toBe('t1');
  });

  it('keeps marks made offline on the phone and sends them in order when it can', async () => {
    calls.start.mockResolvedValue(two());
    calls.done.mockRejectedValueOnce(offline());
    const model = new BatchModeModel(7);
    await model.load();
    model.mark('done', 't1');
    await model.flush();
    expect(model.pending).toHaveLength(1);
    expect(model.worked?.now?.id).toBe('t2'); // it carries on locally
    const kept = JSON.parse(localStorage.getItem('mealwright.batchmode.7') ?? '{}');
    expect(kept.pending).toHaveLength(1);
    const after = two();
    after.tasks[0] = { ...after.tasks[0]!, done_at: new Date().toISOString() };
    calls.done.mockResolvedValue(after);
    await model.flush();
    expect(model.pending).toEqual([]);
  });

  it('sends the time a timer was pressed, so one started offline counts from then', async () => {
    calls.start.mockResolvedValue(
      schedule([task({ id: 't1', hands: 'waiting', equipment: 'pressure', slot: 1, minutes: 15 })])
    );
    calls.timer.mockRejectedValueOnce(offline());
    const model = new BatchModeModel(7);
    await model.load();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-11-15T10:00:00Z'));
    model.mark('timer', 't1');
    const pressed = model.pending[0]!.at;
    vi.setSystemTime(new Date('2026-11-15T10:20:00Z')); // the connection is back twenty minutes on
    calls.timer.mockResolvedValue(schedule([task({ id: 't1', hands: 'waiting' })]));
    await model.flush();
    vi.useRealTimers();
    expect(pressed).toBe('2026-11-15T10:00:00.000Z');
    expect(calls.timer).toHaveBeenLastCalledWith(7, 't1', pressed);
    model.stop();
  });

  it('tries the waiting marks again by itself when the first try fails', async () => {
    vi.useFakeTimers();
    try {
      calls.start.mockResolvedValue(two());
      calls.done.mockRejectedValueOnce(offline());
      const model = new BatchModeModel(7);
      await model.load();
      model.mark('done', 't1');
      await model.flush();
      expect(model.pending).toHaveLength(1);
      const after = two();
      after.tasks[0] = { ...after.tasks[0]!, done_at: new Date().toISOString() };
      calls.done.mockResolvedValue(after);
      await vi.advanceTimersByTimeAsync(3100);
      expect(model.pending).toEqual([]);
      model.stop();
    } finally {
      vi.useRealTimers();
    }
  });

  it('sends nothing, and tries nothing again, once the screen is left', async () => {
    vi.useFakeTimers();
    try {
      calls.start.mockResolvedValue(two());
      calls.done.mockRejectedValue(offline());
      const model = new BatchModeModel(7);
      await model.load();
      model.mark('done', 't1');
      await model.flush();
      expect(calls.done).toHaveBeenCalledTimes(1);
      model.stop(); // the retry was waiting
      await vi.advanceTimersByTimeAsync(10_000);
      await model.flush();
      expect(calls.done).toHaveBeenCalledTimes(1);
      expect(model.pending).toHaveLength(1); // still kept on the phone
    } finally {
      vi.useRealTimers();
    }
  });

  it('a reload while offline carries on from what the phone kept', async () => {
    calls.start.mockResolvedValue(two());
    calls.done.mockRejectedValue(offline());
    const first = new BatchModeModel(7);
    await first.load();
    first.mark('done', 't1');
    await first.flush();
    calls.start.mockRejectedValue(offline());
    const reloaded = new BatchModeModel(7);
    await reloaded.load();
    expect(reloaded.problem).toBeNull();
    expect(reloaded.worked?.now?.id).toBe('t2');
    expect(reloaded.pending).toHaveLength(1);
  });

  it('a mark the server refuses is dropped and its words shown', async () => {
    calls.start.mockResolvedValue(two());
    calls.done.mockRejectedValue(
      new ApiError(404, 'That task isn’t in this schedule.', 'not_found')
    );
    const model = new BatchModeModel(7);
    await model.load();
    model.mark('done', 't1');
    await model.flush();
    expect(model.pending).toEqual([]);
    expect(model.problem).toBe('That task isn’t in this schedule.');
  });

  it('asks again when another phone marked something, but not while its own marks wait', async () => {
    calls.start.mockResolvedValue(two());
    const model = new BatchModeModel(7);
    await model.load();
    const other = two();
    other.tasks[0] = { ...other.tasks[0]!, done_at: new Date().toISOString() };
    calls.get.mockResolvedValue(other);
    await model.refresh();
    expect(model.worked?.now?.id).toBe('t2');
    calls.done.mockRejectedValue(offline());
    model.mark('done', 't2');
    await model.flush();
    calls.get.mockClear();
    await model.refresh();
    expect(calls.get).not.toHaveBeenCalled();
  });

  it('Plan again makes it afresh and drops waiting marks', async () => {
    calls.start.mockResolvedValue(two());
    const model = new BatchModeModel(7);
    await model.load();
    await model.load(true);
    expect(calls.start).toHaveBeenLastCalledWith(7, true);
  });
});
