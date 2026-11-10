import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { DraftOut } from '#lib/client/drafts.js';
import type { ImportReview } from '#lib/client/imports.js';
import { ImportFlow } from '#lib/import.svelte.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { handleUndoKey, undoHistory } from '#lib/undo.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { fakeApi, PLACES, SHOPS } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW, reviewFlow } from '#lib/testing/importSamples.js';
import AlreadySheet from './AlreadySheet.svelte';
import ImportStart from './ImportStart.svelte';
import ReviewScreen from './ReviewScreen.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The page's own guard against leaving (beforeNavigate) is kept here so a test can leave.
const nav = vi.hoisted(() => ({
  goto: vi.fn(),
  guard: null as null | ((navigation: unknown) => void)
}));
vi.mock('$app/navigation', () => ({
  goto: nav.goto,
  beforeNavigate: (guard: (navigation: unknown) => void) => {
    nav.guard = guard;
  }
}));

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

    it('says several links are read one after another (F110)', async () => {
      const flow = new ImportFlow();
      show(flow);
      flow.text = 'https://kitchen.example/dal\nhttps://kitchen.example/rice';
      flushSync();
      await expect.element(page.getByText('2 links · one after another')).toBeVisible();
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
        .element(page.getByRole('link', { name: 'Open Settings', exact: true }))
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

    it('tells how to paste the recipe when a site refuses, with the box empty and ready (F115)', async () => {
      const flow = new ImportFlow();
      flow.problem = {
        code: 'site_refused',
        message:
          'That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.',
        switchedOff: false,
        admin: false
      };
      show(flow);
      await expect
        .element(page.getByText(/That site wouldn’t let Mealwright read the page/))
        .toBeVisible();
      const steps = page.getByRole('list', { name: 'How to paste the recipe instead' });
      await expect.element(steps).toBeVisible();
      await expect
        .element(steps.getByRole('listitem').first())
        .toHaveTextContent(
          'Open the recipe in your browser. Tip: the page’s “Print recipe” button gives a cleaner copy.'
        );
      await expect
        .element(steps.getByRole('listitem').nth(1))
        .toHaveTextContent('Select from the title to the end of the method, and copy it.');
      await expect
        .element(steps.getByRole('listitem').nth(2))
        .toHaveTextContent('Paste it here, in place of the link. Pasted text never goes online.');
      const box = page.getByLabelText('Paste a link or the recipe’s text');
      await expect.element(box).toHaveValue('');
      await expect.element(box).toHaveFocus();
    });

    it('gives the how-to steps to a refusing site only, not to the other refusals (F115)', async () => {
      const flow = new ImportFlow();
      flow.problem = {
        code: 'timeout',
        message: 'That site took too long to answer. Try again later.',
        switchedOff: false,
        admin: false
      };
      show(flow);
      await expect
        .element(page.getByText('That site took too long to answer. Try again later.'))
        .toBeVisible();
      expect(
        page.getByRole('list', { name: 'How to paste the recipe instead' }).elements()
      ).toHaveLength(0);
    });

    it('needs the server: offline, the button is off and the note says why', async () => {
      network.offline = true;
      network.deviceOffline = true;
      const flow = new ImportFlow();
      flow.text = 'Sambar\n1 onion';
      show(flow);
      await expect.element(page.getByText(/needs your Mealwright server/)).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Read the recipe' })).toBeDisabled();
    });

    it('server down: the note says the server can’t be reached, not that the device is offline', async () => {
      network.offline = true;
      network.deviceOffline = false;
      const flow = new ImportFlow();
      flow.text = 'Sambar\n1 onion';
      show(flow);
      await expect
        .element(page.getByText('Can’t reach your Mealwright server. Try again when it’s back.'))
        .toBeVisible();
      expect(document.body.textContent).not.toMatch(/back online/);
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

    it('fetches the places again when Check opens, for one made on another phone (M1)', async () => {
      await placesAndShops.load();
      expect(placesAndShops.places.map((p) => p.id)).not.toContain(9);
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({
        'POST /recipes/import': [200, REVIEW],
        'GET /places': [200, [...PLACES, { id: 9, name: 'Garage freezer', kind: 'freezer' }]],
        'GET /shops': [200, SHOPS]
      });
      await flow.read();
      show(flow, ReviewScreen);
      await vi.waitFor(() => expect(placesAndShops.places.map((p) => p.id)).toContain(9));
    });

    it('shows the counts, each line as written, and Photo not downloaded', async () => {
      await reviewing();
      await expect.element(page.getByText('1 matched')).toBeVisible();
      await expect.element(page.getByText('1 to confirm')).toBeVisible();
      await expect.element(page.getByText('1 needs you')).toBeVisible();
      await expect
        .element(page.getByText(/1 cup \(200 g\) thuvaram paruppu/).first())
        .toBeVisible();
      await expect
        .element(page.getByText(/^Photo not downloaded\. Photo downloads are off in Settings/))
        .toBeVisible();
      await expect
        .element(page.getByText(/Settings → Privacy\. You can add your own photo later\.$/))
        .toBeVisible();
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
      expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', learn: true });
      await expect
        .element(page.getByText('Adds “red onion” as another name for Onions when you save.'))
        .toBeVisible();
      await page.getByRole('button', { name: 'Change' }).click();
      expect(flow.choices[1]).toBeUndefined();
    });

    it('offers Pick an ingredient, New ingredient and Treat as staple for a line that needs you', async () => {
      const flow = await reviewing();
      await expect.element(page.getByText('· not in your ingredients')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Pick an ingredient' })).toBeVisible();
      await page.getByRole('button', { name: 'Treat as staple' }).nth(1).click();
      expect(flow.choices[2]).toMatchObject({ kind: 'staple', name: 'Asafoetida' });
      await expect.element(page.getByText(/Made a staple when you save/)).toBeVisible();
      // The first guess can be changed right there.
      await page.getByLabelText('Name').nth(1).fill('Hing');
      expect(flow.choices[2]).toMatchObject({ name: 'Hing' });
    });

    it('asks “Pantry keeps it by” with its hint on a new ingredient (F119)', async () => {
      await reviewing();
      await page.getByRole('button', { name: 'New ingredient' }).first().click();
      await expect.element(page.getByLabelText(/^Pantry keeps it by/)).toBeVisible();
      await expect
        .element(page.getByText(/The way you buy it: a 500.g jar → by weight\. Recipes can still/))
        .toBeVisible();
      expect(document.body.textContent).not.toContain('How it’s counted');
    });

    it('names what it read on a line that is not in your ingredients (F5)', async () => {
      await reviewing();
      // Not "2 tbsp  Not in your ingredients": the name is there, so the amount isn't mistaken
      // for it (mockup Dark-ImportCheck07-Desktop: the name, the amount, then the words).
      await expect.element(page.getByText('asafoetida', { exact: true })).toBeVisible();
      await expect.element(page.getByRole('button', { name: /^Amount ¼ tsp/ })).toBeVisible();
      await expect.element(page.getByText('· not in your ingredients')).toBeVisible();
    });

    it('gives every line a status dot with its meaning in words', async () => {
      await reviewing();
      await expect.element(page.getByRole('img', { name: 'Ready' })).toBeVisible();
      await expect.element(page.getByRole('img', { name: 'To confirm' })).toBeVisible();
      await expect.element(page.getByRole('img', { name: 'Needs you' })).toBeVisible();
    });

    it('says “No amount” on a line with none, as a chip that opens the boxes', async () => {
      const flow = await reviewing();
      flow.editLine(2, { amount: null, amount_text: null, unit: null });
      flushSync();
      await expect.element(page.getByRole('button', { name: /^No amount/ })).toBeVisible();
    });

    it('fixes the amount, unit and note from the chips (F30.6)', async () => {
      const flow = await reviewing();
      await page.getByRole('button', { name: /^Amount ¼ tsp/ }).click();
      await page.getByLabelText('Amount', { exact: true }).fill('2');
      expect(flow.review!.lines[2]).toMatchObject({ amount: 2, amount_text: '2' });
      await page.getByLabelText(/^Unit/).selectOptions('tbsp');
      expect(flow.review!.lines[2]!.unit).toBe('tbsp');
      await page.getByLabelText('Note').fill('heaped');
      expect(flow.body()!.lines[2]).toMatchObject({ amount: 2, unit: 'tbsp', note: 'heaped' });
      await page.getByLabelText('Amount', { exact: true }).fill('lots');
      await expect.element(page.getByText('Type a number, like 2 or ½.')).toBeVisible();
      expect(flow.review!.lines[2]!.amount).toBe(2);
      // Done on a box that couldn't be read puts the stored amount back; Done again closes.
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByLabelText('Amount', { exact: true })).toHaveValue('2');
      await expect.element(page.getByText('Type a number, like 2 or ½.')).not.toBeInTheDocument();
      expect(flow.review!.lines[2]!.amount).toBe(2);
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByLabelText(/^Unit/)).not.toBeInTheDocument();
    });

    it('keeps the sheet open on a last card when the last line is skipped (L1)', async () => {
      const flow = await reviewing();
      await page.getByRole('button', { name: 'Save recipe' }).click();
      const sheet = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
      await sheet.getByRole('button', { name: 'Skip this line' }).click();
      await sheet.getByRole('button', { name: 'Skip this line' }).click();
      const last = page.getByRole('dialog', { name: '2 lines left unlinked' });
      await expect.element(last).toBeVisible();
      expect(flow.saved).toBeNull();
      await expect.element(last.getByRole('button', { name: 'Back to Check' })).toBeVisible();
      // The button that was pressed went with the line card: focus moves to Back to Check.
      await expect.element(last.getByRole('button', { name: 'Back to Check' })).toHaveFocus();
      await last.getByRole('button', { name: 'Back to Check' }).click();
      await expect.element(last).not.toBeInTheDocument();
    });

    it('Ctrl+Z does nothing while the Save sheet is open, so no choice lands on a moved line (fix 1)', async () => {
      undoHistory.clear();
      const flow = await reviewing();
      flow.removeLine(0); // the matched line: the two left are red onion and asafoetida
      await page.getByRole('button', { name: 'Save recipe' }).click();
      const sheet = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
      await expect.element(sheet).toBeVisible();
      const at = flow.walk!.queue.slice();
      const key = new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, cancelable: true });
      handleUndoKey(key);
      expect(key.defaultPrevented).toBe(false);
      await Promise.resolve();
      expect(flow.review!.lines).toHaveLength(2);
      expect(flow.walk!.queue).toEqual(at);
      // Closed again, the key works as before.
      await sheet.getByRole('button', { name: 'Back to Check' }).click();
      await expect.element(sheet).not.toBeInTheDocument();
      const again = new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, cancelable: true });
      handleUndoKey(again);
      expect(again.defaultPrevented).toBe(true);
      await vi.waitFor(() => expect(flow.review!.lines).toHaveLength(3));
    });

    it('the Save sheet offers Made in this recipe, first for a "from the …" line (F108)', async () => {
      const flow = await reviewing();
      flow.review!.lines[1] = { ...flow.review!.lines[1]!, note: 'from the spice blend' };
      await page.getByRole('button', { name: 'Save recipe' }).click();
      const sheet = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
      await expect.element(sheet).toBeVisible(); // the sheet loads when first needed
      const buttons = Array.from(sheet.element().querySelectorAll('.choices button'));
      expect(buttons[0]?.textContent?.trim()).toBe('Made in this recipe');
      await sheet.getByRole('button', { name: 'Made in this recipe' }).click();
      expect(flow.choices[1]).toEqual({ kind: 'here' });
      expect(flow.walk!.at).toBe(1); // on to the next line
      // The next line has it as one of its choices, not the first.
      const next = Array.from(sheet.element().querySelectorAll('.choices button'));
      expect(next.map((b) => b.textContent?.trim())).toContain('Made in this recipe');
      expect(next[0]?.textContent).not.toContain('Made in this recipe');
    });

    it('offers Treat as staple on a line to confirm too (F21)', async () => {
      const flow = await reviewing();
      const staples = page.getByRole('button', { name: 'Treat as staple' });
      await expect.element(staples.first()).toBeVisible();
      await staples.first().click();
      expect(flow.choices[1]).toMatchObject({ kind: 'staple', name: 'Red onion' });
    });

    it('closes the New ingredient form with Done and shows a settled line (F10)', async () => {
      const flow = await reviewing();
      await page.getByRole('button', { name: /^New ingredient “Asafoetida”/ }).click();
      await expect.element(page.getByLabelText('Name').nth(1)).toBeVisible();
      await page.getByRole('switch', { name: 'Treat as staple (never counted)' }).click();
      expect(flow.choices[2]).toMatchObject({ kind: 'staple' });
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByLabelText('Name').nth(1)).not.toBeInTheDocument();
      await expect.element(page.getByText('New staple:')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Edit' })).toBeVisible();
      await page.getByRole('button', { name: 'Edit' }).click();
      await expect.element(page.getByLabelText('Name').nth(1)).toBeVisible();
    });

    it('“+ Place” in Usually kept in makes the place and keeps the new ingredient there (L5)', async () => {
      const flow = await reviewing();
      fakeApi({
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS],
        'POST /places': [201, { id: 9, name: 'Garage freezer', kind: 'freezer' }]
      });
      await page.getByRole('button', { name: /^New ingredient “Asafoetida”/ }).click();
      await page.getByRole('combobox', { name: 'Usually kept in' }).selectOptions('+ Place');
      await page.getByRole('textbox', { name: 'Place’s name' }).fill('Garage freezer');
      await page.getByRole('radio', { name: 'Freezer' }).click();
      await page.getByRole('button', { name: 'Add place' }).click();
      await vi.waitFor(() => expect(flow.choices[2]).toMatchObject({ place_id: 9 }));
      await expect
        .element(page.getByRole('combobox', { name: 'Usually kept in' }))
        .toHaveDisplayValue('Garage freezer');
    });

    it('will not close the form on an empty name', async () => {
      await reviewing();
      await page.getByRole('button', { name: /^New ingredient “Asafoetida”/ }).click();
      await page.getByLabelText('Name').nth(1).fill('');
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByText('Type a name.')).toBeVisible();
    });

    it('says when a line took the choice made on another (F6)', async () => {
      const flow = await reviewing();
      flow.review!.lines[1] = { ...flow.review!.lines[1]!, words: 'asafoetida', learn_name: null };
      flow.newIngredient(2);
      flushSync();
      await expect.element(page.getByText(/^Also used for 1 more line/)).toBeVisible();
      await expect.element(page.getByText(/^Same choice as/)).toBeVisible();
    });

    it('a settled new ingredient says “Pantry keeps it by”, as the question does (F119)', async () => {
      await reviewing();
      await page.getByRole('button', { name: /^New ingredient “Asafoetida”/ }).click();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect
        .element(page.getByText(/Pantry keeps it by volume · kept in\s+nowhere/))
        .toBeVisible();
      await expect.element(page.getByText(/Counted by/)).not.toBeInTheDocument();
    });

    it('the Save sheet’s card says “Pantry keeps it by” for a new ingredient guess (F119)', async () => {
      await reviewing();
      await page.getByRole('button', { name: 'Save recipe' }).click();
      const sheet = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
      await sheet.getByRole('button', { name: 'Skip this line' }).click();
      await expect.element(sheet.getByText('Line 2 of 2')).toBeVisible();
      await expect.element(sheet.getByText('Pantry keeps it by volume')).toBeVisible();
      await expect.element(sheet.getByText(/Counted by/)).not.toBeInTheDocument();
    });

    it('goes through the lines with no ingredient when Save finds some (F4)', async () => {
      const flow = await reviewing();
      await page.getByRole('button', { name: 'Save recipe' }).click();
      const sheet = page.getByRole('dialog', { name: '2 lines aren’t linked yet' });
      await expect.element(sheet).toBeVisible();
      await expect.element(sheet.getByText('Line 1 of 2')).toBeVisible();
      await sheet.getByRole('button', { name: 'Skip this line' }).click();
      await expect.element(sheet.getByText('Line 2 of 2')).toBeVisible();
      await sheet.getByRole('button', { name: 'Treat as staple' }).click();
      expect(flow.choices[2]).toMatchObject({ kind: 'staple' });
      // The skipped line is still not linked: the sheet ends on its last card, with nothing saved.
      await expect
        .element(page.getByRole('dialog', { name: '1 line left unlinked' }))
        .toBeVisible();
      expect(flow.saved).toBeNull();
    });

    it('Back to Check closes the sheet; Save anyway saves (F4)', async () => {
      const flow = await reviewing();
      await page.getByRole('button', { name: 'Save recipe' }).click();
      await page.getByRole('button', { name: 'Back to Check' }).click();
      await expect
        .element(page.getByRole('dialog', { name: '2 lines aren’t linked yet' }))
        .not.toBeInTheDocument();
      fakeApi({
        'POST /recipes/import/save': [
          200,
          {
            recipe: { id: 5, name: 'Sambar' },
            change: { id: 1, summary: 'Imported Sambar' },
            new_ingredients: [],
            learned: 0
          }
        ]
      });
      await page.getByRole('button', { name: 'Save recipe' }).click();
      await page.getByRole('button', { name: 'Save anyway' }).click();
      await vi.waitFor(() => expect(flow.saved).not.toBeNull());
    });

    it('shows a long step’s split before keeping it, with a way back (F13)', async () => {
      const flow = await reviewing();
      flow.review!.steps = [
        {
          kind: 'step',
          text: 'Beat the butter. Add the eggs. Fold in the flour. Divide between the tins. Level the tops.'
        }
      ];
      flushSync();
      await expect.element(page.getByText('A long step (5 sentences)')).toBeVisible();
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await expect.element(page.getByText('Preview: this step as 3 steps')).toBeVisible();
      expect(flow.review!.steps).toHaveLength(1);
      await page.getByRole('button', { name: 'Keep as one' }).click();
      expect(flow.review!.steps).toHaveLength(1);
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await page.getByRole('button', { name: 'Keep the split' }).click();
      expect(flow.review!.steps).toHaveLength(3);
      await page.getByRole('button', { name: 'Put the steps back as they were' }).click();
      expect(flow.review!.steps).toHaveLength(1);
    });

    const METHOD: ImportReview['steps'] = [
      { kind: 'step', text: 'Soak the rice.' },
      { kind: 'heading', text: 'For the filling' },
      { kind: 'step', text: 'Fry the onion.' },
      { kind: 'step', text: 'Add the spices.' }
    ];

    it('changes a step’s words in a box: Enter is Done, Escape is Cancel, nothing is saved (F111)', async () => {
      const flow = await reviewing();
      flow.review!.steps = METHOD.map((s) => ({ ...s }));
      flushSync();
      await page.getByRole('button', { name: /^Change step 3/ }).click();
      const box = page.getByRole('textbox', { name: 'Words of step 3' });
      await expect.element(box).toHaveFocus();
      await box.fill('Add the cumin and the chilli.');
      // Escape: back as it was, focus back on the step.
      await box.click();
      await userEvent.keyboard('{Escape}');
      expect(flow.review!.steps[3]!.text).toBe('Add the spices.');
      await expect.element(page.getByRole('button', { name: /^Change step 3/ })).toHaveFocus();
      // Enter: the new words.
      await page.getByRole('button', { name: /^Change step 3/ }).click();
      await page
        .getByRole('textbox', { name: 'Words of step 3' })
        .fill('Add the cumin and the chilli.');
      await userEvent.keyboard('{Enter}');
      expect(flow.review!.steps[3]!.text).toBe('Add the cumin and the chilli.');
      await expect.element(page.getByRole('button', { name: /^Change step 3/ })).toHaveFocus();
      // What Save sends has the new words, and nothing was sent to the server.
      expect(flow.body()!.steps.map((s) => s.text)).toContain('Add the cumin and the chilli.');
      expect(flow.saved).toBeNull();
    });

    it('can’t keep an empty step: says so and offers Remove (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = METHOD.map((s) => ({ ...s }));
      flushSync();
      await page.getByRole('button', { name: /^Change step 1/ }).click();
      await page.getByRole('textbox', { name: 'Words of step 1' }).fill('   ');
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByRole('alert').getByText(/can’t be empty/)).toBeVisible();
      expect(flow.review!.steps[0]!.text).toBe('Soak the rice.');
      await page.getByRole('button', { name: 'Remove step' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(3));
      expect(toasts.current?.message).toBe('Removed step 1');
    });

    it('changes a heading, and the numbers do not move (F111, F112)', async () => {
      const flow = await reviewing();
      flow.review!.steps = METHOD.map((s) => ({ ...s }));
      flushSync();
      await page.getByRole('button', { name: 'For the filling' }).click();
      await page.getByRole('textbox', { name: 'Words of heading' }).fill('For the masala');
      await userEvent.keyboard('{Enter}');
      expect(flow.review!.steps[1]).toEqual({ kind: 'heading', text: 'For the masala' });
      await expect.element(page.getByRole('button', { name: /^Change step 3/ })).toBeVisible();
    });

    it('removes a step or a heading with Undo, back in its place, numbers following (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = METHOD.map((s) => ({ ...s }));
      flushSync();
      await page.getByRole('button', { name: 'Remove step 2' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(3));
      expect(toasts.current?.message).toBe('Removed step 2');
      // The step after it is step 2 now.
      await expect
        .element(page.getByRole('button', { name: /^Change step 2: Add the spices/ }))
        .toBeVisible();
      await page.getByRole('button', { name: 'Remove heading: For the filling' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      expect(toasts.current?.message).toBe('Removed “For the filling”');
      // Undo goes newest first, each back where it was.
      expect(await undoHistory.undoLast()).toBe(true);
      expect(flow.review!.steps.map((s) => s.text)).toEqual([
        'Soak the rice.',
        'For the filling',
        'Add the spices.'
      ]);
      expect(await undoHistory.undoLast()).toBe(true);
      expect(flow.review!.steps.map((s) => s.text)).toEqual(METHOD.map((s) => s.text));
    });

    it('Undo of a removed step works out of order and after a split (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = [
        { kind: 'step', text: 'One.' },
        {
          kind: 'step',
          text: 'Beat the butter. Add the eggs. Fold in the flour. Divide between the tins. Level the tops.'
        },
        { kind: 'step', text: 'Three.' }
      ];
      flushSync();
      // Take step 1 out, then split the long one into three, then Undo the first removal.
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await page.getByRole('button', { name: 'Keep the split' }).click();
      expect(flow.review!.steps).toHaveLength(4);
      // Remove the second part of the split, then Undo it: it goes back between its neighbours.
      const parts = flow.review!.steps.map((s) => s.text);
      await page.getByRole('button', { name: 'Remove step 2' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(3));
      expect(await undoHistory.undoLast()).toBe(true);
      expect(flow.review!.steps.map((s) => s.text)).toEqual(parts);
      // The first removal's Undo: the step it followed was split away, so it goes to its old place.
      expect(await undoHistory.undoLast()).toBe(true);
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['One.', ...parts]);
    });

    const ABC = (): ImportReview['steps'] => [
      { kind: 'step', text: 'A.' },
      { kind: 'step', text: 'B.' },
      { kind: 'step', text: 'C.' }
    ];

    it('an open box stays on its own step when Undo moves the list (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = ABC();
      flushSync();
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      await page.getByRole('button', { name: /^Change step 2: C\./ }).click(); // C
      expect(await undoHistory.undoLast()).toBe(true); // A comes back before B: C is step 3 now
      flushSync();
      await page.getByRole('textbox', { name: /^Words of/ }).fill('C changed.');
      await page.getByRole('button', { name: 'Done' }).click();
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['A.', 'B.', 'C changed.']);
    });

    it('Put the steps back closes a box open on a split piece; Done changes nothing (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      const long =
        'Beat the butter. Add the eggs. Fold in the flour. Divide between the tins. Level the tops.';
      flow.review!.steps = [
        { kind: 'step', text: long },
        { kind: 'step', text: 'C.' }
      ];
      flushSync();
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await page.getByRole('button', { name: 'Keep the split' }).click();
      await page.getByRole('button', { name: /^Change step 2/ }).click();
      await expect.element(page.getByRole('textbox', { name: /^Words of/ })).toBeVisible();
      await page.getByRole('button', { name: 'Put the steps back as they were' }).click();
      await expect
        .element(page.getByRole('textbox', { name: /^Words of/ }))
        .not.toBeInTheDocument();
      expect(flow.review!.steps.map((s) => s.text)).toEqual([long, 'C.']);
    });

    it('Ctrl+Z with the cursor on Done does not put the words on another step (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = ABC();
      flushSync();
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      await page.getByRole('button', { name: /^Change step 2: C\./ }).click();
      await page.getByRole('textbox', { name: /^Words of/ }).fill('C changed.');
      const done = page.getByRole('button', { name: 'Done' }).element() as HTMLElement;
      done.focus();
      const key = new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, cancelable: true });
      done.dispatchEvent(key);
      handleUndoKey(key); // its target is the Done button, not a text box
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(3));
      await page.getByRole('button', { name: 'Done' }).click();
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['A.', 'B.', 'C changed.']);
    });

    it('Undo after Put the steps back puts nothing back twice (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      const long =
        'Beat the butter. Add the eggs. Fold in the flour. Divide between the tins. Level the tops.';
      flow.review!.steps = [
        { kind: 'step', text: 'A.' },
        { kind: 'step', text: long },
        { kind: 'step', text: 'C.' }
      ];
      flushSync();
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await page.getByRole('button', { name: 'Keep the split' }).click();
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(4));
      await page.getByRole('button', { name: 'Put the steps back as they were' }).click();
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['A.', long, 'C.']);
      expect(undoHistory.size).toBe(0);
      expect(toasts.current?.message).not.toBe('Removed step 1');
      expect(await undoHistory.undoLast()).toBe(false);
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['A.', long, 'C.']);
    });

    it('an Undo that finds neither neighbour says so and puts nothing back (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = ABC();
      flushSync();
      await page.getByRole('button', { name: 'Remove step 2' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      flow.review!.steps = [
        { kind: 'step', text: 'X.' },
        { kind: 'step', text: 'Y.' }
      ];
      expect(await undoHistory.undoLast()).toBe(true);
      expect(toasts.current?.message).toBe('Couldn’t put it back: the steps have changed.');
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['X.', 'Y.']);
    });

    it('Remove on another step keeps the box open with what was typed (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = ABC();
      flushSync();
      await page.getByRole('button', { name: /^Change step 3/ }).click();
      await page.getByRole('textbox', { name: /^Words of/ }).fill('C half typed');
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(flow.review!.steps).toHaveLength(2));
      await expect
        .element(page.getByRole('textbox', { name: /^Words of/ }))
        .toHaveValue('C half typed');
      await page.getByRole('button', { name: 'Done' }).click();
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['B.', 'C half typed']);
    });

    it('Undo for a removed step is forgotten when the screen goes (F111)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.steps = METHOD.map((s) => ({ ...s }));
      flushSync();
      await page.getByRole('button', { name: 'Remove step 1' }).click();
      await vi.waitFor(() => expect(undoHistory.size).toBe(1));
      flow.forgetTakenOut();
      expect(undoHistory.size).toBe(0);
    });

    it('says "also called" for another name, never for the line’s own (F103)', async () => {
      const flow = await reviewing();
      // A ready line says which name it matched by, as before.
      await expect.element(page.getByText('· also called thuvaram paruppu')).toBeVisible();
      // A line that matched by its own words: the bold name is those words, so no repeat.
      flow.review!.lines[1] = {
        ...flow.review!.lines[1]!,
        words: 'Basmati rice',
        matched_by: 'basmati rice',
        food: { id: 9, name: 'Rice' }
      };
      flushSync();
      await expect.element(page.getByText('Basmati rice', { exact: true })).toBeVisible();
      expect(page.getByText(/also called basmati rice/i).elements()).toHaveLength(0);
      expect(page.getByText(/also called/).elements()).toHaveLength(1);
    });

    it('has Remove line on each ingredient line: out of the recipe, the counts and the warning, with Undo (F105)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      expect(page.getByText(/without an ingredient/).elements()).toHaveLength(0); // F152
      expect(page.getByRole('button', { name: /^Remove line/ }).elements()).toHaveLength(3);
      await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
      expect(flow.review!.lines).toHaveLength(2);
      expect(toasts.current?.message).toBe('Removed “1 red onion, sliced”');
      expect(page.getByText(/without an ingredient/).elements()).toHaveLength(0); // F152
      await expect.element(page.getByText('0 to confirm')).toBeVisible();
      expect(document.querySelector('.lines h2')?.textContent).toContain('2');
      expect(page.getByText('1 red onion, sliced').elements()).toHaveLength(0);
      // The cursor stays in the list, on the Remove of the line that took its place.
      expect(document.activeElement?.getAttribute('aria-label')).toBe(
        'Remove line: ¼ tsp asafoetida'
      );
      expect(flow.body()!.lines.map((l) => l.words)).toEqual(['thuvaram paruppu', 'asafoetida']);
      // Undo brings it back in the same place.
      expect(await undoHistory.undoLast()).toBe(true);
      flushSync();
      expect(page.getByText(/without an ingredient/).elements()).toHaveLength(0); // F152
      expect(flow.review!.lines.map((l) => l.written)).toEqual([
        '1 cup (200 g) thuvaram paruppu',
        '1 red onion, sliced',
        '¼ tsp asafoetida'
      ]);
    });

    it('Split into two on any line: two names, then two lines (F109)', async () => {
      undoHistory.clear();
      toasts.dismiss();
      const flow = await reviewing();
      flow.review!.lines[1] = {
        ...flow.review!.lines[1]!,
        written: '4 1/2 cups water and broth',
        words: 'water and broth',
        amount: 4.5,
        amount_text: '4½',
        unit: 'cup',
        note: null,
        learn_name: null
      };
      fakeApi({
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS],
        'GET /foods?q=water&limit=8': [200, { foods: [] }],
        'GET /foods?q=broth&limit=8': [200, { foods: [] }]
      });
      flushSync();
      await page
        .getByRole('button', { name: /^Split into two: 4 1\/2 cups water and broth/ })
        .click();
      // The name is cut at its "and" for the boxes.
      await expect.element(page.getByLabelText('First ingredient')).toHaveValue('water');
      await expect.element(page.getByLabelText('Second ingredient')).toHaveValue('broth');
      await expect.element(page.getByText(/“4½ cups together” goes in its note/)).toBeVisible();
      await page.getByRole('button', { name: 'Split', exact: true }).click();
      await vi.waitFor(() => expect(flow.review!.lines).toHaveLength(4));
      expect(flow.review!.lines.map((l) => l.words)).toEqual([
        'thuvaram paruppu',
        'water',
        'broth',
        'asafoetida'
      ]);
      expect(toasts.current?.message).toBe('Split “4 1/2 cups water and broth” into two');
    });

    it('a name that is not two things is left alone: Cancel closes the boxes (F109)', async () => {
      await reviewing();
      await page.getByRole('button', { name: /^Split into two: ¼ tsp asafoetida/ }).click();
      await expect.element(page.getByLabelText('First ingredient')).toHaveValue('asafoetida');
      await expect.element(page.getByLabelText('Second ingredient')).toHaveValue('');
      await page.getByRole('button', { name: 'Split', exact: true }).click();
      await expect.element(page.getByText('Type two different names.')).toBeVisible();
      await page.getByRole('button', { name: 'Cancel', exact: true }).first().click();
      expect(page.getByLabelText('First ingredient').elements()).toHaveLength(0);
    });

    it('offers Made in this recipe first for a "from the …" line, and as a plain choice for the others (F108)', async () => {
      const flow = await reviewing();
      flow.review!.lines[1] = {
        ...flow.review!.lines[1]!,
        note: 'from the spice blend'
      };
      flushSync();
      const first = page.getByRole('button', { name: 'Made in this recipe' }).first();
      await expect.element(first).toBeVisible();
      // It leads the red onion line's buttons, and the asafoetida line has it as a later choice.
      const buttons = Array.from(document.querySelectorAll('.line:nth-of-type(2) .buttons button'));
      expect(buttons[0]?.textContent).toBe('Made in this recipe');
      const later = Array.from(document.querySelectorAll('.line:nth-of-type(3) .buttons button'));
      expect(later.map((b) => b.textContent?.trim())).toEqual([
        'New ingredient “Asafoetida”',
        'Pick an ingredient',
        'Made in this recipe',
        'Treat as staple'
      ]);
      await first.click();
      expect(flow.choices[1]).toEqual({ kind: 'here' });
      await expect
        .element(page.getByText('Made in this recipe: saved as words only', { exact: false }))
        .toBeVisible();
      expect(flow.unlinked).toBe(1);
    });

    it('numbers the steps through the method, never counting a heading (F112)', async () => {
      const flow = await reviewing();
      flow.review!.steps = [
        { kind: 'step', text: 'Soak the rice.' },
        { kind: 'heading', text: 'For the batter' },
        { kind: 'step', text: 'Grind it.' },
        { kind: 'step', text: 'Ferment it.' },
        { kind: 'heading', text: 'To serve' },
        { kind: 'step', text: 'Fry it.' }
      ];
      flushSync();
      await expect.element(page.getByRole('heading', { name: 'For the batter' })).toBeVisible();
      const lists = Array.from(document.querySelectorAll('.method ol'));
      expect(lists.map((ol) => ol.getAttribute('start'))).toEqual(['1', '2', '4']);
      expect(document.querySelectorAll('.method ol li')).toHaveLength(4);
      expect(document.querySelectorAll('.method li.heading')).toHaveLength(0);
    });

    it('has no note about lines saved without an ingredient, and Save recipe is on (F152)', async () => {
      await reviewing();
      expect(page.getByText(/without an ingredient/).elements()).toHaveLength(0); // F152
    });

    it('keeps Save off while offline, and says so', async () => {
      await reviewing();
      // The places the rows ask for have come: no answer is left to say we're connected.
      await vi.waitFor(() => expect(placesAndShops.places.length).toBeGreaterThan(0));
      network.offline = true;
      network.deviceOffline = true;
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

  describe('a US recipe (pints)', () => {
    beforeEach(() => fakeApi({ 'GET /places': [200, PLACES], 'GET /shops': [200, SHOPS] }));

    it('says it looks like a US recipe, with the pints switch on, and reads US pints', async () => {
      show(reviewFlow(PINTS_REVIEW), ReviewScreen);
      await expect.element(page.getByText('This looks like a US recipe')).toBeVisible();
      await expect
        .element(page.getByRole('switch', { name: 'Read its pints as US pints (473 ml)' }))
        .toBeChecked();
      await expect
        .element(page.getByText('For this recipe only. Your setting stays UK pints.'))
        .toBeVisible();
      await expect.element(page.getByText('946 ml')).toBeVisible();
      await expect.element(page.getByText(/2 pints whole milk · US pints/)).toBeVisible();
      await expect
        .element(page.getByText('Switch it off and the whole milk reads 1.14 L (UK pints).'))
        .toBeVisible();
    });

    it('re-reads the pint lines when the switch is turned off, and back on', async () => {
      const flow = reviewFlow(PINTS_REVIEW);
      show(flow, ReviewScreen);
      await page.getByRole('switch', { name: 'Read its pints as US pints (473 ml)' }).click();
      expect(flow.pints).toBe('uk');
      await expect.element(page.getByText('1136 ml')).toBeVisible();
      await expect.element(page.getByText(/2 pints whole milk · UK pints/)).toBeVisible();
      await expect
        .element(page.getByText('Switch it on and the whole milk reads 946 ml (US pints).'))
        .toBeVisible();
      await page.getByRole('switch', { name: 'Read its pints as US pints (473 ml)' }).click();
      expect(flow.pints).toBe('us');
      await expect.element(page.getByText('946 ml')).toBeVisible();
    });

    it('shows no card on a page that does not look American, or for a US household', async () => {
      show(
        reviewFlow({ ...PINTS_REVIEW, pints: { household: 'uk', us_site: false, reading: 'uk' } }),
        ReviewScreen
      );
      expect(document.body.textContent).not.toContain('This looks like a US recipe');
      unmount(component!);
      component = null;
      show(
        reviewFlow({ ...PINTS_REVIEW, pints: { household: 'us', us_site: true, reading: 'us' } }),
        ReviewScreen
      );
      expect(document.body.textContent).not.toContain('This looks like a US recipe');
    });
  });

  describe('leaving without saving: “Save as draft?”', () => {
    const KEPT: DraftOut = {
      id: 7,
      name: 'Sambar',
      source: { kind: 'link', site: 'kitchen.example' },
      started_by: 'Tess',
      started_at: '2026-10-24T10:00:00Z',
      updated_at: '2026-10-24T10:00:00Z',
      expires_at: '2026-11-08T10:00:00Z',
      days_left: 15,
      lines_total: 3,
      lines_checked: 1,
      text: 'https://kitchen.example/dal',
      review: REVIEW,
      choices: { name: 'Sambar', serves: '4', minutes: '50', lines: {} }
    };

    beforeEach(() => {
      nav.goto.mockReset();
      nav.guard = null;
      drafts.forget();
    });

    /** Someone clicks away: the page's guard is asked, and says whether it stopped them. */
    function leaveFor(path: string, extra: Record<string, unknown> = {}) {
      const cancel = vi.fn();
      nav.guard?.({
        to: { url: new URL(path, location.href) },
        cancel,
        willUnload: false,
        ...extra
      });
      flushSync();
      return cancel;
    }

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

    it('stops the leaving and asks, in the mockup’s words, with the three choices', async () => {
      await reviewing();
      const cancel = leaveFor('/recipes');
      expect(cancel).toHaveBeenCalled();
      const dialog = page.getByRole('dialog', { name: 'Save as draft?' });
      await expect.element(dialog).toBeVisible();
      await expect
        .element(
          page.getByText(
            'You haven’t finished checking Sambar. A draft keeps your choices so far for 15 days, in Recipes → Drafts. Anyone in your household can carry on.'
          )
        )
        .toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Save draft' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Keep checking' })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Discard', exact: true }))
        .toBeVisible();
    });

    it('Cancel leaves for Recipes, which asks', async () => {
      await reviewing();
      await page.getByRole('button', { name: 'Cancel' }).click();
      expect(nav.goto).toHaveBeenCalledWith('/recipes');
    });

    it('Save draft keeps it on the server and goes to Drafts', async () => {
      await reviewing();
      const requests = fakeApi({
        'POST /recipes/drafts': [201, KEPT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      leaveFor('/recipes');
      await page.getByRole('button', { name: 'Save draft' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests[0]!.method + ' ' + requests[0]!.path).toBe('POST /recipes/drafts');
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
    });

    it('Save draft from another tab goes where the person was going', async () => {
      await reviewing();
      fakeApi({
        'POST /recipes/drafts': [201, KEPT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      leaveFor('/pantry');
      await page.getByRole('button', { name: 'Save draft' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/pantry$/);
    });

    it('says why it can’t keep another draft, and stays', async () => {
      await reviewing();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      leaveFor('/recipes');
      await page.getByRole('button', { name: 'Save draft' }).click();
      await expect
        .element(page.getByText('You have 50 drafts. Finish or delete one first.'))
        .toBeVisible();
      expect(nav.goto).not.toHaveBeenCalled();
      // Discard is still there, and keeping checking too.
      await page.getByRole('button', { name: 'Keep checking' }).click();
      expect(page.getByRole('dialog').elements()).toHaveLength(0);
    });

    it('Keep checking stays; Discard leaves without keeping anything', async () => {
      const flow = await reviewing();
      const requests = fakeApi({});
      leaveFor('/recipes');
      await page.getByRole('button', { name: 'Keep checking' }).click();
      expect(nav.goto).not.toHaveBeenCalled();
      expect(page.getByRole('dialog').elements()).toHaveLength(0);
      leaveFor('/recipes');
      await page.getByRole('button', { name: 'Discard', exact: true }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
      expect(requests).toHaveLength(0);
      expect(flow.draftId).toBeNull();
    });

    it('F93: the header counts follow every choice on the lines, and Change puts them back', async () => {
      const flow = await reviewing();
      const read = () =>
        page.getByLabelText('What was found').element().textContent.replace(/\s+/g, ' ');
      const shows = (words: string) => vi.waitFor(() => expect(read()).toContain(words));
      await shows('1 matched');
      await shows('1 needs you');
      expect(flow.unlinked).toBe(2);
      // Line 2 (needs you) and line 1 (to confirm): a new ingredient, then a staple.
      flow.newIngredient(2);
      await shows('0 need you');
      await shows('1 to confirm');
      await shows('2 matched');
      flow.newIngredient(1, true);
      await shows('0 to confirm');
      await shows('1 staple');
      await shows('2 matched');
      expect(flow.unlinked).toBe(0);
      // Pick an existing one on a line, then take each choice back.
      flow.unchoose(1);
      flow.sameAs(1, { id: 2, name: 'Onions' });
      await shows('3 matched');
      flow.unchoose(1);
      flow.unchoose(2);
      await shows('1 matched');
      await shows('1 to confirm');
      await shows('1 needs you');
      await shows('0 staples');
      // The tick in the New ingredient form makes the same line a staple, and back.
      flow.newIngredient(2);
      flow.setStaple(2, true);
      await shows('1 staple');
      flow.setStaple(2, false);
      await shows('0 staples');
      flow.unchoose(2);
      // An amount edit changes no status.
      flow.editLine(2, { amount: 2, amount_text: '2' });
      await shows('1 needs you');
    });

    it('F92: Discard deletes the review’s waiting photo at once; a draft’s photo stays', async () => {
      const PHOTO = {
        id: 41,
        width: 800,
        height: 600,
        url: '/api/v1/recipes/photos/41/large',
        list_width: 156,
        list_height: 117,
        list_url: '/api/v1/recipes/photos/41/list'
      };
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({
        'POST /recipes/import': [
          200,
          { ...REVIEW, photo: { state: 'downloaded', photo: PHOTO, message: null } }
        ],
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS]
      });
      await flow.read();
      show(flow, ReviewScreen);
      const requests = fakeApi({ 'DELETE /recipes/photos/41': [204, null] });
      leaveFor('/recipes');
      await page.getByRole('button', { name: 'Discard', exact: true }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests.map((r) => r.method + ' ' + r.path)).toEqual(['DELETE /recipes/photos/41']);
      // Asked again, it does nothing more.
      await flow.dropPhoto();
      expect(requests).toHaveLength(1);

      // A kept draft owns its photo: nothing is deleted.
      const kept = new ImportFlow();
      kept.load({
        ...KEPT,
        review: { ...REVIEW, photo: { state: 'downloaded', photo: PHOTO, message: null } }
      });
      const none = fakeApi({});
      await kept.dropPhoto();
      expect(none).toHaveLength(0);
    });

    it('a photo error fails the address the picture tried, not the photo shown by then', async () => {
      const PHOTO = {
        id: 41,
        width: 800,
        height: 600,
        url: '/api/v1/recipes/photos/41/large',
        list_width: 156,
        list_height: 117,
        list_url: '/api/v1/recipes/photos/41/list'
      };
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({
        'POST /recipes/import': [
          200,
          { ...REVIEW, photo: { state: 'downloaded', photo: PHOTO, message: null } }
        ],
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS]
      });
      await flow.read();
      show(flow, ReviewScreen);
      const img = () =>
        document.querySelector<HTMLImageElement>('img[alt="Downloaded from the page"]');
      await vi.waitFor(() => expect(img()?.getAttribute('src')).toBe(PHOTO.url));
      // A late error from an address no longer shown leaves the large copy alone.
      img()!.setAttribute('src', '/api/v1/recipes/photos/40/large');
      img()!.dispatchEvent(new Event('error'));
      flushSync();
      expect(img()?.getAttribute('width')).toBe('800');
      // A real error on the shown large copy still falls back to the list copy.
      img()!.setAttribute('src', PHOTO.url);
      img()!.dispatchEvent(new Event('error'));
      flushSync();
      await vi.waitFor(() => expect(img()?.getAttribute('src')).toBe(PHOTO.list_url));
    });

    it('does not ask after Save, or when the tab is closed or reloaded', async () => {
      const flow = await reviewing();
      expect(leaveFor('/recipes', { willUnload: true })).not.toHaveBeenCalled();
      expect(page.getByRole('dialog').elements()).toHaveLength(0);
      flow.saved = {
        recipe: { id: 1, name: 'Sambar' },
        change: { id: 1 } as never,
        new_ingredients: [],
        learned: 0
      };
      expect(leaveFor('/recipes/1')).not.toHaveBeenCalled();
    });

    it('a draft opened and left alone just leaves; one that was changed asks in its own words', async () => {
      const flow = new ImportFlow();
      flow.load(KEPT);
      fakeApi({ 'GET /places': [200, PLACES], 'GET /shops': [200, SHOPS] });
      show(flow, ReviewScreen);
      expect(leaveFor('/recipes/drafts')).not.toHaveBeenCalled();
      flow.minutes = '40';
      const cancel = leaveFor('/recipes/drafts');
      expect(cancel).toHaveBeenCalled();
      await expect.element(page.getByRole('dialog', { name: 'Save your changes?' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Discard changes' })).toBeVisible();
      // Saving it saves over the same draft.
      const requests = fakeApi({
        'PUT /recipes/drafts/7': [200, KEPT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      await page.getByRole('button', { name: 'Save draft' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests[0]!.method + ' ' + requests[0]!.path).toBe('PUT /recipes/drafts/7');
    });
  });
});
