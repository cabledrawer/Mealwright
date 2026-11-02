import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
import {
  PLACES,
  SHOPS,
  changeOf,
  fakeApi,
  toorDal,
  type FakeRequest
} from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import IngredientSheet from './IngredientSheet.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

// A staple's restock date in the ingredient editor (0.7 K5).
describe('the editor’s Restocked date', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];
  let food = toorDal();

  function start(overrides: Parameters<typeof toorDal>[0]) {
    food = toorDal(overrides);
    requests = fakeApi({
      'GET /foods/7': () => [200, food],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      'GET /household': [200, { today: '2026-11-02' }],
      'PATCH /foods/7': (request) => {
        const day = (request.body as { restocked_on: string }).restocked_on;
        food = { ...food, restocked_on: day, restocked_days_ago: 3 };
        return [200, { food, change: changeOf(900, 'Toor dal restocked') }];
      },
      'POST /foods/7/restock': () => {
        food = { ...food, restocked_on: '2026-11-02', restocked_days_ago: 0 };
        return [200, { food, change: changeOf(901, 'Toor dal restocked') }];
      },
      'POST /changes/901/undo': [
        200,
        { result: 'done', message: 'Undone.', change: changeOf(902, 'Undid'), food: null }
      ]
    });
    component = mount(IngredientSheet, { target: document.body });
    flushSync();
    ingredientEditor.open(7);
    flushSync();
    return page.getByRole('dialog', { name: 'Edit Toor dal' });
  }

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(() => {
    ingredientEditor.close();
    flushSync();
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('is only there for a staple', async () => {
    const dialog = start({ staple: false });
    await expect.element(dialog.getByRole('switch', { name: 'Staple' })).toBeVisible();
    expect(dialog.getByLabelText('Date restocked').elements()).toHaveLength(0);
  });

  it('shows the date, how long ago, and stops at the household’s today', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    const date = dialog.getByLabelText('Date restocked');
    await expect.element(date).toHaveValue('2026-10-12');
    await expect.element(dialog.getByText('Restocked 3 weeks ago · 12 Oct 2026')).toBeVisible();
    await vi.waitFor(() => expect(date.element().getAttribute('max')).toBe('2026-11-02'));
  });

  it('says so when it was never restocked', async () => {
    const dialog = start({ staple: true });
    await expect.element(dialog.getByText(/^Not restocked yet/)).toBeVisible();
  });

  it('saves a picked day as the household’s own day, with Undo in the toast', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    const date = dialog.getByLabelText('Date restocked');
    await expect.element(date).toBeVisible();
    await date.fill('2026-10-30');
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({
        restocked_on: '2026-10-30'
      })
    );
    await expect.element(dialog.getByText('Restocked 3 days ago · 30 Oct 2026')).toBeVisible();
  });

  it('“Restocked” sets it to now (the server’s clock) and can be undone', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    await dialog.getByRole('button', { name: 'Restocked', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.method === 'POST' && r.path === '/foods/7/restock')).toBe(true)
    );
    expect(requests.find((r) => r.path === '/foods/7/restock')?.body).toBeUndefined();
    await expect.element(dialog.getByText('Restocked today · 2 Nov 2026')).toBeVisible();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Toor dal restocked'));
    expect(toasts.current?.action?.label).toBe('Undo');
  });
});
