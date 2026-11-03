// Check on the phone (F141, cabledrawer 3 Nov): Focus and One at a time, and a computer that keeps
// the whole screen whatever the choice. The layouts come from ReviewPage, which reads the choice
// in Settings → Appearance.
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
  fakeApi({ 'GET /places': [200, PLACES], 'GET /shops': [200, SHOPS] });
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
    const close = page.getByRole('button', { name: /^Close/ });
    await expect.element(close).toHaveTextContent('Close Kept in Drafts');
    await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Cancel' }).elements()).toEqual([]);
    // No page header with its back link and settings cog: the page is its own.
    expect(page.getByRole('link', { name: /· Settings$/ }).elements()).toEqual([]);
  });

  it('puts the header and the bar on the screen and lets only the list scroll', async () => {
    show(reviewFlow(), true);
    const save = page.getByRole('button', { name: 'Save recipe' }).element();
    const bottom = save.getBoundingClientRect().bottom;
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
    await page.getByRole('button', { name: /^Close/ }).click();
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
    await page.getByRole('button', { name: /^Close/ }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(requests.filter((r) => r.method !== 'GET')).toEqual([]);
    expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
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
    await page.getByRole('button', { name: /^Close/ }).click();
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
    await page.getByRole('button', { name: /^Close/ }).click();
    await expect
      .element(page.getByText('You have 50 drafts. Finish or delete one first.'))
      .toBeVisible();
    expect(nav.goto).not.toHaveBeenCalled();
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
    await expect.element(page.getByRole('button', { name: /^Close/ })).toBeDisabled();
    await page.getByRole('button', { name: 'Done' }).click();
    await page.getByRole('button', { name: /^Close/ }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(flow.review!.steps.find((x) => x.kind === 'step')!.text).toBe(
      'Boil the dal for 20 minutes.'
    );
  });

  it('when the draft can’t be kept, Discard is the way out and lands on Recipes', async () => {
    show(reviewFlow(), true);
    fakeApi({
      'POST /recipes/drafts': [
        409,
        { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
      ]
    });
    await page.getByRole('button', { name: /^Close/ }).click();
    await page.getByRole('button', { name: 'Discard', exact: true }).click();
    await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
    expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
  });

  it('Close and Save recipe each wait while the other runs', async () => {
    const flow = reviewFlow();
    show(flow, true);
    flow.saving = true;
    flushSync();
    await expect.element(page.getByRole('button', { name: /^Close/ })).toBeDisabled();
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
  it('keeps today’s Check screen whatever the phone’s choice is', async () => {
    for (const choice of ['focus', 'one'] as const) {
      checkMode.set(choice);
      await page.viewport(1280, 900);
      show(reviewFlow(), false);
      await expect.element(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
      await expect.element(page.getByRole('list', { name: 'Import steps' })).toBeVisible();
      await expect.element(page.getByText('Nothing is saved until you choose.')).toBeVisible();
      expect(page.getByRole('button', { name: /^Close/ }).elements()).toEqual([]);
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
      .element(page.getByRole('button', { name: 'Close (kept in Drafts)' }))
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
      await page.getByRole('button', { name: 'Change', exact: true }).click();
      expect(flow.choices[1]).toBeUndefined();
    });

    it('Pick another opens the picker for this line', async () => {
      await opened();
      await page.getByRole('button', { name: 'Pick another' }).click();
      await expect
        .element(page.getByLabelText('Pick an ingredient for 1 red onion, sliced'))
        .toBeVisible();
    });

    it('New ingredient opens its form, with Done', async () => {
      const flow = await opened();
      await page.getByRole('button', { name: 'New ingredient', exact: true }).click();
      expect(flow.choices[1]).toMatchObject({ kind: 'new' });
      await expect.element(page.getByLabelText('Name')).toBeVisible();
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
      await expect.element(heading()).toHaveTextContent('Ingredients · 1 of 2 to check');
    });

    it('Split into two opens the two names, and splits the line', async () => {
      const flow = await opened();
      fakeApi({
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS],
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
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
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
      await expect.element(heading()).toHaveTextContent('Method · step 1 of 3');
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
      await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
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
      await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
      await expect
        .element(page.getByText('You have 50 drafts. Finish or delete one first.'))
        .toBeVisible();
      expect(nav.goto).not.toHaveBeenCalled();
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
        .element(page.getByRole('button', { name: 'Close (kept in Drafts)' }))
        .toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(flow.review!.steps[1]!.text).toBe('Boil the dal for 20 minutes.');
    });

    it('when the draft can’t be kept, Discard is the way out and lands on Recipes', async () => {
      await opened();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      await page.getByRole('button', { name: 'Close (kept in Drafts)' }).click();
      await page.getByRole('button', { name: 'Discard', exact: true }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
    });

    it('Close and Save recipe each wait while the other runs', async () => {
      const flow = await opened();
      for (let i = 0; i < 4; i++) await next().click();
      flow.saving = true;
      flushSync();
      await expect
        .element(page.getByRole('button', { name: 'Close (kept in Drafts)' }))
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
      await expect.element(page.getByRole('button', { name: /^Close Kept/ })).toBeVisible();
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

    it('with nothing to look at, says so and offers Save recipe', async () => {
      await opened({
        lines: [{ ...SAMPLE_LINES[1]! }],
        steps: [],
        counts: { matched: 1, to_confirm: 0, needs_you: 0, staple: 0 },
        left_out: []
      });
      await expect.element(heading()).toHaveTextContent('Nothing to check');
      await expect.element(page.getByRole('button', { name: 'Save recipe' })).toBeVisible();
      expect(back().elements()).toEqual([]);
    });
  });
});
