// Settings → Your data → Import from Mealie (0.9.5, cabledrawer 13 Nov): choose the file, see what's
// in it before anything is added, bring it in (on the server), then Done with one Undo. A phone
// has the simple screens; a computer the steps, the table with its tick boxes, chips and search.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { MealieImport, PreviewRecipe } from '#lib/client/mealie.js';
import { POLL_MS } from '#lib/mealieFlow.svelte.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Mealie from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const RECIPES: PreviewRecipe[] = [
  { key: 'm1', name: 'Green curry', tags: ['Dinner', 'Thai'], photo: true, already: false },
  { key: 'm2', name: 'Shakshuka', tags: ['Breakfast'], photo: true, already: false },
  { key: 'm3', name: 'Pâté on toast', tags: [], photo: false, already: false },
  { key: 'm4', name: 'Dal makhani', tags: ['Dinner'], photo: false, already: true }
];

const READY: MealieImport = {
  id: 7,
  state: 'ready',
  file_name: 'mealie_2026.11.10.zip',
  file_bytes: 48_000_000,
  started_by: 'Sam',
  created_at: '2026-11-13T21:30:00Z',
  started_at: null,
  finished_at: null,
  undo_until: null,
  photos: true,
  leave_out: [],
  total: 0,
  done: 0,
  counts: { saved: 0, drafts: 0, already: 0, skipped: 0, new_foods: 0 },
  preview: {
    new: 3,
    already: 1,
    with_photo: 2,
    photo_bytes: 41_200_000,
    foods_matching: 120,
    foods_new: 85,
    left_out: { meal_plans: 6, shopping_lists: 2, users: 3, cookbooks: 4 },
    recipes: RECIPES
  },
  recent: [],
  to_check: []
};

const RUNNING: MealieImport = {
  ...READY,
  state: 'running',
  started_at: '2026-11-13T21:32:00Z',
  total: 3,
  done: 1,
  preview: { ...READY.preview, recipes: [] },
  recent: [
    {
      key: 'm1',
      name: 'Green curry',
      state: 'draft',
      unread: ['1 tin coconut milk (optional)'],
      unread_count: 2
    }
  ]
};

const inAWeek = () => new Date(Date.now() + 6 * 86_400_000).toISOString();

const DONE = (): MealieImport => ({
  ...RUNNING,
  state: 'done',
  done: 3,
  finished_at: new Date().toISOString(),
  undo_until: inAWeek(),
  counts: { saved: 2, drafts: 1, already: 1, skipped: 0, new_foods: 85 },
  to_check: [
    {
      key: 'm1',
      name: 'Green curry',
      state: 'draft',
      draft_id: 31,
      unread: ['1 tin coconut milk (optional)', 'salt to taste'],
      unread_count: 3
    }
  ]
});

const zip = () => new File(['PK'], 'mealie_2026.11.10.zip', { type: 'application/zip' });

/** Choose a file the way the file picker does. */
function choose(file: File) {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  const files = new DataTransfer();
  files.items.add(file);
  input.files = files.files;
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

describe('Import from Mealie', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  async function open(routes: Parameters<typeof fakeApi>[0], width = 390) {
    await page.viewport(width, 844);
    requests = fakeApi(routes);
    component = mount(Mealie, { target: document.body });
    flushSync();
  }

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  beforeEach(() => {
    network.reset();
    session.me = { ...ME, role: 'member' };
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.useRealTimers();
    vi.unstubAllGlobals();
    network.reset();
    session.me = null;
  });

  describe('on a phone', () => {
    it('starts with how, what comes across and what never does', async () => {
      await open({ 'GET /mealie-imports/current': [200, { current: null }] });
      await expect
        .element(page.getByRole('heading', { name: 'Import from Mealie', level: 1 }))
        .toBeVisible();
      await expect
        .element(page.getByText(/Bring your recipes and ingredients across/))
        .toBeVisible();
      await expect
        .element(page.getByText('In Mealie: Settings › Admin Settings › Backups › Create Backup.'))
        .toBeVisible();
      await expect
        .element(page.getByText('Meal plans, shopping lists, users and cookbooks'))
        .toBeVisible();
      await expect
        .element(page.getByText(/It never connects to Mealie or to the internet/))
        .toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Choose the Mealie file (.zip)' }))
        .toBeEnabled();
      // The phone never fetches the computer's table.
      expect(page.getByRole('table').elements()).toEqual([]);
    });

    it('sends the file as it is, then shows what’s in it before anything is added', async () => {
      await open({
        'GET /mealie-imports/current': [200, { current: null }],
        'POST /mealie-imports': [201, READY]
      });
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
      choose(zip());
      await expect.element(page.getByRole('heading', { name: 'In this file' })).toBeVisible();
      const [upload] = sent('POST', '/mealie-imports');
      expect(upload!.url).toBe('/mealie-imports?file_name=mealie_2026.11.10.zip');
      expect(upload!.body).toBeInstanceOf(Blob);
      await expect.element(page.getByText('mealie_2026.11.10.zip')).toBeVisible();
      await expect.element(page.getByText('2 with a photo')).toBeVisible();
      await expect.element(page.getByText('Same name and source: left out')).toBeVisible();
      await page.getByRole('button', { name: 'See which' }).click();
      await expect
        .element(page.getByRole('listitem', { name: 'You already have these' }))
        .toHaveTextContent('Dal makhani');
      await expect
        .element(
          page.getByText('Not brought in: 6 meal plans, 2 shopping lists, 3 users, 4 cookbooks.')
        )
        .toBeVisible();
      await expect.element(page.getByRole('switch', { name: 'Bring in photos' })).toBeChecked();
      await expect.element(page.getByRole('button', { name: 'Bring in 3 recipes' })).toBeEnabled();
      // Nothing is added until Bring in.
      expect(sent('POST', '/mealie-imports/7/start')).toEqual([]);
    });

    it('says why the server refused the file, and stays on the start', async () => {
      await open({
        'GET /mealie-imports/current': [200, { current: null }],
        'POST /mealie-imports': [422, { detail: 'This isn’t a Mealie backup file.' }]
      });
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
      choose(zip());
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('This isn’t a Mealie backup file.');
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
    });

    it('Bring in, without photos when switched off, then shows how far it has got', async () => {
      let job = READY;
      await open({
        'GET /mealie-imports/current': () => [200, { current: job }],
        'POST /mealie-imports/7/start': () => {
          job = RUNNING;
          return [200, RUNNING];
        }
      });
      await page.getByRole('switch', { name: 'Bring in photos' }).click();
      await page.getByRole('button', { name: 'Bring in 3 recipes' }).click();
      await expect.element(page.getByText('Bringing in recipes…')).toBeVisible();
      expect(sent('POST', '/mealie-imports/7/start')[0]!.body).toEqual({
        leave_out: [],
        photos: false
      });
      await expect
        .element(page.getByRole('progressbar', { name: 'Recipes brought in' }))
        .toHaveAttribute('aria-valuenow', '1');
      await expect.element(page.getByText('2 lines to check')).toBeVisible();
      await expect.element(page.getByText(/The import carries on on your server/)).toBeVisible();
      expect(
        page.getByRole('link', { name: 'Leave it running' }).element().getAttribute('href')
      ).toBe('/');
    });

    it('asks how far it has got while it runs, and shows Done when it finishes', async () => {
      const done = DONE();
      let polls = 0;
      await open({
        'GET /mealie-imports/current': [200, { current: RUNNING }],
        'GET /mealie-imports/7': () => [200, ++polls > 1 ? done : RUNNING]
      });
      await expect.element(page.getByText('1 of 3')).toBeVisible();
      await expect
        .element(page.getByText('3 recipes brought in'), { timeout: POLL_MS * 3 })
        .toBeVisible();
      expect(polls).toBe(2);
    });

    it('Cancel deletes the file on the server and goes back to the start', async () => {
      await open({
        'GET /mealie-imports/current': [200, { current: READY }],
        'DELETE /mealie-imports/7': [204, null]
      });
      await page.getByRole('button', { name: 'Cancel' }).click();
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
      expect(sent('DELETE', '/mealie-imports/7')).toHaveLength(1);
    });

    it('Done says what came in, links to the ones to check, and undoes the whole import', async () => {
      await open({
        'GET /mealie-imports/current': [200, { current: DONE() }],
        'POST /mealie-imports/7/undo': [200, { recipes: 2, drafts: 1, foods: 85, kept: 0 }]
      });
      await expect.element(page.getByText('3 recipes brought in')).toBeVisible();
      await expect.element(page.getByText(/From mealie_2026.11.10.zip, today/)).toBeVisible();
      expect(page.getByRole('link', { name: 'Check the 1' }).element().getAttribute('href')).toBe(
        '/recipes/drafts?from=mealie'
      );
      await expect
        .element(
          page.getByText(
            'Takes out the 3 recipes and the 85 new ingredients. Works for 7 days; recipes you’ve changed or cooked since are kept.'
          )
        )
        .toBeVisible();
      await page.getByRole('button', { name: 'Undo' }).click();
      await expect.element(page.getByText('Import undone')).toBeVisible();
      await expect
        .element(page.getByText(/Took out 3 recipes and 85 ingredients\.$/))
        .toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
    });

    it('once Undo no longer works, the screen starts again', async () => {
      const old = { ...DONE(), undo_until: '2026-01-01T00:00:00Z' };
      await open({ 'GET /mealie-imports/current': [200, { current: old }] });
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeVisible();
      await expect.element(page.getByText('3 recipes brought in')).not.toBeInTheDocument();
    });

    it('offline, the file can’t be chosen', async () => {
      await open({ 'GET /mealie-imports/current': [200, { current: null }] });
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeEnabled();
      network.offline = true;
      await expect
        .element(page.getByRole('button', { name: /Choose the Mealie file/ }))
        .toBeDisabled();
    });
  });

  describe('on a computer', () => {
    it('shows the steps and the table; unticked recipes are left out', async () => {
      let job = READY;
      await open(
        {
          'GET /mealie-imports/current': () => [200, { current: job }],
          'POST /mealie-imports/7/start': () => {
            job = RUNNING;
            return [200, RUNNING];
          }
        },
        1300
      );
      await expect.element(page.getByRole('table')).toBeVisible();
      await expect.element(page.getByRole('list', { name: 'Steps' })).toBeVisible();
      await expect
        .element(page.getByText('Showing 4 of 4. Untick any you don’t want.'))
        .toBeVisible();
      // Already here: shown, not tickable.
      await expect
        .element(page.getByRole('checkbox', { name: 'Bring in Dal makhani' }))
        .toBeDisabled();
      await page.getByRole('checkbox', { name: 'Bring in Shakshuka' }).click();
      await expect.element(page.getByRole('button', { name: 'Bring in 2 recipes' })).toBeEnabled();
      await page.getByRole('button', { name: 'Bring in 2 recipes' }).click();
      await expect.element(page.getByText(/Bringing in recipes…/)).toBeVisible();
      expect(sent('POST', '/mealie-imports/7/start')[0]!.body).toEqual({
        leave_out: ['m2'],
        photos: true
      });
    });

    it('the chips and the search narrow the table', async () => {
      await open({ 'GET /mealie-imports/current': [200, { current: READY }] }, 1300);
      await expect.element(page.getByRole('button', { name: 'All 4' })).toBeVisible();
      await page.getByRole('button', { name: 'Already here 1' }).click();
      await expect
        .element(page.getByText('Showing 1 of 1. Untick any you don’t want.'))
        .toBeVisible();
      await expect.element(page.getByRole('rowheader', { name: 'Dal makhani' })).toBeVisible();
      await page.getByRole('button', { name: 'New 3' }).click();
      await page.getByRole('searchbox', { name: 'Find a recipe' }).fill('pate');
      await expect.element(page.getByRole('rowheader', { name: 'Pâté on toast' })).toBeVisible();
      await expect
        .element(page.getByText('Showing 1 of 1. Untick any you don’t want.'))
        .toBeVisible();
    });

    it('takes a file dropped on it', async () => {
      await open(
        {
          'GET /mealie-imports/current': [200, { current: null }],
          'POST /mealie-imports': [201, READY]
        },
        1300
      );
      const zone = page.getByRole('group', { name: 'Drop the Mealie backup here' });
      await expect.element(zone).toBeVisible();
      const files = new DataTransfer();
      files.items.add(zip());
      zone.element().dispatchEvent(new DragEvent('drop', { dataTransfer: files, bubbles: true }));
      await expect.element(page.getByRole('table')).toBeVisible();
      expect(sent('POST', '/mealie-imports')).toHaveLength(1);
    });

    it('Done lists the ones to check, and saves them all as they are', async () => {
      let job = DONE();
      await open(
        {
          'GET /mealie-imports/current': [200, { current: job }],
          'POST /mealie-imports/drafts/save-all': () => {
            job = { ...job, counts: { ...job.counts, saved: 3, drafts: 0 }, to_check: [] };
            return [200, { saved: 1 }];
          },
          'GET /mealie-imports/7': () => [200, job]
        },
        1300
      );
      await expect.element(page.getByRole('heading', { name: '1 recipe to check' })).toBeVisible();
      await expect
        .element(page.getByText('“1 tin coconut milk (optional)”, “salt to taste”, and 1 more'))
        .toBeVisible();
      expect(
        page.getByRole('link', { name: 'Check Green curry' }).element().getAttribute('href')
      ).toBe('/recipes/drafts/31');
      await page.getByRole('button', { name: 'Save all as they are' }).click();
      await expect
        .element(page.getByRole('heading', { name: '1 recipe to check' }))
        .not.toBeInTheDocument();
      expect(sent('POST', '/mealie-imports/drafts/save-all')).toHaveLength(1);
    });
  });
});
