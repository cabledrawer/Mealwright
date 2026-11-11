import { describe, expect, it } from 'vitest';
import type { ScheduleRecipe, ScheduleTask } from './client/batchMode';
import { rows, work } from './batchModeState';

const T0 = Date.parse('2026-11-15T10:00:00Z');
const min = (n: number) => T0 + n * 60_000;

function task(over: Partial<ScheduleTask> & { id: string }): ScheduleTask {
  return {
    kind: 'step',
    title: over.id,
    recipe_ids: [1],
    step_ids: [],
    start: 0,
    end: 5,
    minutes: 5,
    hands: 'hands',
    equipment: 'none',
    slot: null,
    lacks: false,
    state: 'later',
    started_at: null,
    done_at: null,
    ends_at: null,
    ...over
  };
}

const recipes: ScheduleRecipe[] = [
  { batch_id: 1, recipe_id: 1, recipe_name: 'Sambar', tub_count: 3, pattern: 'pick', colour: null },
  {
    batch_id: 2,
    recipe_id: 2,
    recipe_name: 'Chettinad',
    tub_count: 4,
    pattern: 'pick',
    colour: null
  }
];

// Shared chop (both), then Sambar's dal in the pressure cooker (waiting), then its tempering;
// Chettinad's frying.
const tasks = [
  task({ id: 't1', kind: 'prep', recipe_ids: [1, 2], minutes: 6, end: 6, title: 'Chop 3 onions' }),
  task({
    id: 't2',
    recipe_ids: [1],
    hands: 'waiting',
    equipment: 'pressure',
    slot: 1,
    start: 6,
    end: 21,
    minutes: 15
  }),
  task({ id: 't3', recipe_ids: [2], equipment: 'hob', slot: 1, start: 6, end: 14, minutes: 8 }),
  task({ id: 't4', recipe_ids: [1], equipment: 'hob', slot: 2, start: 21, end: 26, minutes: 5 })
];

describe('batch cook mode state', () => {
  it('starts with the shared prep as Now and the next hands-on task as Next', () => {
    const w = work(tasks, min(0));
    expect(w.now?.id).toBe('t1');
    expect(w.next?.id).toBe('t3');
    expect(w.tasks.map((t) => t.state)).toEqual(['ready', 'later', 'later', 'later']);
    expect(w.minutesLeft).toBe(6 + 8 + 5);
  });

  it('a done task frees what follows it in each of its recipes', () => {
    const done = tasks.map((t) => (t.id === 't1' ? { ...t, done_at: '2026-11-15T10:06:00Z' } : t));
    const w = work(done, min(6));
    expect(w.now?.id).toBe('t3');
    expect(w.tasks.find((t) => t.id === 't2')?.state).toBe('ready'); // its timer can be started
    expect(w.tasks.find((t) => t.id === 't4')?.state).toBe('later'); // waits for the dal
    expect(w.doneCount).toBe(1);
  });

  it('a running timer holds its equipment and ends by itself', () => {
    const run = tasks.map((t) =>
      t.id === 't1'
        ? { ...t, done_at: '2026-11-15T10:06:00Z' }
        : t.id === 't2'
          ? { ...t, started_at: '2026-11-15T10:07:00Z' }
          : t
    );
    const during = work(run, min(10));
    expect(during.tasks.find((t) => t.id === 't2')?.state).toBe('running');
    expect(during.inUse).toEqual({ hob: 1, pressure: 1, oven: 0 }); // the dal and the frying
    const after = work(run, min(23));
    expect(after.tasks.find((t) => t.id === 't2')?.state).toBe('done');
    expect(after.tasks.find((t) => t.id === 't4')?.state).toBe('ready');
    expect(after.inUse.pressure).toBe(0);
  });

  it('says when each recipe starts, has a timer running, or is ready for its timer', () => {
    const start = work(tasks, min(0));
    const first = rows(recipes, start, min(0));
    expect(first.map((r) => r.kind)).toEqual(['later', 'later']);
    const run = tasks.map((t) =>
      t.id === 't1'
        ? { ...t, done_at: '2026-11-15T10:06:00Z' }
        : t.id === 't2'
          ? { ...t, started_at: '2026-11-15T10:07:00Z' }
          : t
    );
    const w = work(run, min(10));
    const r = rows(recipes, w, min(10));
    expect(r[0]!.kind).toBe('running');
    expect(r[0]!.left).toBe(12 * 60); // 15 minutes from 10:07, at 10:10
    expect(r[1]!.kind).toBe('later');
    const over = work(run, min(23));
    expect(rows(recipes, over, min(23))[0]!.kind).toBe('over');
    const waiting = work(
      tasks.map((t) => (t.id === 't1' ? { ...t, done_at: '2026-11-15T10:06:00Z' } : t)),
      min(7)
    );
    expect(rows(recipes, waiting, min(7))[0]!.kind).toBe('ready');
  });

  it('is done when everything is', () => {
    const all = tasks.map((t) => ({ ...t, done_at: '2026-11-15T11:00:00Z' }));
    const w = work(all, min(60));
    expect(w.now).toBeNull();
    expect(w.next).toBeNull();
    expect(w.doneCount).toBe(4);
    expect(rows(recipes, w, min(60)).map((r) => r.kind)).toEqual(['done', 'done']);
  });
});
