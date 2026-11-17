import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { IngredientGroups as Groups } from '#lib/client/drafts.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { changeOf, fakeApi } from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import IngredientGroups from './IngredientGroups.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const PLACES = [
  { id: 1, name: 'Fridge' },
  { id: 3, name: 'Cupboard' }
];

const GROUPS: Groups = {
  groups: [
    {
      key: 'soya sauce',
      name: 'soya sauce',
      drafts: 46,
      lines: 50,
      examples: ['2 tbsp soya sauce', 'soya sauce, dark'],
      suggestion: { id: 9, name: 'Soy sauce' },
      new_name: 'Soya sauce',
      new_place: { id: 3, name: 'Cupboard' }
    },
    {
      key: 'galangal',
      name: 'galangal',
      drafts: 1,
      lines: 1,
      examples: ['a thumb of galangal'],
      suggestion: null,
      new_name: 'Galangal',
      new_place: null
    }
  ],
  total: 2,
  drafts: 47,
  recipes_ready: 3,
  places: PLACES
};

const ANSWERED = {
  change: changeOf(40, 'Answered “soya sauce” in 46 drafts · 3 recipes moved to Recipes'),
  drafts: 46,
  moved: 3,
  ingredient: { id: 9, name: 'Soy sauce' }
};

describe('Drafts, by ingredient', () => {
  let component: ReturnType<typeof mount> | null = null;

  async function open(routes: Parameters<typeof fakeApi>[0], width = 1100) {
    await page.viewport(width, 844);
    const requests = fakeApi({
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }],
      ...routes
    });
    component = mount(IngredientGroups, { target: document.body, props: { phone: width < 768 } });
    flushSync();
    return requests;
  }

  beforeEach(() => {
    network.reset();
    drafts.forget();
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('says how many ingredients are left and how many recipes are ready, with a bar', async () => {
    await open({ 'GET /recipes/drafts/by-ingredient': [200, GROUPS] });
    await expect.element(page.getByText('2 ingredients still to answer')).toBeVisible();
    await expect.element(page.getByText('· 3 recipes ready so far')).toBeVisible();
    await expect
      .element(page.getByRole('progressbar', { name: 'Recipes ready' }))
      .toHaveAttribute('aria-valuenow', '6');
    await expect.element(page.getByText('in 46 drafts')).toBeVisible();
  });

  it('opens the first group on a computer, with the suggestion chosen, and sends one answer', async () => {
    const requests = await open({
      'GET /recipes/drafts/by-ingredient': [200, GROUPS],
      'POST /recipes/drafts/by-ingredient/answer': [200, ANSWERED]
    });
    await expect.element(page.getByText('Used in 46 drafts, written as')).toBeVisible();
    await expect.element(page.getByText('Soy sauce', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Use for all 46 drafts' }).click();
    const sent = requests.find((r) => r.method === 'POST');
    expect(sent?.body).toEqual({ key: 'soya sauce', kind: 'ingredient', food_id: 9 });
    expect(sent?.headers['Idempotency-Key'] ?? sent?.headers['idempotency-key']).toBeTruthy();
    await vi.waitFor(() => {
      expect(toasts.current?.message).toBe(
        'Answered “soya sauce” in 46 drafts · 3 recipes moved to Recipes'
      );
      expect(toasts.current?.action?.label).toBe('Undo');
    });
  });

  it('a new ingredient is sent with its name and place; plain text with neither', async () => {
    const requests = await open({
      'GET /recipes/drafts/by-ingredient': [200, GROUPS],
      'POST /recipes/drafts/by-ingredient/answer': [200, ANSWERED]
    });
    await page.getByRole('button', { name: 'A new ingredient' }).click();
    await page.getByRole('button', { name: 'Fridge' }).click();
    await page.getByRole('button', { name: 'Use for all 46 drafts' }).click();
    expect(requests.find((r) => r.method === 'POST')?.body).toEqual({
      key: 'soya sauce',
      kind: 'new',
      name: 'Soya sauce',
      place_id: 1
    });
    await page.getByRole('button', { name: /Keep it as plain text/ }).click();
    await page.getByRole('button', { name: 'Use for all 1 draft' }).click();
    const posts = requests.filter((r) => r.method === 'POST');
    expect(posts[1]?.body).toEqual({ key: 'galangal', kind: 'text' });
  });

  it('a press again after a failed one sends the same change ID; another answer gets its own', async () => {
    let calls = 0;
    const requests = await open({
      'GET /recipes/drafts/by-ingredient': [200, GROUPS],
      'POST /recipes/drafts/by-ingredient/answer': () => {
        calls += 1;
        return calls === 1 ? [500, { detail: 'Something went wrong.' }] : [200, ANSWERED];
      }
    });
    const button = page.getByRole('button', { name: 'Use for all 46 drafts' });
    await button.click();
    await expect.element(button).toBeVisible();
    await vi.waitFor(() => expect(requests.filter((r) => r.method === 'POST')).toHaveLength(1));
    await button.click();
    await vi.waitFor(() => expect(requests.filter((r) => r.method === 'POST')).toHaveLength(2));
    const [first, second] = requests.filter((r) => r.method === 'POST');
    const key = (r?: { headers: Record<string, string> }) =>
      r?.headers['Idempotency-Key'] ?? r?.headers['idempotency-key'];
    expect(key(first)).toBeTruthy();
    expect(key(second)).toBe(key(first));
    // The next answer (another group, so another body) is a new change.
    await page.getByRole('button', { name: /Keep it as plain text/ }).click();
    await page.getByRole('button', { name: 'Use for all 1 draft' }).click();
    await vi.waitFor(() => expect(requests.filter((r) => r.method === 'POST')).toHaveLength(3));
    expect(key(requests.filter((r) => r.method === 'POST')[2])).not.toBe(key(first));
  });

  it('Skip for now sends nothing and opens the next ingredient', async () => {
    const requests = await open({ 'GET /recipes/drafts/by-ingredient': [200, GROUPS] });
    await page.getByRole('button', { name: 'Skip for now' }).click();
    await expect.element(page.getByRole('heading', { name: 'galangal' })).toBeVisible();
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(0);
  });

  it('Undo in the toast takes the answer back and fetches the list again', async () => {
    const requests = await open({
      'GET /recipes/drafts/by-ingredient': [200, GROUPS],
      'POST /recipes/drafts/by-ingredient/answer': [200, ANSWERED],
      'POST /changes/40/undo': [
        200,
        { result: 'done', message: 'Undone', change: changeOf(41, 'Undid') }
      ]
    });
    await page.getByRole('button', { name: 'Use for all 46 drafts' }).click();
    await vi.waitFor(() => expect(toasts.current?.action?.label).toBe('Undo'));
    toasts.current?.action?.run();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.method === 'POST' && r.path === '/changes/40/undo')).toBe(true)
    );
    await vi.waitFor(() =>
      expect(
        requests.filter((r) => r.path === '/recipes/drafts/by-ingredient').length
      ).toBeGreaterThan(2)
    );
  });

  it('Show all asks for more when the list is cut short', async () => {
    const requests = await open({
      'GET /recipes/drafts/by-ingredient': [200, { ...GROUPS, total: 300 }]
    });
    await page.getByRole('button', { name: 'Show all' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/recipes/drafts/by-ingredient?limit=5000')).toBe(true)
    );
  });

  it('says so when someone else already answered the group', async () => {
    await open({
      'GET /recipes/drafts/by-ingredient': [200, GROUPS],
      'POST /recipes/drafts/by-ingredient/answer': [404, { detail: 'No draft uses it.' }]
    });
    await page.getByRole('button', { name: 'Use for all 46 drafts' }).click();
    await expect
      .element(page.getByText('That ingredient was already answered. The list is up to date.'))
      .toBeVisible();
  });

  it('on a phone the list comes first, the answer is a page with a back button', async () => {
    await open(
      {
        'GET /recipes/drafts/by-ingredient': [200, GROUPS],
        'POST /recipes/drafts/by-ingredient/answer': [200, ANSWERED]
      },
      390
    );
    await expect.element(page.getByText('2 ingredients to answer · 3 recipes ready')).toBeVisible();
    await expect
      .element(page.getByRole('button', { name: 'Use for all 46' }))
      .not.toBeInTheDocument();
    await page.getByRole('button', { name: /soya sauce/ }).click();
    const answer = page.getByRole('button', { name: 'Use for all 46' });
    await expect.element(answer).toBeVisible();
    for (const button of [
      answer,
      page.getByRole('button', { name: 'Skip' }),
      page.getByRole('button', { name: 'Back to the list' })
    ]) {
      expect(button.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
    await page.getByRole('button', { name: 'Back to the list' }).click();
    await expect.element(page.getByText('2 ingredients to answer · 3 recipes ready')).toBeVisible();
  });

  it('offline the answer button is off', async () => {
    await open({ 'GET /recipes/drafts/by-ingredient': [200, GROUPS] });
    await expect.element(page.getByRole('button', { name: 'Use for all 46 drafts' })).toBeVisible();
    network.offline = true;
    flushSync();
    await expect
      .element(page.getByRole('button', { name: 'Use for all 46 drafts' }))
      .toBeDisabled();
  });

  it('shows an all-answered note when nothing is left', async () => {
    await open({
      'GET /recipes/drafts/by-ingredient': [200, { ...GROUPS, groups: [], total: 0, drafts: 0 }]
    });
    await expect.element(page.getByText('Every ingredient is answered')).toBeVisible();
  });
});
