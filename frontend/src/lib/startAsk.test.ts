// "When will you start it?" (M3, F124; cabledrawer 9 Nov): a recipe with a long wait asks when it
// will be started, in every way a recipe is added to the plan, and again from the meal. Online
// only: with the server out of reach the recipe is planned as it always was, with no time.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanItem, StartOptions } from './client/plan';
import { methodAsk } from './methodAsk.svelte';
import { network } from './network.svelte';
import { optionalAsk } from './optionalAsk.svelte';
import { PlanModel } from './plan.svelte';
import { startAsk } from './startAsk.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const FERMENT = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };
const OPTIONS: StartOptions = {
  wait: FERMENT,
  eats_at: '08:00',
  options: [
    { day: '2026-11-13', time: '21:00', ready_by: '08:00', ready_by_day: '2026-11-14' },
    { day: '2026-11-13', time: '19:00', ready_by: '07:30', ready_by_day: '2026-11-14' }
  ]
};
const NONE: StartOptions = { wait: null, eats_at: '08:00', options: [] };
const WRITE = [200, { change: null, meal_id: 1, item_id: 2 }] as [number, unknown];

beforeEach(() => network.reset());
afterEach(() => {
  startAsk.dismiss();
  methodAsk.dismiss();
  optionalAsk.dismiss();
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

const body = (requests: ReturnType<typeof fakeApi>) =>
  requests.find((r) => r.method === 'POST' && r.path === '/plan/items')?.body;

describe('asking', () => {
  it('shows the times the server offers, the first picked, and answers with the one chosen', async () => {
    const requests = fakeApi({ 'GET /plan/start-options': [200, OPTIONS] });
    const answer = startAsk.ask(
      { id: 5, name: 'Masala dosa' },
      { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' }
    );
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    const question = startAsk.current!.question;
    expect(requests[0]!.url).toBe('/plan/start-options?recipe_id=5&date=2026-11-14&slot_id=1');
    expect(question).toMatchObject({
      recipeName: 'Masala dosa',
      where: 'Sat breakfast',
      eatsWords: 'Breakfast at 08:00',
      button: 'Add to plan'
    });
    expect(question.options.map((o) => `${o.day} ${o.time}`)).toEqual([
      '2026-11-13 21:00',
      '2026-11-13 19:00'
    ]);
    startAsk.answer({ day: '2026-11-13', time: '19:00' });
    expect(await answer).toEqual({ day: '2026-11-13', time: '19:00' });
  });

  it('asks about the way of cooking it the meal uses', async () => {
    const requests = fakeApi({ 'GET /plan/start-options': [200, OPTIONS] });
    void startAsk.ask(
      { id: 5, name: 'Masala dosa' },
      { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' },
      { method: 11 }
    );
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(requests[0]!.url).toContain('&method_id=11');
  });

  it('Cancel answers null', async () => {
    fakeApi({ 'GET /plan/start-options': [200, OPTIONS] });
    const answer = startAsk.ask(
      { id: 5, name: 'Masala dosa' },
      { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' }
    );
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    startAsk.dismiss();
    expect(await answer).toBeNull();
  });

  it('asks nothing when the server says the recipe has no long wait', async () => {
    fakeApi({ 'GET /plan/start-options': [200, NONE] });
    expect(
      await startAsk.ask(
        { id: 6, name: 'Plain rice' },
        { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' }
      )
    ).toBeUndefined();
    expect(startAsk.current).toBeNull();
  });

  it('asks nothing, and fetches nothing, of a recipe the list says has no long wait', async () => {
    const requests = fakeApi({});
    const meal = { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' };
    expect(await startAsk.ask({ id: 6, name: 'A', wait: null }, meal)).toBeUndefined();
    expect(
      await startAsk.ask(
        { id: 6, name: 'A', wait: { ...FERMENT, min_minutes: 30, max_minutes: 60 } },
        meal
      )
    ).toBeUndefined();
    expect(requests).toHaveLength(0);
  });

  it('a recipe with two ways is asked about even when the first has no wait', async () => {
    const requests = fakeApi({ 'GET /plan/start-options': [200, NONE] });
    const meal = { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' };
    await startAsk.ask({ id: 6, name: 'A', wait: null, method_count: 2 }, meal);
    expect(requests).toHaveLength(1);
  });

  it('plans as it always did when the server cannot be asked', async () => {
    fakeApi({});
    expect(
      await startAsk.ask(
        { id: 5, name: 'Masala dosa' },
        { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' }
      )
    ).toBeUndefined();
  });
});

describe('every way a recipe is added to the plan asks, through PlanModel.add', () => {
  it('sends the time chosen with the recipe', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'POST /plan/items': WRITE
    });
    const added = new PlanModel().add(
      { recipe: { id: 5, name: 'Masala dosa', wait: FERMENT } },
      '2026-11-14',
      1
    );
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    expect((await added).ok).toBe(true);
    expect(body(requests)).toEqual({
      date: '2026-11-14',
      slot_id: 1,
      recipe_id: 5,
      start: { day: '2026-11-13', time: '21:00' }
    });
  });

  it('plans nothing when the question is cancelled', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'POST /plan/items': WRITE
    });
    const added = new PlanModel().add({ recipe: { id: 5, name: 'Masala dosa' } }, '2026-11-14', 1);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    startAsk.dismiss();
    const outcome = await added;
    expect(outcome.ok === false && outcome.cancelled).toBe(true);
    expect(body(requests)).toBeUndefined();
  });

  it('a recipe with no long wait is planned at once, with no start in the request', async () => {
    const requests = fakeApi({ 'POST /plan/items': WRITE });
    await new PlanModel().add(
      { recipe: { id: 6, name: 'Plain rice', optional_count: 0, method_count: 1, wait: null } },
      '2026-11-14',
      1
    );
    expect(startAsk.current).toBeNull();
    expect(body(requests)).toEqual({ date: '2026-11-14', slot_id: 1, recipe_id: 6 });
  });

  it('an ingredient or a note is never asked', async () => {
    const requests = fakeApi({ 'POST /plan/items': WRITE });
    await new PlanModel().add({ ingredient: { id: 9, name: 'Banana' } }, '2026-11-14', 1);
    expect(requests.some((r) => r.path === '/plan/start-options')).toBe(false);
  });
});

describe('from the meal', () => {
  const item = (ahead: unknown) =>
    ({
      id: 77,
      kind: 'recipe',
      recipe: { id: 5, name: 'Masala dosa', removed: false },
      method_id: null,
      ahead
    }) as unknown as PlanItem;
  const AHEAD = {
    step_id: 3,
    step_text: 'Soak.',
    wait: FERMENT,
    active_minutes: 30,
    eats_at: '08:00',
    start_day: '2026-11-13',
    start_time: '20:00',
    started_day: null,
    started_time: null,
    waited_minutes: null
  };

  it('starts with the meal’s own time, shown first when it is not one of the suggestions, and sends the new one', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'PUT /plan/items/77/start': WRITE
    });
    const model = new PlanModel();
    model.plan = {
      start: '2026-11-14',
      end: '2026-11-14',
      meals: [
        {
          id: 1,
          date: '2026-11-14',
          slot_id: 1,
          status: 'planned',
          items: [item(AHEAD)],
          kcal: null,
          eater_login_ids: []
        }
      ],
      batch_cooks: [],
      tubs: []
    };
    model.slots = [{ id: 1, name: 'Breakfast', position: 1, enabled: true }];
    const changed = model.changeStart(item(AHEAD), '2026-11-14');
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(startAsk.current!.question.current).toEqual({ day: '2026-11-13', time: '20:00' });
    expect(startAsk.current!.question.button).toBe('Save');
    startAsk.answer({ day: '2026-11-13', time: '19:00' });
    await changed;
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({
      start: { day: '2026-11-13', time: '19:00' }
    });
  });

  it('the same time sends nothing', async () => {
    const requests = fakeApi({
      'GET /plan/start-options': [200, OPTIONS],
      'PUT /plan/items/77/start': WRITE
    });
    const model = new PlanModel();
    model.plan = {
      start: '2026-11-14',
      end: '2026-11-14',
      meals: [
        {
          id: 1,
          date: '2026-11-14',
          slot_id: 1,
          status: 'planned',
          items: [item(AHEAD)],
          kcal: null,
          eater_login_ids: []
        }
      ],
      batch_cooks: [],
      tubs: []
    };
    model.slots = [{ id: 1, name: 'Breakfast', position: 1, enabled: true }];
    const changed = model.changeStart(item(AHEAD), '2026-11-14');
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    startAsk.answer({ day: '2026-11-13', time: '20:00' });
    await changed;
    expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(0);
  });

  it('Done already marks the wait as begun', async () => {
    const requests = fakeApi({ 'PUT /plan/items/77/started': WRITE });
    await new PlanModel().markStarted(item(AHEAD));
    expect(requests[0]!.body).toEqual({ started: true });
  });
});
