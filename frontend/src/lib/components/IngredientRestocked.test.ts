import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
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
      'GET /places': [200, { places: PLACES }],
      'GET /shops': [200, { shops: SHOPS }],
      'GET /household': [200, { today: '2026-11-02' }],
      'PATCH /foods/7': (request) => {
        const day = (request.body as { restocked_on: string }).restocked_on;
        const ago = day === '2026-11-02' ? 0 : 3;
        food = { ...food, restocked_on: day, restocked_days_ago: ago };
        return [200, { food, change: changeOf(ago === 0 ? 901 : 900, 'Toor dal restocked') }];
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

  const patches = () => requests.filter((r) => r.method === 'PATCH');

  it('typing a date sends nothing until the field is left, then one PATCH (not one per key)', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    const date = dialog.getByLabelText('Date restocked');
    await expect.element(date).toHaveAttribute('max', '2026-11-02');
    const input = date.element() as HTMLInputElement;
    input.focus();
    // Chrome fires "change" as each part of a typed date becomes valid.
    for (const typed of ['0001-10-12', '0020-10-12', '0202-10-12', '2025-10-12']) {
      await userEvent.keyboard('1');
      input.value = typed;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
    expect(patches()).toHaveLength(0);
    input.blur();
    await vi.waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0]!.body).toEqual({ restocked_on: '2025-10-12' });
  });

  it('a typed date that is junk, from last century or after today is put back, with no request', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    const date = dialog.getByLabelText('Date restocked');
    await expect.element(date).toHaveAttribute('max', '2026-11-02');
    const input = date.element() as HTMLInputElement;
    for (const typed of ['0001-10-03', '1999-12-31', '2026-11-03', '']) {
      input.focus();
      await userEvent.keyboard('1');
      input.value = typed;
      input.blur();
      expect(input.value).toBe('2026-10-12');
    }
    expect(patches()).toHaveLength(0);
  });

  it('Enter saves a typed date', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    const date = dialog.getByLabelText('Date restocked');
    await expect.element(date).toHaveAttribute('max', '2026-11-02');
    const input = date.element() as HTMLInputElement;
    input.focus();
    await userEvent.keyboard('1');
    input.value = '2026-10-30';
    await userEvent.keyboard('{Enter}');
    await vi.waitFor(() => expect(patches()).toHaveLength(1));
  });

  it('the hint keeps the days while a save is on its way', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: null });
    await expect.element(dialog.getByText('Restocked 3 weeks ago · 12 Oct 2026')).toBeVisible();
    expect(document.body.textContent).not.toContain('Not restocked yet');
  });

  it('the date field is off while offline, like the Restocked button', async () => {
    try {
      const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
      await expect.element(dialog.getByLabelText('Date restocked')).toBeEnabled();
      network.offline = true;
      await expect.element(dialog.getByLabelText('Date restocked')).toBeDisabled();
      await expect
        .element(dialog.getByRole('button', { name: 'Restocked', exact: true }))
        .toBeDisabled();
    } finally {
      network.reset();
    }
  });

  it('“Restocked” sends today (the household’s) as the day, and can be undone', async () => {
    const dialog = start({ staple: true, restocked_on: '2026-10-12', restocked_days_ago: 21 });
    await dialog.getByRole('button', { name: 'Restocked', exact: true }).click();
    await vi.waitFor(() => expect(patches()).toHaveLength(1));
    expect(patches()[0]!.body).toEqual({ restocked_on: '2026-11-02' });
    expect(requests.some((r) => r.path.endsWith('/restock'))).toBe(false);
    await expect.element(dialog.getByText('Restocked today · 2 Nov 2026')).toBeVisible();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Toor dal restocked'));
    expect(toasts.current?.action?.label).toBe('Undo');
  });
});
