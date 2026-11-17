// Settings: Meal slots, Shops & places, Recent changes and Your kitchen, each on its own page (0.8, S1;
// F252). The list and the pages' places are tested in list.test.ts.

import { flushSync, mount, unmount, type Component } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { kitchen as freshness } from '#lib/freshness.svelte.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { privacy } from '#lib/privacy.svelte.js';
import { updates } from '#lib/updates.svelte.js';
import { session } from '#lib/session.svelte.js';
import { changeOf, fakeApi, PLACES, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Kitchen from './kitchen/+page.svelte';
import MealSlotsPage from './meal-slots/+page.svelte';
import RecentChangesPage from './recent-changes/+page.svelte';
import ShopsPlacesPage from './shops-places/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));

/** The page each group of tests opens (each item of Settings is its own page, F252). */
let view: Component = MealSlotsPage;

const SLOTS = [
  { id: 1, name: 'Breakfast', position: 0, enabled: true },
  { id: 2, name: 'Lunch', position: 1, enabled: true },
  { id: 3, name: 'Snack', position: 2, enabled: false },
  { id: 4, name: 'Dinner', position: 3, enabled: true }
];
const SHOPS = [
  { id: 1, name: 'Supermarket' },
  { id: 2, name: 'Indian grocer' }
];
const write = (summary: string, id = 90) => [
  200,
  { change: { ...changeOf(id, summary), kind: 'shop_removed' } }
];

const KITCHEN = { hob_rings: 4, pressure_cookers: 1, oven: true, asked: false };

let mounted: ReturnType<typeof mount> | null = null;

function open(routes: Record<string, Parameters<typeof fakeApi>[0][string]> = {}): FakeRequest[] {
  const requests = fakeApi({
    'GET /household': [200, { name: 'Home', pints: 'uk' }],
    'GET /household/kitchen': [200, KITCHEN],
    'GET /meal-slots': [200, SLOTS],
    'GET /shops': [200, SHOPS],
    'GET /places': [200, PLACES],
    'GET /changes': [200, { changes: [], next: null }],
    'GET /people': [
      200,
      { people: [{ id: 1 }, { id: 2 }], can_change: true, ask_whos_this: false }
    ],
    ...routes
  });
  mounted = mount(view, { target: document.body.appendChild(document.createElement('div')) });
  flushSync();
  return requests;
}

beforeEach(async () => {
  session.me = { ...ME };
  network.reset();
  placesAndShops.forget();
  privacy.forget();
  updates.forget();
  undoHistory.clear();
  await page.viewport(1300, 900);
});

afterEach(() => {
  if (mounted) unmount(mounted);
  mounted = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  network.reset();
  toasts.dismiss();
});

describe('Meal slots', () => {
  beforeEach(() => {
    view = MealSlotsPage;
  });

  it('renames a meal in place, and says nothing is lost on Undo', async () => {
    const requests = open({
      'PATCH /meal-slots/2': [
        200,
        { change: { ...changeOf(91, 'Renamed Lunch to Midday meal'), kind: 'plan_slot' } }
      ]
    });
    await page.getByRole('button', { name: 'Rename Lunch' }).click();
    const box = page.getByRole('textbox', { name: 'Name of Lunch' });
    await box.fill('Midday meal');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByText('Midday meal', { exact: true })).toBeVisible();
    const patch = requests.find((r) => r.method === 'PATCH')!;
    expect(patch.body).toEqual({ name: 'Midday meal' });
    expect(patch.headers['idempotency-key']).toBeTruthy();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Renamed Lunch to Midday meal'));
    expect(toasts.current?.action?.label).toBe('Undo');
  });

  it('Move down puts a meal after the next one, and sends the whole order', async () => {
    const requests = open({
      'PUT /meal-slots/order': [200, { change: null }]
    });
    await page.getByRole('button', { name: 'Move Breakfast down' }).click();
    const put = requests.find((r) => r.method === 'PUT')!;
    expect(put.body).toEqual({ ids: [2, 1, 3, 4] });
    const first = page.getByRole('region', { name: 'Meal slots' }).getByRole('listitem').first();
    await expect.element(first).toHaveTextContent('Lunch');
    // The first can't go up, the last can't go down.
    await expect.element(page.getByRole('button', { name: 'Move Lunch up' })).toBeDisabled();
    await expect.element(page.getByRole('button', { name: 'Move Dinner down' })).toBeDisabled();
  });

  it('reads the meals again when the list was out of date, and lets you try again (RF5, H5)', async () => {
    const NEW = { id: 5, name: 'Supper', position: 4, enabled: true };
    let all = SLOTS;
    const requests = open({
      'GET /meal-slots': () => [200, all],
      'PUT /meal-slots/order': (request) => {
        const ids = (request.body as { ids: number[] }).ids;
        return ids.length === all.length
          ? [200, { change: null }]
          : [
              422,
              { code: 'not_all_slots', detail: 'Send every meal once, in the order you want.' }
            ];
      }
    });
    await expect.element(page.getByText('Breakfast', { exact: true })).toBeVisible();
    all = [...SLOTS, NEW];
    await page.getByRole('button', { name: 'Move Breakfast down' }).click();
    await expect.element(page.getByText('Supper', { exact: true })).toBeVisible();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('The list changed. Try again.'));
    await page.getByRole('button', { name: 'Move Breakfast down' }).click();
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'PUT').at(-1)?.body).toEqual({
        ids: [2, 1, 3, 4, 5]
      })
    );
  });

  it('puts the order back, and says why, when the server refuses it', async () => {
    open({
      'PUT /meal-slots/order': [
        403,
        { code: 'admins_only', detail: 'Only the household’s admin can change this.' }
      ]
    });
    await page.getByRole('button', { name: 'Move Breakfast down' }).click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Only the household’s admin can change this.')
    );
    const first = page.getByRole('region', { name: 'Meal slots' }).getByRole('listitem').first();
    await expect.element(first).toHaveTextContent('Breakfast');
  });

  it('drags a meal onto another to reorder', async () => {
    const requests = open({ 'PUT /meal-slots/order': [200, { change: null }] });
    const rows = page.getByRole('region', { name: 'Meal slots' }).getByRole('listitem');
    await expect.element(rows.nth(3)).toBeVisible();
    await rows.nth(3).dropTo(rows.nth(0));
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ ids: [4, 1, 2, 3] })
    );
  });

  it('adds a meal, last', async () => {
    const requests = open({
      'POST /meal-slots': [201, { id: 9, name: 'Supper', position: 4, enabled: true }]
    });
    await page.getByRole('button', { name: '+ New meal' }).click();
    await page.getByRole('textbox', { name: 'New meal' }).fill('Supper');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect.element(page.getByText('Supper', { exact: true })).toBeVisible();
    expect(requests.find((r) => r.method === 'POST')?.body).toEqual({ name: 'Supper' });
  });

  it('says what the server said when the name is taken', async () => {
    open({
      'POST /meal-slots': [
        409,
        { code: 'slot_exists', detail: 'There’s already a meal called Dinner.' }
      ]
    });
    await page.getByRole('button', { name: '+ New meal' }).click();
    await page.getByRole('textbox', { name: 'New meal' }).fill('dinner');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect.element(page.getByText('There’s already a meal called Dinner.')).toBeVisible();
  });

  it('switches a meal off, and has no way to remove one', async () => {
    const requests = open({
      'PATCH /meal-slots/1': [
        200,
        { change: { ...changeOf(92, 'Hid Breakfast in the plan'), kind: 'plan_slot' } }
      ]
    });
    await page.getByRole('switch', { name: 'Show Breakfast in the plan' }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({ enabled: false })
    );
    expect(page.getByRole('button', { name: /^Remove (Breakfast|Lunch)/ }).elements()).toHaveLength(
      0
    );
  });
});

describe('Shops', () => {
  beforeEach(() => {
    view = ShopsPlacesPage;
  });

  it('renames a shop', async () => {
    const requests = open({ 'PATCH /shops/1': [200, { id: 1, name: 'Tesco' }] });
    await page.getByRole('button', { name: 'Rename Supermarket' }).click();
    await page.getByRole('textbox', { name: 'Name of Supermarket' }).fill('Tesco');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByText('Tesco', { exact: true })).toBeVisible();
    expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({ name: 'Tesco' });
  });

  it('keeps the box open and says why when the name is taken', async () => {
    open({
      'PATCH /shops/1': [
        409,
        { code: 'shop_exists', detail: 'There’s already a shop called Indian grocer.' }
      ]
    });
    await page.getByRole('button', { name: 'Rename Supermarket' }).click();
    await page.getByRole('textbox', { name: 'Name of Supermarket' }).fill('indian grocer');
    await userEvent.keyboard('{Enter}');
    await expect
      .element(page.getByText('There’s already a shop called Indian grocer.'))
      .toBeVisible();
    await expect.element(page.getByRole('textbox', { name: 'Name of Supermarket' })).toBeVisible();
  });

  it('puts shops in order with Move down', async () => {
    const requests = open({ 'PUT /shops/order': [200, [SHOPS[1], SHOPS[0]]] });
    await page.getByRole('button', { name: 'Move Supermarket down' }).click();
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ ids: [2, 1] });
  });

  it('reads the shops again when the list was out of date, and lets you try again (RF5, H5)', async () => {
    // Another tab added a shop: the order sent is missing it, so the server refuses.
    const NEW = { id: 3, name: 'Market stall' };
    let all = SHOPS;
    const requests = open({
      'GET /shops': () => [200, all],
      'PUT /shops/order': (request) => {
        const ids = (request.body as { ids: number[] }).ids;
        return ids.length === all.length
          ? [200, ids.map((id) => all.find((s) => s.id === id))]
          : [
              422,
              { code: 'not_all_shops', detail: 'Send every shop once, in the order you want.' }
            ];
      }
    });
    await expect.element(page.getByText('Indian grocer', { exact: true })).toBeVisible();
    all = [...SHOPS, NEW];
    await page.getByRole('button', { name: 'Move Supermarket down' }).click();
    // The list is read again and shows the new shop; the developer's words are not shown.
    await expect.element(page.getByText('Market stall', { exact: true })).toBeVisible();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('The list changed. Try again.'));
    // And trying again sends all three.
    await page.getByRole('button', { name: 'Move Supermarket down' }).click();
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'PUT').at(-1)?.body).toEqual({ ids: [2, 1, 3] })
    );
  });

  it('removes a shop at once, with an Undo that brings it back', async () => {
    let gone = false;
    const requests = open({
      'DELETE /shops/1': () => {
        gone = true;
        return write('Removed the shop Supermarket') as [number, unknown];
      },
      'POST /changes/90/undo': () => {
        gone = false;
        return [
          200,
          { result: 'done', message: 'Undone.', brought_back: [], undone: changeOf(90, 'x') }
        ];
      },
      'GET /shops': () => [200, gone ? [SHOPS[1]] : SHOPS]
    });
    await page.getByRole('button', { name: 'Remove Supermarket' }).click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Removed the shop Supermarket'));
    expect(page.getByText('Supermarket', { exact: true }).elements()).toHaveLength(0);
    expect(requests.find((r) => r.method === 'DELETE')?.headers['idempotency-key']).toBeTruthy();
    expect(
      page.getByText('Removing a shop moves its ingredients to “Any shop”, with Undo.')
    ).toBeTruthy();
    // No "Are you sure?" on the way: the toast's Undo is the way back.
    toasts.current!.action!.run();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/90/undo')).toBe(true));
    await expect.element(page.getByText('Supermarket', { exact: true })).toBeVisible();
  });

  it('puts the shop back and says why when the server will not remove it', async () => {
    open({ 'DELETE /shops/1': [500, { detail: 'Something went wrong.' }] });
    await page.getByRole('button', { name: 'Remove Supermarket' }).click();
    await vi.waitFor(() => expect(toasts.current?.tone).toBe('problem'));
    await expect.element(page.getByText('Supermarket', { exact: true })).toBeVisible();
  });

  it('adds a shop', async () => {
    const requests = open({ 'POST /shops': [201, { id: 7, name: 'Farmers market' }] });
    await page.getByRole('button', { name: '+ New shop' }).click();
    await page.getByRole('textbox', { name: 'New shop' }).fill('Farmers market');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect.element(page.getByText('Farmers market', { exact: true })).toBeVisible();
    expect(requests.find((r) => r.method === 'POST')?.body).toEqual({ name: 'Farmers market' });
  });
});

describe('Places', () => {
  beforeEach(() => {
    view = ShopsPlacesPage;
  });

  it('shows each place’s kind', async () => {
    open();
    const places = page.getByRole('region', { name: 'Places at home' });
    await expect.element(places).toMatchTextContent(/Freezer Freezer/);
    await expect.element(places).toMatchTextContent(/Spice rack Cupboard/);
  });

  it('adds a place with a kind', async () => {
    const requests = open({
      'POST /places': [201, { id: 9, name: 'Garage freezer', kind: 'freezer' }]
    });
    await page.getByRole('button', { name: '+ New place' }).click();
    await page.getByRole('textbox', { name: 'New place' }).fill('Garage freezer');
    await page.getByRole('combobox', { name: 'Kind' }).selectOptions('freezer');
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await expect.element(page.getByText('Garage freezer', { exact: true })).toBeVisible();
    expect(requests.find((r) => r.method === 'POST' && r.path === '/places')?.body).toEqual({
      name: 'Garage freezer',
      kind: 'freezer'
    });
  });

  it('removes an empty place with Undo', async () => {
    const requests = open({
      'DELETE /places/4': [
        200,
        { change: { ...changeOf(95, 'Removed the place Spice rack'), kind: 'place_removed' } }
      ]
    });
    await page.getByRole('button', { name: 'Remove Spice rack' }).click();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Removed the place Spice rack'));
    expect(toasts.current?.action?.label).toBe('Undo');
    expect(requests.find((r) => r.method === 'DELETE')?.url).toBe('/places/4');
  });

  it('a place with things in it says how many and asks where to move them, then removes it', async () => {
    const requests = open({
      'DELETE /places/3': (request) =>
        request.url.includes('move_to')
          ? [
              200,
              { change: { ...changeOf(96, 'Removed the place Cupboard'), kind: 'place_removed' } }
            ]
          : [
              409,
              {
                code: 'place_not_empty',
                detail: 'Cupboard has 14 things in it. Move them to…',
                things: 14
              }
            ]
    });
    await page.getByRole('button', { name: 'Remove Cupboard' }).click();
    const ask = page.getByRole('form', { name: 'Move things out of Cupboard' });
    await expect
      .element(ask.getByText('Cupboard has 14 things in it. Move them to…'))
      .toBeVisible();
    // Cupboard stays on the list while it is asked.
    await expect.element(page.getByRole('button', { name: 'Remove Cupboard' })).toBeVisible();
    await ask.getByRole('combobox', { name: 'Move them to' }).selectOptions('4');
    await ask.getByRole('button', { name: 'Move and remove' }).click();
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'DELETE').map((r) => r.url)).toEqual([
        '/places/3',
        '/places/3?move_to=4'
      ])
    );
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Removed the place Cupboard'));
    expect(page.getByRole('button', { name: 'Remove Cupboard' }).elements()).toHaveLength(0);
  });

  it('the last Fridge and the last Freezer can’t be removed, and the screen says why', async () => {
    open();
    await expect.element(page.getByRole('button', { name: 'Remove Fridge' })).toBeDisabled();
    await expect.element(page.getByRole('button', { name: 'Remove Freezer' })).toBeDisabled();
    await expect.element(page.getByRole('button', { name: 'Remove Cupboard' })).toBeEnabled();
    await expect
      .element(page.getByRole('region', { name: 'Places at home' }))
      .toMatchTextContent(/Mealwright needs at least one Fridge and one Freezer\./);
  });

  it('a second Fridge can go', async () => {
    open({
      'GET /places': [200, [...PLACES, { id: 8, name: 'Garage fridge', kind: 'fridge' }]]
    });
    await expect.element(page.getByRole('button', { name: 'Remove Fridge' })).toBeEnabled();
    await expect.element(page.getByRole('button', { name: 'Remove Garage fridge' })).toBeEnabled();
  });

  it('puts places in order with Move up', async () => {
    const requests = open({ 'PUT /places/order': [200, PLACES] });
    await page.getByRole('button', { name: 'Move Spice rack up' }).click();
    expect(requests.find((r) => r.method === 'PUT')?.body).toEqual({ ids: [1, 2, 4, 3] });
  });

  it('reads the places again when the list was out of date, and lets you try again (RF5, H5)', async () => {
    const NEW = { id: 9, name: 'Pantry shelf', kind: 'cupboard' };
    let all = PLACES;
    const requests = open({
      'GET /places': () => [200, all],
      'PUT /places/order': (request) => {
        const ids = (request.body as { ids: number[] }).ids;
        return ids.length === all.length
          ? [200, ids.map((id) => all.find((p) => p.id === id))]
          : [
              422,
              { code: 'not_all_places', detail: 'Send every place once, in the order you want.' }
            ];
      }
    });
    await expect.element(page.getByRole('button', { name: 'Move Spice rack up' })).toBeVisible();
    all = [...PLACES, NEW];
    await page.getByRole('button', { name: 'Move Spice rack up' }).click();
    await expect.element(page.getByText('Pantry shelf', { exact: true })).toBeVisible();
    await vi.waitFor(() => expect(toasts.current?.message).toBe('The list changed. Try again.'));
    await page.getByRole('button', { name: 'Move Spice rack up' }).click();
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'PUT').at(-1)?.body).toEqual({
        ids: [1, 2, 4, 3, 9]
      })
    );
  });

  it('renames a place', async () => {
    const requests = open({
      'PATCH /places/4': [200, { id: 4, name: 'Spices', kind: 'cupboard' }]
    });
    await page.getByRole('button', { name: 'Rename Spice rack' }).click();
    await page.getByRole('textbox', { name: 'Name of Spice rack' }).fill('Spices');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByText('Spices', { exact: true })).toBeVisible();
    expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({ name: 'Spices' });
  });
});

describe('Recent changes', () => {
  beforeEach(() => {
    view = RecentChangesPage;
  });

  const made = (id: number, kind: string, summary: string) => ({ ...changeOf(id, summary), kind });

  it('lists every kind, newest first, and undoes one', async () => {
    let undone = false;
    const requests = open({
      'GET /changes': () => [
        200,
        {
          changes: [
            made(50, 'plan_add', 'Planned Dal curry for Mon dinner'),
            made(49, 'cooked', 'Cooked Sambar (2 portions)'),
            made(48, 'recipe_imported', 'Imported Sambar, with 2 new ingredients'),
            { ...made(47, 'used', 'Used 200 g Toor dal'), can_undo: !undone }
          ],
          next: null
        }
      ],
      'POST /changes/47/undo': () => {
        undone = true;
        return [
          200,
          { result: 'done', message: 'Undone.', brought_back: [], undone: made(47, 'used', 'x') }
        ];
      }
    });
    const list = page.getByRole('region', { name: 'Recent changes' });
    await expect.element(list.getByText('Planned Dal curry for Mon dinner')).toBeVisible();
    const rows = list
      .getByRole('listitem')
      .elements()
      .map((r) => r.textContent ?? '');
    expect(rows[0]).toContain('Planned Dal curry');
    expect(rows[1]).toContain('Cooked Sambar');
    expect(rows[2]).toContain('Imported Sambar');
    expect(rows[3]).toContain('Used 200 g Toor dal');
    // The change's own kind of verb is in bold.
    expect(list.getByText('Cooked', { exact: true }).element().tagName).toBe('B');
    await list.getByRole('button', { name: 'Undo: Used 200 g Toor dal' }).click();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/47/undo')).toBe(true));
    await vi.waitFor(() =>
      expect(
        list.getByRole('button', { name: 'Undo: Used 200 g Toor dal' }).elements()
      ).toHaveLength(0)
    );
    // It asked for all kinds: no area.
    expect(requests.find((r) => r.path === '/changes')?.url).toBe('/changes?limit=20');
  });

  it('pages with Show more, until there are no older changes', async () => {
    const requests = open({
      'GET /changes?limit=20': [
        200,
        { changes: [made(60, 'used', 'Used 100 g Rice')], next: '60' }
      ],
      'GET /changes?limit=20&before=60': [
        200,
        { changes: [made(59, 'cooked', 'Cooked Rasam (1 portion)')], next: null }
      ]
    });
    const list = page.getByRole('region', { name: 'Recent changes' });
    await expect.element(list.getByText('Used 100 g Rice')).toBeVisible();
    await list.getByRole('button', { name: 'Show more' }).click();
    await expect.element(list.getByText('Cooked Rasam (1 portion)')).toBeVisible();
    expect(list.getByRole('button', { name: 'Show more' }).elements()).toHaveLength(0);
    expect(requests.some((r) => r.url === '/changes?limit=20&before=60')).toBe(true);
  });

  it('says so when there is nothing yet, and when it can’t load', async () => {
    open();
    await expect
      .element(page.getByText('Nothing yet. Changes show here, with Undo for 7 days.'))
      .toBeVisible();
    unmount(mounted!);
    document.body.innerHTML = '';
    mounted = null;
    open({ 'GET /changes': [500, { detail: 'No.' }] });
    await expect.element(page.getByText(/Couldn’t load the recent changes\./)).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  });
});

describe('Your kitchen (Batch cook, B1; mockup Dark-BatchKit08)', () => {
  beforeEach(() => {
    view = Kitchen;
  });

  const kitchen = () => page.getByRole('region', { name: 'Your kitchen' });

  it('shows the kitchen as it is, and says it has not been asked yet', async () => {
    open();
    await expect.element(kitchen()).toBeVisible();
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Hob rings\s*4/));
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Pressure cookers\s*1/));
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Oven\s*Yes/));
    await vi.waitFor(() => expect(kitchen().element().textContent).toContain('Not asked yet'));
  });

  it('puts a space between "has." and "Not asked yet" (RF5, prerelease 3)', async () => {
    open();
    await vi.waitFor(() =>
      expect(kitchen().element().textContent).toContain('has. Not asked yet: Batch cook asks')
    );
  });

  it('reads the kitchen again after an Undo elsewhere (RF5, H8; Recent changes is its own page now, F252)', async () => {
    const requests = open({
      'PATCH /household/kitchen': [
        200,
        { hob_rings: 3, pressure_cookers: 1, oven: true, asked: true }
      ]
    });
    const reads = (path: string) => requests.filter((r) => r.path === path).length;
    await page.getByRole('button', { name: 'Change' }).click();
    const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
    await sheet.getByRole('button', { name: 'Fewer hob rings' }).click();
    await sheet.getByRole('button', { name: 'Save' }).click();
    // An Undo from Recent changes (or the toast) puts the old numbers back: Your kitchen reads them.
    const kitchenBefore = reads('/household/kitchen');
    freshness.changed({ elsewhere: true });
    await vi.waitFor(() => expect(reads('/household/kitchen')).toBeGreaterThan(kitchenBefore));
  });

  it('Change opens the sheet; Save sends the kitchen, and the section shows it', async () => {
    const requests = open({
      'PATCH /household/kitchen': [
        200,
        { hob_rings: 3, pressure_cookers: 2, oven: false, asked: true }
      ]
    });
    await page.getByRole('button', { name: 'Change' }).click();
    const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
    await expect.element(sheet).toBeVisible();
    await sheet.getByRole('button', { name: 'Fewer hob rings' }).click();
    await sheet.getByRole('button', { name: 'More pressure cookers' }).click();
    await sheet.getByRole('radio', { name: 'No' }).click();
    await sheet.getByRole('button', { name: 'Save' }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'PATCH')?.body).toEqual({
        hob_rings: 3,
        pressure_cookers: 2,
        oven: false
      })
    );
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Hob rings\s*3/));
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Oven\s*No/));
    expect(kitchen().element().textContent).not.toContain('Not asked yet');
  });

  it('keeps the steppers between 1 and 12 hob rings and 0 and 6 pressure cookers', async () => {
    open({ 'GET /household/kitchen': [200, { ...KITCHEN, hob_rings: 1, pressure_cookers: 0 }] });
    await page.getByRole('button', { name: 'Change' }).click();
    const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
    await expect.element(sheet.getByRole('button', { name: 'Fewer hob rings' })).toBeDisabled();
    await expect
      .element(sheet.getByRole('button', { name: 'Fewer pressure cookers' }))
      .toBeDisabled();
  });

  it('Close leaves it as it was, and nothing is sent', async () => {
    const requests = open();
    await page.getByRole('button', { name: 'Change' }).click();
    const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
    await sheet.getByRole('button', { name: 'More hob rings' }).click();
    await sheet.getByRole('button', { name: 'Close' }).click();
    await vi.waitFor(() => expect(kitchen().element().textContent).toMatch(/Hob rings\s*4/));
    expect(requests.some((r) => r.method === 'PATCH')).toBe(false);
  });

  it('says it could not save, and keeps the sheet open', async () => {
    open({ 'PATCH /household/kitchen': [503, { detail: 'down' }] });
    await page.getByRole('button', { name: 'Change' }).click();
    const sheet = page.getByRole('dialog', { name: 'Your kitchen' });
    await sheet.getByRole('button', { name: 'Save' }).click();
    await expect.element(sheet.getByRole('alert')).toBeVisible();
    await expect.element(sheet).toBeVisible();
  });
});
