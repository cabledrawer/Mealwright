// Settings: the "Finish setup" row (cabledrawer 12 Nov: an admin who didn't finish set-up is not sent
// back to it; Settings shows the row until it is done), on the phone's list and the computer's.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { session } from '#lib/session.svelte.js';
import { updates } from '#lib/updates.svelte.js';
import { fakeApi, PLACES, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Settings from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
const route = vi.hoisted(() => ({ url: new URL('http://localhost/settings') }));
vi.mock('$app/state', () => ({ page: route }));

const WORDS = 'A few quick things: amounts, household, shops.';
let mounted: ReturnType<typeof mount> | null = null;
let requests: FakeRequest[] = [];

/** The household has been read and the page has had time to draw what it said. */
async function householdRead() {
  await vi.waitFor(() => expect(requests.some((r) => r.path.endsWith('/household'))).toBe(true));
  await new Promise((done) => setTimeout(done, 300));
}

function open(done: boolean, role: 'admin' | 'member' = 'admin') {
  session.me = { ...ME, role };
  requests = fakeApi({
    'GET /household': [200, { name: 'Home', pints: 'uk', onboarding_done: done }],
    'GET /household/kitchen': [
      200,
      { hob_rings: 4, pressure_cookers: 1, oven: true, asked: false }
    ],
    'GET /meal-slots': [200, []],
    'GET /shops': [200, []],
    'GET /places': [200, PLACES],
    'GET /changes': [200, { changes: [], next: null }],
    'GET /people': [200, { people: [{ id: 1 }], can_change: true, ask_whos_this: false }]
  });
  mounted = mount(Settings, { target: document.body.appendChild(document.createElement('div')) });
  flushSync();
}

beforeEach(() => {
  route.url = new URL('http://localhost/settings');
  network.reset();
  placesAndShops.forget();
  privacy.forget();
  updates.forget();
});

afterEach(() => {
  if (mounted) unmount(mounted);
  mounted = null;
  document.body.innerHTML = '';
  network.reset();
});

for (const [name, width] of [
  ['phone', 428],
  ['computer', 1300]
] as const) {
  describe(`on the ${name}`, () => {
    beforeEach(async () => {
      await page.viewport(width, 900);
    });

    it('shows Finish setup to an admin until set-up is done, opening onboarding', async () => {
      open(false);
      const row = page.getByRole('link', { name: /Finish setup/ });
      await expect.element(row).toBeVisible();
      await expect.element(row).toHaveAttribute('href', expect.stringContaining('/onboarding'));
      await expect.element(page.getByText(WORDS)).toBeVisible();
    });

    it('is gone once set-up is done', async () => {
      open(true);
      await householdRead();
      expect(document.body.textContent).not.toContain('Finish setup');
    });

    it('is never shown to a member', async () => {
      open(false, 'member');
      await householdRead();
      expect(document.body.textContent).not.toContain('Finish setup');
    });
  });
}
