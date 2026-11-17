// Settings: the "Finish setup" row (cabledrawer 12 Nov: an admin who didn't finish set-up is not sent
// back to it; Settings shows the row until it is done), on the phone's list and the computer's.

import { createRawSnippet, flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { session } from '#lib/session.svelte.js';
import { updates } from '#lib/updates.svelte.js';
import { fakeApi, PLACES, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Layout from './+layout.svelte';
import Settings from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
const route = vi.hoisted(() => ({ url: new URL('http://localhost/settings') }));
vi.mock('$app/state', () => ({ page: route }));

const WORDS = 'A few quick things: amounts, household, shops.';
let mounted: ReturnType<typeof mount>[] = [];
let requests: FakeRequest[] = [];

// The row that is on screen (the other list is hidden at this width).
const finishRow = () =>
  [...document.querySelectorAll('a[href*="onboarding"]')].find(
    (a) => a.getClientRects().length > 0
  )!;

/** The household has been read and the page has had time to draw what it said. */
async function householdRead() {
  await vi.waitFor(() => expect(requests.some((r) => r.path.endsWith('/household'))).toBe(true));
  await new Promise((done) => setTimeout(done, 300));
}

function open(
  done: boolean,
  role: 'admin' | 'member' = 'admin',
  counts: { people: number; shops: number } = { people: 1, shops: 0 }
) {
  session.me = { ...ME, role };
  requests = fakeApi({
    'GET /household': [200, { name: 'Home', pints: 'uk', onboarding_done: done }],
    'GET /household/kitchen': [
      200,
      { hob_rings: 4, pressure_cookers: 1, oven: true, asked: false }
    ],
    'GET /meal-slots': [200, []],
    'GET /shops': [
      200,
      Array.from({ length: counts.shops }, (_, i) => ({ id: i + 1, name: `Shop ${i + 1}` }))
    ],
    'GET /places': [200, PLACES],
    'GET /changes': [200, { changes: [], next: null }],
    'GET /people': [
      200,
      {
        people: Array.from({ length: counts.people }, (_, i) => ({ id: i + 1 })),
        can_change: true,
        ask_whos_this: false
      }
    ]
  });
  // The list beside the page (the computer's) and the page that is the phone's list; each is hidden
  // at the other's width.
  const children = createRawSnippet(() => ({ render: () => '<div></div>' }));
  mounted = [
    mount(Layout, {
      target: document.body.appendChild(document.createElement('div')),
      props: { children }
    }),
    mount(Settings, { target: document.body.appendChild(document.createElement('div')) })
  ];
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
  for (const component of mounted.splice(0)) unmount(component);
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
      await expect.element(row.getByText(WORDS)).toBeVisible();
    });

    it('draws a part-filled amber ring and "N of 5" from what is done, not a tick (cabledrawer 13 Nov)', async () => {
      open(false, 'admin', { people: 2, shops: 1 });
      const row = page.getByRole('link', { name: /Finish setup/ });
      await expect.element(row).toBeVisible();
      await vi.waitFor(() => expect(finishRow().textContent).toContain('3 of 5'));
      const svg = finishRow().querySelector('svg')!;
      expect(svg.getAttribute('aria-hidden')).toBe('true');
      expect(svg.getAttribute('data-ring')).toBe('part');
      expect(svg.querySelectorAll('circle')).toHaveLength(1);
      // The arc, and no tick: one path, an arc that starts at the top.
      const paths = [...svg.querySelectorAll('path')];
      expect(paths).toHaveLength(1);
      expect(paths[0]!.getAttribute('d')).toMatch(/^M12 3\.5A8\.5 8\.5 0 /);
      expect(document.body.innerHTML).not.toContain('M8 12.5l3 3 5-6');
    });

    it('says 1 of 5 when only the account is there, and the ring follows the count', async () => {
      open(false, 'admin', { people: 1, shops: 0 });
      await vi.waitFor(() => expect(finishRow().textContent).toContain('1 of 5'));
      const arc = finishRow().querySelector('svg path')!.getAttribute('d');
      expect(arc).toBe('M12 3.5A8.5 8.5 0 0 1 20.08 9.37');
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
