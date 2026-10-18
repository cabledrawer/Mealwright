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
import { kitchen } from '$lib/freshness.svelte';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import NewIngredient from '$lib/components/NewIngredient.svelte';
import { newIngredient } from '$lib/newIngredient.svelte';
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
  let dialog: ReturnType<typeof mount> | null = null;
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
      'GET /foods/50': [200, toorDal({ id: 50, name: 'Tahini', counted_as: 'count' })],
      'POST /foods': [
        201,
        {
          food: toorDal({ id: 50, name: 'Tahini', counted_as: 'count' }),
          change: changeOf(960, 'Added Tahini')
        }
      ],
      'GET /changes?limit=10&area=ingredients': [
        200,
        {
          changes: [
            changeOf(961, 'Toor dal is now a staple'),
            { ...changeOf(960, 'Added Tahini'), can_undo: false, undone: { at: 'x', who: {} } },
            {
              ...changeOf(959, 'Merged Moong dal into Mung dal'),
              who: { login_id: 2, name: 'Wren' }
            }
          ],
          next: null
        }
      ],
      'POST /changes/961/undo': [
        200,
        {
          result: 'done',
          message: 'Undone.',
          change: changeOf(962, 'Undid: Toor dal is now a staple'),
          undone: changeOf(961, 'Toor dal is now a staple'),
          food: null,
          groups: [],
          brought_back: []
        }
      ],
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
    dialog = mount(NewIngredient, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    newIngredient.cancel();
    if (dialog) unmount(dialog);
    dialog = null;
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('lists every ingredient from the server, with its counts', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    await expect.element(page.getByText(/^2 ingredients · shared by/)).toBeVisible();
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

  it('New ingredient asks How do you count it?, makes it and opens it', async () => {
    requests.length = 0;
    await page.getByRole('button', { name: '+ New ingredient' }).click();
    await expect.element(page.getByRole('heading', { name: 'How do you count it?' })).toBeVisible();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tahini');
    await page.getByRole('radio', { name: /One by one/ }).click();
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body).toEqual({
        name: 'Tahini',
        staple: false,
        counted_as: 'count'
      })
    );
  });

  it('desktop: Recent changes sits beside the list, with Undo for what can be undone', async () => {
    await page.viewport(1300, 900);
    const recent = page.getByRole('region', { name: 'Recent changes' });
    await expect.element(recent.getByRole('listitem').first()).toBeVisible();
    expect(recent.getByRole('listitem').elements()).toHaveLength(3);
    // "Toor dal is now a staple" starts with the ingredient, so only the verbs are bold.
    expect(recent.getByRole('listitem').first().element().querySelector('b')).toBeNull();
    await expect.element(recent.getByText('Added', { exact: true })).toBeVisible();
    await expect.element(recent.getByText('· Wren')).toBeVisible();
    // No button on desktop; the panel is always there.
    expect(page.getByRole('button', { name: 'Recent changes' }).elements()).toHaveLength(0);
    // Undone already, so no Undo; the others have one.
    expect(recent.getByRole('button', { name: 'Undo: Added Tahini' }).elements()).toHaveLength(0);
    await recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/961/undo')).toBe(true));
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Undone: Toor dal is now a staple')
    );
    // And the list is fetched again, as after any change.
    const asked = () => requests.filter((r) => r.path === '/changes').length;
    await vi.waitFor(() => expect(asked()).toBeGreaterThan(1));
  });

  it('desktop: Undo that the server refuses puts Undo back and says why', async () => {
    await page.viewport(1300, 900);
    fakeApi({
      'GET /changes?limit=10&area=ingredients': [
        200,
        { changes: [changeOf(961, 'Toor dal is now a staple')], next: null }
      ],
      'POST /changes/961/undo': [
        409,
        { detail: 'That is too old to undo.', code: 'too_old', title: 'Too old' }
      ]
    });
    kitchen.changed();
    const recent = page.getByRole('region', { name: 'Recent changes' });
    await recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() => expect(toasts.current?.tone).toBe('problem'));
    await expect
      .element(recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }))
      .toBeVisible();
  });

  it('phone: a Recent changes button opens a sheet with the same list', async () => {
    await page.viewport(390, 900);
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
    await page.getByRole('button', { name: 'Recent changes' }).click();
    const sheet = page.getByRole('dialog', { name: 'Recent changes' });
    expect(sheet.getByRole('listitem').elements()).toHaveLength(3);
    await sheet.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Undone: Toor dal is now a staple')
    );
    await sheet.getByRole('button', { name: 'Close' }).click();
    await vi.waitFor(() =>
      expect(
        [...document.querySelectorAll('dialog')].find(
          (d) => d.querySelector('h2')?.textContent === 'Recent changes'
        )?.open
      ).toBe(false)
    );
  });

  it('Recent changes is fetched again when something changed', async () => {
    const asked = () => requests.filter((r) => r.path === '/changes').length;
    const before = asked();
    kitchen.changed();
    await vi.waitFor(() => expect(asked()).toBeGreaterThan(before));
  });
});
