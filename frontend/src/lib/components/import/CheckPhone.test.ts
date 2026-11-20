// Check on the phone (F141, cabledrawer 3 Nov): Focus and One at a time, and a computer that keeps
// the whole screen whatever the choice. The layouts come from ReviewPage, which reads the choice
// in Settings › Appearance.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { CHECK_MODE_STORAGE_KEY, checkMode } from '#lib/checkMode.svelte.js';
import type { DraftOut } from '#lib/client/drafts.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { fakeApi, PLACES, SHOPS } from '#lib/testing/fakeApi.js';
import { SAMPLE_LINES, reviewFlow } from '#lib/testing/importSamples.js';
import { walkItems } from '#lib/importWalk.js';
import type { ImportReview } from '#lib/client/imports.js';
import { handleUndoKey } from '#lib/undo.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import ReviewPage from './ReviewPage.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

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
  text: 'https://kitchen.example/sambar',
  review: reviewFlow().review!,
  choices: { name: 'Sambar', serves: '4', minutes: '50', lines: {} }
};

let component: ReturnType<typeof mount> | null = null;

function show(flow: ReturnType<typeof reviewFlow>, phone: boolean) {
  component = mount(ReviewPage, { target: document.body, props: { flow, phone } });
  flushSync();
}

beforeEach(async () => {
  await page.viewport(390, 844);
  network.reset();
  placesAndShops.forget();
  drafts.forget();
  nav.goto.mockReset();
  nav.guard = null;
  localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
  checkMode.reload();
  fakeApi({ 'GET /places': [200, { places: PLACES }], 'GET /shops': [200, { shops: SHOPS }] });
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  toasts.dismiss();
  undoHistory.clear();
  vi.unstubAllGlobals();
  localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
  checkMode.reload();
});

/** Someone clicks away (a link, the browser's Back): the page's guard is asked. */
function leaveFor(path = '/recipes') {
  const cancel = vi.fn();
  nav.guard?.({ to: { url: new URL(path, location.href) }, cancel, willUnload: false });
  flushSync();
  return cancel;
}

/** Discard draft asks once (F211); this answers yes. */
async function discardDraft() {
  await page.getByRole('button', { name: 'Discard draft', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Discard draft' }).click();
}

/** How see-through a button is: a blocked one is greyed the same way Save recipe is (F154). */
const faded = (button: ReturnType<typeof page.getByRole>) =>
  Number(getComputedStyle(button.element()).opacity);

describe('Focus (the phone’s default)', () => {
  it('hides the app’s menu and shows the header, the counts, Close and Save as drawn', async () => {
    show(reviewFlow(), true);
    expect(document.documentElement.hasAttribute('data-full-page')).toBe(true);
    await expect
      .element(page.getByRole('heading', { level: 1, name: 'Check before saving' }))
      .toBeVisible();
    await expect.element(page.getByText('Step 2 of 3 · nothing saved yet')).toBeVisible();
    await expect.element(page.getByText('2 ok')).toBeVisible();
    await expect.element(page.getByText('1 to confirm')).toBeVisible();
    await expect.element(page.getByText('3 need you')).toBeVisible();
    await expect.element(page.getByText('1 staple', { exact: true })).toBeVisible();
    const close = page.getByRole('button', { name: /^Back to drafts/ });
    await expect.element(close).toHaveTextContent('Back to drafts Kept in Drafts');
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Cancel' }).elements()).toEqual([]);
    // No page header with its back link and settings cog: the page is its own.
    expect(page.getByRole('link', { name: /· Settings$/ }).elements()).toEqual([]);
  });

  it('puts the header and the bar on the screen and lets only the list scroll', async () => {
    show(reviewFlow(), true);
    // The bar's last button (Discard draft, under Save recipe and Back to drafts) rests at the foot.
    const last = page.getByRole('button', { name: 'Discard draft' }).element();
    const bottom = last.getBoundingClientRect().bottom;
    const heading = page.getByRole('heading', { level: 1 }).element();
    expect(heading.getBoundingClientRect().top).toBeGreaterThanOrEqual(0);
    expect(bottom).toBeLessThanOrEqual(844);
    expect(bottom).toBeGreaterThan(844 - 90);
    // The list is the one thing that scrolls.
    expect(document.documentElement.scrollHeight).toBeLessThanOrEqual(844);
  });

  it('shows the ingredients before the recipe’s name box', async () => {
    show(reviewFlow(), true);
    const ingredients = page.getByRole('heading', { name: /^Ingredients/ }).element();
    const name = page.getByLabelText('Name').element();
    expect(
      ingredients.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('Close keeps the draft with the choices made so far, and opens Drafts', async () => {
    const flow = reviewFlow();
    show(flow, true);
    const requests = fakeApi({
      'POST /recipes/drafts': [201, KEPT],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    flow.sameAs(3, { id: 2, name: 'Onions' }); // "1 red onion": a choice made on the screen
    flushSync();
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    leaveFor('/recipes/drafts'); // the leave guard asks, as for any leave (F211)
    await page.getByRole('button', { name: 'Save draft' }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    const keep = requests.find((r) => r.method === 'POST' && r.path === '/recipes/drafts')!;
    const body = keep.body as { choices: { lines: Record<string, { kind: string }> } };
    expect(body.choices.lines['3']?.kind).toBe('ingredient');
    expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
    expect(flow.draftId).toBe(7);
  });

  it('Close on a draft that was opened and not changed just leaves', async () => {
    const flow = reviewFlow();
    flow.load(KEPT);
    show(flow, true);
    const requests = fakeApi({});
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(requests.filter((r) => r.method !== 'GET')).toEqual([]);
    expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
  });

  it('Back to drafts on a changed draft asks “Save your changes?”; Keep checking stays, Discard changes leaves, nothing is sent (F211)', async () => {
    const flow = reviewFlow();
    flow.load(KEPT);
    show(flow, true);
    const requests = fakeApi({});
    flow.name = 'Sambar with okra';
    flushSync();
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    const cancel = leaveFor('/recipes/drafts');
    expect(cancel).toHaveBeenCalledTimes(1);
    await expect.element(page.getByRole('dialog', { name: 'Save your changes?' })).toBeVisible();
    await page.getByRole('button', { name: 'Keep checking' }).click();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    leaveFor('/recipes/drafts');
    await page.getByRole('button', { name: 'Discard changes' }).click();
    await vi.waitFor(() => expect(nav.goto.mock.calls.length).toBeGreaterThan(1));
    expect(requests.filter((r) => r.method !== 'GET')).toEqual([]);
  });

  it('Close on a draft that was changed saves it over, and says nothing was lost', async () => {
    const flow = reviewFlow();
    flow.load(KEPT);
    show(flow, true);
    const requests = fakeApi({
      'PUT /recipes/drafts/7': [200, KEPT],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    flow.name = 'Sambar with okra';
    flushSync();
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    leaveFor('/recipes/drafts'); // the leave guard asks, as for any leave (F211)
    await page.getByRole('button', { name: 'Save draft' }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(requests.some((r) => r.method === 'PUT' && r.path === '/recipes/drafts/7')).toBe(true);
  });

  it('Close says why when the draft can’t be kept, and stays on Check', async () => {
    show(reviewFlow(), true);
    fakeApi({
      'POST /recipes/drafts': [
        409,
        { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
      ]
    });
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    leaveFor('/recipes/drafts'); // the leave guard asks, as for any leave (F211)
    await page.getByRole('button', { name: 'Save draft' }).click();
    await expect
      .element(page.getByText('You have 50 drafts. Finish or delete one first.').first())
      .toBeVisible();
    // Only Back to drafts' own attempt (the guard stopped it): nothing else left.
    expect(nav.goto).toHaveBeenCalledTimes(1);
  });

  it('Close and Save recipe both look greyed while a step box is open (F154)', async () => {
    show(reviewFlow(), true);
    const close = page.getByRole('button', { name: /^Back to drafts/ });
    const save = page.getByRole('button', { name: 'Save recipe' });
    expect(faded(close)).toBe(1);
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    await expect.element(close).toBeDisabled();
    expect(faded(close)).toBeLessThan(1);
    expect(faded(close)).toBe(faded(save));
  });

  it('Close waits while a step box is open, and works after Done with the edit kept', async () => {
    const flow = reviewFlow();
    show(flow, true);
    fakeApi({
      'POST /recipes/drafts': [201, KEPT],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    const box = page.getByLabelText('Words of step 1');
    await box.fill('Boil the dal for 20 minutes.');
    await expect.element(page.getByRole('button', { name: /^Back to drafts/ })).toBeDisabled();
    await page.getByRole('button', { name: 'Done' }).click();
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(flow.review!.steps.find((x) => x.kind === 'step')!.text).toBe(
      'Boil the dal for 20 minutes.'
    );
  });

  it('Discard draft on a review never kept lets go of it and lands on Recipes', async () => {
    show(reviewFlow(), true);
    fakeApi({
      'POST /recipes/drafts': [
        409,
        { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
      ]
    });
    await discardDraft();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
  });

  it('Discard waits while Save recipe runs', async () => {
    const flow = reviewFlow();
    show(flow, true);
    fakeApi({
      'POST /recipes/drafts': [
        409,
        { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
      ]
    });
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    flow.saving = true;
    flushSync();
    await expect
      .element(page.getByRole('button', { name: 'Discard draft', exact: true }))
      .toBeDisabled();
    flow.saving = false;
  });

  it('Save recipe and Discard wait while a step box is open, and work after Done with the words kept (F143)', async () => {
    const flow = reviewFlow();
    show(flow, true);
    fakeApi({
      'POST /recipes/drafts': [
        409,
        { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
      ]
    });
    await page.getByRole('button', { name: /^Back to drafts/ }).click();
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    await page.getByLabelText('Words of step 1').fill('Boil the dal for 20 minutes.');
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
    await expect
      .element(page.getByRole('button', { name: 'Discard draft', exact: true }))
      .toBeDisabled();
    await page.getByRole('button', { name: 'Done' }).click();
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeEnabled();
    await expect
      .element(page.getByRole('button', { name: 'Discard draft', exact: true }))
      .toBeEnabled();
    expect(flow.review!.steps.find((x) => x.kind === 'step')!.text).toBe(
      'Boil the dal for 20 minutes.'
    );
    await discardDraft();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
  });

  it('leaving the page waits while a step box is open, and keeps the typed words (F143)', async () => {
    show(reviewFlow(), true);
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    const box = page.getByLabelText('Words of step 1');
    await box.fill('Boil the dal for 20 minutes.');
    expect(leaveFor()).toHaveBeenCalledTimes(1);
    await expect.element(box).toHaveValue('Boil the dal for 20 minutes.');
    await expect.element(box).toHaveFocus();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    await page.getByRole('button', { name: 'Done' }).click();
    expect(leaveFor()).toHaveBeenCalledTimes(1); // the leave sheet's question, as before
    await expect.element(page.getByRole('dialog')).toBeVisible();
  });

  it('Close and Save recipe each wait while the other runs', async () => {
    const flow = reviewFlow();
    show(flow, true);
    flow.saving = true;
    flushSync();
    await expect.element(page.getByRole('button', { name: /^Back to drafts/ })).toBeDisabled();
    flow.saving = false;
    flow.keeping = true;
    flushSync();
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
    flow.keeping = false;
  });

  it('leaves the menu back when Check goes', async () => {
    show(reviewFlow(), true);
    expect(document.documentElement.hasAttribute('data-full-page')).toBe(true);
    unmount(component!);
    component = null;
    expect(document.documentElement.hasAttribute('data-full-page')).toBe(false);
  });
});

describe('a computer', () => {
  it('leaving the page waits while a step box is open, and keeps the typed words (F143)', async () => {
    await page.viewport(1280, 900);
    show(reviewFlow(), false);
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    const box = page.getByLabelText('Words of step 1');
    await box.fill('Boil the dal for 20 minutes.');
    expect(leaveFor()).toHaveBeenCalledTimes(1);
    await expect.element(box).toHaveValue('Boil the dal for 20 minutes.');
    await expect.element(box).toHaveFocus();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    await page.getByRole('button', { name: 'Done' }).click();
    expect(leaveFor()).toHaveBeenCalledTimes(1); // the leave sheet's question, as before
    await expect.element(page.getByRole('dialog')).toBeVisible();
  });

  it('Back to drafts looks greyed, as Save recipe does, while a step box is open (F154)', async () => {
    show(reviewFlow(), false);
    const cancel = page.getByRole('button', { name: 'Back to drafts' });
    const save = page.getByRole('button', { name: 'Save recipe' });
    expect(faded(cancel)).toBe(1);
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    await expect.element(cancel).toBeDisabled();
    expect(faded(cancel)).toBeLessThan(1);
    expect(faded(cancel)).toBe(faded(save));
  });

  it('Save recipe and Back to drafts wait while a step box is open, and work after Done (F143)', async () => {
    await page.viewport(1280, 900);
    const flow = reviewFlow();
    show(flow, false);
    await page.getByRole('button', { name: /^Change step 1/ }).click();
    await page.getByLabelText('Words of step 1').fill('Boil the dal for 20 minutes.');
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
    const cancel = () => page.getByRole('button', { name: 'Back to drafts' });
    await expect.element(cancel()).toBeDisabled();
    await page.getByRole('button', { name: 'Done' }).click();
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeEnabled();
    await expect.element(cancel()).toBeEnabled();
    expect(flow.review!.steps.find((x) => x.kind === 'step')!.text).toBe(
      'Boil the dal for 20 minutes.'
    );
    await cancel().click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
  });

  it('keeps today’s Check screen whatever the phone’s choice is', async () => {
    for (const choice of ['focus', 'one'] as const) {
      checkMode.set(choice);
      await page.viewport(1280, 900);
      show(reviewFlow(), false);
      await expect.element(page.getByRole('button', { name: 'Back to drafts' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Discard draft' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
      await expect.element(page.getByRole('list', { name: 'Import steps' })).toBeVisible();
      await expect.element(page.getByText('Nothing is saved until you choose.')).toBeVisible();
      expect(page.getByText('Kept in Drafts').elements()).toEqual([]); // the phone's own label
      expect(page.getByRole('button', { name: 'Next →' }).elements()).toEqual([]);
      expect(document.documentElement.hasAttribute('data-full-page')).toBe(false);
      unmount(component!);
      component = null;
    }
  });
});

// --- One at a time -------------------------------------------------------------------------------

const LONG =
  'Heat the ghee. Add the cumin. Add the garlic. Add the chillies. Pour it over the dal.';
/** Three lines (a ready one, one to confirm, one that needs you) and four steps under a heading. */
function oneReview(): Partial<ImportReview> {
  const [, matched, , onion, asafoetida] = SAMPLE_LINES;
  return {
    lines: [matched!, onion!, asafoetida!].map((l) => ({ ...l })),
    steps: [
      { kind: 'heading', text: 'The tempering' },
      { kind: 'step', text: 'Boil the dal.' },
      { kind: 'step', text: LONG },
      { kind: 'step', text: 'Eat it.' }
    ],
    counts: { matched: 1, to_confirm: 1, needs_you: 1, staple: 0 },
    left_out: []
  };
}

describe('One at a time', () => {
  beforeEach(() => {
    checkMode.set('one');
    undoHistory.clear();
    toasts.dismiss();
  });

  const heading = () => page.getByRole('heading', { level: 1 });
  const next = () => page.getByRole('button', { name: /^Next/ });
  const back = () => page.getByRole('button', { name: /^← Back/ });

  async function opened(over: Partial<ImportReview> = oneReview()) {
    const flow = reviewFlow(over);
    show(flow, true);
    await expect.element(heading()).toBeVisible();
    return flow;
  }

  it('starts on the first line that needs you, as drawn, with the menu hidden', async () => {
    await opened();
    expect(document.documentElement.hasAttribute('data-full-page')).toBe(true);
    await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
    await expect.element(page.getByText('Sambar · nothing saved yet')).toBeVisible();
    await expect.element(page.getByText('Lines that need you · 1 of 2')).toBeVisible();
    await expect.element(page.getByText(/1 red onion, sliced/).first()).toBeVisible();
    await expect.element(back()).toBeDisabled();
    await expect.element(page.getByRole('button', { name: 'See all' })).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }))
      .toBeVisible();
    // The ready line is not on a card of its own.
    expect(document.body.textContent).not.toContain('thuvaram paruppu');
  });

  it('walks the lines that need you, then every step, then Save recipe', async () => {
    const flow = await opened();
    const seen: string[] = [];
    const items = walkItems(flow.review!);
    for (let n = 0; n < items.length; n++) {
      seen.push(heading().element().textContent!);
      if (n < items.length - 1) await next().click();
    }
    expect(seen).toEqual([
      'Ingredients · 1 of 2 to check',
      'Ingredients · 2 of 2 to check',
      'Method · step 1 of 3',
      'Method · step 2 of 3',
      'Method · step 3 of 3'
    ]);
    // Next is Save recipe on the last screen, and Back goes the way it came.
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
    expect(next().elements()).toEqual([]);
    await back().click();
    await expect.element(heading()).toHaveTextContent('Method · step 2 of 3');
  });

  it('shows the step with its heading, and says the long one is long', async () => {
    await opened();
    await next().click();
    await next().click();
    await expect.element(page.getByText('The tempering')).toBeVisible();
    await expect.element(page.getByText('Boil the dal.')).toBeVisible();
    await expect.element(page.getByText('Every step · 1 of 3')).toBeVisible();
    await next().click();
    await expect.element(page.getByText('A long step (5 sentences)')).toBeVisible();
  });

  describe('a line, with the Check screen’s own options', () => {
    it('Same as “Onions” (a line to confirm), and Change takes it back', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: 'Same as “Onions”' }).click();
      expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', food: { id: 2 } });
      // The line stays in the walk: Next still goes on to the second.
      await expect.element(page.getByText('Same as', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: /^Change: / }).click();
      await page.getByRole('button', { name: 'Back to how it was read' }).click();
      expect(flow.choices[1]).toBeUndefined();
    });

    it('Pick another opens the picker for this line', async () => {
      await opened();
      await page.getByRole('button', { name: 'Pick another' }).click();
      // The pick-list for a line (F189, W4d): what is it, as written, a search box, the two buttons.
      await expect.element(page.getByLabelText('Search')).toBeVisible();
      await expect.element(page.getByText('As written: 1 red onion, sliced')).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: '+ New ingredient', exact: true }).last())
        .toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Made in another recipe…' }))
        .toBeVisible();
    });

    it('New ingredient opens its form, with Done', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: '+ New ingredient', exact: true }).click();
      expect(flow.choices[1]).toMatchObject({ kind: 'new' });
      // The recipe's own Name box is at the top of this first screen; the form's is the last.
      await expect.element(page.getByLabelText('Name').last()).toBeVisible();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByText('New ingredient:')).toBeVisible();
    });

    it('Treat as staple, on a line that needs you', async () => {
      const flow = await opened();
      await next().click();
      await expect.element(heading()).toHaveTextContent('Ingredients · 2 of 2 to check');
      await page.getByRole('button', { name: 'Treat as staple', exact: true }).click();
      expect(flow.choices[2]).toMatchObject({ kind: 'staple' });
    });

    it('Made in this recipe, offered first for a “from the …” line', async () => {
      const over = oneReview();
      over.lines![1] = { ...over.lines![1]!, note: 'from the spice blend' };
      const flow = await opened(over);
      const first = document.querySelector('.line .buttons button');
      expect(first?.textContent?.trim()).toBe('Made in this recipe');
      await page.getByRole('button', { name: 'Made in this recipe' }).click();
      expect(flow.choices[1]).toEqual({ kind: 'here' });
    });

    it('Remove line takes it out with Undo, and the next line takes its place', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
      expect(flow.review!.lines).toHaveLength(2);
      expect(toasts.current?.message).toBe('Removed “1 red onion, sliced”');
      // The only other line that needs you is now the first and last of the lines.
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 1 to check');
      await expect.element(page.getByText(/¼ tsp asafoetida/).first()).toBeVisible();
      expect(await undoHistory.undoLast()).toBe(true);
      flushSync();
      expect(flow.review!.lines).toHaveLength(3);
      // The walk stays on the line it was on (F141); the one that came back is before it.
      await expect.element(heading()).toHaveTextContent('Ingredients · 2 of 2 to check');
      await expect.element(page.getByText(/¼ tsp asafoetida/).first()).toBeVisible();
    });

    it('Split into two opens the two names, and splits the line', async () => {
      const flow = await opened();
      fakeApi({
        'GET /places': [200, { places: PLACES }],
        'GET /shops': [200, { shops: SHOPS }],
        'GET /foods?q=red&limit=8': [200, { foods: [] }],
        'GET /foods?q=onion&limit=8': [200, { foods: [] }]
      });
      flow.review!.lines[1] = {
        ...flow.review!.lines[1]!,
        written: '2 cups red and white onion',
        words: 'red and white onion'
      };
      flushSync();
      await page.getByRole('button', { name: /^Split into two:/ }).click();
      await expect.element(page.getByLabelText('First ingredient')).toHaveValue('red');
      await page.getByLabelText('Second ingredient').fill('onion');
      await page.getByRole('button', { name: 'Split', exact: true }).click();
      await vi.waitFor(() => expect(flow.review!.lines).toHaveLength(4));
      expect(toasts.current?.message).toContain('into two');
    });

    it('the amount and note boxes open from the chips', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: /^Amount 1/ }).click();
      await page.getByLabelText('Amount', { exact: true }).fill('3');
      expect(flow.review!.lines[1]).toMatchObject({ amount: 3 });
    });

    it('Ctrl+Z undoes a removed line here as on the Check screen', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
      expect(flow.review!.lines).toHaveLength(2);
      handleUndoKey(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, cancelable: true }));
      await vi.waitFor(() => expect(flow.review!.lines).toHaveLength(3));
    });
  });

  it('the focus goes to the top of the screen after Next, Back, Remove line and Split into two', async () => {
    const flow = await opened();
    const region = () => document.activeElement?.classList.contains('one');
    await next().click();
    expect(region()).toBe(true);
    await back().click();
    expect(region()).toBe(true);
    await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
    await vi.waitFor(() => expect(region()).toBe(true));
    expect(await undoHistory.undoLast()).toBe(true);
    flushSync();
    fakeApi({
      'GET /places': [200, { places: PLACES }],
      'GET /shops': [200, { shops: SHOPS }],
      'GET /foods?q=red&limit=8': [200, { foods: [] }],
      'GET /foods?q=onion&limit=8': [200, { foods: [] }]
    });
    flow.review!.lines[1] = {
      ...flow.review!.lines[1]!,
      written: '2 cups red and white onion',
      words: 'red and white onion'
    };
    flushSync();
    await page.getByRole('button', { name: /^Split into two:/ }).click();
    await page.getByLabelText('Second ingredient').fill('onion');
    await page.getByRole('button', { name: 'Split', exact: true }).click();
    await vi.waitFor(() => expect(flow.review!.lines).toHaveLength(4));
    await vi.waitFor(() => expect(region()).toBe(true));
  });

  it('the focus is on the screen after Next reaches the last screen, with Save recipe in Next’s place', async () => {
    await opened();
    for (let i = 0; i < 4; i++) await next().click();
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
    expect(document.activeElement?.classList.contains('one')).toBe(true);
  });

  it('the focus goes to the top of the screen after Keep the split', async () => {
    await opened();
    await next().click();
    for (let i = 0; i < 2; i++) await next().click();
    await page.getByRole('button', { name: 'Split into shorter steps' }).click();
    await page.getByRole('button', { name: 'Keep the split' }).click();
    await vi.waitFor(() => expect(document.activeElement?.classList.contains('one')).toBe(true));
  });

  describe('a step, with the Check screen’s own options', () => {
    async function onStep(n: number) {
      const flow = await opened();
      await next().click(); // line 2
      for (let i = 0; i <= n; i++) await next().click();
      return flow;
    }

    it('Change the words: nothing is saved, the step changes, Back and Next wait for Done', async () => {
      const flow = await onStep(0);
      await page.getByRole('button', { name: 'Change the words' }).click();
      const box = page.getByLabelText('Words of step 1');
      await expect.element(box).toHaveValue('Boil the dal.');
      await expect.element(next()).toBeDisabled();
      await box.fill('Boil the dal for 20 minutes.');
      await page.getByRole('button', { name: 'Done' }).click();
      expect(flow.review!.steps[1]!.text).toBe('Boil the dal for 20 minutes.');
      await expect.element(page.getByText('Boil the dal for 20 minutes.')).toBeVisible();
      await expect.element(next()).toBeEnabled();
    });

    it('tapping the step’s words opens the same box, and Cancel leaves them', async () => {
      const flow = await onStep(0);
      await page.getByRole('button', { name: 'Change step 1: Boil the dal.' }).click();
      await page.getByLabelText('Words of step 1').fill('Nothing');
      await page.getByRole('button', { name: 'Cancel' }).click();
      expect(flow.review!.steps[1]!.text).toBe('Boil the dal.');
    });

    it('an empty step can’t be kept, and offers Remove step', async () => {
      const flow = await onStep(0);
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText('Words of step 1').fill('  ');
      await page.getByRole('button', { name: 'Done' }).click();
      await expect
        .element(page.getByText('A step can’t be empty. Write something, or remove it.'))
        .toBeVisible();
      await page.getByRole('button', { name: 'Remove step' }).click();
      expect(flow.review!.steps.map((s) => s.text)).not.toContain('Boil the dal.');
    });

    it('Remove step takes it out with Undo, and the next step takes its place', async () => {
      const flow = await onStep(0);
      await page.getByRole('button', { name: 'Remove step' }).click();
      expect(toasts.current?.message).toBe('Removed step 1');
      expect(flow.review!.steps.map((s) => s.text)).toEqual(['The tempering', LONG, 'Eat it.']);
      await expect.element(heading()).toHaveTextContent('Method · step 1 of 2');
      await expect.element(page.getByText('A long step (5 sentences)')).toBeVisible();
      expect(await undoHistory.undoLast()).toBe(true);
      flushSync();
      expect(flow.review!.steps.map((s) => s.text)).toEqual([
        'The tempering',
        'Boil the dal.',
        LONG,
        'Eat it.'
      ]);
      // Stays on the step it was on (the one that took the removed step's place).
      await expect.element(heading()).toHaveTextContent('Method · step 2 of 3');
      await expect.element(page.getByText('A long step (5 sentences)')).toBeVisible();
    });

    it('Undo with a step box open on the stand-in step keeps the screen, the box and the words', async () => {
      const flow = await onStep(0); // step 1 of 3: "Boil the dal."
      await page.getByRole('button', { name: 'Remove step' }).click(); // LONG stands in
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText(/^Words of step/).fill('Typed words');
      expect(await undoHistory.undoLast()).toBe(true);
      flushSync();
      expect(flow.review!.steps.map((x) => x.text)).toContain('Boil the dal.');
      await expect.element(heading()).toHaveTextContent('Method · step 2 of 3');
      await expect.element(page.getByLabelText(/^Words of step/)).toHaveValue('Typed words');
      await expect.element(next()).toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(next()).toBeEnabled();
    });

    it('a refused save while a step box is open leaves the box and its words, and goes to the line after Done', async () => {
      const flow = await onStep(0);
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText('Words of step 1').fill('Typed words');
      flow.saveProblem = { line: 0, message: 'That amount is too big.' };
      flushSync();
      await expect.element(page.getByLabelText('Words of step 1')).toHaveValue('Typed words');
      await expect.element(heading()).toHaveTextContent('Method · step 1 of 3');
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 3 to check');
      expect(flow.review!.steps.map((x) => x.text)).toContain('Typed words');
    });

    it('Split into shorter steps shows the preview, Keep the split makes more steps, and they can be put back', async () => {
      const flow = await onStep(1);
      await expect.element(page.getByText('A long step (5 sentences)')).toBeVisible();
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await expect.element(page.getByText('Preview: this step as 3 steps')).toBeVisible();
      // Keep as one leaves it.
      await page.getByRole('button', { name: 'Keep as one' }).click();
      expect(flow.review!.steps).toHaveLength(4);
      await page.getByRole('button', { name: 'Split into shorter steps' }).click();
      await page.getByRole('button', { name: 'Keep the split' }).click();
      expect(flow.review!.steps).toHaveLength(6);
      // Step 2 of 5 is now the first piece, and Next walks the new steps too.
      await expect.element(heading()).toHaveTextContent('Method · step 2 of 5');
      await expect.element(page.getByText('Heat the ghee. Add the cumin.')).toBeVisible();
      await page.getByRole('button', { name: 'Put the steps back as they were' }).click();
      expect(flow.review!.steps).toHaveLength(4);
      expect(flow.review!.steps[2]!.text).toBe(LONG);
      await expect.element(heading()).toHaveTextContent('Method · step 2 of 3');
    });
  });

  describe('Close, See all and Save', () => {
    it('Close keeps the draft with the choices so far, and opens Drafts', async () => {
      const flow = await opened();
      const requests = fakeApi({
        'POST /recipes/drafts': [201, KEPT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      await page.getByRole('button', { name: 'Same as “Onions”' }).click();
      await page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }).click();
      leaveFor('/recipes/drafts'); // the leave guard asks, as for any leave (F211)
      await page.getByRole('button', { name: 'Save draft' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      const keep = requests.find((r) => r.method === 'POST' && r.path === '/recipes/drafts')!;
      const body = keep.body as { choices: { lines: Record<string, { kind: string }> } };
      expect(body.choices.lines['1']?.kind).toBe('ingredient');
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
      expect(flow.draftId).toBe(7);
    });

    it('Close says why when the draft can’t be kept, and stays', async () => {
      await opened();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      await page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }).click();
      leaveFor('/recipes/drafts'); // the leave guard asks, as for any leave (F211)
      await page.getByRole('button', { name: 'Save draft' }).click();
      await expect
        .element(page.getByText('You have 50 drafts. Finish or delete one first.').first())
        .toBeVisible();
      // Only Back to drafts' own attempt (the guard stopped it): nothing else left.
      expect(nav.goto).toHaveBeenCalledTimes(1);
    });

    it('Close waits while a step box is open, and works after Done with the edit kept', async () => {
      const flow = await opened();
      fakeApi({
        'POST /recipes/drafts': [201, KEPT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      await next().click(); // line 2
      await next().click(); // step 1
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText('Words of step 1').fill('Boil the dal for 20 minutes.');
      await expect
        .element(page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }))
        .toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(flow.review!.steps[1]!.text).toBe('Boil the dal for 20 minutes.');
    });

    it('Close, See all, Back and Next all look greyed while a step box is open (F154)', async () => {
      await opened();
      await next().click(); // line 2
      await next().click(); // step 1
      const buttons = [
        page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }),
        page.getByRole('button', { name: 'See all' }),
        back(),
        next()
      ];
      for (const button of buttons) expect(faded(button)).toBe(1);
      await page.getByRole('button', { name: 'Change the words' }).click();
      for (const button of buttons) {
        await expect.element(button).toBeDisabled();
        expect(faded(button)).toBeLessThan(1);
      }
    });

    describe('swiping (F145)', () => {
      const swipe = (dx: number, dy = 0, target?: Element) => {
        const el = target ?? document.querySelector('.one')!;
        const fire = (type: string, x: number, y: number) =>
          el.dispatchEvent(
            new PointerEvent(type, { clientX: x, clientY: y, pointerId: 1, bubbles: true })
          );
        fire('pointerdown', 200, 300);
        fire('pointerup', 200 + dx, 300 + dy);
        flushSync();
      };

      it('left is Next and right is Back; short, downward and past-the-end swipes do nothing', async () => {
        await opened();
        await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
        swipe(20);
        swipe(-100, 200);
        swipe(120); // no screen before the first
        await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
        swipe(-120);
        await expect.element(heading()).toHaveTextContent('Ingredients · 2 of 2 to check');
        swipe(120);
        await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
        for (let n = 0; n < 6; n++) swipe(-120);
        // The last screen: a swipe does not save, it stays.
        await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
        expect(nav.goto).not.toHaveBeenCalled();
      });

      it('a swipe that starts on a button or box is not a swipe', async () => {
        await opened();
        swipe(-120, 0, page.getByRole('button', { name: 'Treat as staple' }).element());
        await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
      });

      it('waits while a step box is open, and works after Done', async () => {
        await opened();
        await next().click(); // line 2
        await next().click(); // step 1
        await page.getByRole('button', { name: 'Change the words' }).click();
        swipe(-120);
        swipe(120);
        await expect.element(page.getByLabelText('Words of step 1')).toBeVisible();
        await expect.element(heading()).toHaveTextContent('Method · step 1 of 3');
        await page.getByRole('button', { name: 'Done' }).click();
        swipe(-120);
        await expect.element(heading()).toHaveTextContent('Method · step 2 of 3');
      });
    });

    it('See all waits while a step box is open', async () => {
      await opened();
      await next().click(); // line 2
      await next().click(); // step 1
      await page.getByRole('button', { name: 'Change the words' }).click();
      await expect.element(page.getByRole('button', { name: 'See all' })).toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByRole('button', { name: 'See all' })).toBeEnabled();
    });

    it('leaving the page waits while a step box is open, and keeps the typed words (F143)', async () => {
      await opened();
      await next().click(); // line 2
      await next().click(); // step 1
      await page.getByRole('button', { name: 'Change the words' }).click();
      const box = page.getByLabelText('Words of step 1');
      await box.fill('Boil the dal for 20 minutes.');
      expect(leaveFor()).toHaveBeenCalledTimes(1);
      await expect.element(box).toHaveValue('Boil the dal for 20 minutes.');
      await expect.element(box).toHaveFocus();
      await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
      await page.getByRole('button', { name: 'Done' }).click();
      expect(leaveFor()).toHaveBeenCalledTimes(1); // the leave sheet's question, as before
      await expect.element(page.getByRole('dialog')).toBeVisible();
    });

    it('a box left behind by a change of screen does not hold the page (F143)', async () => {
      // The phone turned (or the choice changed) with a box open: that screen and its box are gone,
      // so leaving asks the leave sheet's question as usual, rather than staying put for good.
      await opened();
      await next().click(); // line 2
      await next().click(); // step 1
      await page.getByRole('button', { name: 'Change the words' }).click();
      await expect.element(page.getByLabelText('Words of step 1')).toBeVisible();
      checkMode.set('focus');
      flushSync();
      await expect.element(page.getByLabelText('Words of step 1')).not.toBeInTheDocument();
      expect(leaveFor()).toHaveBeenCalledTimes(1);
      await expect.element(page.getByRole('dialog')).toBeVisible();
    });

    it('a box on the whole list does not hold the page once One at a time shows (F143)', async () => {
      checkMode.set('focus');
      show(reviewFlow(oneReview()), true);
      await page.getByRole('button', { name: /^Change step 1/ }).click();
      await expect.element(page.getByLabelText('Words of step 1')).toBeVisible();
      checkMode.set('one');
      flushSync();
      await expect.element(page.getByLabelText('Words of step 1')).not.toBeInTheDocument();
      expect(leaveFor()).toHaveBeenCalledTimes(1);
      await expect.element(page.getByRole('dialog')).toBeVisible();
    });

    it('Discard waits while a step box is open, and works after Done (F143)', async () => {
      const flow = await opened();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      await page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }).click();
      await next().click(); // line 2
      await next().click(); // step 1
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText('Words of step 1').fill('Boil the dal for 20 minutes.');
      await expect
        .element(page.getByRole('button', { name: 'Discard draft', exact: true }))
        .toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      expect(flow.review!.steps[1]!.text).toBe('Boil the dal for 20 minutes.');
      await discardDraft();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    });

    it('Save recipe on the last screen waits while a step box is open, and works after Done (F143)', async () => {
      const flow = await opened();
      for (let i = 0; i < 4; i++) await next().click();
      await page.getByRole('button', { name: 'Change the words' }).click();
      await page.getByLabelText(/^Words of step/).fill('Last step, changed.');
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeEnabled();
      expect(flow.review!.steps.map((x) => x.text)).toContain('Last step, changed.');
    });

    it('Discard waits while Save recipe runs', async () => {
      const flow = await opened();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      await page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }).click();
      flow.saving = true;
      flushSync();
      await expect
        .element(page.getByRole('button', { name: 'Discard draft', exact: true }))
        .toBeDisabled();
      flow.saving = false;
    });

    it('Discard draft on a review never kept lets go of it and lands on Recipes', async () => {
      await opened();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      await discardDraft();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
    });

    it('Close and Save recipe each wait while the other runs', async () => {
      const flow = await opened();
      for (let i = 0; i < 4; i++) await next().click();
      flow.saving = true;
      flushSync();
      await expect
        .element(page.getByRole('button', { name: 'Back to drafts (kept in Drafts)' }))
        .toBeDisabled();
      flow.saving = false;
      flow.keeping = true;
      flushSync();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
      flow.keeping = false;
    });

    it('See all shows the whole list (Focus) for this visit', async () => {
      await opened();
      await page.getByRole('button', { name: 'See all' }).click();
      await expect
        .element(page.getByRole('button', { name: /^Back to drafts Kept/ }))
        .toBeVisible();
      await expect.element(page.getByText('Toor dal').first()).toBeVisible();
      expect(next().elements()).toEqual([]);
    });

    it('Save recipe on the last screen goes through the same Save: unlinked lines are asked about', async () => {
      const flow = await opened();
      for (let n = 0; n < 4; n++) await next().click();
      await page.getByRole('button', { name: 'Save recipe' }).click();
      await expect
        .element(page.getByRole('dialog', { name: '2 lines aren’t linked yet' }))
        .toBeVisible();
      expect(flow.walk?.queue).toHaveLength(2);
    });

    it('Save recipe sends the recipe once every line has a choice', async () => {
      const flow = await opened();
      flow.sameAs(1, { id: 2, name: 'Onions' });
      flow.madeHere(2);
      flushSync();
      for (let n = 0; n < 4; n++) await next().click();
      const requests = fakeApi({
        'POST /recipes/import/save': [
          500,
          { detail: 'Couldn’t save. Try again.', code: 'server_error' }
        ]
      });
      await page.getByRole('button', { name: 'Save recipe' }).click();
      await vi.waitFor(() => expect(requests.some((r) => r.method === 'POST')).toBe(true));
      expect(requests.find((r) => r.method === 'POST')!.path).toContain('/recipes/import');
    });

    describe('what Focus shows, here on the screen it belongs to (F141 follow-ups, cabledrawer 6 Nov)', () => {
      const boxes = () => ({
        name: page.getByLabelText('Name').first(),
        serves: page.getByLabelText('Serves'),
        minutes: page.getByLabelText('Minutes')
      });

      it('shows the recipe’s name, Serves and minutes at the top of the first screen only', async () => {
        const flow = await opened();
        const { name, serves, minutes } = boxes();
        await expect.element(name).toHaveValue('Sambar');
        await expect.element(serves).toHaveValue('4');
        await expect.element(minutes).toHaveValue('50');
        await name.fill('Sambar, my way');
        await serves.fill('6');
        expect(flow.name).toBe('Sambar, my way');
        expect(flow.serves).toBe('6');
        // Above the first line, and gone on the next screen.
        const top = name.element().getBoundingClientRect().top;
        const line = page
          .getByText(/1 red onion, sliced/)
          .first()
          .element();
        expect(top).toBeLessThan(line.getBoundingClientRect().top);
        await next().click();
        expect(page.getByLabelText('Serves').elements()).toEqual([]);
        await back().click();
        await expect.element(page.getByLabelText('Serves')).toBeVisible();
      });

      it('shows the photo note on the first screen only', async () => {
        await opened();
        await expect
          .element(page.getByText('Photo not downloaded', { exact: false }))
          .toBeVisible();
        await next().click();
        expect(page.getByText('Photo not downloaded', { exact: false }).elements()).toEqual([]);
      });

      it('says “first 200 lines” on the last ingredient screen and “shortened” on the last step', async () => {
        await opened({ ...oneReview(), lines_cut: true, steps_shortened: 2 });
        const first200 = page.getByText(
          'The page had more than 200 ingredient lines. The first 200 are here.'
        );
        const shortened = page.getByText('2 steps were shortened to 5,000 characters.');
        expect(first200.elements()).toEqual([]);
        await next().click(); // line 2 of 2: the last
        await expect.element(first200).toBeVisible();
        await next().click(); // step 1
        expect(first200.elements()).toEqual([]);
        expect(shortened.elements()).toEqual([]);
        await next().click();
        await next().click(); // the last step
        await expect.element(shortened).toBeVisible();
        expect(first200.elements()).toEqual([]);
      });
    });

    it('the offline line shows on every screen while offline, not only the last', async () => {
      await opened();
      network.offline = true;
      network.deviceOffline = true;
      flushSync();
      const words = () => document.querySelector('.foot [role="status"]')?.textContent ?? '';
      for (let n = 0; n < 4; n++) {
        await vi.waitFor(() => expect(words()).toMatch(/^You’re offline\. Save /));
        await next().click();
      }
      // The last screen (Save recipe) says it too.
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeDisabled();
      expect(words()).toMatch(/^You’re offline\. Save /);
    });

    it('a save problem on a line outside the walk goes to that line and says what is wrong', async () => {
      const flow = await opened();
      // The first line (thuvaram paruppu) is ready, so the walk doesn't stop at it.
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
      await next().click();
      await next().click(); // step 1
      flow.saveProblem = { line: 0, message: 'That amount is too big.' };
      flushSync();
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 3 to check');
      await expect.element(page.getByText(/thuvaram paruppu/).first()).toBeVisible();
      await expect.element(page.getByText('That amount is too big.').first()).toBeVisible();
      // The walk went on to hold it: the other lines still follow, then the steps.
      await next().click();
      await expect.element(heading()).toHaveTextContent('Ingredients · 2 of 3 to check');
    });

    it('Undo of a removed line does not move the walk off the screen the person is on', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: /^Remove line: 1 red onion, sliced/ }).click();
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 1 to check');
      await next().click(); // step 1, "Boil the dal."
      await expect.element(heading()).toHaveTextContent('Method · step 1 of 3');
      expect(await undoHistory.undoLast()).toBe(true);
      flushSync();
      expect(flow.review!.lines).toHaveLength(3);
      // Still on step 1, though the line that came back is now ahead of it in the walk.
      await expect.element(heading()).toHaveTextContent('Method · step 1 of 3');
      await expect.element(page.getByText('Boil the dal.').first()).toBeVisible();
    });

    it('with nothing to look at, says so and offers Save recipe', async () => {
      await opened({
        lines: [{ ...SAMPLE_LINES[1]! }],
        steps: [],
        counts: { matched: 1, to_confirm: 0, needs_you: 0, staple: 0 },
        left_out: []
      });
      await expect.element(heading()).toHaveTextContent('Nothing to check');
      await expect
        .element(
          page.getByText(
            'Nothing to check here. Press Save recipe, or See all to look at the whole recipe.'
          )
        )
        .toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
      expect(back().elements()).toEqual([]);
    });
  });
});

// --- Steps that wait (M1, mockup CheckWait08) ----------------------------------------------------

const MARINATE = { kind: 'marinate', min_minutes: 240, max_minutes: 720, overnight: true };
const NB = ' ';

function waitReview(): Partial<ImportReview> {
  return {
    lines: [],
    steps: [
      {
        kind: 'step',
        text: 'Rub the chicken. Leave to marinate for 4 hours, or overnight.',
        wait: { ...MARINATE }
      },
      { kind: 'step', text: 'Fry the onions until golden, about 12 minutes.' }
    ],
    counts: { matched: 0, to_confirm: 0, needs_you: 0, staple: 0 },
    left_out: [],
    time_minutes: 45
  };
}

describe('Steps that wait on Check', () => {
  const yes = () => page.getByRole('button', { name: 'Yes, it waits' });
  const change = () => page.getByRole('button', { name: 'Change', exact: true });
  const noWait = () => page.getByRole('button', { name: 'No wait' });

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
  });

  for (const mode of ['one', 'focus'] as const) {
    describe(mode === 'one' ? 'One at a time' : 'Focus', () => {
      beforeEach(() => checkMode.set(mode));

      async function opened() {
        const flow = reviewFlow(waitReview());
        show(flow, true);
        await expect.element(page.getByRole('heading', { level: 1 })).toBeVisible();
        await expect
          .element(page.getByText(`Marinate · 4${NB}h – overnight`).first())
          .toBeVisible();
        return flow;
      }

      it('shows the wait the reader found, "To confirm", and the three answers', async () => {
        const flow = await opened();
        await expect.element(page.getByText('To confirm')).toBeVisible();
        await expect.element(yes()).toBeVisible();
        await expect.element(change()).toBeVisible();
        await expect.element(noWait()).toBeVisible();
        // Nothing is saved or changed by looking.
        expect(flow.review!.steps[0]!.wait).toEqual(MARINATE);
        expect(flow.review!.steps[0]!.wait_confirmed).toBeUndefined();
      });

      it('Yes, it waits keeps it and clears "To confirm"; Save sends the wait, not the answer', async () => {
        const flow = await opened();
        await yes().click();
        await expect.element(page.getByText('To confirm')).not.toBeInTheDocument();
        expect(flow.review!.steps[0]!.wait_confirmed).toBe(true);
        const sent = flow.body()!.steps;
        expect(sent[0]).toEqual({
          kind: 'step',
          text: 'Rub the chicken. Leave to marinate for 4 hours, or overnight.',
          optional: undefined,
          wait: MARINATE
        });
        expect('wait_confirmed' in sent[0]!).toBe(false);
      });

      it('No wait takes it off, Save sends none, and Undo puts it back', async () => {
        const flow = await opened();
        await noWait().click();
        await expect.element(page.getByText(/^Marinate ·/)).not.toBeInTheDocument();
        expect(flow.body()!.steps[0]!.wait).toBeNull();
        expect(flow.waitTotal).toBeNull();
        expect(toasts.current?.message).toBe('Took off the wait');
        expect(await undoHistory.undoLast()).toBe(true);
        flushSync();
        expect(flow.review!.steps[0]!.wait).toEqual(MARINATE);
        await expect.element(page.getByText('To confirm')).toBeVisible();
      });

      it('Change opens the boxes; Done keeps the new wait as confirmed', async () => {
        const flow = await opened();
        await change().click();
        await page.getByLabelText('Shortest, step 1', { exact: false }).fill('6');
        await page.getByLabelText('Longest (if it varies), step 1', { exact: false }).fill('10');
        await page.getByRole('switch', { name: /^Ends overnight/ }).click(); // off
        await page.getByRole('button', { name: 'Done' }).click();
        expect(flow.review!.steps[0]!.wait).toEqual({
          kind: 'marinate',
          min_minutes: 360,
          max_minutes: 600,
          overnight: false
        });
        expect(flow.review!.steps[0]!.wait_confirmed).toBe(true);
        await expect.element(page.getByText(`Marinate · 6${NB}h – 10${NB}h`)).toBeVisible();
      });

      it('shows the time split under the Minutes box', async () => {
        await opened();
        await expect
          .element(page.getByText(`45${NB}min active · plus 4${NB}h – overnight marinating`))
          .toBeVisible();
      });
    });
  }
});
