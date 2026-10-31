import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
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
import { handleUndoKey, undoHistory } from '#lib/undo.svelte.js';
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
    // Used in no recipe: the heading is still there, and says so calmly.
    await expect.element(dialog.getByRole('heading', { name: 'Used in recipes' })).toBeVisible();
    await expect.element(dialog.getByText('Not in any recipe yet.')).toBeVisible();
    expect(dialog.getByText(/^Used in \d/).elements()).toHaveLength(0);
  });

  it('asks “Pantry keeps it by”, with its hint (F119)', async () => {
    const dialog = await openToorDal();
    await expect.element(dialog.getByLabelText(/^Pantry keeps it by/)).toBeVisible();
    await expect
      .element(dialog.getByText(/The way you buy it: a 500.g jar → by weight\. Recipes can still/))
      .toBeVisible();
  });

  describe('the recipes that use it (0.4)', () => {
    const recipes = (names: string[]) => names.map((name, i) => ({ id: 30 + i, name }));

    /** Following a link would load a new page into the test runner. */
    function noNavigation() {
      const stop = (event: Event) => event.preventDefault();
      document.addEventListener('click', stop, true);
      return () => document.removeEventListener('click', stop, true);
    }

    it('lists them A to Z as links to their pages, under “Used in 3 recipes”', async () => {
      food = toorDal({ used_in_recipes: 3, used_in: recipes(['Dal tadka', 'Rasam', 'Sambar']) });
      const dialog = await openToorDal();
      await expect
        .element(dialog.getByRole('heading', { name: 'Used in 3 recipes' }))
        .toBeVisible();
      const links = dialog.getByRole('link').elements() as HTMLAnchorElement[];
      expect(links.map((a) => a.textContent)).toEqual(['Dal tadka', 'Rasam', 'Sambar']);
      expect(links.map((a) => new URL(a.href).pathname)).toEqual([
        '/recipes/30',
        '/recipes/31',
        '/recipes/32'
      ]);
      expect(dialog.getByRole('button', { name: /more/ }).elements()).toHaveLength(0);
    });

    it('says “Used in 1 recipe” for one', async () => {
      food = toorDal({ used_in_recipes: 1, used_in: recipes(['Sambar']) });
      const dialog = await openToorDal();
      await expect.element(dialog.getByRole('heading', { name: 'Used in 1 recipe' })).toBeVisible();
    });

    it('folds a long list behind “+ 2 more”, and the same button shows fewer again', async () => {
      const names = ['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((l) => `Recipe ${l}`);
      food = toorDal({ used_in_recipes: 7, used_in: recipes(names) });
      const dialog = await openToorDal();
      expect(dialog.getByRole('link').elements()).toHaveLength(5);
      const more = dialog.getByRole('button', { name: '+ 2 more recipes' });
      await expect.element(more).toHaveAttribute('aria-expanded', 'false');
      await more.click();
      expect(dialog.getByRole('link').elements()).toHaveLength(7);
      const fewer = dialog.getByRole('button', { name: 'Show fewer' });
      await expect.element(fewer).toHaveAttribute('aria-expanded', 'true');
      expect(document.activeElement).toBe(fewer.element()); // focus stays on the button
      await fewer.click();
      expect(dialog.getByRole('link').elements()).toHaveLength(5);
    });

    it('a long name wraps instead of widening the editor', async () => {
      const long = 'Spiced roasted cauliflower with tahini and pomegranate '.repeat(4).trim();
      food = toorDal({ used_in_recipes: 1, used_in: recipes([long]) });
      const dialog = await openToorDal();
      const link = dialog.getByRole('link', { name: long }).element() as HTMLElement;
      const box = (document.querySelector('dialog') as HTMLElement).getBoundingClientRect();
      expect(link.getBoundingClientRect().right).toBeLessThanOrEqual(box.right);
      expect(link.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    });

    it('following a recipe closes the editor; a new-tab click leaves it open', async () => {
      food = toorDal({ used_in_recipes: 2, used_in: recipes(['Rasam', 'Sambar']) });
      const dialog = await openToorDal();
      const restore = noNavigation();
      try {
        (dialog.getByRole('link', { name: 'Rasam' }).element() as HTMLElement).dispatchEvent(
          new MouseEvent('click', { bubbles: true, cancelable: true, ctrlKey: true })
        );
        expect(ingredientEditor.foodId).toBe(7);
        await dialog.getByRole('link', { name: 'Sambar' }).click();
        expect(ingredientEditor.foodId).toBeNull();
      } finally {
        restore();
      }
    });

    it('“Remove from Ingredients” says “Used in 3 recipes” first, and the recipes do not block it', async () => {
      food = toorDal({ used_in_recipes: 3, used_in: recipes(['Dal tadka', 'Rasam', 'Sambar']) });
      const dialog = await openToorDal();
      const hint = dialog.getByText(
        'Used in 3 recipes. Their lines keep their words and show “not linked”.'
      );
      await expect.element(hint).toBeVisible();
      const remove = dialog.getByRole('button', { name: 'Remove from Ingredients' });
      await expect
        .element(remove)
        .toHaveAccessibleDescription(
          'Used in 3 recipes. Their lines keep their words and show “not linked”.'
        );
      await remove.click();
      await vi.waitFor(() =>
        expect(toasts.current?.message).toBe('Removed Toor dal from Ingredients')
      );
      expect(toasts.current?.action?.label).toBe('Undo');
      toasts.act();
      await vi.waitFor(() =>
        expect(toasts.current?.message).toBe('Undone: Removed Toor dal from Ingredients')
      );
    });

    it('one recipe: “Its line keeps its words and shows “not linked”.”', async () => {
      food = toorDal({ used_in_recipes: 1, used_in: recipes(['Sambar']) });
      const dialog = await openToorDal();
      await expect
        .element(
          dialog.getByText('Used in 1 recipe. Its line keeps its words and shows “not linked”.')
        )
        .toBeVisible();
    });

    it('a recipe’s own made-ahead ingredient says why it can’t be removed, with a link', async () => {
      food = toorDal({
        used_in_recipes: 1,
        used_in: recipes(['Dosa']),
        made_by: { id: 31, name: 'Dosa batter' }
      });
      const dialog = await openToorDal();
      await expect.element(dialog.getByText(/^Made by the recipe/)).toBeVisible();
      await expect
        .element(dialog.getByText(/Turn off Made ahead there to remove it\./))
        .toBeVisible();
      const link = dialog.getByRole('link', { name: 'Dosa batter' });
      expect(new URL((link.element() as HTMLAnchorElement).href).pathname).toBe('/recipes/31');
      expect(
        dialog.getByRole('button', { name: 'Remove from Ingredients' }).elements()
      ).toHaveLength(0);
    });
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
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Couldn’t save. Try again.'));
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

  it('Ctrl+Z after removing an ingredient says what was undone', async () => {
    const dialog = await openToorDal();
    await dialog.getByRole('button', { name: 'Remove from Ingredients' }).click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Removed Toor dal from Ingredients')
    );
    document.body.addEventListener('keydown', handleUndoKey, { once: true });
    document.body.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true, cancelable: true })
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Undone: Removed Toor dal from Ingredients')
    );
    expect(requests.some((r) => r.path === '/changes/904/undo')).toBe(true);
  });

  it('won’t add a size whose name is only a number', async () => {
    const dialog = await openToorDal();
    await dialog.getByRole('button', { name: '+ Add a size' }).click();
    const name = dialog.getByRole('textbox', { name: 'Name' });
    await expect.element(name).toHaveAttribute('placeholder', 'packet, tub, dozen…');
    await name.fill('1');
    await dialog.getByRole('textbox', { name: 'Amount' }).fill('200');
    await dialog.getByRole('button', { name: 'Add', exact: true }).click();
    await expect
      .element(dialog.getByRole('alert'))
      .toHaveTextContent('Give the size a name, like tub or packet.');
    expect(requests.some((r) => r.url.includes('/sizes'))).toBe(false);
  });
});
