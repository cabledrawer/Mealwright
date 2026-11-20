import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { PlanActions } from '#lib/planActions.js';
import PlanAdd from './PlanAdd.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The recipe list is a stand-in with one recipe, and no ingredient search goes out.
vi.mock('#lib/recipes.svelte.js', () => ({
  RecipeList: class {
    query = '';
    recipes = [{ id: 7, name: 'Stew', time_minutes: null, kcal: null }];
    loaded = true;
    problem = null;
    load = async () => {};
  }
}));
vi.mock('#lib/client/foods.js', () => ({ listFoods: vi.fn(async () => ({ foods: [] })) }));

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

type Target = { day: string; slotId: number | null } | null;

/** Mounts the sheet on a day, picks "Cook once here…" and the recipe; the plan answers later. */
async function startCooking(first: Target) {
  let answer: (value: unknown) => void = () => {};
  const openCookOnce = vi.fn();
  const model = {
    slotsOn: [
      { id: 1, name: 'Dinner' },
      { id: 2, name: 'Lunch' }
    ],
    slotName: () => 'Dinner',
    tubsLeft: [],
    today: '2026-11-02',
    add: () => new Promise((resolve) => (answer = resolve))
  };
  const actions = { model, readonly: false, openCookOnce } as unknown as PlanActions;
  const props = $state({ actions, target: first, onclose: () => {} });
  component = mount(PlanAdd, { target: document.body, props });
  flushSync();
  await page.getByRole('button', { name: 'Cook once here…' }).click();
  await page.getByRole('button', { name: /Stew/ }).click();
  const reply = async () => {
    answer({ ok: true, value: { meal_id: 5, item_id: 9 } });
    for (let n = 0; n < 20; n++) await Promise.resolve(); // let the continuation run
  };
  return { props, openCookOnce, reply };
}

describe('Cook once here… (F52) and a late answer', () => {
  it('opens Cook once when the answer comes and nothing changed', async () => {
    const { openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    await reply();
    await vi.waitFor(() => expect(openCookOnce).toHaveBeenCalledTimes(1));
  });

  it('does nothing if the sheet is opened on another day before the answer', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = { day: '2026-11-04', slotId: 1 };
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });

  it('does nothing if the sheet is opened on another meal of the same day', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = { day: '2026-11-03', slotId: 2 };
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });

  it('does nothing if the sheet was closed before the answer', async () => {
    const { props, openCookOnce, reply } = await startCooking({ day: '2026-11-03', slotId: 1 });
    props.target = null;
    flushSync();
    await reply();
    expect(openCookOnce).not.toHaveBeenCalled();
  });
});

describe('the sheet’s title (F127)', () => {
  function open(slotId: number | null) {
    const model = {
      slotsOn: [
        { id: 1, name: 'Dinner' },
        { id: 2, name: 'Lunch' }
      ],
      slotName: (id: number) => (id === 1 ? 'Dinner' : 'Lunch'),
      tubsLeft: [],
      today: '2026-11-02',
      add: async () => ({ ok: true })
    };
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(PlanAdd, {
      target: document.body,
      props: { actions, target: { day: '2026-11-11', slotId }, onclose: () => {} }
    });
    flushSync();
  }

  it('before a meal is picked: "Pick a meal, then what to add" over the full day', async () => {
    open(null);
    await expect.element(page.getByText('Pick a meal, then what to add')).toBeVisible();
    await expect
      .element(page.getByRole('heading', { name: 'Wednesday 11 November' }))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('a meal ·');
  });

  it('after picking: "Add to" over "Dinner · Wednesday 11"', async () => {
    open(null);
    await page.getByRole('button', { name: 'Dinner', exact: true }).click();
    await expect.element(page.getByText('Add to', { exact: true })).toBeVisible();
    await expect
      .element(page.getByRole('heading', { name: 'Dinner · Wednesday 11' }))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('Pick a meal, then what to add');
  });

  it('a meal already chosen on opening starts on "Add to"', async () => {
    open(1);
    await expect
      .element(page.getByRole('heading', { name: 'Dinner · Wednesday 11' }))
      .toBeVisible();
  });
});

describe('Use a tub never offers a tub not cooked yet (F230, spec F50)', () => {
  const tub = (id: number, name: string, cookedOn: string, batch: number) => ({
    id,
    batch_id: batch,
    number: 1,
    tub_count: 4,
    recipe_name: name,
    colour: null,
    cooked_on: cookedOn,
    amount_quarters: 4,
    place_id: null,
    place_kind: 'fridge',
    member_id: null,
    use_by: '2026-11-20'
  });

  function open(day: string, slotId: number, tubsLeft?: ReturnType<typeof tub>[]) {
    const model = {
      slotsOn: [
        { id: 1, name: 'Breakfast' },
        { id: 2, name: 'Dinner' }
      ],
      slotName: (id: number) => (id === 1 ? 'Breakfast' : 'Dinner'),
      tubsLeft: tubsLeft ?? [
        tub(1, 'Khichdi', '2026-11-14', 10), // cooked on Sat 14, at Breakfast
        tub(2, 'Dal Tadka', '2026-11-12', 11)
      ],
      plan: {
        meals: [{ id: 50, date: '2026-11-14', slot_id: 1 }],
        batch_cooks: [{ id: 10, cook_meal_id: 50 }]
      },
      today: '2026-11-11',
      add: async () => ({ ok: true })
    };
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(PlanAdd, {
      target: document.body,
      props: { actions, target: { day, slotId }, onclose: () => {} }
    });
    flushSync();
  }

  it('Fri 13 breakfast: only the tub that is already cooked', async () => {
    open('2026-11-13', 1);
    await expect.element(page.getByText('Dal Tadka', { exact: false })).toBeVisible();
    expect(document.body.textContent).not.toContain('Khichdi');
  });

  it('Sat 14: not at the cooking meal, but at the dinner after it', async () => {
    open('2026-11-14', 1);
    await expect.element(page.getByText('Dal Tadka', { exact: false })).toBeVisible();
    expect(document.body.textContent).not.toContain('Khichdi');
    unmount(component!);
    document.body.innerHTML = '';
    open('2026-11-14', 2);
    await expect.element(page.getByText('Khichdi', { exact: false })).toBeVisible();
  });

  it('a batch really cooked a day before its planned meal has no cook meal to come after (L1)', async () => {
    // Planned for Sat 14 breakfast, cooked ahead on Fri 13: on Fri 13 at breakfast the tub is
    // offered, because the meal on Sat 14 is not the day the tub was cooked.
    open('2026-11-13', 1, [tub(1, 'Khichdi', '2026-11-13', 10)]);
    await expect.element(page.getByText('Khichdi', { exact: false })).toBeVisible();
  });
});

describe('closing the sheet', () => {
  it('Escape and the Close button both close it', async () => {
    const onclose = vi.fn();
    const model = {
      slotsOn: [{ id: 1, name: 'Dinner' }],
      slotName: () => 'Dinner',
      tubsLeft: [],
      today: '2026-11-02',
      add: async () => ({ ok: true })
    };
    const actions = { model, readonly: false } as unknown as PlanActions;
    component = mount(PlanAdd, {
      target: document.body,
      props: { actions, target: { day: '2026-11-11', slotId: 1 }, onclose }
    });
    flushSync();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await vi.waitFor(() => expect(onclose).toHaveBeenCalledTimes(1));
    await page.getByRole('button', { name: 'Close' }).click();
    await vi.waitFor(() => expect(onclose).toHaveBeenCalledTimes(2));
  });
});
