// Change on every Check row (F214, cabledrawer 10 Nov): matched, to confirm, needs you and staple rows
// each have Change, one sheet to pick an ingredient, edit the name read, or make a new one.
// Cancel leaves the row as it was.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { ImportFlow } from '#lib/import.svelte.js';
import { renamedLine } from '#lib/importRename.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import type { FoodRow } from '#lib/client/types.js';
import { fakeApi, PLACES, SHOPS } from '#lib/testing/fakeApi.js';
import { reviewFlow, SAMPLE_LINES } from '#lib/testing/importSamples.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import ReviewScreen from './ReviewScreen.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: () => {} }));

let component: ReturnType<typeof mount> | null = null;

function show(flow: ImportFlow, phone = false) {
  component = mount(ReviewScreen, { target: document.body, props: { flow, phone } });
  flushSync();
}

beforeEach(async () => {
  await page.viewport(1280, 900);
  network.reset();
  placesAndShops.forget();
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  toasts.dismiss();
  undoHistory.clear();
  vi.unstubAllGlobals();
});

const change = (written: string) => page.getByRole('button', { name: `Change: ${written}` });
const SHOWN = [
  '1 cup (200 g) thuvaram paruppu', // matched
  '1 red onion, sliced', // to confirm
  '¼ tsp asafoetida', // needs you
  'salt to taste' // staple
];

const foodRow = (over: Partial<FoodRow> & { id: number; name: string }): FoodRow => ({
  other_names: [],
  matched_name: null,
  counted_as: 'weight',
  staple: false,
  counted_as_display: 'By weight',
  place: null,
  stand_ins: [],
  maybe_same: [],
  ...over
});

const FOODS: Record<string, [number, unknown]> = {
  'GET /places': [200, PLACES],
  'GET /shops': [200, SHOPS]
};

describe('Change on every row', () => {
  it('is on a matched, a to-confirm, a needs-you and a staple row', async () => {
    fakeApi({ ...FOODS });
    show(reviewFlow());
    for (const written of SHOWN) await expect.element(change(written)).toBeVisible();
  });

  it('opens one sheet with the three ways, and Cancel leaves the row as it was', async () => {
    fakeApi({ ...FOODS });
    const flow = reviewFlow();
    show(flow);
    const before = JSON.stringify(flow.review!.lines);
    await change('1 cup (200 g) thuvaram paruppu').click();
    const sheet = page.getByRole('group', { name: 'Change Toor dal' });
    await expect.element(sheet.getByRole('button', { name: 'Pick an ingredient' })).toBeVisible();
    await expect.element(sheet.getByRole('button', { name: 'Edit the name read' })).toBeVisible();
    await expect.element(sheet.getByRole('button', { name: 'New ingredient' })).toBeVisible();
    // Nothing is taken back on a row with no choice.
    expect(sheet.getByRole('button', { name: 'Back to how it was read' }).elements()).toEqual([]);
    await sheet.getByRole('button', { name: 'Cancel' }).click();
    await expect.element(sheet).not.toBeInTheDocument();
    expect(JSON.stringify(flow.review!.lines)).toBe(before);
    expect(flow.choices).toEqual({});
  });

  it('Pick an ingredient replaces a matched row’s ingredient with the one picked', async () => {
    fakeApi({
      ...FOODS,
      'GET /foods': [200, { foods: [foodRow({ id: 9, name: 'Masoor dal' })], total: 1 }],
      'GET /recipes': [200, { recipes: [], total: 0 }]
    });
    const flow = reviewFlow();
    show(flow);
    await change('1 cup (200 g) thuvaram paruppu').click();
    await page
      .getByRole('group', { name: 'Change Toor dal' })
      .getByRole('button', { name: 'Pick an ingredient' })
      .click();
    await page.getByRole('button', { name: /Masoor dal/ }).click();
    expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', food: { id: 9 } });
  });

  it('New ingredient opens the form with the name to edit, on a matched row too', async () => {
    fakeApi({ ...FOODS });
    const flow = reviewFlow();
    show(flow);
    await change('1 cup (200 g) thuvaram paruppu').click();
    await page
      .getByRole('group', { name: 'Change Toor dal' })
      .getByRole('button', { name: 'New ingredient' })
      .click();
    expect(flow.choices[1]).toMatchObject({ kind: 'new', name: 'Thuvaram paruppu' });
    await expect.element(page.getByLabelText('Name').first()).toBeVisible();
  });

  it('Edit the name read corrects the name, and a name nothing has leaves the row needing you', async () => {
    fakeApi({ ...FOODS, 'GET /foods': [200, { foods: [], total: 0 }] });
    const flow = reviewFlow();
    show(flow);
    await change('¼ tsp asafoetida').click();
    await page.getByRole('button', { name: 'Edit the name read' }).click();
    const box = page.getByLabelText('Name read');
    await expect.element(box).toHaveValue('asafoetida');
    await box.fill('hing powder');
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() => expect(flow.review!.lines[4]!.words).toBe('hing powder'));
    expect(flow.review!.lines[4]).toMatchObject({
      label: 'needs_you',
      food: null,
      new_ingredient: { name: 'Hing powder' }
    });
    // The line was as written still, and the New ingredient now starts from the corrected name.
    expect(flow.review!.lines[4]!.written).toBe('¼ tsp asafoetida');
    await expect
      .element(page.getByRole('button', { name: 'New ingredient “Hing powder”' }))
      .toBeVisible();
  });

  it('an ingredient with exactly that name becomes the row’s ingredient (ok)', async () => {
    fakeApi({
      ...FOODS,
      'GET /foods': [200, { foods: [foodRow({ id: 12, name: 'Hing' })], total: 1 }]
    });
    const flow = reviewFlow();
    show(flow);
    await change('¼ tsp asafoetida').click();
    await page.getByRole('button', { name: 'Edit the name read' }).click();
    await page.getByLabelText('Name read').fill('hing');
    await page.getByRole('button', { name: 'Done' }).click();
    await vi.waitFor(() => expect(flow.review!.lines[4]!.label).toBe('matched'));
    expect(flow.review!.lines[4]!.food).toEqual({ id: 12, name: 'Hing' });
  });

  it('an empty name is refused and nothing changes; Cancel leaves the row as it was', async () => {
    fakeApi({ ...FOODS });
    const flow = reviewFlow();
    show(flow);
    await change('¼ tsp asafoetida').click();
    await page.getByRole('button', { name: 'Edit the name read' }).click();
    await page.getByLabelText('Name read').fill('  ');
    await page.getByRole('button', { name: 'Done' }).click();
    await expect.element(page.getByText('Type a name.')).toBeVisible();
    expect(flow.review!.lines[4]!.words).toBe('asafoetida');
    await page.getByRole('button', { name: 'Cancel' }).first().click();
    expect(flow.review!.lines[4]!.words).toBe('asafoetida');
  });

  it('a choice on the row can be taken back with Back to how it was read', async () => {
    fakeApi({ ...FOODS });
    const flow = reviewFlow();
    flow.sameAs(3, { id: 2, name: 'Onions' });
    show(flow);
    await change('1 red onion, sliced').click();
    await page.getByRole('button', { name: 'Back to how it was read' }).click();
    expect(flow.choices[3]).toBeUndefined();
  });
});

describe('renamedLine (the lookup behind Edit the name read)', () => {
  const line = SAMPLE_LINES[4]!; // asafoetida, needs you
  it('matches by the ingredient’s name or another name for it, ignoring capitals and spaces', async () => {
    const hing = foodRow({ id: 3, name: 'Hing', other_names: ['Asafoetida'] });
    const byName = await renamedLine(line, '  HING ', async () => [hing]);
    expect(byName).toMatchObject({
      label: 'matched',
      food: { id: 3, name: 'Hing' },
      matched_by: null
    });
    const byOther = await renamedLine(line, 'asafoetida powder', async () => [
      { ...hing, other_names: ['asafoetida powder'] }
    ]);
    expect(byOther).toMatchObject({ label: 'matched', matched_by: 'asafoetida powder' });
  });

  it('a close match is not guessed: the row needs the person, with the corrected name as the guess', async () => {
    const found = await renamedLine(line, 'bbq rub', async () => [
      foodRow({ id: 4, name: 'Rub mix' })
    ]);
    expect(found).toMatchObject({
      label: 'needs_you',
      food: null,
      new_ingredient: { name: 'Bbq rub' }
    });
  });

  it('with no answer the row needs the person, and nothing throws', async () => {
    const found = await renamedLine(line, 'hing', async () => {
      throw new Error('offline');
    });
    expect(found.label).toBe('needs_you');
  });
});
