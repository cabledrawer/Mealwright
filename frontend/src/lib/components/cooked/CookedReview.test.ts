import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { CookRow, Proposal } from '#lib/client/cook.js';
import { CookReview, type CookTarget } from '#lib/cookReview.svelte.js';
import CookedReview, { type LeftoverOptions } from './CookedReview.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

const amount = (n: number, unit: 'g' | 'ml' | 'count' = 'g') => ({
  amount: n,
  unit,
  as_sold: null,
  about: false,
  short: unit === 'count' ? `${n}` : `${n} g`,
  display: `${n}`
});

function row(name: string, id: number, extra: Partial<CookRow> = {}): CookRow {
  return {
    key: `food:${id}`,
    status: 'take',
    lines: [{ id, words: name.toLowerCase(), amount: '200', unit: 'g' }],
    food: { id, name },
    recipe: null,
    needed: amount(200),
    takes: [
      {
        food: { id, name },
        stand_in: false,
        amount: amount(200),
        before: amount(800),
        after: amount(600),
        lots: [
          {
            lot_id: 1,
            place: { id: 1, name: 'Fridge' },
            use_by: null,
            amount: amount(100),
            used_all: false
          },
          {
            lot_id: 2,
            place: { id: 2, name: 'Cupboard' },
            use_by: null,
            amount: amount(100),
            used_all: false
          }
        ]
      }
    ],
    use: true,
    short: null,
    make_first: false,
    add_to_list: false,
    list_amount: null,
    running_low: false,
    in_freezer: null,
    from_freezer: false,
    ask: null,
    estimate: false,
    ask_need: null,
    half: null,
    count_note: null,
    bought: false,
    unit: 'g',
    ...extra
  };
}

const shallot = (): CookRow =>
  row('Shallots', 9, {
    status: 'none_in_pantry',
    takes: [],
    use: false,
    needed: amount(15, 'count'),
    unit: 'count'
  });

const salt = (): CookRow =>
  row('Salt', 8, { status: 'staple', takes: [], use: false, needed: null });

const proposal = (name: string, rows: CookRow[], portions = 4): Proposal => ({
  recipe: { id: 1, name },
  portions,
  servings: 4,
  rows
});

type Body = {
  items: { item_id: number; portions?: number; choices?: unknown[] }[];
  answers: unknown[];
};
type Call = { url: string; body: Body };
let calls: Call[] = [];
let previews: Proposal[][] = [];

/** A server that answers the meal's preview (the next in `previews`) and its confirm. */
function fakeServer() {
  calls = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ url, body });
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { 'content-type': 'application/json' }
      });
    if (url.endsWith('/cook/preview')) {
      const next = previews.length > 1 ? previews.shift()! : previews[0]!;
      return json({
        meal_id: 7,
        items: next.map((p, i) => ({ item_id: 100 + i, proposal: p }))
      });
    }
    if (url.endsWith('/cook')) {
      return json(
        {
          change: { id: 5, kind: 'cooked', summary: 'Cooked it', can_undo: true, undone: null },
          cooked: []
        },
        201
      );
    }
    return json({}, 404);
  });
}

const target = (names: string[]): CookTarget => ({
  title: `Cooked ${names.join(' and ')}`,
  subtitle: 'Thu 15 Oct · dinner',
  mealId: 7,
  parts: names.map((name, i) => ({ itemId: 100 + i, batchId: null, name }))
});

/** The text of an element contains this (spaces normalised), once the screen has caught up. */
async function has(element: { element: () => Element }, text: string | RegExp) {
  await expect
    .poll(() => (element.element().textContent ?? '').replace(/[\s\u00a0]+/g, ' '))
    .toSatisfy((got: string) => (typeof text === 'string' ? got.includes(text) : text.test(got)));
}

describe('the "Cooked it" review', () => {
  let component: ReturnType<typeof mount> | null = null;
  let review: CookReview;
  let confirmed: unknown[] = [];

  async function show(names: string[], leftover: boolean | LeftoverOptions | null = null) {
    review = new CookReview();
    confirmed = [];
    component = mount(CookedReview, {
      target: document.body,
      props: {
        review,
        leftover: leftover === true ? { itemId: 100, today: '2026-10-16' } : leftover || null,
        onclose: () => review.close(),
        onconfirmed: (l: unknown) => void confirmed.push(l)
      }
    });
    await review.open(target(names));
    flushSync();
  }

  beforeEach(() => {
    previews = [[proposal('Sambar', [row('Toor dal', 1), shallot(), salt()])]];
    fakeServer();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('shows each ingredient: where, Before → after, what is taken; staples apart', async () => {
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    const dal = dialog.getByTestId('cook-row').first();
    await has(dal, 'Toor dal');
    await has(dal, 'Fridge, Cupboard');
    await has(dal, '800 → 600 g');
    await has(dal, '−200 g');
    await expect.element(dialog.getByText('Not in pantry')).toBeVisible();
    await expect.element(dialog.getByText('Staples · not counted')).toBeVisible();
    await expect
      .element(dialog.getByRole('list', { name: 'Staples' }).or(dialog.getByText('Salt')))
      .toBeVisible();
    // Stock in two places is one total (F101).
    expect(calls[0]!.url).toBe('/api/v1/plan/meals/7/cook/preview');
  });

  it('Use off leaves an ingredient out of what is sent, and Confirm goes with one request', async () => {
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    const toggle = dialog.getByRole('switch', { name: 'Take Toor dal from the pantry' });
    await expect.element(toggle).toHaveAttribute('aria-checked', 'true');
    await toggle.click();
    await expect.element(toggle).toHaveAttribute('aria-checked', 'false');
    await expect
      .element(
        dialog
          .getByText('1 ingredient will change')
          .or(dialog.getByText('Nothing will be taken from the pantry'))
      )
      .toBeVisible();
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
    expect(sent.body.items).toEqual([{ item_id: 100, choices: [{ key: 'food:1', use: false }] }]);
    expect(sent.body.answers).toEqual([]);
  });

  it('a row with nothing in the pantry starts off, and Bought some is kept on the record', async () => {
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    await expect
      .element(dialog.getByRole('switch', { name: 'Take Shallots from the pantry' }))
      .toBeDisabled();
    const bought = dialog.getByRole('button', { name: 'Bought some — used them' });
    await expect.element(bought).toHaveAttribute('aria-pressed', 'false');
    await bought.click();
    await expect.element(bought).toHaveAttribute('aria-pressed', 'true');
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
    expect(sent.body.items[0]!.choices).toEqual([{ key: 'food:9', bought: true }]);
  });

  it('Portions cooked − N + asks again and every row follows', async () => {
    previews = [
      [proposal('Sambar', [row('Toor dal', 1)], 4)],
      [
        proposal(
          'Sambar',
          [
            row('Toor dal', 1, {
              takes: [{ ...row('Toor dal', 1).takes[0]!, amount: amount(300), after: amount(500) }]
            })
          ],
          5
        )
      ]
    ];
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    await has(dialog.getByRole('group', { name: 'Portions cooked' }), /\b4\b/);
    await dialog.getByRole('button', { name: 'More portions' }).click();
    await has(dialog.getByTestId('cook-row').first(), '−300 g');
    await has(dialog.getByRole('group', { name: 'Portions cooked' }), /\b5\b/);
    const asked = calls.filter((c) => c.url.endsWith('/cook/preview')).at(-1)!;
    expect(asked.body.items).toEqual([{ item_id: 100, portions: 5 }]);
  });

  it('F170: a recipe with no Serves has no Portions cooked, and says how to scale it', async () => {
    previews = [[{ ...proposal('Sandwich', [row('Toor dal', 1)]), servings: null }]];
    await show(['Sandwich']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sandwich' });
    await has(dialog, 'Add Serves to the recipe to scale it.');
    await expect
      .element(dialog.getByRole('group', { name: 'Portions cooked' }))
      .not.toBeInTheDocument();
    await expect.element(dialog.getByText('as planned')).not.toBeInTheDocument();
  });

  it('several recipes: one tab for each, one Confirm for all', async () => {
    previews = [[proposal('Dosa', [row('Rice', 1)]), proposal('Chutney', [row('Coconut', 2)])]];
    await show(['Dosa', 'Chutney']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Dosa and Chutney' });
    const dosa = dialog.getByRole('tab', { name: 'Dosa' });
    const chutney = dialog.getByRole('tab', { name: 'Chutney' });
    await expect.element(dosa).toHaveAttribute('aria-selected', 'true');
    await expect.element(dialog.getByText('Rice')).toBeVisible();
    await chutney.click();
    await expect.element(chutney).toHaveAttribute('aria-selected', 'true');
    await expect.element(dialog.getByText('Coconut')).toBeVisible();
    await dialog.getByRole('switch', { name: 'Take Coconut from the pantry' }).click();
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    const confirms = calls.filter((c) => c.url.endsWith('/plan/meals/7/cook'));
    expect(confirms).toHaveLength(1);
    expect(confirms[0]!.body.items).toEqual([
      { item_id: 100, choices: [] },
      { item_id: 101, choices: [{ key: 'food:2', use: false }] }
    ]);
  });

  it('a counted ingredient has Used / Left and a stepper', async () => {
    const onion = row('Onions', 3, {
      unit: 'count',
      takes: [
        {
          ...row('Onions', 3).takes[0]!,
          amount: amount(2, 'count'),
          before: amount(5, 'count'),
          after: amount(3, 'count')
        }
      ]
    });
    previews = [[proposal('Sambar', [onion])]];
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    await dialog.getByRole('button', { name: 'More Onions' }).click();
    await has(dialog.getByTestId('cook-row'), '5 → 2½');
    await dialog.getByRole('button', { name: 'Left' }).click();
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
    expect(sent.body.items[0]!.choices).toEqual([
      { key: 'food:3', left: { amount: 2.5, unit: 'count' } }
    ]);
  });

  it('"Any left over?" gives the answer to Today along with the confirm', async () => {
    await show(['Sambar'], true);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    await dialog.getByRole('button', { name: 'More tubs' }).click();
    await dialog.getByRole('button', { name: 'Freezer' }).click();
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    expect(confirmed[0]).toEqual({ count: 1, place_kind: 'freezer', item_id: 100 });
  });

  describe('"Eat it on…" offers only meals up to the tub’s use-by (F128)', () => {
    const at = (day: string) => ({ day, slotId: 3, label: `${day} · Dinner` });
    const eatOn = ['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20'].map(at);
    const offered = async () => {
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await dialog.getByRole('button', { name: 'More tubs' }).click();
      flushSync();
      return dialog;
    };
    const days = () =>
      [...document.querySelectorAll<HTMLOptionElement>('.eaton option')]
        .map((o) => o.value.split('|')[0])
        .filter(Boolean);

    it('the fridge’s use-by day is offered, the day after is not; the freezer’s go further', async () => {
      await show(['Sambar'], {
        itemId: 100,
        today: '2026-10-16',
        useByFridge: '2026-10-18',
        useByFreezer: '2027-01-16',
        eatOn
      });
      const dialog = await offered();
      expect(days()).toEqual(['2026-10-17', '2026-10-18']);
      await dialog.getByRole('button', { name: 'Freezer' }).click();
      flushSync();
      expect(days()).toEqual(['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20']);
    });

    it('with no use-by known, no meal is offered (never one the server will refuse)', async () => {
      await show(['Sambar'], { itemId: 100, today: '2026-10-16', eatOn });
      const dialog = await offered();
      await expect.element(dialog.getByText('Use by the usual number of days')).toBeVisible();
      expect(days()).toEqual([]);
    });
  });

  it('a line with no amount can be switched on and given one', async () => {
    const pinch = row('Cardamom', 6, {
      status: 'no_amount',
      takes: [],
      needed: null,
      use: false,
      lines: [{ id: 6, words: 'cardamom, a few' }]
    });
    previews = [[proposal('Sambar', [pinch])]];
    await show(['Sambar']);
    const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
    await dialog.getByRole('switch', { name: 'Take Cardamom from the pantry' }).click();
    await dialog.getByRole('textbox', { name: /How much was used/ }).fill('3');
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
    expect(sent.body.items[0]!.choices).toEqual([
      { key: 'food:6', use: true, used: { amount: 3, unit: 'g' } }
    ]);
  });

  it('the answer for the meal is given before the screen lets go of the meal', async () => {
    // Today and the Plan keep "the meal being answered" and clear it when the screen closes.
    let answering: string | null = 'Sambar';
    const answered: (string | null)[] = [];
    review = new CookReview();
    component = mount(CookedReview, {
      target: document.body,
      props: {
        review,
        onclose: () => {
          answering = null;
          review.close();
        },
        onconfirmed: () => void answered.push(answering)
      }
    });
    await review.open(target(['Sambar']));
    flushSync();
    await page
      .getByRole('dialog', { name: 'Cooked Sambar' })
      .getByRole('button', { name: 'Confirm · update pantry' })
      .click();
    await vi.waitFor(() => expect(answered).toHaveLength(1));
    expect(answered).toEqual(['Sambar']);
  });

  it('a meal with no recipe has nothing to take and can still be answered', async () => {
    review = new CookReview();
    confirmed = [];
    component = mount(CookedReview, {
      target: document.body,
      props: {
        review,
        onclose: () => review.close(),
        onconfirmed: (l: unknown) => void confirmed.push(l)
      }
    });
    await review.open({ title: 'Cooked Rice', subtitle: '', mealId: 7, parts: [] });
    flushSync();
    const dialog = page.getByRole('dialog', { name: 'Cooked Rice' });
    await expect
      .element(dialog.getByText('Nothing in this meal comes from the pantry.'))
      .toBeVisible();
    await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
    await vi.waitFor(() => expect(confirmed).toHaveLength(1));
    expect(calls).toEqual([]);
  });

  describe('a unit the pantry counts differently (F106, F89)', () => {
    const cup = {
      food_id: 1,
      food_name: 'Jaggery',
      kind: 'weight_per_ml' as const,
      question: 'About how much does 1 cup of Jaggery weigh?',
      cup_ml: 250,
      suggested: 200
    };
    const asking = (extra: Partial<CookRow> = {}): CookRow =>
      row('Jaggery', 1, {
        status: 'ask',
        takes: [],
        needed: null,
        use: true,
        lines: [{ id: 1, words: 'jaggery', amount: '1½', unit: 'tbsp' }],
        ask: cup,
        ask_need: { amount: 25, unit: 'ml' },
        half: amount(250),
        ...extra
      });

    it('asks in the pantry unit, learns the answer, and marks the amount an estimate', async () => {
      const worked = row('Jaggery', 1, {
        estimate: true,
        lines: [{ id: 1, words: 'jaggery', amount: '1½', unit: 'tbsp' }],
        takes: [
          {
            ...row('Jaggery', 1).takes[0]!,
            amount: amount(20),
            before: amount(500),
            after: amount(480)
          }
        ]
      });
      previews = [[proposal('Sambar', [asking()])], [proposal('Sambar', [worked])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await has(dialog, 'Recipe says 1½ tbsp jaggery');
      await expect.element(dialog.getByText('How much Jaggery did you use?')).toBeVisible();
      // Never blocks: the row starts off, Confirm is there.
      await expect
        .element(dialog.getByRole('switch', { name: 'Take Jaggery from the pantry' }))
        .toHaveAttribute('aria-checked', 'false');
      await dialog.getByRole('textbox', { name: /^Your answer/ }).fill('20');
      await dialog.getByRole('button', { name: 'Use this' }).click();
      await expect.element(dialog.getByText('estimate')).toBeVisible();
      const asked = calls.filter((c) => c.url.endsWith('/cook/preview')).at(-1)!;
      // 20 g for 25 ml is 0.8 g a ml: 200 g in a 250 ml cup.
      expect(asked.body.answers).toEqual([
        { kind: 'weight_per_ml', food_id: 1, grams: 200, remember: true }
      ]);
      await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
      await vi.waitFor(() => expect(confirmed).toHaveLength(1));
      const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
      expect(sent.body.answers).toEqual(asked.body.answers);
    });

    it('Remember for next time off uses the answer for this cook only', async () => {
      previews = [[proposal('Sambar', [asking()])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      const remember = dialog.getByRole('switch', { name: 'Remember for next time' });
      await expect.element(remember).toHaveAttribute('aria-checked', 'true');
      await remember.click();
      await dialog.getByRole('textbox', { name: /^Your answer/ }).fill('25');
      await dialog.getByRole('button', { name: 'Use this' }).click();
      await vi.waitFor(() =>
        expect(calls.filter((c) => c.url.endsWith('/cook/preview'))).toHaveLength(2)
      );
      expect(calls.filter((c) => c.url.endsWith('/cook/preview')).at(-1)!.body.answers).toEqual([
        { kind: 'weight_per_ml', food_id: 1, grams: 250, remember: false }
      ]);
    });

    it('"About half" answers with half the packet; a figure too far off is not learned', async () => {
      previews = [[proposal('Sambar', [asking({ half: amount(20) })])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await dialog.getByRole('button', { name: 'About half' }).click();
      await vi.waitFor(() =>
        expect(calls.filter((c) => c.url.endsWith('/cook/preview'))).toHaveLength(2)
      );
      expect(calls.filter((c) => c.url.endsWith('/cook/preview')).at(-1)!.body.answers).toEqual([
        { kind: 'weight_per_ml', food_id: 1, grams: 200, remember: true }
      ]);
    });

    it('a figure too far off to be a real weight is not learned, and says so', async () => {
      previews = [[proposal('Sambar', [asking()])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await dialog.getByRole('textbox', { name: /^Your answer/ }).fill('900');
      await dialog.getByRole('button', { name: 'Use this' }).click();
      await expect
        .element(dialog.getByText('That doesn’t look right. Try another amount.'))
        .toBeVisible();
      expect(calls.filter((c) => c.url.endsWith('/cook/preview'))).toHaveLength(1);
    });

    it('Skip is Use off, and Confirm is never blocked by a question', async () => {
      previews = [[proposal('Sambar', [asking()])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await dialog.getByRole('button', { name: 'Skip' }).click();
      await expect.element(dialog.getByText('Skipped')).toBeVisible();
      await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
      await vi.waitFor(() => expect(confirmed).toHaveLength(1));
      const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
      expect(sent.body.items[0]!.choices).toEqual([{ key: 'food:1', use: false }]);
    });

    it('cups against a count cannot be settled by one number: the old question', async () => {
      previews = [[proposal('Sambar', [asking({ ask_need: null })])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await expect.element(dialog.getByText(cup.question)).toBeVisible();
      await expect.element(dialog.getByRole('button', { name: 'Answer' })).toBeVisible();
    });

    it('garlic counted by number asks in its own word, takes a fraction, and learns a clove as a part of one', async () => {
      const garlic = row('Garlic', 4, {
        status: 'no_amount',
        takes: [],
        needed: null,
        use: false,
        unit: 'count',
        unit_word: 'bulbs',
        lines: [{ id: 4, words: 'garlic' }],
        count_note: { count: 2, word: 'clove' }
      });
      previews = [[proposal('Sambar', [garlic])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await expect.element(dialog.getByText('2 cloves is how many bulbs of Garlic?')).toBeVisible();
      await dialog.getByRole('textbox', { name: /^Your answer, in bulbs/ }).fill('¼');
      await dialog.getByRole('button', { name: 'Use this' }).click();
      await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
      await vi.waitFor(() => expect(confirmed).toHaveLength(1));
      const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
      expect(sent.body.items[0]!.choices).toEqual([
        { key: 'food:4', use: true, used: { amount: 0.25, unit: 'count' } }
      ]);
      expect(sent.body.answers).toEqual([
        { kind: 'size', food_id: 4, name: 'clove', amount: 0.125 }
      ]);
    });

    it('"2 cloves" asks in the pantry unit and learns the size of a clove', async () => {
      const garlic = row('Garlic', 4, {
        status: 'no_amount',
        takes: [],
        needed: null,
        use: false,
        lines: [{ id: 4, words: 'garlic' }],
        count_note: { count: 2, word: 'clove' },
        half: amount(50)
      });
      previews = [[proposal('Sambar', [garlic])]];
      await show(['Sambar']);
      const dialog = page.getByRole('dialog', { name: 'Cooked Sambar' });
      await expect.element(dialog.getByText('How much is 2 cloves of garlic?')).toBeVisible();
      await dialog.getByRole('textbox', { name: /^Your answer/ }).fill('10');
      await dialog.getByRole('button', { name: 'Use this' }).click();
      await dialog.getByRole('button', { name: 'Confirm · update pantry' }).click();
      await vi.waitFor(() => expect(confirmed).toHaveLength(1));
      const sent = calls.find((c) => c.url.endsWith('/plan/meals/7/cook'))!;
      expect(sent.body.items[0]!.choices).toEqual([
        { key: 'food:4', use: true, used: { amount: 10, unit: 'g' } }
      ]);
      expect(sent.body.answers).toEqual([{ kind: 'size', food_id: 4, name: 'clove', amount: 5 }]);
    });
  });
});
