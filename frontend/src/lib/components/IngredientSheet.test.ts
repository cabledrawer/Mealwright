import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { ingredientEditor } from '$lib/ingredientEditor.svelte';
import { PLACES, SHOPS, changeOf, fakeApi, toorDal, type FakeRequest } from '$lib/testing/fakeApi';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import IngredientSheet from './IngredientSheet.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const UUID = /^[0-9a-f-]{36}$/;

describe('the ingredient editor, opened from anywhere', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];
  let food = toorDal();

  beforeEach(() => {
    food = toorDal();
    undoHistory.clear();
    toasts.dismiss();
    requests = fakeApi({
      'GET /foods/7': () => [200, food],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      'PATCH /foods/7': (request) => {
        food = { ...food, ...(request.body as object) } as typeof food;
        return [200, { food, change: changeOf(900, 'Changed Toor dal') }];
      },
      'POST /foods/7/other-names': (request) => {
        const name = (request.body as { name: string }).name;
        food = { ...food, other_names: [...food.other_names, { id: 50, name }] };
        return [201, { food, change: changeOf(901, `Added ${name}`) }];
      },
      'POST /foods/7/split': (request) => {
        const id = (request.body as { other_name_id: number }).other_name_id;
        food = { ...food, other_names: food.other_names.filter((n) => n.id !== id) };
        return [
          201,
          {
            food: toorDal({ id: 60, name: 'arhar dal', other_names: [] }),
            change: changeOf(903, 'Made arhar dal its own food again')
          }
        ];
      },
      'DELETE /foods/7': [200, { change: changeOf(904, 'Removed Toor dal from Ingredients') }],
      'POST /changes/904/undo': [
        200,
        { result: 'done', message: '', change: changeOf(905, 'Undid'), food: null }
      ],
      'POST /changes/900/undo': [
        200,
        { result: 'done', message: 'Undone.', change: changeOf(902, 'Undid'), food: null }
      ]
    });
    component = mount(IngredientSheet, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    ingredientEditor.close();
    flushSync();
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  async function openToorDal() {
    ingredientEditor.open(7);
    flushSync();
    const dialog = page.getByRole('dialog', { name: 'Edit Toor dal' });
    await expect.element(dialog).toBeVisible();
    return dialog;
  }

  it('opens for the food asked for, as a dialog, with what the server says', async () => {
    const dialog = await openToorDal();
    await expect.element(dialog.getByRole('heading', { name: 'Toor dal' })).toBeVisible();
    await expect.element(dialog.getByText('Packet = 500 g')).toBeVisible();
    await expect.element(dialog.getByRole('switch', { name: 'Staple' })).toBeVisible();
    await expect.element(dialog.getByLabelText('Running low at')).toHaveValue('½ packet');
    await expect.element(dialog.getByLabelText(/^Lives in/)).toHaveDisplayValue('Cupboard');
    expect(dialog.getByText(/used in/i).elements()).toHaveLength(0); // waits for 0.4
  });

  it('closes with Done and with Escape', async () => {
    await openToorDal();
    await page.getByRole('button', { name: 'Done' }).click();
    expect(ingredientEditor.foodId).toBeNull();

    await openToorDal();
    await userEvent.keyboard('{Escape}');
    expect(ingredientEditor.foodId).toBeNull();
  });

  it('switching Staple saves at once, with a change ID, and offers Undo', async () => {
    const dialog = await openToorDal();
    const staple = dialog.getByRole('switch', { name: 'Staple' });
    await staple.click();
    await expect.element(staple).toHaveAttribute('aria-checked', 'true');
    await vi.waitFor(() => expect(requests.some((r) => r.method === 'PATCH')).toBe(true));
    const patch = requests.find((r) => r.method === 'PATCH')!;
    expect(patch.body).toEqual({ staple: true });
    expect(patch.headers['idempotency-key']).toMatch(UUID);
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Changed Toor dal'));
    expect(toasts.current?.action?.label).toBe('Undo');

    toasts.act();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.method === 'POST' && r.path === '/changes/900/undo')).toBe(true)
    );
  });

  it('a failed save puts the switch back and says so calmly', async () => {
    fakeApi({
      'GET /foods/7': [200, food],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      'PATCH /foods/7': [503, { detail: 'Busy' }]
    });
    const dialog = await openToorDal();
    const staple = dialog.getByRole('switch', { name: 'Staple' });
    await staple.click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Couldn’t save — try again'));
    await expect.element(staple).toHaveAttribute('aria-checked', 'false');
  });

  it('adds other names', async () => {
    const dialog = await openToorDal();
    await dialog.getByRole('button', { name: '+ Add' }).first().click();
    await userEvent.keyboard('tuvar dal{Enter}');
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/7/other-names')?.body).toEqual({
        name: 'tuvar dal'
      })
    );
    await expect.element(dialog.getByText(/tuvar dal/)).toBeVisible();
  });

  it('reads "Running low at" as an amount', async () => {
    const dialog = await openToorDal();
    const box = dialog.getByLabelText('Running low at');
    await box.fill('1 packet');
    await userEvent.keyboard('{Enter}');
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({
        running_low_at: { amount: 1, unit: 'packet' }
      })
    );
  });

  it('every button is at least 44 px tall', async () => {
    await openToorDal();
    await expect.element(page.getByText('Packet = 500 g')).toBeVisible();
    const buttons = document.querySelectorAll<HTMLElement>(
      'dialog button:not(.remove):not([role="switch"])'
    );
    expect(buttons.length).toBeGreaterThan(5);
    for (const button of buttons) {
      expect(
        button.getBoundingClientRect().height,
        button.textContent ?? ''
      ).toBeGreaterThanOrEqual(44);
    }
  });

  it('"Make its own ingredient" splits an other name off, with Undo, and stays on this food', async () => {
    const dialog = await openToorDal();
    await dialog.getByRole('button', { name: 'arhar dal', exact: true }).click();
    await dialog.getByRole('button', { name: 'Make its own ingredient' }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/7/split')?.body).toEqual({ other_name_id: 22 })
    );
    expect(requests.find((r) => r.path === '/foods/7/split')!.headers['idempotency-key']).toMatch(
      UUID
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Made arhar dal its own food again')
    );
    expect(toasts.current?.action?.label).toBe('Undo');
    await expect.element(dialog.getByRole('heading', { name: 'Toor dal' })).toBeVisible();
    expect(dialog.getByRole('button', { name: 'arhar dal', exact: true }).elements()).toHaveLength(
      0
    );
  });

  it('"Remove from Ingredients" shows only when none is in the pantry', async () => {
    food = toorDal({ stock: { amount: 750, display: '1½ packets · about 750 g' } });
    const dialog = await openToorDal();
    await expect.element(dialog.getByText('Packet = 500 g')).toBeVisible();
    expect(dialog.getByRole('button', { name: 'Remove from Ingredients' }).elements()).toHaveLength(
      0
    );
  });

  it('"Remove from Ingredients" removes it, with Undo', async () => {
    const dialog = await openToorDal();
    await dialog.getByRole('button', { name: 'Remove from Ingredients' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.method === 'DELETE' && r.path === '/foods/7')).toBe(true)
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Removed Toor dal from Ingredients')
    );
    expect(ingredientEditor.foodId).toBeNull(); // the editor closes
    toasts.act();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/904/undo')).toBe(true));
  });
});
