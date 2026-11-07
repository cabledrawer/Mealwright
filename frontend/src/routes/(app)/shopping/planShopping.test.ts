// Plan shopping (0.8 S3): from 1100 px the Shopping page is one column by shop and aisle with
// one-line rows, and a column of panels beside it. The 768 to 1099 px computer screen and the
// phone are tested in page.test.ts.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import Toast from '#lib/components/Toast.svelte';
import { ME, fakeShopping, sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import type { ShoppingCopy } from '#lib/shopping/types.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Shopping from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const WHY = {
  'i-onions': { why: 'Sambar (Tue) · Rasam (Thu)', staple_offer: false },
  'i-yoghurt': { why: 'Added by you', staple_offer: true },
  'i-dal': { why: '120 g needed · Sambar (Tue)', staple_offer: false }
};

describe('Plan shopping', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let copy: ShoppingCopy;
  let server: ReturnType<typeof fakeShopping>;

  /** The server's list read: the lines grouped as the screen asks, with why. */
  const listRead = () => [
    200,
    {
      shops: [
        {
          aisles: [{ items: Object.entries(WHY).map(([id, w]) => ({ id, ...w })) }],
          in_trolley: []
        }
      ]
    }
  ];

  async function render(width: number, extra: Parameters<typeof fakeShopping>[1] = {}) {
    server = fakeShopping(copy, { 'GET /shopping/lists/main': listRead as never, ...extra });
    await page.viewport(width, 1000);
    for (const component of [Shopping, Toast]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
  }

  beforeEach(() => {
    freshPhone();
    copy = sampleCopy();
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
  });

  afterEach(async () => {
    network.reset();
    await dropPhone();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('is Plan shopping from 1100 px, and the phone screen under it', async () => {
    await render(1100);
    await expect
      .element(page.getByRole('heading', { name: 'Plan shopping', level: 1 }))
      .toBeVisible();
    await expect.element(page.getByRole('region', { name: 'Shops' })).toBeVisible();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    await render(1099);
    await expect.element(page.getByRole('heading', { name: 'Shopping', level: 1 })).toBeVisible();
    expect(page.getByRole('region', { name: 'Shops' }).elements()).toEqual([]);
  });

  it('groups by shop in Settings order, Any shop last, with the count in each header', async () => {
    await render(1300);
    await expect
      .element(page.getByRole('heading', { level: 2, name: /^Supermarket/ }))
      .toBeVisible();
    const names = page
      .getByRole('heading', { level: 2 })
      .elements()
      .map((h) => h.textContent?.replace(/\s+/g, ' ').trim());
    expect(names.indexOf('Supermarket · 2')).toBeGreaterThanOrEqual(0);
    expect(names.indexOf('Supermarket · 2')).toBeLessThan(names.indexOf('Indian grocer · 1'));
    expect(names.indexOf('Indian grocer · 1')).toBeLessThan(names.indexOf('Any shop · 1'));
  });

  it('says why each line is there, from the server’s list read, and a typed line offline', async () => {
    await render(1300);
    await expect.element(page.getByText('Sambar (Tue) · Rasam (Thu)')).toBeVisible();
    await expect.element(page.getByText('120 g needed · Sambar (Tue)')).toBeVisible();
    await expect.element(page.getByText('Added by you').first()).toBeVisible();
  });

  it('has the shop chips, and a chip shows just that shop', async () => {
    await render(1300);
    await expect
      .element(page.getByRole('button', { name: 'All · 4' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect.element(page.getByRole('button', { name: 'Supermarket · 2' })).toBeVisible();
    await expect.element(page.getByRole('link', { name: 'Manage' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: '+ New shop' })).toBeVisible();
    await page.getByRole('button', { name: 'Indian grocer · 1' }).click();
    await expect.element(page.getByRole('button', { name: 'Toor dal', exact: true })).toBeVisible();
    expect(page.getByRole('button', { name: 'Onions', exact: true }).elements()).toEqual([]);
  });

  it('+ New shop asks for a name and adds the shop', async () => {
    await render(1300, {
      'POST /shops': [201, { id: 9, name: 'Corner shop', position: 2, aisle_order: null }]
    });
    await page.getByRole('button', { name: '+ New shop' }).click();
    await page.getByRole('textbox', { name: 'Shop name' }).fill('Corner shop');
    await page.getByRole('button', { name: 'Add shop' }).click();
    await vi.waitFor(() =>
      expect(server.requests.find((r) => r.method === 'POST' && r.path === '/shops')?.body).toEqual(
        {
          name: 'Corner shop'
        }
      )
    );
  });

  it('keeps ticked lines in an In the trolley panel, open, with a clear button each and Clear ticked', async () => {
    await render(1300);
    await expect.element(page.getByRole('heading', { name: 'In the trolley · 2' })).toBeVisible();
    await page.getByRole('button', { name: 'Clear Coriander' }).click();
    await vi.waitFor(() =>
      expect(server.actions).toMatchObject([{ kind: 'clear_ticked', item_ids: ['i-coriander'] }])
    );
    await page.getByRole('button', { name: 'Clear ticked' }).click();
    await vi.waitFor(() =>
      expect(server.actions[1]).toMatchObject({ kind: 'clear_ticked', item_ids: ['i-paneer'] })
    );
  });

  it('folds Check you have these until Show', async () => {
    await render(1300, {
      'POST /shopping/from-plan': [
        200,
        {
          days: 7,
          from_plan: 0,
          changed: false,
          staples: [{ food: { id: 9, name: 'Turmeric' }, used_in: ['Sambar'] }]
        }
      ]
    });
    const toggle = page.getByRole('button', { name: /^Check you have these/ });
    await expect.element(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(page.getByRole('button', { name: 'Got it, Turmeric' }).elements()).toEqual([]);
    await toggle.click();
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
  });

  describe('Usual pack? quick picks', () => {
    const picks = [
      { pack: null, name: 'pack', amount: 200, display: 'pack · 200 g', amount_text: '200 g' },
      { pack: null, name: 'pack', amount: 500, display: 'pack · 500 g', amount_text: '500 g' }
    ];

    beforeEach(() => {
      const yoghurt = copy.items.find((i) => i.id === 'i-yoghurt')!;
      yoghurt.amount = 60;
      yoghurt.display = '60 g';
      yoghurt.pack = { suggestions: picks };
    });

    it('sit under a line with no size, and a tap makes the pick the Usual size', async () => {
      await render(1300, {
        'POST /foods/3/sizes': [201, { change: null }]
      });
      const group = page.getByRole('group', { name: 'Usual pack for Yoghurt?' });
      await expect.element(group).toBeVisible();
      await group.getByRole('button', { name: '200 g' }).click();
      await vi.waitFor(() =>
        expect(server.requests.find((r) => r.path === '/foods/3/sizes')?.body).toEqual({
          name: 'pack',
          amount: 200,
          usual: true
        })
      );
    });

    it('are not there once the ingredient has a size, nor on a line with no amount', async () => {
      copy.foods.find((f) => f.id === 3)!.sizes = [
        { id: 8, name: 'tub', plural: 'tubs', amount: 500, usual: true }
      ];
      await render(1300);
      await expect
        .element(page.getByRole('button', { name: 'Yoghurt', exact: true }))
        .toBeVisible();
      expect(page.getByRole('group', { name: 'Usual pack for Yoghurt?' }).elements()).toEqual([]);
      expect(page.getByRole('group', { name: 'Usual pack for Toor dal?' }).elements()).toEqual([]);
    });
  });

  it('offers Make it a staple? when the list read says so, and one tap sends it', async () => {
    await render(1300, {
      'PATCH /foods/3': [
        200,
        { food: { id: 3 }, change: { id: 9, summary: 'Yoghurt is now a staple', can_undo: true } }
      ]
    });
    const link = page.getByRole('button', { name: 'Make it a staple?' });
    await expect.element(link).toBeVisible();
    await link.click();
    await vi.waitFor(() =>
      expect(
        server.requests.find((r) => r.method === 'PATCH' && r.path === '/foods/3')?.body
      ).toEqual({
        staple: true
      })
    );
  });

  it('shows no Make it a staple? while offline', async () => {
    await render(1300);
    await expect.element(page.getByRole('button', { name: 'Make it a staple?' })).toBeVisible();
    network.offline = true;
    flushSync();
    await vi.waitFor(() =>
      expect(page.getByRole('button', { name: 'Make it a staple?' }).elements()).toEqual([])
    );
  });
});
