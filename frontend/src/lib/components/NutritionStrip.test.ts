import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import NutritionStrip from './NutritionStrip.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const FIGURES = { kcal: 268, protein: 5, carbs: 40, fat: 9, fibre: 2 };

describe('NutritionStrip: possibly out of date (0.7.0)', () => {
  let component: ReturnType<typeof mount> | null = null;
  afterEach(() => {
    if (component) unmount(component);
    component = null;
  });

  it('says so for an imported recipe that has been edited', async () => {
    component = mount(NutritionStrip, {
      target: document.body,
      props: { nutrition: FIGURES, outOfDate: true }
    });
    flushSync();
    await expect.element(page.getByText('Nutrition possibly out of date')).toBeVisible();
  });

  it('says nothing for any other recipe', async () => {
    component = mount(NutritionStrip, { target: document.body, props: { nutrition: FIGURES } });
    flushSync();
    await expect.element(page.getByText('Nutrition possibly out of date')).not.toBeInTheDocument();
  });
});
