// The saved copy of Today belongs to the login that read it (security finding M1): another
// login's copy is refused and removed, an old-format copy is ignored, and a read that finishes
// after a wipe or a sign-out saves nothing.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TodayData } from './client/today';

const read = vi.hoisted(() => ({ today: vi.fn() }));
vi.mock('./client/today', async (original) => ({
  ...(await original<typeof import('./client/today')>()),
  getToday: read.today
}));

import { session } from './session.svelte';
import { COPY_KEY, forgetToday, readCopy, TodayModel } from './today.svelte';

const data = (): TodayData => ({
  today: '2026-10-17',
  first_day: false,
  slots: [],
  plan: { start: '2026-10-10', end: '2026-10-23', meals: [], batch_cooks: [], tubs: [] },
  people: [],
  waiting: [],
  tubs_left: [],
  tubs_left_more: false,
  use_soon_lots: [],
  use_soon_tubs: [],
  next_cook: null
});

const me = (id: number) => ({
  id,
  name: 'Someone',
  username: `login${id}`,
  role: 'admin' as const,
  theme: 'auto' as const
});

beforeEach(() => {
  localStorage.removeItem(COPY_KEY);
  session.me = me(1);
  read.today.mockReset();
});

afterEach(() => {
  localStorage.removeItem(COPY_KEY);
  session.me = null;
});

describe('the saved copy of Today', () => {
  it('is kept with its owner and read back by the same login', async () => {
    read.today.mockResolvedValue(data());
    await new TodayModel().load();
    const saved = JSON.parse(localStorage.getItem(COPY_KEY)!) as { v: number; login_id: number };
    expect(saved.v).toBe(3);
    expect(saved.login_id).toBe(1);
    expect(readCopy()?.today).toBe('2026-10-17');
  });

  it('saved before the Use soon tub rows changed (v 2) is refused and removed (F203)', () => {
    const old = data();
    // The old tub row: one tub, no place, "place_kind" and "number" instead.
    old.use_soon_tubs = [
      {
        id: 5,
        batch_id: 1,
        number: 1,
        tub_count: 3,
        recipe_name: 'Lemon rice',
        place_kind: 'fridge'
      }
    ] as unknown as TodayData['use_soon_tubs'];
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 2, login_id: 1, data: old }));
    expect(readCopy()).toBeNull();
    expect(localStorage.getItem(COPY_KEY)).toBeNull();
  });

  it('saved with the rolled-up tub rows (v 3) is used', () => {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 3, login_id: 1, data: data() }));
    expect(readCopy()?.today).toBe('2026-10-17');
  });

  it('is refused, and removed, for another login', () => {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 3, login_id: 1, data: data() }));
    session.me = me(2);
    expect(readCopy()).toBeNull();
    expect(localStorage.getItem(COPY_KEY)).toBeNull();
  });

  it('in the old format (no owner) is ignored and removed', () => {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 1, data: data() }));
    expect(readCopy()).toBeNull();
    expect(localStorage.getItem(COPY_KEY)).toBeNull();
  });

  it('is shown to nobody when the owner of the browser is not known', () => {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 3, login_id: 1, data: data() }));
    session.me = null;
    expect(readCopy()).toBeNull();
  });

  it('is not written by a read that finishes after a wipe', async () => {
    let finish: (value: TodayData) => void = () => {};
    read.today.mockReturnValue(new Promise<TodayData>((done) => (finish = done)));
    const model = new TodayModel();
    const loading = model.load();
    forgetToday(); // Sign out in another tab, or on this one
    finish(data());
    await loading;
    expect(localStorage.getItem(COPY_KEY)).toBeNull();
    expect(model.data).toBeNull();
  });

  it('is not written for a login that has signed out meanwhile', async () => {
    let finish: (value: TodayData) => void = () => {};
    read.today.mockReturnValue(new Promise<TodayData>((done) => (finish = done)));
    const loading = new TodayModel().load();
    session.me = me(2);
    finish(data());
    await loading;
    expect(localStorage.getItem(COPY_KEY)).toBeNull();
  });
});

describe('the first toast after Cooked it (F161)', () => {
  it('names the recipes this press cooked, never the whole meal', async () => {
    const { toasts } = await import('./toast.svelte');
    const { changeOf, fakeApi } = await import('./testing/fakeApi');
    fakeApi({
      'POST /plan/meals/5/mark-cooked': [
        201,
        {
          change: {
            ...changeOf(9, 'Cooked Lentil soup (Dinner on Fri 6 Nov)'),
            kind: 'plan_cooked'
          }
        }
      ]
    });
    const model = new TodayModel();
    const item = (id: number, name: string) => ({
      id,
      kind: 'recipe',
      recipe: { id, name },
      cooked: id === 1
    });
    model.data = {
      ...data(),
      plan: {
        ...data().plan,
        meals: [
          {
            id: 5,
            date: '2026-10-17',
            slot_id: 1,
            status: 'planned',
            items: [item(1, 'Banana bread'), item(2, 'Lentil soup')]
          }
        ]
      }
    } as unknown as TodayData;
    const waiting = { meal_id: 5, date: '2026-10-17', slot_id: 1 } as never;
    void model.cooked(waiting, null, undefined, undefined, 'Cooked Lentil soup');
    expect(toasts.current?.message).toBe('Cooked Lentil soup');
    toasts.dismiss();
  });
});
