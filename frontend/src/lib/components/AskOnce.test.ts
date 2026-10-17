import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { askOnce } from '$lib/askOnce.svelte';
import type { Ask } from '$lib/client/types';
import AskOnce from './AskOnce.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const ask: Ask = {
  food_id: 7,
  food_name: 'Toor dal',
  kind: 'weight_per_ml',
  question: 'About how much does 1 cup of toor dal weigh?',
  unit: 'g',
  per: 'cup',
  cup_ml: 250,
  suggested: 200
};

describe('the "ask once" question', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(() => {
    component = mount(AskOnce, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    askOnce.dismiss();
    flushSync();
    if (component) unmount(component);
  });

  it('asks, with the suggestion filled in and Remember on', async () => {
    const answer = askOnce.ask(ask);
    flushSync();
    const dialog = page.getByRole('dialog', { name: ask.question });
    await expect.element(dialog).toBeVisible();
    await expect.element(dialog.getByRole('textbox', { name: /^Your answer/ })).toHaveValue('200');
    await expect
      .element(dialog.getByRole('switch', { name: 'Remember for next time' }))
      .toHaveAttribute('aria-checked', 'true');
    await dialog.getByRole('textbox', { name: /^Your answer/ }).fill('180');
    await dialog.getByRole('button', { name: 'Save' }).click();
    expect(await answer).toEqual({
      kind: 'weight_per_ml',
      food_id: 7,
      grams: 180,
      remember: true
    });
  });

  it('Not now, or Escape, answers nothing', async () => {
    let answer = askOnce.ask(ask);
    flushSync();
    await page.getByRole('button', { name: 'Not now' }).click();
    expect(await answer).toBeNull();

    answer = askOnce.ask(ask);
    flushSync();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    await userEvent.keyboard('{Escape}');
    expect(await answer).toBeNull();
  });
});
