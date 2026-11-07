import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { starterPacks } from '#lib/starterPacks.svelte.js';
import StarterPacks from './StarterPacks.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

const item = (key: string, name: string, extra: object = {}) => ({
  key,
  name,
  already_have: false,
  have_as: null,
  staple: false,
  ...extra
});

const PACKS = {
  packs: [
    {
      id: 'indian',
      name: 'Indian',
      already_have: 1,
      items: [
        item('toor_dal', 'toor dal', { already_have: true, have_as: 'Thuvaram paruppu' }),
        item('ghee', 'ghee'),
        item('turmeric', 'turmeric'),
        item('poha', 'poha')
      ]
    },
    {
      id: 'household',
      name: 'Household',
      already_have: 0,
      items: [item('salt', 'salt', { staple: true })]
    }
  ]
};

let component: ReturnType<typeof mount> | null = null;
let posts: { url: string; body: unknown; key: string | null }[] = [];

beforeEach(() => {
  posts = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    if (url === '/api/v1/starter-packs') return json(PACKS);
    if (url === '/api/v1/starter-packs/indian/add' && init.method === 'POST') {
      posts.push({
        url,
        body: JSON.parse(String(init.body)),
        key: new Headers(init.headers).get('idempotency-key')
      });
      return json(
        {
          added: 2,
          skipped: 1,
          change: {
            id: 9,
            kind: 'food_created',
            summary: 'Added the Indian starter pack: 2 ingredients',
            can_undo: true
          }
        },
        201
      );
    }
    return new Response('{}', { status: 404 });
  });
  component = mount(StarterPacks, { target: document.body });
  flushSync();
});

afterEach(() => {
  starterPacks.close();
  if (component) unmount(component);
  component = null;
  network.offline = false;
  vi.unstubAllGlobals();
});

describe('Add a starter pack', () => {
  it('lists the packs, then a pack with every ingredient ticked and Already have rows left out', async () => {
    starterPacks.show();
    await page.getByRole('button', { name: /^Indian/ }).click();
    await expect.element(page.getByRole('heading', { name: 'Indian starter pack' })).toBeVisible();
    for (const name of ['ghee', 'turmeric', 'poha']) {
      await expect.element(page.getByRole('checkbox', { name })).toBeChecked();
    }
    const had = page.getByRole('checkbox', { name: /toor dal/ });
    await expect.element(had).toBeDisabled();
    await expect.element(had).not.toBeChecked();
    await expect.element(page.getByText('Already have as “Thuvaram paruppu”')).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Add 3 ingredients' })).toBeEnabled();
  });

  it('unticking one changes the count; Add sends just the ticked ones', async () => {
    starterPacks.show();
    await page.getByRole('button', { name: /^Indian/ }).click();
    await page.getByRole('checkbox', { name: 'poha' }).click();
    await expect.element(page.getByRole('button', { name: 'Add 2 ingredients' })).toBeVisible();
    await page.getByRole('button', { name: 'Add 2 ingredients' }).click();
    await vi.waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.body).toEqual({ keys: ['ghee', 'turmeric'] });
    expect(posts[0]!.key).toBeTruthy();
    expect(starterPacks.open).toBe(false);
  });

  it('Untick all turns Add off until something is ticked again', async () => {
    starterPacks.show();
    await page.getByRole('button', { name: /^Indian/ }).click();
    await page.getByRole('button', { name: 'Untick all' }).click();
    await expect.element(page.getByRole('button', { name: 'Add 0 ingredients' })).toBeDisabled();
    await page.getByRole('button', { name: 'Tick all' }).click();
    await expect.element(page.getByRole('button', { name: 'Add 3 ingredients' })).toBeEnabled();
  });

  it('the Household pack says its ingredients are not counted', async () => {
    starterPacks.show();
    await page.getByRole('button', { name: /^Household/ }).click();
    await expect.element(page.getByText(/Don’t count it/)).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Add 1 ingredient' })).toBeVisible();
  });

  it('with the server down Add is off and says why', async () => {
    starterPacks.show();
    await page.getByRole('button', { name: /^Indian/ }).click();
    network.offline = true;
    await expect.element(page.getByRole('button', { name: 'Add 3 ingredients' })).toBeDisabled();
  });
});
