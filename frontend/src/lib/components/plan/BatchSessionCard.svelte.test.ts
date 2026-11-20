// The Plan's Batch cook card: while the session is under way it doesn't say "Start batch cook"
// (F234, cabledrawer 12 Nov).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { PlanSession } from '#lib/client/plan.js';
import type { PlanActions } from '#lib/planActions.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import BatchSessionCard from './BatchSessionCard.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

const session: PlanSession = {
  id: 3,
  cook_day: '2026-11-14',
  together_minutes: 110,
  one_by_one_minutes: 175,
  start_day: null,
  start_time: null
};

const recipe = (batch_id: number, left_out: string | null) => ({
  batch_id,
  recipe_id: batch_id,
  recipe_name: `Dish ${batch_id}`,
  tub_count: 2,
  pattern: 'dinners',
  colour: 'blue',
  left_out
});

function open(schedule: [number, unknown]) {
  fakeApi({ 'GET /batch-cook/sessions/3/schedule': schedule });
  const model = {
    plan: {
      batch_cooks: [1, 2].map((id) => ({
        id,
        recipe_name: `Dish ${id}`,
        tub_count: 2,
        colour: 'blue',
        session_id: 3
      }))
    },
    refresh: async () => {}
  };
  const actions = { model, readonly: false } as unknown as PlanActions;
  component = mount(BatchSessionCard, { target: document.body, props: { actions, session } });
  flushSync();
}

describe('the Batch cook card while the session is under way (F234)', () => {
  it('says Start batch cook before it is started', async () => {
    open([409, { detail: 'Not started.', code: 'schedule_not_started' }]);
    await expect.element(page.getByRole('button', { name: 'Start batch cook' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Carry on batch cook' }).elements()).toHaveLength(0);
  });

  it('says Carry on batch cook once it is started', async () => {
    open([200, { session_id: 3, recipes: [recipe(1, null), recipe(2, null)], tasks: [] }]);
    await expect.element(page.getByRole('button', { name: 'Carry on batch cook' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Start batch cook' }).elements()).toHaveLength(0);
  });

  it('keeps saying Carry on batch cook when every recipe in it is cooked (the schedule exists)', async () => {
    open([200, { session_id: 3, recipes: [recipe(1, 'cooked'), recipe(2, 'cooked')], tasks: [] }]);
    await expect.element(page.getByRole('button', { name: 'Carry on batch cook' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Start batch cook' }).elements()).toHaveLength(0);
  });

  it('ignores an older answer that arrives after a newer one', async () => {
    const answers: ((r: Response) => void)[] = [];
    vi.stubGlobal('fetch', () => new Promise<Response>((resolve) => answers.push(resolve)));
    const model = $state({
      plan: { batch_cooks: [] as unknown[] },
      refresh: async () => {}
    });
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(BatchSessionCard, { target: document.body, props: { actions, session } });
    flushSync();
    model.plan = { batch_cooks: [] }; // the plan was read again: a second question
    flushSync();
    await vi.waitFor(() => expect(answers).toHaveLength(2));
    const started = JSON.stringify({ session_id: 3, recipes: [recipe(1, null)], tasks: [] });
    const notStarted = JSON.stringify({ detail: 'Not started.', code: 'schedule_not_started' });
    answers[1]!(new Response(notStarted, { status: 409 })); // the newer answer first
    answers[0]!(new Response(started, { status: 200 })); // then the older one, late
    await new Promise((r) => setTimeout(r, 50));
    await expect.element(page.getByRole('button', { name: 'Start batch cook' })).toBeVisible();
  });

  it('does not ask while Batch cook is hidden', async () => {
    const { batchCook } = await import('#lib/batchCook.svelte.js');
    batchCook.shown = false;
    const requests = fakeApi({ 'GET /batch-cook/sessions/3/schedule': [200, { recipes: [] }] });
    const model = { plan: { batch_cooks: [] }, refresh: async () => {} };
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(BatchSessionCard, { target: document.body, props: { actions, session } });
    flushSync();
    await new Promise((r) => setTimeout(r, 50));
    batchCook.shown = true;
    expect(requests).toHaveLength(0);
  });
});
