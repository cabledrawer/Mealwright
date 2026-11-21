// Settings' list (F252; mockups Dark-Settings2-Desktop and -Phone): the grouped list beside the page
// on a computer, the same list as the phone's /settings page, the Household group for admins only,
// "Only an admin can change this." for a member who opens an address in it, and older links.

import { createRawSnippet, flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { goto } from '$app/navigation';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { session } from '#lib/session.svelte.js';
import { updates } from '#lib/updates.svelte.js';
import { fakeApi, PLACES, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Layout from './+layout.svelte';
import { settingsKnown } from './finishSetup.svelte.js';
import Settings from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));
const route = vi.hoisted(() => ({
  url: new URL('http://localhost/settings'),
  route: { id: '/(app)/settings' as string | null }
}));
vi.mock('$app/state', () => ({ page: route }));

const GROUP_NAMES = ['Your settings', 'Kitchen settings', 'Household settings', 'Mealwright'];
const mounted: ReturnType<typeof mount>[] = [];
let requests: FakeRequest[] = [];

/** The list beside the page: the layout, with a stand-in for the page. */
function openLayout(
  at: string,
  role: 'admin' | 'member',
  more: Record<string, [number, unknown]> = {},
  routeId: string = `/(app)${at.replace(/\/\d+$/, '/[id]')}`
) {
  route.url = new URL(`http://localhost${at}`);
  route.route = { id: routeId };
  session.me = { ...ME, role };
  requests = fakeApi({
    'GET /household': [200, { name: 'Home', pints: 'uk', onboarding_done: true }],
    ...more
  });
  const children = createRawSnippet(() => ({
    render: () => '<p data-testid="the-page">The page itself</p>'
  }));
  mounted.push(
    mount(Layout, {
      target: document.body.appendChild(document.createElement('div')),
      props: { children }
    })
  );
  flushSync();
}

/** The phone's /settings page, with the values its rows show. */
async function openPhoneList(role: 'admin' | 'member', at = '/settings') {
  route.url = new URL(`http://localhost${at}`);
  session.me = { ...ME, role };
  requests = fakeApi({
    'GET /household': [200, { name: 'Home', pints: 'us', onboarding_done: true }],
    'GET /household/kitchen': [
      200,
      { hob_rings: 4, pressure_cookers: 1, oven: true, asked: false }
    ],
    'GET /meal-slots': [
      200,
      {
        meal_slots: [
          { id: 1, name: 'Breakfast', enabled: true },
          { id: 2, name: 'Dinner', enabled: true },
          { id: 3, name: 'Snack', enabled: false }
        ]
      }
    ],
    'GET /shops': [200, { shops: [{ id: 1, name: 'Shop' }] }],
    'GET /places': [200, { places: PLACES }],
    'GET /people': [
      200,
      { people: [{ id: 1 }, { id: 2 }], can_change: true, ask_whos_this: false }
    ],
    'GET /privacy': [200, { switches: {}, can_change: true }],
    'GET /privacy/own-network': [200, { entries: [], can_change: true }]
  });
  // The layout reads the household for the page; the page alone is mounted here.
  settingsKnown.forget();
  await settingsKnown.load(role === 'admin');
  mounted.push(
    mount(Settings, { target: document.body.appendChild(document.createElement('div')) })
  );
  flushSync();
}

beforeEach(async () => {
  vi.mocked(goto).mockClear();
  network.reset();
  placesAndShops.forget();
  privacy.forget();
  updates.forget();
  await page.viewport(1300, 900);
});

afterEach(() => {
  for (const component of mounted.splice(0)) unmount(component);
  document.body.innerHTML = '';
  network.reset();
});

const list = () => page.getByRole('navigation', { name: 'Settings' });

describe('/settings on a computer', () => {
  it('goes to Appearance without reading any row values', async () => {
    await openPhoneList('admin');
    await vi.waitFor(() => expect(goto).toHaveBeenCalled());
    // Only the household's own settings (read to set up the test) may be asked; every row's
    // read ("/meal-slots", "/shops", "/places", "/people", "/privacy/...", "/updates", the
    // kitchen) is caught by prefix.
    const asked = requests.map((r) => r.path).filter((path) => path !== '/household');
    expect(asked).toEqual([]);
  });
});

describe('the list beside the page (computer)', () => {
  it('shows an admin the four groups and every item, the open one marked', async () => {
    openLayout('/settings/shops-places', 'admin');
    for (const name of GROUP_NAMES)
      await expect.element(list().getByRole('group', { name })).toBeVisible();
    for (const item of [
      'Appearance',
      'Amounts',
      'Your sign-in',
      'Meal slots',
      'Shops & places',
      'Your kitchen',
      'People',
      'Sign-in for everyone',
      'API tokens',
      'Outside connections',
      'Backups & your data',
      'Recent changes',
      'About'
    ])
      await expect.element(list().getByRole('link', { name: item })).toBeVisible();
    await expect
      .element(list().getByRole('link', { name: 'Shops & places' }))
      .toHaveAttribute('aria-current', 'page');
    await expect
      .element(list().getByRole('link', { name: 'Appearance' }))
      .not.toHaveAttribute('aria-current');
    await expect.element(page.getByTestId('the-page')).toBeVisible();
  });

  it('marks the item that an address under it belongs to', async () => {
    openLayout('/settings/people/7', 'admin');
    await expect
      .element(list().getByRole('link', { name: 'People' }))
      .toHaveAttribute('aria-current', 'page');
  });

  it('hides the Household group, and Meal slots, from a member', async () => {
    openLayout('/settings/appearance', 'member');
    await expect.element(list().getByRole('link', { name: 'Appearance' })).toBeVisible();
    await expect.element(list().getByRole('link', { name: 'Shops & places' })).toBeVisible();
    for (const hidden of [
      'People',
      'Sign-in for everyone',
      'API tokens',
      'Outside connections',
      'Backups & your data',
      'Meal slots'
    ])
      expect(list().getByRole('link', { name: hidden }).elements()).toEqual([]);
    expect(list().getByRole('group', { name: 'Household settings' }).elements()).toEqual([]);
    expect(document.body.textContent).not.toContain('admins only');
  });

  it('says "admins only" by the Household group for an admin', async () => {
    openLayout('/settings/appearance', 'admin');
    await expect.element(list().getByText('admins only')).toBeVisible();
  });

  it('shows a member who opens a Household address "Only an admin can change this.", not the page', async () => {
    for (const at of [
      '/settings/people',
      '/settings/people/3',
      // The old addresses too, while they send the person on (FE25).
      '/settings/household',
      '/settings/household/3',
      '/settings/sign-in-everyone',
      '/settings/sso',
      '/settings/api-tokens',
      '/settings/outside-connections',
      '/settings/privacy',
      '/settings/your-data',
      '/settings/your-data/restore',
      '/settings/meal-slots'
    ]) {
      openLayout(at, 'member');
      await expect.element(page.getByText('Only an admin can change this.')).toBeVisible();
      expect(page.getByTestId('the-page').elements(), at).toEqual([]);
      for (const component of mounted.splice(0)) unmount(component);
      document.body.innerHTML = '';
    }
    // The layout asked for nothing of the Household group's data.
    expect(requests.some((r) => /people|privacy|api-tokens|sso|backups/.test(r.path))).toBe(false);
  });

  it('still refuses a member an address spelt with percent-codes (the page, not the text, decides)', async () => {
    openLayout('/settings/%70eople', 'member', {}, '/(app)/settings/people');
    await expect.element(page.getByText('Only an admin can change this.')).toBeVisible();
    expect(page.getByTestId('the-page').elements()).toEqual([]);
  });

  it('shows an admin the page at the same addresses', async () => {
    openLayout('/settings/people', 'admin');
    await expect.element(page.getByTestId('the-page')).toBeVisible();
    expect(page.getByText('Only an admin can change this.').elements()).toEqual([]);
  });

  it('shows a member the page for an item they may open', async () => {
    openLayout('/settings/your-kitchen', 'member');
    await expect.element(page.getByTestId('the-page')).toBeVisible();
  });

  const UPDATES = (outcome: string, canCheck = true): [number, unknown] => [
    200,
    {
      version: '0.9.0',
      released_on: '2026-11-12',
      releases_page: 'https://github.com/cabledrawer/mealwright/releases',
      can_check: canCheck,
      daily: canCheck ? true : null,
      last: canCheck
        ? {
            outcome,
            latest: outcome === 'newer' ? 'v0.9.1' : null,
            checked_at: new Date().toISOString()
          }
        : null
    }
  ];

  it('shows "Update available" by About for an admin once a check found a newer version', async () => {
    openLayout('/settings/about', 'admin', { 'GET /updates': UPDATES('newer') });
    await expect
      .element(list().getByRole('link', { name: 'About Update available' }))
      .toBeVisible();
  });

  it('shows no badge when up to date, and a member never asks for it', async () => {
    openLayout('/settings/about', 'admin', { 'GET /updates': UPDATES('up_to_date') });
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/updates')).toBe(true));
    await expect.element(list().getByRole('link', { name: 'About' })).toBeVisible();
    expect(page.getByText('Update available').elements()).toEqual([]);
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    updates.forget();
    openLayout('/settings/about', 'member', { 'GET /updates': UPDATES('newer') });
    await expect.element(list().getByRole('link', { name: 'About' })).toBeVisible();
    expect(requests.some((r) => r.path === '/updates')).toBe(false);
    expect(page.getByText('Update available').elements()).toEqual([]);
  });
});

describe('the phone’s list (/settings)', () => {
  beforeEach(async () => {
    await page.viewport(428, 900);
  });

  it('shows an admin the groups with each row’s value, the rows opening their own pages', async () => {
    await openPhoneList('admin');
    await expect.element(page.getByRole('heading', { name: 'Settings', level: 1 })).toBeVisible();
    const row = (name: string) => page.getByRole('link', { name: new RegExp(`^${name}`) });
    await expect.element(row('Appearance')).toHaveAttribute('href', '/settings/appearance');
    await expect.element(row('Your kitchen')).toHaveAttribute('href', '/settings/your-kitchen');
    await expect.element(row('People')).toHaveAttribute('href', '/settings/people');
    await expect
      .element(row('Outside connections'))
      .toHaveAttribute('href', '/settings/outside-connections');
    await vi.waitFor(() => expect(row('Meal slots').element().textContent).toMatch(/2\s+on/));
    await vi.waitFor(() => expect(row('Amounts').element().textContent).toMatch(/US\s+pints/));
    await vi.waitFor(() => expect(row('People').element().textContent).toMatch(/2\s+people/));
    await vi.waitFor(() =>
      expect(row('Your kitchen').element().textContent).toMatch(/4\s+hob\s+rings/)
    );
    await expect.element(page.getByRole('heading', { name: /^Household/, level: 2 })).toBeVisible();
    await expect.element(page.getByText('admins only')).toBeVisible();
    expect(page.getByRole('link', { name: /Report a problem/ }).elements()).toHaveLength(1);
  });

  it('does not show a member the Household group, and asks for none of its data', async () => {
    await openPhoneList('member');
    await expect.element(page.getByRole('link', { name: /^Appearance/ })).toBeVisible();
    expect(page.getByRole('link', { name: /^People/ }).elements()).toEqual([]);
    expect(page.getByRole('link', { name: /^API tokens/ }).elements()).toEqual([]);
    expect(page.getByRole('heading', { name: /^Household/, level: 2 }).elements()).toEqual([]);
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/shops')).toBe(true));
    expect(requests.some((r) => /^\/(people|privacy)/.test(r.path))).toBe(false);
  });

  it('does not send the phone anywhere', async () => {
    await openPhoneList('admin');
    await expect.element(page.getByRole('link', { name: /^Appearance/ })).toBeVisible();
    expect(goto).not.toHaveBeenCalled();
  });
});

describe('where /settings sends a computer, and an older link', () => {
  it('a computer goes on to Appearance', async () => {
    await openPhoneList('admin');
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/settings/appearance', { replace: true })
    );
  });

  it.each([
    ['?section=sign-in', '/settings/sign-in'],
    ['?section=household', '/settings/people'],
    ['?section=people', '/settings/people'],
    ['?section=privacy', '/settings/outside-connections'],
    ['?section=outside-connections', '/settings/outside-connections'],
    ['?section=your-data', '/settings/your-data'],
    ['?section=about', '/settings/about'],
    ['?section=meal-slots', '/settings/meal-slots'],
    ['?section=shops-places', '/settings/shops-places'],
    ['?section=your-kitchen', '/settings/your-kitchen'],
    ['?section=kitchen', '/settings/your-kitchen'],
    ['?section=recent-changes', '/settings/recent-changes'],
    ['#about', '/settings/about'],
    ['#shops-places', '/settings/shops-places'],
    ['#appearance', '/settings/appearance']
  ])('%s goes to %s', async (tail, goes) => {
    for (const width of [428, 1300]) {
      await page.viewport(width, 900);
      vi.mocked(goto).mockClear();
      await openPhoneList('admin', `/settings${tail}`);
      await vi.waitFor(() => expect(goto).toHaveBeenCalledWith(goes, { replace: true }));
      for (const component of mounted.splice(0)) unmount(component);
      document.body.innerHTML = '';
    }
  });
});
