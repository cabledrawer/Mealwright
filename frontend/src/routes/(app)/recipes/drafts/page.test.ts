import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { DraftOut } from '#lib/client/drafts.js';
import type { ImportReview } from '#lib/client/imports.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { PLACES, SHOPS, fakeApi } from '#lib/testing/fakeApi.js';
import DraftPage from './[id]/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$app/state', () => ({ page: { params: { id: '7' }, url: new URL('http://x/') } }));

const REVIEW: ImportReview = {
  source: { kind: 'text', url: null, site: null },
  name: 'Rava dosa',
  description: null,
  author: null,
  time_minutes: null,
  serves: 4,
  makes: null,
  tags: [],
  nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
  photo: { state: 'none', photo: null, message: null },
  lines: [
    {
      kind: 'ingredient',
      written: '1 red onion, sliced',
      words: 'red onion',
      amount: 1,
      amount_text: '1',
      unit: null,
      size: null,
      note: null,
      readable: true,
      label: 'to_confirm',
      food: { id: 2, name: 'Onions' },
      place: null,
      matched_by: null,
      counts: true,
      new_ingredient: { name: 'Red onion', counted_as: 'count', place: null },
      learn_name: 'red onion'
    }
  ],
  steps: [{ kind: 'step', text: 'Make the batter.' }],
  counts: { matched: 0, to_confirm: 1, needs_you: 0, staple: 0 },
  lines_cut: false,
  steps_cut: false,
  steps_shortened: 0,
  left_out: []
};

const DRAFT: DraftOut = {
  id: 7,
  name: 'Rava dosa with extra',
  source: { kind: 'text', site: null },
  started_by: 'Remy',
  started_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  expires_at: '2026-11-06T10:00:00Z',
  days_left: 13,
  lines_total: 1,
  lines_checked: 1,
  text: 'Rava dosa\n1 red onion, sliced',
  review: REVIEW,
  choices: {
    name: 'Rava dosa with extra',
    serves: '6',
    minutes: null,
    lines: { '0': { kind: 'ingredient', food: { id: 2, name: 'Onions' }, learn: true } }
  }
};

describe('carrying on with a draft', () => {
  let component: ReturnType<typeof mount> | null = null;

  async function open(routes: Parameters<typeof fakeApi>[0]) {
    await page.viewport(390, 844);
    const requests = fakeApi({
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      ...routes
    });
    component = mount(DraftPage, { target: document.body });
    flushSync();
    return requests;
  }

  beforeEach(() => {
    network.reset();
    drafts.forget();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('opens the review with every choice made so far, and does not change the draft by looking', async () => {
    const requests = await open({ 'GET /recipes/drafts/7': [200, DRAFT] });
    await expect.element(page.getByRole('heading', { name: 'Check before saving' })).toBeVisible();
    // On a phone this is the Focus page (F141): Back to drafts, kept in Drafts, takes the back link's place.
    await expect.element(page.getByRole('button', { name: /^Back to drafts/ })).toBeVisible();
    await expect.element(page.getByLabelText('Name')).toHaveValue('Rava dosa with extra');
    await expect.element(page.getByLabelText('Serves')).toHaveValue('6');
    // “Same as Onions” was chosen, and is shown as chosen.
    await expect
      .element(page.getByText('Adds “red onion” as another name for Onions when you save.'))
      .toBeVisible();
    expect(requests.filter((r) => r.method !== 'GET')).toEqual([]);
  });

  it('says the draft is gone when someone deleted it, with a way back', async () => {
    await open({
      'GET /recipes/drafts/7': [
        404,
        { detail: 'That draft isn’t here any more.', code: 'not_found' }
      ]
    });
    await expect.element(page.getByText('That draft isn’t here any more.')).toBeVisible();
    await expect
      .element(page.getByRole('link', { name: 'Back to Drafts' }))
      .toHaveAttribute('href', '/recipes/drafts');
  });

  it('offers Try again when the server could not be reached, and opens it then', async () => {
    await open({ 'GET /recipes/drafts/7': [500, { detail: 'Something went wrong.' }] });
    await expect.element(page.getByText('Something went wrong.')).toBeVisible();
    fakeApi({
      'GET /recipes/drafts/7': [200, DRAFT],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS]
    });
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect.element(page.getByLabelText('Name')).toHaveValue('Rava dosa with extra');
  });
});
