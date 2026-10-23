import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { ImportReview } from '$lib/client/imports';
import { ImportFlow } from '$lib/import.svelte';
import { network } from '$lib/network.svelte';
import { placesAndShops } from '$lib/placesAndShops.svelte';
import { fakeApi, PLACES, SHOPS } from '$lib/testing/fakeApi';
import AlreadySheet from './AlreadySheet.svelte';
import ImportStart from './ImportStart.svelte';
import ReviewScreen from './ReviewScreen.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn() }));

const REVIEW: ImportReview = {
  source: { kind: 'link', url: 'https://kitchen.example/dal', site: 'kitchen.example' },
  name: 'Sambar',
  description: null,
  author: 'A cook',
  time_minutes: 50,
  serves: 4,
  makes: null,
  tags: [],
  nutrition: { kcal: 320, protein: null, carbs: null, fat: null, fibre: null },
  photo: { state: 'off', photo: null, message: 'Photo not downloaded' },
  lines: [
    {
      kind: 'ingredient',
      written: '1 cup (200 g) thuvaram paruppu',
      words: 'thuvaram paruppu',
      amount: 200,
      amount_text: '200',
      unit: 'g',
      size: null,
      note: 'as written: 1 cup (200 g) thuvaram paruppu',
      readable: true,
      label: 'matched',
      food: { id: 1, name: 'Toor dal' },
      place: 'Cupboard',
      matched_by: 'thuvaram paruppu',
      counts: true,
      new_ingredient: { name: 'Thuvaram paruppu', counted_as: 'weight', place: null },
      learn_name: 'thuvaram paruppu'
    },
    {
      kind: 'ingredient',
      written: '1 red onion, sliced',
      words: 'red onion',
      amount: 1,
      amount_text: '1',
      unit: null,
      size: null,
      note: 'sliced',
      readable: true,
      label: 'to_confirm',
      food: { id: 2, name: 'Onions' },
      place: null,
      matched_by: null,
      counts: true,
      new_ingredient: {
        name: 'Red onion',
        counted_as: 'count',
        place: { id: 3, name: 'Cupboard' }
      },
      learn_name: 'red onion'
    },
    {
      kind: 'ingredient',
      written: '¼ tsp asafoetida',
      words: 'asafoetida',
      amount: 0.25,
      amount_text: '¼',
      unit: 'tsp',
      size: null,
      note: null,
      readable: true,
      label: 'needs_you',
      food: null,
      place: null,
      matched_by: null,
      counts: true,
      new_ingredient: { name: 'Asafoetida', counted_as: 'volume', place: null },
      learn_name: 'asafoetida'
    }
  ],
  steps: [
    { kind: 'step', text: 'Boil the dal.' },
    { kind: 'step', text: 'Add the rest.' }
  ],
  counts: { matched: 1, to_confirm: 1, needs_you: 1, staple: 0 },
  lines_cut: false,
  steps_cut: false,
  steps_shortened: 0,
  left_out: [{ heading: 'Tips', lines: 4 }]
};

describe('Import a recipe', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    placesAndShops.forget();
    fakeApi({ 'GET /places': [200, PLACES], 'GET /shops': [200, SHOPS] });
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  function show(flow: ImportFlow, which: typeof ImportStart | typeof ReviewScreen = ImportStart) {
    component = mount(which as typeof ImportStart, {
      target: document.body,
      props: { flow } as never
    });
    flushSync();
  }

  describe('the box', () => {
    it('has one box for a link or text, and says which it thinks it is', async () => {
      const flow = new ImportFlow();
      show(flow);
      await expect.element(page.getByLabelText('Paste a link or the recipe’s text')).toBeVisible();
      flow.text = 'https://kitchen.example/dal';
      flushSync();
      await expect
        .element(page.getByText('A link · your server visits this page once'))
        .toBeVisible();
      flow.text = 'Sambar\n1 onion';
      flushSync();
      await expect.element(page.getByText('Pasted text · nothing goes online')).toBeVisible();
    });

    it('can’t read an empty box', async () => {
      show(new ImportFlow());
      await expect.element(page.getByRole('button', { name: 'Read the recipe' })).toBeDisabled();
    });

    it('says importing from links is switched off, with Settings for an admin', async () => {
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      flow.problem = {
        code: 'import_switched_off',
        message: 'Importing from links is switched off',
        switchedOff: true,
        admin: true
      };
      show(flow);
      await expect.element(page.getByText('Importing from links is switched off')).toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Open Settings → Privacy' }))
        .toBeVisible();
      await page.getByRole('button', { name: 'Paste text instead' }).click();
      expect(flow.text).toBe('');
      expect(flow.problem).toBeNull();
    });

    it('tells a member an admin can switch it on, with no Settings link', async () => {
      const flow = new ImportFlow();
      flow.problem = {
        code: 'import_switched_off',
        message: 'Importing from links is switched off. An admin can switch it on.',
        switchedOff: true,
        admin: false
      };
      show(flow);
      await expect.element(page.getByText(/An admin can switch it on in Settings/)).toBeVisible();
      expect(document.body.textContent).not.toContain('Open Settings');
    });

    it('shows the other sentences as they come', async () => {
      const flow = new ImportFlow();
      flow.problem = {
        code: 'not_a_page',
        message: 'This link isn’t a web page.',
        switchedOff: false,
        admin: false
      };
      show(flow);
      await expect.element(page.getByText('This link isn’t a web page.')).toBeVisible();
    });

    it('needs the server: offline, the button is off and the note says why', async () => {
      network.offline = true;
      const flow = new ImportFlow();
      flow.text = 'Sambar\n1 onion';
      show(flow);
      await expect.element(page.getByText(/needs your Mealwright server/)).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Read the recipe' })).toBeDisabled();
    });

    it('says Reading… while the server works', async () => {
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      flow.phase = 'reading';
      show(flow);
      await expect.element(page.getByRole('button', { name: 'Reading…' })).toBeDisabled();
    });
  });

  describe('You already have this recipe', () => {
    it('offers Open it and Import again as a copy', async () => {
      const copy = vi.fn();
      component = mount(AlreadySheet, {
        target: document.body,
        props: {
          already: {
            recipe: { id: 9, name: 'Sambar' },
            site: 'kitchen.example',
            importedAt: '2026-10-03T10:00:00Z',
            photo: null
          },
          oncopy: copy,
          onclose: () => {}
        }
      });
      flushSync();
      await expect
        .element(page.getByRole('dialog', { name: 'You already have this recipe' }))
        .toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Open it' }))
        .toHaveAttribute('href', '/recipes/9');
      await page.getByRole('button', { name: 'Import again as a copy' }).click();
      expect(copy).toHaveBeenCalled();
    });
  });

  describe('the review', () => {
    async function reviewing() {
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({
        'POST /recipes/import': [200, REVIEW],
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS]
      });
      await flow.read();
      show(flow, ReviewScreen);
      return flow;
    }

    it('shows the counts, each line as written, and Photo not downloaded', async () => {
      await reviewing();
      await expect.element(page.getByText('1 matched')).toBeVisible();
      await expect.element(page.getByText('1 to confirm')).toBeVisible();
      await expect.element(page.getByText('1 needs you')).toBeVisible();
      await expect
        .element(page.getByText(/1 cup \(200 g\) thuvaram paruppu/).first())
        .toBeVisible();
      await expect.element(page.getByText('Photo not downloaded')).toBeVisible();
      await expect.element(page.getByRole('link', { name: 'Settings → Privacy' })).toBeVisible();
      await expect.element(page.getByText('Nothing is saved until you choose.')).toBeVisible();
      await expect
        .element(page.getByText('4 lines after “Tips” were left out. You can add them by hand.'))
        .toBeVisible();
    });

    it('has Save, and no Save & plan it until 0.6', async () => {
      await reviewing();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
      expect(document.body.textContent).not.toContain('plan it');
    });

    it('offers “Same as Onions” and New ingredient for a line to confirm', async () => {
      const flow = await reviewing();
      await expect.element(page.getByRole('button', { name: 'Same as “Onions”' })).toBeVisible();
      await expect
        .element(
          page.getByText('“Same as” adds “red onion” as another name for Onions when you save.')
        )
        .toBeVisible();
      await page.getByRole('button', { name: 'Same as “Onions”' }).click();
      expect(flow.choices[1]).toMatchObject({ kind: 'food', learn: true });
      await expect
        .element(page.getByText('Adds “red onion” as another name for Onions when you save.'))
        .toBeVisible();
      await page.getByRole('button', { name: 'Change' }).click();
      expect(flow.choices[1]).toBeUndefined();
    });

    it('offers Pick an ingredient, New ingredient and Treat as staple for a line that needs you', async () => {
      const flow = await reviewing();
      await expect.element(page.getByText('Not in your ingredients')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Pick an ingredient' })).toBeVisible();
      await page.getByRole('button', { name: 'Treat as staple' }).click();
      expect(flow.choices[2]).toMatchObject({ kind: 'staple', name: 'Asafoetida' });
      await expect.element(page.getByText(/Made a staple when you save/)).toBeVisible();
      // The first guess can be changed right there.
      await page.getByLabelText('Name').nth(1).fill('Hing');
      expect(flow.choices[2]).toMatchObject({ name: 'Hing' });
    });

    it('says how many lines will be saved without an ingredient', async () => {
      await reviewing();
      await expect
        .element(page.getByText('2 lines will be saved without an ingredient.', { exact: false }))
        .toBeVisible();
    });

    it('keeps Save off while offline, and says so', async () => {
      await reviewing();
      // The places the rows ask for have come: no answer is left to say we're connected.
      await vi.waitFor(() => expect(placesAndShops.places.length).toBeGreaterThan(0));
      network.offline = true;
      flushSync();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
      await expect
        .element(page.getByText('You’re offline. Save when you’re back online.'))
        .toBeVisible();
    });

    it('shows the line a refused Save is about', async () => {
      const flow = await reviewing();
      flow.saveProblem = { message: 'There’s already an ingredient called Onions.', line: 1 };
      flushSync();
      await expect
        .element(page.getByText('There’s already an ingredient called Onions.').first())
        .toBeVisible();
    });
  });
});
