import { createRawSnippet, flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RecipeRow } from '#lib/client/recipes.js';
import { importLinks } from '#lib/importLinks.svelte.js';
import { WIPED } from '#lib/offline/otherTabs.js';
import { phoneDatabaseName } from '#lib/offline/phone.js';
import { recipePeek } from '#lib/recipePeek.js';
import { session } from '#lib/session.svelte.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import Layout from './+layout.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// Sam signs out in one tab. This tab, still open, must forget everything it held for him, so the
// next person who signs in here sees none of it (not his recipe row, not his import links).

const navigation = vi.hoisted(() => ({ goto: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => ({
  goto: navigation.goto,
  afterNavigate: () => {},
  beforeNavigate: () => {},
  onNavigate: () => {},
  invalidate: async () => {},
  invalidateAll: async () => {},
  preloadData: async () => {},
  preloadCode: async () => {},
  pushState: () => {},
  replaceState: () => {},
  disableScrollHandling: () => {}
}));

describe('another tab signing out', () => {
  const mounted: ReturnType<typeof mount>[] = [];

  beforeEach(async () => {
    freshPhone();
    session.me = { ...ME };
    vi.stubGlobal('fetch', () => new Promise<Response>(() => {}));
    vi.stubGlobal('EventSource', undefined);
    navigation.goto.mockClear();
  });

  afterEach(async () => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    recipePeek.forget();
    importLinks.forget();
    vi.unstubAllGlobals();
    await dropPhone();
  });

  it('clears the held recipe row and the import links, and goes to sign in', async () => {
    mounted.push(
      mount(Layout, {
        target: document.body.appendChild(document.createElement('div')),
        props: { children: createRawSnippet(() => ({ render: () => '<p>the page</p>' })) }
      })
    );
    flushSync();
    recipePeek.hold({ id: 123, name: 'Sam’s dal' } as unknown as RecipeRow);
    importLinks.rows = [{ link: 'https://example.com/a' } as never];
    expect(recipePeek.of(123)).not.toBeNull();

    window.dispatchEvent(
      new StorageEvent('storage', { key: WIPED, newValue: phoneDatabaseName() })
    );
    flushSync();

    expect(recipePeek.of(123)).toBeNull();
    expect(importLinks.rows).toEqual([]);
    expect(session.me).toBeNull();
    await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
  }, 30_000);
});
