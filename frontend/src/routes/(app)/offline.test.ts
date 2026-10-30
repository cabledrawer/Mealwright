import { flushSync, mount, unmount, type Component } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { addToPantry } from '#lib/addToPantry.svelte.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Ingredients from './recipes/ingredients/+page.svelte';
import Today from './+page.svelte';
import Plan from './plan/+page.svelte';
import Pantry from './pantry/+page.svelte';
import Recipes from './recipes/+page.svelte';
import Settings from './settings/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

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
    network.deviceOffline = true;
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
    ['Recipes', Recipes],
    ['Settings', Settings]
  ] as const) {
    it(`${name} says it needs the server, with a Shopping button`, async () => {
      show(screen);
      await expect.element(page.getByRole('heading', { name: 'You’re offline.' })).toBeVisible();
      await expect
        .element(
          page.getByText(`${name} needs your Mealwright server. Your shopping list works offline.`)
        )
        .toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Shopping' }))
        .toHaveAttribute('href', '/shopping');
    });
  }

  it('Settings still lets you sign out and change the theme (phone)', async () => {
    await page.viewport(390, 800);
    show(Settings);
    await expect.element(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
    // cabledrawer 18 Oct, "Keep it visible": the theme is saved on this device.
    await expect.element(page.getByRole('heading', { name: 'Appearance' })).toBeVisible();
    const switcher = page.getByRole('group', { name: 'Theme' });
    const dark = switcher.getByRole('button', { name: 'Dark' });
    await dark.click();
    await expect.element(dark).toHaveAttribute('aria-pressed', 'true');
    expect(document.documentElement.dataset.theme).toBe('dark');
    // Saved on this device; nothing needs the server.
    expect(localStorage.getItem('mealwright.theme')).toBe('dark');
    await switcher.getByRole('button', { name: 'Auto' }).click();
  });

  // cabledrawer 18 Oct: keep the button visible; a tap explains instead of opening the sheet.
  const NEEDS_SERVER =
    'Adding to the pantry needs your Mealwright server. Try again when you’re back online.';

  for (const [layout, width, name] of [
    ['phone', 390, 'Add to pantry'],
    ['desktop', 1280, '+ Add to pantry']
  ] as const) {
    it(`${layout}: “${name}” stays offline; a tap says it needs the server and opens no sheet`, async () => {
      await page.viewport(width, 800);
      toasts.dismiss();
      addToPantry.close();
      show(Pantry);
      await expect.element(page.getByRole('heading', { name: 'You’re offline.' })).toBeVisible();
      const button = page.getByRole('button', { name, exact: true });
      await expect.element(button).toBeVisible();
      await expect.element(button).toBeEnabled();
      const askedBefore = asked.length;
      await button.click();
      expect(toasts.current?.message).toBe(NEEDS_SERVER);
      // Nothing was sent: the tap only explains.
      expect(asked.slice(askedBefore)).toEqual([]);
      expect(addToPantry.open).toBe(false);
      expect(page.getByRole('dialog', { name: 'Add to pantry' }).elements()).toEqual([]);
      addToPantry.close();
      toasts.dismiss();
    });
  }

  it('Pantry fetches again once the connection is back', async () => {
    show(Pantry);
    await expect.element(page.getByRole('heading', { name: 'You’re offline.' })).toBeVisible();
    const before = asked.length;
    // An answer from the server: the bar and the failure both clear.
    network.succeeded();
    flushSync();
    await vi.waitFor(() => expect(asked.length).toBeGreaterThan(before));
    expect(asked.slice(before).some((url) => url.startsWith('/api/v1/pantry'))).toBe(true);
  });
});

// The server down behind the reverse proxy, the device's network fine (F67, cabledrawer 30 Oct):
// "One steady message from the start, chosen by the cause … Same wording on every page, and
// it stays until things change." No "Couldn't load" or plain-text line first, and no change of
// words when the bar comes 3 seconds later.
describe('the online-only screens, server down', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  beforeEach(async () => {
    // The phone: All recipes is a page of its own there (desktop: the layout's panes).
    await page.viewport(390, 800);
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('', { status: 502 })));
    session.me = { ...ME };
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  for (const [name, screen] of [
    ['Today', Today],
    ['Plan', Plan],
    ['Pantry', Pantry],
    ['Ingredients', Ingredients],
    ['Recipes', Recipes],
    ['Settings', Settings]
  ] as const) {
    it(`${name}: “Can’t reach your Mealwright server.” from the start, the same once the bar shows`, async () => {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(screen, { target }));
      flushSync();
      const title = page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' });
      const body = page.getByText(
        `${name} comes back by itself when the server answers. Your shopping list works offline.`
      );
      await expect.element(title).toBeVisible();
      // Before the bar: the note is already the steady one.
      expect(network.offline).toBe(false);
      await expect.element(body).toBeVisible();
      await expect.poll(() => network.offline, { timeout: 6000 }).toBe(true);
      await expect.element(title).toBeVisible();
      await expect.element(body).toBeVisible();
      expect(document.body.textContent).not.toMatch(/You’re offline|Couldn’t load|Try again\./);
    });
  }
});

// Something else answers before the bar's 3 s (the live stream's hello): the page fetches
// again by itself, rather than keep its note while the server answers (F67 review 2).
describe('the online-only screens, back before the bar', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  for (const [name, screen] of [
    ['Today', Today],
    ['Plan', Plan],
    ['Pantry', Pantry],
    ['Recipes', Recipes]
  ] as const) {
    it(`${name} fetches again when the server answers, with no bar`, async () => {
      await page.viewport(390, 800);
      vi.stubGlobal('fetch', () => Promise.resolve(new Response('', { status: 502 })));
      session.me = { ...ME };
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(screen, { target }));
      flushSync();
      await expect
        .element(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' }))
        .toBeVisible();
      const asked: string[] = [];
      vi.stubGlobal('fetch', (input: string) => {
        asked.push(String(input));
        return Promise.reject(new TypeError('Failed to fetch'));
      });
      network.succeeded();
      flushSync();
      expect(network.offline).toBe(false);
      await vi.waitFor(() => expect(asked.length).toBeGreaterThan(0));
    });
  }
});
