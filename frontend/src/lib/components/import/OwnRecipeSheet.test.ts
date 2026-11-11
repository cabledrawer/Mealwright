// The sheet that makes a section its own recipe refuses a name another section already uses
// (RF4 I12): Save would otherwise refuse the second one with no line marked.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { ReviewLine } from '#lib/client/imports.js';
import { OWN_NAME_TAKEN } from '#lib/importOwn.js';
import { reviewFlow } from '#lib/testing/importSamples.js';
import OwnRecipeSheet from './OwnRecipeSheet.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function twoSections() {
  const flow = reviewFlow();
  const base = flow.review!.lines[0]!;
  const heading = (words: string): ReviewLine => ({
    ...base,
    kind: 'heading',
    words,
    written: words,
    label: null,
    food: null
  });
  flow.review!.lines = [
    heading('For the batter'),
    { ...base },
    heading('For the chutney'),
    { ...base }
  ];
  flow.review!.lines[0]!.own = { name: 'Sauce', amount: 2, unit: 'cup' };
  return flow;
}

describe('the section sheet', () => {
  it('says so when another section already makes a recipe with that name', async () => {
    const flow = twoSections();
    let closed = false;
    component = mount(OwnRecipeSheet, {
      target: document.body,
      props: { flow, heading: 2, onclose: () => (closed = true) }
    });
    flushSync();
    await page.getByLabelText('Name of the new recipe').fill(' sauce ');
    await page.getByLabelText('How much it makes').fill('2');
    await page.getByRole('button', { name: 'Make it its own recipe' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent(OWN_NAME_TAKEN);
    expect(closed).toBe(false);
    expect(flow.review!.lines[2]!.own).toBeFalsy();
    await page.getByLabelText('Name of the new recipe').fill('Chutney');
    await page.getByRole('button', { name: 'Make it its own recipe' }).click();
    expect(closed).toBe(true);
    expect(flow.review!.lines[2]!.own?.name).toBe('Chutney');
  });
});
