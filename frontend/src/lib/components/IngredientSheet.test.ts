import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { kitchen } from '$lib/foods.sample.svelte';
import { ingredientEditor } from '$lib/ingredientEditor.svelte';
import IngredientSheet from './IngredientSheet.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

describe('the ingredient editor, opened from anywhere', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(() => {
    component = mount(IngredientSheet, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    ingredientEditor.close();
    flushSync();
    if (component) unmount(component);
    component = null;
  });

  it('opens for the food asked for, as a dialog', async () => {
    ingredientEditor.open(kitchen.foods[0]!.id);
    flushSync();
    const dialog = page.getByRole('dialog', { name: 'Edit toor dal' });
    await expect.element(dialog).toBeVisible();
    await expect.element(dialog.getByRole('heading', { name: 'Toor dal' })).toBeVisible();
    await expect.element(dialog.getByRole('switch', { name: 'Staple' })).toBeVisible();
  });

  it('closes with Done and with Escape', async () => {
    ingredientEditor.open(kitchen.foods[0]!.id);
    flushSync();
    await page.getByRole('button', { name: 'Done' }).click();
    expect(ingredientEditor.foodId).toBeNull();

    ingredientEditor.open(kitchen.foods[0]!.id);
    flushSync();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    await userEvent.keyboard('{Escape}');
    expect(ingredientEditor.foodId).toBeNull();
  });

  it('adds and removes other names', async () => {
    const food = kitchen.foods[0]!;
    ingredientEditor.open(food.id);
    flushSync();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: '+ Add' }).first().click();
    await userEvent.keyboard('tuvar dal{Enter}');
    expect(food.otherNames).toContain('tuvar dal');
    await dialog.getByRole('button', { name: 'Remove tuvar dal' }).click();
    expect(food.otherNames).not.toContain('tuvar dal');
  });

  it('every button is at least 44 px tall', async () => {
    ingredientEditor.open(kitchen.foods[0]!.id);
    flushSync();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    for (const button of document.querySelectorAll<HTMLElement>(
      'dialog button:not(.remove):not([role="switch"])'
    )) {
      expect(
        button.getBoundingClientRect().height,
        button.textContent ?? ''
      ).toBeGreaterThanOrEqual(44);
    }
  });
});
