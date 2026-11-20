// Discard draft on Check (F211, cabledrawer 10 Nov): on the phone's Focus, One at a time and on a
// computer. It asks once, deletes the draft the way the Drafts list does (one Undo, in the toast
// and in Recent changes), and its waiting photo goes with it. Back to drafts leaves and keeps.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { CHECK_MODE_STORAGE_KEY, checkMode } from '#lib/checkMode.svelte.js';
import type { DraftOut } from '#lib/client/drafts.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { changeOf, fakeApi, PLACES, SHOPS } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW, reviewFlow } from '#lib/testing/importSamples.js';
import { nextDraft } from '#lib/nextDraft.svelte.js';
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

beforeEach(() => {
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

const screens = [
  { name: 'Focus on the phone', phone: true, choice: 'focus', width: 390 },
  { name: 'One at a time on the phone', phone: true, choice: 'one', width: 390 },
  { name: 'a computer', phone: false, choice: 'focus', width: 1280 }
] as const;

for (const screen of screens) {
  describe(`Discard draft on ${screen.name}`, () => {
    beforeEach(async () => {
      await page.viewport(screen.width, screen.width === 390 ? 844 : 900);
      checkMode.set(screen.choice);
    });

    const opened = (extra: Record<string, Parameters<typeof fakeApi>[0][string]> = {}) => {
      const flow = reviewFlow();
      flow.load(KEPT);
      show(flow, screen.phone);
      return {
        flow,
        requests: fakeApi({
          'GET /places': [200, { places: PLACES }],
          'GET /shops': [200, { shops: SHOPS }],
          ...extra
        })
      };
    };
    const discardButton = () => page.getByRole('button', { name: 'Discard draft', exact: true });
    const sheetButton = () =>
      page.getByRole('dialog').getByRole('button', { name: 'Discard draft' });

    it('asks once, and Keep checking sends nothing', async () => {
      const { requests } = opened();
      await discardButton().click();
      await expect.element(page.getByRole('dialog', { name: 'Discard this draft?' })).toBeVisible();
      await page.getByRole('button', { name: 'Keep checking' }).click();
      await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
      expect(requests.filter((r) => r.method === 'DELETE')).toEqual([]);
      expect(nav.goto).not.toHaveBeenCalled();
    });

    it('deletes the draft with one Undo, and opens Drafts', async () => {
      const { requests } = opened({
        'DELETE /recipes/drafts/7': [200, { change: changeOf(40, 'Deleted the Sambar draft') }]
      });
      await discardButton().click();
      await sheetButton().click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests.filter((r) => r.method === 'DELETE').map((r) => r.path)).toEqual([
        '/recipes/drafts/7'
      ]);
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes\/drafts$/);
      expect(undoHistory.size).toBe(1);
    });

    it('says why and stays when the delete did not go through', async () => {
      opened({ 'DELETE /recipes/drafts/7': [500, { detail: 'Something went wrong.' }] });
      await discardButton().click();
      await sheetButton().click();
      await expect.element(page.getByText('Something went wrong.')).toBeVisible();
      expect(nav.goto).not.toHaveBeenCalled();
      expect(undoHistory.size).toBe(0);
    });

    it('a review that was never kept just lets go, with its waiting photo, and opens Recipes', async () => {
      const photo = {
        id: 41,
        width: 800,
        height: 600,
        url: '/api/v1/recipes/photos/41/large',
        list_width: 156,
        list_height: 117,
        list_url: '/api/v1/recipes/photos/41/list'
      };
      const flow = reviewFlow({ photo: { state: 'downloaded', photo, message: null } });
      show(flow, screen.phone);
      const requests = fakeApi({
        'GET /places': [200, { places: PLACES }],
        'GET /shops': [200, { shops: SHOPS }],
        'DELETE /recipes/photos/41': [204, null]
      });
      await discardButton().click();
      await sheetButton().click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests.filter((r) => r.method === 'DELETE').map((r) => r.path)).toEqual([
        '/recipes/photos/41'
      ]);
      expect(String(nav.goto.mock.calls[0]![0])).toMatch(/\/recipes$/);
      expect(undoHistory.size).toBe(0);
    });

    it('waits while a step box is open (F143), and works after Done', async () => {
      opened();
      if (screen.choice === 'one') return; // its box is tested with the rest of One at a time
      await page.getByRole('button', { name: /^Change step 1/ }).click();
      await expect.element(discardButton()).toBeDisabled();
      await page.getByRole('button', { name: 'Done' }).click();
      await expect.element(discardButton()).toBeEnabled();
    });
  });
}

for (const screen of screens) {
  describe(`Save recipe on ${screen.name} (F212, cabledrawer 10 Nov)`, () => {
    it('opens the new recipe’s page, and marks it so that page offers Next draft', async () => {
      await page.viewport(screen.width, screen.width === 390 ? 844 : 900);
      checkMode.set(screen.choice);
      nextDraft.savedId = null;
      const flow = reviewFlow({ ...PINTS_REVIEW });
      show(flow, screen.phone);
      const requests = fakeApi({
        'GET /places': [200, { places: PLACES }],
        'GET /shops': [200, { shops: SHOPS }],
        'POST /recipes/import/save': [
          201,
          {
            recipe: { id: 55, name: 'Creamy rice pudding' },
            change: changeOf(60, 'Imported Creamy rice pudding'),
            new_ingredients: [],
            learned: 0
          }
        ]
      });
      // One at a time shows one line at a time: Next until the last screen's Save recipe.
      for (let n = 0; n < 12; n++) {
        const save = page.getByRole('button', { name: 'Save recipe' });
        const more = page.getByRole('button', { name: 'Next →' });
        // One at a time loads its own code first: wait for either button.
        await vi.waitFor(() =>
          expect(more.elements().length + save.elements().length).toBeGreaterThan(0)
        );
        if (more.elements().length > 0) await more.click();
        else {
          await save.click();
          break;
        }
      }
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      expect(requests.some((r) => r.path === '/recipes/import/save')).toBe(true);
      expect(String(nav.goto.mock.calls[0]![0])).toBe('/recipes/55');
      expect(nextDraft.savedId).toBe(55);
    });
  });
}
