// Batch cook mode's state, worked out on the screen from the schedule and what is marked done or
// started (the same rules as the server's `batch_mode.states`, so a phone that is offline for a
// while still moves on by itself): a task is done, running (a waiting task with a timer going),
// ready (everything before it in its recipe is done) or later. Pure, so it is tested without a
// screen.

import type { ScheduleRecipe, ScheduleTask } from './client/batchMode';

/** What a task has on it: when its timer was started and when it was marked done (ISO text). */
export interface Marks {
  started_at: string | null;
  done_at: string | null;
}

export interface Worked {
  tasks: ScheduleTask[];
  now: ScheduleTask | null;
  next: ScheduleTask | null;
  inUse: { hob: number; pressure: number; oven: number };
  doneCount: number;
  /** Hands-on minutes still to give. */
  minutesLeft: number;
}

/** Each task's previous task in each of its recipes. */
function before(tasks: ScheduleTask[]): Map<string, string[]> {
  const last = new Map<number, string>();
  const out = new Map<string, string[]>();
  for (const task of tasks) {
    const found: string[] = [];
    for (const recipe of task.recipe_ids) {
      const prev = last.get(recipe);
      if (prev !== undefined && !found.includes(prev)) found.push(prev);
      last.set(recipe, task.id);
    }
    out.set(task.id, found);
  }
  return out;
}

export function work(tasks: ScheduleTask[], nowMs: number): Worked {
  const prior = before(tasks);
  const done = new Set<string>();
  const worked: ScheduleTask[] = [];
  for (const task of tasks) {
    const started = task.started_at ? Date.parse(task.started_at) : null;
    const ends = started !== null ? started + task.minutes * 60_000 : null;
    const waiting = task.hands === 'waiting';
    let state: ScheduleTask['state'];
    if (task.done_at || (waiting && ends !== null && ends <= nowMs)) state = 'done';
    else if (waiting && started !== null) state = 'running';
    else if ((prior.get(task.id) ?? []).every((p) => done.has(p))) state = 'ready';
    else state = 'later';
    if (state === 'done') done.add(task.id);
    worked.push({
      ...task,
      state,
      ends_at: state === 'running' && ends !== null ? new Date(ends).toISOString() : null
    });
  }
  const hands = worked.filter((t) => t.hands === 'hands' && t.state !== 'done');
  const now = hands.find((t) => t.state === 'ready') ?? null;
  const next = now
    ? (hands.find((t) => t.id !== now.id) ?? null)
    : (hands[0] ?? worked.find((t) => t.hands === 'waiting' && t.state === 'ready') ?? null);
  const inUse = { hob: 0, pressure: 0, oven: 0 };
  for (const t of worked) {
    const busy = t.state === 'running' || (now !== null && t.id === now.id);
    if (busy && t.equipment !== 'none' && !t.lacks) inUse[t.equipment]++;
  }
  return {
    tasks: worked,
    now,
    next,
    inUse,
    doneCount: worked.filter((t) => t.state === 'done').length,
    minutesLeft: hands.reduce((n, t) => n + t.minutes, 0)
  };
}

/** One recipe's row under Now: its running timer, a wait ready to start, or when it starts. */
export interface RecipeRow {
  recipe: ScheduleRecipe;
  kind: 'running' | 'ready' | 'later' | 'done' | 'over';
  task: ScheduleTask | null;
  /** Seconds left of a running timer. */
  left: number;
  /** About how many minutes until it starts (kind `later`). */
  inMinutes: number;
}

export function rows(recipes: ScheduleRecipe[], worked: Worked, nowMs: number): RecipeRow[] {
  const first = worked.tasks.find((t) => t.state !== 'done');
  return recipes.map((recipe) => {
    const mine = worked.tasks.filter(
      (t) => recipe.recipe_id !== null && t.recipe_ids.includes(recipe.recipe_id)
    );
    const running = mine.find((t) => t.state === 'running');
    if (running) {
      const left = Math.max(0, Math.ceil((Date.parse(running.ends_at ?? '') - nowMs) / 1000));
      return { recipe, kind: 'running', task: running, left, inMinutes: 0 };
    }
    const todo = mine.find((t) => t.state !== 'done');
    // A timer that has run out stays on the row ("Time’s up") until the recipe's next task is done.
    const over = mine.find(
      (t) => t.hands === 'waiting' && t.started_at && !t.done_at && t.state === 'done'
    );
    if (over && todo) return { recipe, kind: 'over', task: over, left: 0, inMinutes: 0 };
    const ready = mine.find((t) => t.hands === 'waiting' && t.state === 'ready');
    if (ready) return { recipe, kind: 'ready', task: ready, left: 0, inMinutes: 0 };
    if (!todo) return { recipe, kind: 'done', task: null, left: 0, inMinutes: 0 };
    const wait = Math.max(0, todo.start - (first?.start ?? 0));
    return { recipe, kind: 'later', task: todo, left: 0, inMinutes: Math.round(wait / 5) * 5 };
  });
}
