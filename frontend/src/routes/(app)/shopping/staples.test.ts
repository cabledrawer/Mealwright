// The list built from the plan: the "Check you have these" card, "built from this week's plan",
// and Opening Shopping asking the server to bring the list up to date (docs/dev/words.md 21).
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import Toast from '#lib/components/Toast.svelte';
import { ME, food, fakeShopping, item, sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import type { PlanCard } from '#lib/shopping/plan.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import type { ShoppingCopy } from '#lib/shopping/types.js';
import Shopping from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const CARD: PlanCard = {
  days: 7,
  from_plan: 0,
  changed: false,
  staples: [
    { food: { id: 8, name: 'Turmeric' }, used_in: ['Dosa', 'Sambar'] },
    { food: { id: 9, name: 'Sunflower oil' }, used_in: ['Sambar'] }
  ]
};

describe('Shopping: the list from the plan', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let copy: ShoppingCopy;
  let card: PlanCard;
  let server: ReturnType<typeof fakeShopping>;

  const gotItOrNot = (request: { path: string; body: unknown }) => {
    const id = Number(request.path.split('/')[3]);
    if ((request.body as { got_it: boolean }).got_it) {
      card = { ...card, staples: card.staples.filter((s) => s.food.id !== id) };
    } else {
      const back = CARD.staples.find((s) => s.food.id === id)!;
      card = { ...card, staples: [...card.staples, back] };
    }
    return [200, structuredClone(card)] as [number, unknown];
  };

  async function render(width: number, extra: Parameters<typeof fakeShopping>[1] = {}) {
    server = fakeShopping(copy, {
      'POST /shopping/add-from-plan': () => [200, structuredClone(card)],
      'PATCH /shopping/staples/8': gotItOrNot,
      'PATCH /shopping/staples/9': gotItOrNot,
      ...extra
    });
    await page.viewport(width, 1000);
    for (const component of [Shopping, Toast]) {
      const target = document.body.appendChild(document.createElement('div'));
      mounted.push(mount(component, { target }));
    }
    flushSync();
    await expect.element(page.getByRole('heading', { name: /shopping/i, level: 1 })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'This week main list' })).toBeVisible();
  }

  const asked = (method: string, path: string) =>
    server.requests.filter((r) => r.method === method && r.path === path);
  /** "Got it" (true) or its Undo (false) for one staple: a PATCH on it (D3). */
  const gotIt = (id: number, got: boolean) =>
    asked('PATCH', `/shopping/staples/${id}`).filter(
      (r) => (r.body as { got_it: boolean }).got_it === got
    );

  beforeEach(() => {
    freshPhone();
    copy = sampleCopy();
    copy.foods.push(
      food(8, 'Turmeric', 'spices', { staple: true }),
      food(9, 'Sunflower oil', 'dry_goods', { staple: true })
    );
    card = structuredClone(CARD);
    session.me = { ...ME };
    undoHistory.clear();
    toasts.dismiss();
    network.reset();
  });

  afterEach(async () => {
    network.reset();
    await dropPhone();
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
  });

  it('asks the server to bring the list up to date when Shopping opens', async () => {
    await render(390);
    await expect.element(page.getByRole('heading', { name: 'Check you have these' })).toBeVisible();
    expect(asked('POST', '/shopping/add-from-plan').length).toBeGreaterThanOrEqual(1);
  });

  it('shows the card on a phone: each staple with the recipes that use it, Got it and + Add', async () => {
    await render(390);
    await expect.element(page.getByText('Staples this week’s recipes use')).toBeVisible();
    await expect.element(page.getByText('Dosa and Sambar')).toBeVisible();
    for (const name of ['Turmeric', 'Sunflower oil']) {
      await expect.element(page.getByRole('button', { name: `Got it, ${name}` })).toBeVisible();
      await expect.element(page.getByRole('button', { name: `+ Add ${name}` })).toBeVisible();
    }
    const box = page
      .getByRole('button', { name: 'Got it, Turmeric' })
      .element()
      .getBoundingClientRect();
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThanOrEqual(44);
  });

  it('shows the card on a computer too, folded until Show (Plan shopping)', async () => {
    await render(1300);
    await expect
      .element(page.getByRole('heading', { name: /^Check you have these/ }))
      .toBeVisible();
    expect(page.getByRole('button', { name: '+ Add Sunflower oil' }).elements()).toEqual([]);
    await page.getByRole('button', { name: /^Check you have these/ }).click();
    await expect.element(page.getByRole('button', { name: '+ Add Sunflower oil' })).toBeVisible();
    await page.getByRole('button', { name: /^Check you have these/ }).click();
    expect(page.getByRole('button', { name: '+ Add Sunflower oil' }).elements()).toEqual([]);
  });

  it('names the look-ahead when it is not a week', async () => {
    card = { ...card, days: 3 };
    await render(390);
    await expect.element(page.getByText('Staples the next 3 days’ recipes use')).toBeVisible();
  });

  it('has no card when the plan uses no staple', async () => {
    card = { ...card, staples: [] };
    await render(390);
    await new Promise((r) => setTimeout(r, 100));
    expect(page.getByRole('heading', { name: 'Check you have these' }).elements()).toEqual([]);
  });

  it('Got it takes the staple off the card at once, says so, and Undo brings it back', async () => {
    await render(390);
    await page.getByRole('button', { name: 'Got it, Turmeric' }).click();
    await expect
      .element(page.getByRole('button', { name: 'Got it, Turmeric' }))
      .not.toBeInTheDocument();
    await expect.element(page.getByRole('button', { name: 'Got it, Sunflower oil' })).toBeVisible();
    expect(gotIt(8, true)).toHaveLength(1);
    const toast = page.getByRole('status').filter({ hasText: 'Turmeric: got it' });
    await expect.element(toast).toBeVisible();
    await toast.getByRole('button', { name: 'Undo' }).click();
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
    expect(gotIt(8, false)).toHaveLength(1);
    await expect
      .element(page.getByRole('status').filter({ hasText: 'Undone: Turmeric: got it' }))
      .toBeVisible();
  });

  it('the ✕ is Got it for every staple on the card, with one Undo, and the card stays away meanwhile', async () => {
    const seen: boolean[] = [];
    await render(390, {
      'PATCH /shopping/staples/9': (request) => {
        if (!(request.body as { got_it: boolean }).got_it) return gotItOrNot(request); // Undo
        // The second answer is being asked for: the card must not have come back for it.
        flushSync();
        seen.push(!!document.querySelector('[aria-label="Got it, Sunflower oil"]'));
        card = { ...card, staples: [] };
        return [200, structuredClone(card)];
      }
    });
    await page.getByRole('button', { name: 'Dismiss staples check' }).click();
    await expect
      .element(page.getByRole('heading', { name: 'Check you have these' }))
      .not.toBeInTheDocument();
    expect(gotIt(8, true)).toHaveLength(1);
    expect(gotIt(9, true)).toHaveLength(1);
    expect(seen).toEqual([false]);
    await page
      .getByRole('status')
      .filter({ hasText: 'Staples check dismissed' })
      .getByRole('button', { name: 'Undo' })
      .click();
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Got it, Sunflower oil' })).toBeVisible();
  });

  it('+ Add puts the staple on the list as an ordinary line and it leaves the card', async () => {
    await render(390);
    await page.getByRole('button', { name: '+ Add Sunflower oil' }).click();
    await expect
      .element(page.getByRole('button', { name: '+ Add Sunflower oil' }))
      .not.toBeInTheDocument();
    await expect.element(page.getByRole('button', { name: '+ Add Turmeric' })).toBeVisible();
    await vi.waitFor(() =>
      expect(server.actions.filter((a) => a.kind === 'add')).toMatchObject([
        { kind: 'add', list_id: 'main', food_id: 9 }
      ])
    );
  });

  it('a staple already on the main list is not on the card', async () => {
    copy.items.push(item('i-oil', 9, { shop_id: null }));
    await render(390);
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
    expect(page.getByRole('button', { name: 'Got it, Sunflower oil' }).elements()).toEqual([]);
  });

  it('offline: the card stays, its buttons are switched off, and it says why', async () => {
    await render(390);
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
    network.offline = true;
    network.deviceOffline = true;
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeDisabled();
    await expect.element(page.getByRole('button', { name: '+ Add Turmeric' })).toBeDisabled();
    await expect
      .element(page.getByRole('button', { name: 'Dismiss staples check' }))
      .toBeDisabled();
    await expect
      .element(page.getByText('You’re offline. Got it and + Add work when you’re back online.'))
      .toBeVisible();
  });

  it('Got it that the server refuses puts the staple back and says so', async () => {
    await render(390, {
      'PATCH /shopping/staples/8': [500, { detail: 'Couldn’t save. Try again.' }]
    });
    await page.getByRole('button', { name: 'Got it, Turmeric' }).click();
    await expect.element(page.getByText('Couldn’t save. Try again.')).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Got it, Turmeric' })).toBeVisible();
  });

  it('says the list was built from the plan when the plan made some of its lines', async () => {
    copy.items.push(item('i-plan', 5, { source: 'plan', shop_id: 2 }));
    card = { ...card, from_plan: 1 };
    await render(390);
    await expect.element(page.getByText(/to buy · built from this week’s plan/)).toBeVisible();
  });

  it('does not say it when the plan made none', async () => {
    await render(390);
    expect(page.getByText(/built from/).elements()).toEqual([]);
  });

  it('the plan update waits until the list has been read, so it never holds the list back', async () => {
    // cabledrawer 27 Oct: the list shows at once, online, slow or offline; the plan's update runs
    // afterwards, in the background.
    await render(390);
    await vi.waitFor(() => expect(asked('POST', '/shopping/add-from-plan').length).toBe(1));
    const order = server.requests.map((r) => `${r.method} ${r.path}`);
    expect(order.indexOf('GET /shopping/sync')).toBeGreaterThanOrEqual(0);
    expect(order.indexOf('POST /shopping/add-from-plan')).toBeGreaterThan(
      order.indexOf('GET /shopping/sync')
    );
  });

  it('after the plan changed the list, Shopping reads the list again', async () => {
    card = { ...card, changed: true };
    await render(390);
    await vi.waitFor(() => expect(asked('GET', '/shopping/sync').length).toBeGreaterThanOrEqual(2));
  });
});
