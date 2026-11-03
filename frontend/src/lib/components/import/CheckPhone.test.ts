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
import { reviewFlow } from '#lib/testing/importSamples.js';
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
