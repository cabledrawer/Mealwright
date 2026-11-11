import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { batchCook } from '#lib/batchCook.svelte.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { VERSION_WORDS } from '#lib/version.js';
import Sidebar from './Sidebar.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const brief = (id: number) => ({
  id,
  name: `Draft ${id}`,
  source: { kind: 'text', site: null },
  started_by: 'Wren',
  started_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  expires_at: '2026-11-06T10:00:00Z',
  days_left: 13,
  lines_total: 3,
  lines_checked: 1
});

describe('the sidebar’s Drafts entry', () => {
  let component: ReturnType<typeof mount> | null = null;

  async function open(routes: Parameters<typeof fakeApi>[0]) {
    await page.viewport(1280, 800);
    fakeApi(routes);
    component = mount(Sidebar, { target: document.body });
    flushSync();
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

  it('is under Recipes after Import and before Ingredients, with how many drafts there are', async () => {
    await open({
      'GET /recipes/drafts': [200, { drafts: [brief(1), brief(2), brief(3)], count: 3 }]
    });
    const tree = page.getByRole('group', { name: 'Recipes' });
    await expect.element(tree).toBeVisible();
    await expect.element(page.getByRole('link', { name: 'Drafts 3' })).toBeVisible();
    expect(
      tree
        .getByRole('link')
        .elements()
        .map((link) => link.textContent?.replace(/\s+/g, ' ').trim())
    ).toEqual(['All recipes', 'Import', 'Drafts3', 'Ingredients']);
    await expect
      .element(page.getByRole('link', { name: 'Drafts 3' }))
      .toHaveAttribute('href', '/recipes/drafts');
  });

  it('shows no number with no drafts, or when the server can’t say', async () => {
    await open({ 'GET /recipes/drafts': [200, { drafts: [], count: 0 }] });
    await expect.element(page.getByRole('link', { name: 'Drafts', exact: true })).toBeVisible();
    unmount(component!);
    document.body.innerHTML = '';
    drafts.forget();
    await open({ 'GET /recipes/drafts': [500, { detail: 'No.' }] });
    await expect.element(page.getByRole('link', { name: 'Drafts', exact: true })).toBeVisible();
  });

  it('has Import as its own item, linking to the import page (F113)', async () => {
    await open({ 'GET /recipes/drafts': [200, { drafts: [], count: 0 }] });
    await expect
      .element(page.getByRole('group', { name: 'Recipes' }).getByRole('link', { name: 'Import' }))
      .toHaveAttribute('href', '/recipes/import');
  });

  it('shows the build’s own version as small text at the foot, and a cog by the name (N1, F2)', async () => {
    await open({ 'GET /recipes/drafts': [200, { drafts: [], count: 0 }] });
    await expect.element(page.getByText(VERSION_WORDS)).toBeVisible();
    expect(VERSION_WORDS).toMatch(/^Mealwright v\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?$/);
    expect(document.querySelector('.settings .cog')).not.toBeNull();
  });
});

describe('the sidebar’s Batch cook entry (B2)', () => {
  let component: ReturnType<typeof mount> | null = null;

  async function open(batch_cook: boolean) {
    await page.viewport(1280, 800);
    fakeApi({
      'GET /household': [200, { batch_cook }],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    component = mount(Sidebar, { target: document.body });
    flushSync();
  }

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    batchCook.shown = true;
    batchCook.known = false;
  });

  it('is after Plan, with the Experimental flask', async () => {
    await open(true);
    const links = [...document.querySelectorAll('nav[aria-label="Main"] > a')].map((a) =>
      (a.textContent ?? '').replace(/\s+/g, ' ').trim()
    );
    expect(links.slice(0, 4)).toEqual(['Today', 'Plan', 'Batch cook Experimental', 'Shopping']);
    const link = document.querySelector<HTMLAnchorElement>('a[href$="/batch-cook"]')!;
    expect(link.querySelector('.flask')).not.toBeNull();
  });

  it('is gone when an admin has hidden it', async () => {
    await open(false);
    await vi.waitFor(() => expect(document.querySelector('a[href$="/batch-cook"]')).toBeNull());
    expect(batchCook.known).toBe(true);
  });
});
