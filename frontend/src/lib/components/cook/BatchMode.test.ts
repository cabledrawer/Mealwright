// The recipe timers of the Batch cook session (F227; cabledrawer 12 Nov): Start timer, Skip wait and
// End timer sit in one row, buttons of the same size; on a phone they stay in the row.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Schedule, ScheduleTask } from '#lib/client/batchMode.js';

const calls = vi.hoisted(() => ({ start: vi.fn(), timer: vi.fn(), done: vi.fn() }));
vi.mock('#lib/client/batchMode', () => ({
  startSchedule: calls.start,
  getSchedule: vi.fn(),
  markTaskDone: calls.done,
  undoTaskDone: vi.fn(),
  startTaskTimer: calls.timer
}));
vi.mock('#lib/client/recipes.js', () => ({
  getRecipe: vi.fn().mockRejectedValue(new Error('no recipes in this test'))
}));
vi.mock('#lib/chime', () => ({ primeChime: vi.fn(), playChime: vi.fn() }));

import { BatchModeModel } from '#lib/batchMode.svelte.js';
import { forgetBatchMode } from '#lib/batchModeStore.js';
import { ScreenAwake } from '#lib/screenAwake.svelte.js';
import BatchMode from './BatchMode.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const task = (over: Partial<ScheduleTask> & { id: string }): ScheduleTask => ({
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
});

const schedule = (tasks: ScheduleTask[]): Schedule => ({
  session_id: 7,
  cook_day: '2026-11-15',
  made_at: '2026-11-15T09:00:00.000000Z',
  stale: false,
  total_minutes: 60,
  minutes_left: 60,
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
  now_id: 't2',
  next_id: null,
  in_use: { hob: 0, pressure: 0, oven: 0 },
  done_count: 0,
  server_time: new Date().toISOString()
});

let component: ReturnType<typeof mount> | null = null;
beforeEach(() => localStorage.clear());
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  forgetBatchMode(7);
  localStorage.clear();
});

async function show(tasks: ScheduleTask[]) {
  calls.start.mockResolvedValue(schedule(tasks));
  const model = new BatchModeModel(7);
  await model.load();
  component = mount(BatchMode, {
    target: document.body,
    props: { model, awake: new ScreenAwake(), onexit: () => {}, oncooked: () => {} }
  });
  flushSync();
  return model;
}

const wait = (over: Partial<ScheduleTask> = {}) =>
  task({ id: 't1', hands: 'waiting', minutes: 60, end: 60, ...over });
const buttons = (row: Element) => [...row.querySelectorAll<HTMLElement>('button')];
const sizes = (found: HTMLElement[]) =>
  found.map((b) => {
    const r = b.getBoundingClientRect();
    return [Math.round(r.width), Math.round(r.height)];
  });

describe('the recipe timers of a Batch cook session', () => {
  it('puts Start timer and Skip wait in one row, the same size', async () => {
    await show([wait(), task({ id: 't2', start: 60, end: 65 })]);
    const row = document.querySelector('[data-testid="batch-timer"]')!;
    const found = buttons(row);
    expect(found.map((b) => b.firstChild?.textContent?.trim())).toEqual([
      'Start timer',
      'Skip wait'
    ]);
    expect(new Set(found.map((b) => b.parentElement)).size).toBe(1); // one row container
    expect(found[0]!.className).toBe(found[1]!.className);
    expect(found[0]!.classList.contains('go')).toBe(true);
    const [a, b] = sizes(found) as [number[], number[]];
    expect(a).toEqual(b);
    expect(
      Math.abs(found[0]!.getBoundingClientRect().top - found[1]!.getBoundingClientRect().top)
    ).toBeLessThan(1);
  });

  it('keeps them in the row, equal, on a narrow phone', async () => {
    document.body.style.width = '320px';
    await show([wait(), task({ id: 't2', start: 60, end: 65 })]);
    const found = buttons(document.querySelector('[data-testid="batch-timer"]')!);
    const [a, b] = sizes(found) as [number[], number[]];
    expect(a).toEqual(b);
    expect(found[1]!.getBoundingClientRect().left).toBeGreaterThan(
      found[0]!.getBoundingClientRect().left
    );
    expect(found[1]!.getBoundingClientRect().right).toBeLessThanOrEqual(
      document.querySelector('[data-testid="batch-timer"]')!.getBoundingClientRect().right
    );
    document.body.style.width = '';
  });

  it('has End timer, the same kind of button, in the same place while it runs', async () => {
    const started = new Date(Date.now() - 60_000).toISOString();
    const ends = new Date(Date.now() + 3_540_000).toISOString();
    await show([
      wait({ state: 'running', started_at: started, ends_at: ends }),
      task({ id: 't2', start: 60, end: 65 })
    ]);
    const row = document.querySelector('[data-testid="batch-timer"]')!;
    const found = buttons(row);
    expect(found).toHaveLength(1);
    expect(found[0]!.textContent).toContain('End timer');
    expect(found[0]!.classList.contains('go')).toBe(true);
    expect(found[0]!.parentElement!.className).toContain('acts');
    expect(row.querySelector('[role="timer"]')).not.toBeNull();
  });
});

describe('Show ingredients', () => {
  it('opens the Ingredients sheet, and Escape and Done both close it', async () => {
    await show([task({ id: 't2' })]);
    await page.getByRole('button', { name: 'Show ingredients' }).click();
    await expect.element(page.getByRole('dialog', { name: 'Ingredients' })).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    await page.getByRole('button', { name: 'Show ingredients' }).click();
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
  });
});
