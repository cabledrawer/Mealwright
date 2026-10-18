import { flushSync, mount, unmount, type Component } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '$lib/network.svelte';
import { session } from '$lib/session.svelte';
import { ME } from '$lib/testing/fakeShopping';
import Ingredients from './recipes/ingredients/+page.svelte';
import Pantry from './pantry/+page.svelte';
import Settings from './settings/+page.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

// Pantry, Ingredients and Settings need the server in 0.3 (spec section 6, "Opening the app
// offline", cabledrawer 18 Oct): offline they say so and point to Shopping.

describe('the online-only screens, offline', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let asked: string[];

  function show(screen: Component) {
    const target = document.body.appendChild(document.createElement('div'));
    mounted.push(mount(screen, { target }));
    flushSync();
  }

  beforeEach(() => {
    asked = [];
    vi.stubGlobal('fetch', (input: string) => {
      asked.push(String(input));
      return Promise.reject(new TypeError('Failed to fetch'));
    });
    session.me = { ...ME };
    network.offline = true;
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  for (const [name, screen] of [
    ['Pantry', Pantry],
    ['Ingredients', Ingredients],
    ['Settings', Settings]
  ] as const) {
    it(`${name} says it needs the server, with a Shopping button`, async () => {
      show(screen);
      await expect.element(page.getByRole('heading', { name: "You're offline." })).toBeVisible();
      await expect
        .element(
          page.getByText(`${name} needs your Mealwright server — your shopping list works offline.`)
        )
        .toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Shopping' }))
        .toHaveAttribute('href', '/shopping');
    });
  }

  it('Settings still lets you sign out, and hides what needs the server', async () => {
    show(Settings);
    await expect.element(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
    expect(page.getByRole('heading', { name: 'Appearance' }).elements()).toEqual([]);
  });

  it('Pantry fetches again once the connection is back', async () => {
    show(Pantry);
    await expect.element(page.getByRole('heading', { name: "You're offline." })).toBeVisible();
    const before = asked.length;
    network.offline = false;
    flushSync();
    await vi.waitFor(() => expect(asked.length).toBeGreaterThan(before));
    expect(asked.slice(before).some((url) => url.startsWith('/api/v1/pantry'))).toBe(true);
  });
});
