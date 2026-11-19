import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page as view } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { sidebar, SIDEBAR_STORAGE_KEY } from '#lib/sidebar.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import Sidebar from './Sidebar.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

const route = vi.hoisted(() => ({ url: new URL('http://localhost/settings/amounts') }));
vi.mock('$app/state', () => ({ page: route }));

describe('the main menu in Settings (Q3, cabledrawer 18 Nov)', () => {
  let component: ReturnType<typeof mount> | null = null;

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    sidebar.set(false);
  });

  it('"Show the menu" is a button that unfolds the menu in place, and folds it again, without touching the saved choice', async () => {
    await view.viewport(1280, 800);
    fakeApi({ 'GET /recipes/drafts': [200, { drafts: [], count: 0 }] });
    component = mount(Sidebar, { target: document.body });
    flushSync();
    const toggle = view.getByRole('button', { name: 'Show the menu' });
    await expect.element(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(view.getByText('Mealwright', { exact: true }).elements()).toHaveLength(0);

    await toggle.click();
    const fold = view.getByRole('button', { name: 'Collapse sidebar' });
    await expect.element(fold).toHaveAttribute('aria-expanded', 'true');
    await expect.element(view.getByText('Mealwright', { exact: true })).toBeVisible();
    expect(view.getByRole('link', { name: 'Today', exact: true }).element().textContent).toContain(
      'Today'
    );
    expect(route.url.pathname).toBe('/settings/amounts');

    await fold.click();
    await expect
      .element(view.getByRole('button', { name: 'Show the menu' }))
      .toHaveAttribute('aria-expanded', 'false');
    expect(sidebar.collapsed).toBe(false);
    expect(localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();
  });
});
