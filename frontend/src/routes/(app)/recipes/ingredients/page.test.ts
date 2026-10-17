import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import {
  PLACES,
  SHOPS,
  changeOf,
  fakeApi,
  rowOf,
  toorDal,
  type FakeRequest
} from '$lib/testing/fakeApi';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import Ingredients from './+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const dal = toorDal();
const sticks = toorDal({
  id: 40,
  name: 'Drumsticks (moringa)',
  other_names: [],
  counted_as: 'count',
  maybe_same: [{ id: 12, name: 'Drumsticks', merge_into: 12, merge_this: true }]
});

describe('the Ingredients page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
    requests = fakeApi({
      'GET /foods': (request) => {
        const q = new URLSearchParams(request.url.split('?')[1]).get('q');
        const foods = [rowOf(sticks), rowOf(dal)].filter(
          (f) => !q || f.name.toLowerCase().includes(q) || f.other_names.some((n) => n.includes(q))
        );
        return [
          200,
          {
            total: 2,
            counts: { all: 2, staples: 0, maybe_same: 2, maybe_same_pairs: 1 },
            foods,
            next: null
          }
        ];
      },
      'GET /foods/7': [200, dal],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      'POST /foods/40/merge': [
        200,
        {
          food: toorDal({ id: 12, name: 'Drumsticks' }),
          change: changeOf(950, 'Merged Drumsticks (moringa) into Drumsticks')
        }
      ]
    });
    component = mount(Ingredients, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('lists every food from the server, with its counts', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    await expect
      .element(page.getByText('2 foods · shared by recipes, pantry and shopping'))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Maybe the same · 1' })).toBeVisible();
  });

  it('searches by any name on the server', async () => {
    await page.getByRole('searchbox', { name: 'Search ingredients' }).fill('arhar');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?q=arhar&limit=50')).toBe(true)
    );
    await expect.element(page.getByRole('button', { name: /^Drumsticks/ })).not.toBeInTheDocument();
  });

  it('filters', async () => {
    await page.getByRole('button', { name: 'Staples' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?filter=staples&limit=50')).toBe(true)
    );
  });

  it('Merge on a Maybe-the-same row merges straight away, with Undo', async () => {
    await page.getByRole('button', { name: 'Merge', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/40/merge')?.body).toMatchObject({
        into_id: 12
      })
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Merged Drumsticks (moringa) into Drumsticks')
    );
    expect(toasts.current?.action?.label).toBe('Undo');
  });
});
