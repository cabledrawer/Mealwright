// Import a recipe, the box (0.5 PR 3): the note "Recipe photos: not downloaded" under
// "How it works". It is shown only while the server has said photo downloads are off; while
// the answer is on its way, when it can't be had, and while the switch is on, there is no note.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { PrivacySwitches } from '#lib/client/privacy.js';
import { network } from '#lib/network.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { session } from '#lib/session.svelte.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { MOST_LINKS } from '#lib/importLinks.svelte.js';
import ImportPage from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const switches = (photos: boolean): [number, PrivacySwitches] => [
  200,
  {
    switches: [
      { connection: 'recipe_import', on: false },
      { connection: 'recipe_photos', on: photos }
    ],
    can_change: true
  }
];
const OWN = [200, { entries: [], limit: 100, can_change: true }] as [number, unknown];

const NOTE = /Recipe photos: not downloaded/;

describe('Import a recipe: the note about photos', () => {
  let component: ReturnType<typeof mount> | null = null;

  function open(routes: Parameters<typeof fakeApi>[0]) {
    fakeApi(routes);
    component = mount(ImportPage, { target: document.body });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    privacy.forget();
    session.me = { ...ME, role: 'admin' };
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    privacy.forget();
    vi.unstubAllGlobals();
  });

  it('says photos are not downloaded, and links to Settings › Outside connections, while the switch is off', async () => {
    open({ 'GET /privacy/switches': switches(false), 'GET /privacy/own-network': OWN });
    await expect.element(page.getByText(NOTE)).toBeVisible();
    expect(privacy.photosOff).toBe(true);
    await expect
      .element(page.getByRole('link', { name: 'Change in Settings › Outside connections' }))
      .toHaveAttribute('href', '/settings/privacy#outside-connections');
  });

  it('tells a member an admin can switch photos on, with no link to Settings', async () => {
    session.me = { ...ME, role: 'member' };
    open({ 'GET /privacy/switches': switches(false), 'GET /privacy/own-network': OWN });
    await expect
      .element(page.getByText(/An admin can switch them on in Settings › Outside connections/))
      .toBeVisible();
    expect(page.getByRole('link', { name: /Outside connections/ }).elements()).toEqual([]);
  });

  it('says nothing about photos while the switch is on', async () => {
    open({ 'GET /privacy/switches': switches(true), 'GET /privacy/own-network': OWN });
    await vi.waitUntil(() => privacy.loaded);
    flushSync();
    expect(privacy.photosOff).toBe(false);
    expect(document.body.textContent).not.toContain('Recipe photos');
  });

  it('says nothing while the answer has not come yet', async () => {
    vi.stubGlobal('fetch', () => new Promise(() => {}));
    component = mount(ImportPage, { target: document.body });
    flushSync();
    await expect.element(page.getByText('How it works')).toBeVisible();
    expect(privacy.loading).toBe(true);
    expect(privacy.photosOff).toBe(false);
    expect(document.body.textContent).not.toContain('Recipe photos');
  });

  it('says nothing when the answer could not be had', async () => {
    open({
      'GET /privacy/switches': [500, { detail: 'Something went wrong.' }],
      'GET /privacy/own-network': OWN
    });
    await vi.waitUntil(() => privacy.problem !== null);
    flushSync();
    expect(privacy.photosOff).toBe(false);
    expect(document.body.textContent).not.toContain('Recipe photos');
  });

  it('drops the note again if a later look fails, rather than keep an answer that may be old', async () => {
    open({ 'GET /privacy/switches': switches(false), 'GET /privacy/own-network': OWN });
    await expect.element(page.getByText(NOTE)).toBeVisible();
    fakeApi({ 'GET /privacy/switches': [500, { detail: 'Something went wrong.' }] });
    await privacy.load();
    flushSync();
    expect(privacy.photosOff).toBe(false);
    expect(document.body.textContent).not.toContain('Recipe photos');
  });
});

describe('Import a recipe: how many links can be pasted (F208)', () => {
  let component: ReturnType<typeof mount> | null = null;

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    privacy.forget();
    vi.unstubAllGlobals();
  });

  it('says the most links before anything is pasted, with the number the paste is cut at', async () => {
    await page.viewport(390, 844);
    network.reset();
    privacy.forget();
    fakeApi({ 'GET /privacy/switches': switches(true), 'GET /privacy/own-network': OWN });
    component = mount(ImportPage, { target: document.body });
    flushSync();
    const hint = page.getByText(/You can paste up to \d+ links at once/);
    await expect.element(hint).toBeVisible();
    expect(hint.element().textContent).toContain(`up to ${MOST_LINKS} links`);
    // The box points at it, so a screen reader hears it with the box.
    await expect
      .element(page.getByRole('textbox', { name: /Paste a link/ }))
      .toHaveAccessibleDescription(/You can paste up to/);
  });
});
