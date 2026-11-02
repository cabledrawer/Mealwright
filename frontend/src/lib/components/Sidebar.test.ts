import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
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
    expect(VERSION_WORDS).toMatch(/^Mealwright \d+\.\d+\.\d+/);
    expect(document.querySelector('.settings .cog')).not.toBeNull();
  });
});
