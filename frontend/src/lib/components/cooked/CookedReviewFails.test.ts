import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { CookRow, Proposal } from '#lib/client/cook.js';
import { COULDNT_COOK, CookReview, type CookTarget } from '#lib/cookReview.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import CookedReview from './CookedReview.svelte';
import '../../styles/tokens.css';
import '../../styles/base.css';

const amount = (n: number) => ({
  amount: n,
  unit: 'g' as const,
  as_sold: null,
  about: false,
  short: `${n} g`,
  display: `${n} g`
});

function row(name: string, id: number): CookRow {
  return {
    key: `food:${id}`,
    status: 'take',
    lines: [{ id, words: name }],
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
        lots: []
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
    unit: 'g'
  };
}

const proposal = (name: string, rows: CookRow[]): Proposal => ({
  recipe: { id: 1, name },
  portions: 4,
  servings: 4,
  rows
});

// A meal of a dosa (a meal item) and a rasam cooked once for several (a batch).
const target: CookTarget = {
  title: 'Cooked Dosa and Rasam',
  subtitle: 'Thu 15 Oct · dinner',
  mealId: 7,
  parts: [
    { itemId: 100, batchId: null, name: 'Dosa' },
    { itemId: null, batchId: 3, name: 'Rasam' }
  ]
};

let calls: string[] = [];
let batchStatus = 201;
let undoStatus = 200;

function fakeServer() {
  calls = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    calls.push(`${init.method} ${url}`);
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify(data), {
        status,
        headers: { 'content-type': 'application/json' }
      });
    if (url === '/api/v1/plan/meals/7/cook/preview')
      return json({
        meal_id: 7,
        items: [{ item_id: 100, proposal: proposal('Dosa', [row('Rice', 1)]) }]
      });
    if (url === '/api/v1/plan/batches/3/cook/preview')
      return json(proposal('Rasam', [row('Dal', 2)]));
    const change = (id: number) => ({
      id,
      kind: 'cooked',
      summary: `Cooked ${id}`,
      can_undo: true,
      undone: null
    });
    if (url === '/api/v1/plan/meals/7/cook') return json({ change: change(5), cooked: [] }, 201);
    if (url === '/api/v1/plan/batches/3/cook')
      return batchStatus === 201
        ? json({ change: change(6), cooked: null }, 201)
        : json({ detail: 'Nope.', code: 'already_cooked' }, batchStatus);
    if (/\/changes\/\d+\/undo$/.test(url))
      return undoStatus === 200
        ? json({
            result: 'done',
            message: 'ok',
            change: change(9),
            undone: null,
            groups: [],
            food: null
          })
        : json({ detail: 'down', code: null }, undoStatus);
    return json({}, 404);
  });
}

describe('a confirm that goes wrong leaves nothing changed, or an Undo for what stayed', () => {
  let component: ReturnType<typeof mount> | null = null;
  let review: CookReview;
  let answers: boolean[] = [];
  let answer = true;

  async function show() {
    review = new CookReview();
    answers = [];
    component = mount(CookedReview, {
      target: document.body,
      props: {
        review,
        onclose: () => review.close(),
        onconfirmed: () => {
          answers.push(answer);
          return answer;
        }
      }
    });
    await review.open(target);
    flushSync();
    await expect
      .element(page.getByRole('dialog', { name: target.title }).getByRole('tab', { name: 'Rasam' }))
      .toBeVisible();
  }

  const confirm = () =>
    page
      .getByRole('dialog', { name: target.title })
      .getByRole('button', { name: 'Confirm · update pantry' })
      .click();
  const undone = () => calls.filter((c) => c.includes('/undo'));

  beforeEach(() => {
    batchStatus = 201;
    undoStatus = 200;
    answer = true;
    toasts.dismiss(toasts.current?.id ?? 0);
    fakeServer();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
  });

  it('a meal with a batch is one screen and several calls, the meal first, then the batch, then the answer', async () => {
    await show();
    await confirm();
    await vi.waitFor(() => expect(answers).toEqual([true]));
    expect(calls.filter((c) => c.endsWith('/cook'))).toEqual([
      'POST /api/v1/plan/meals/7/cook',
      'POST /api/v1/plan/batches/3/cook'
    ]);
    expect(undone()).toEqual([]);
    await expect.element(page.getByRole('dialog', { name: target.title })).not.toBeInTheDocument();
  });

  it('the batch fails after the meal worked: the meal is put back and the screen stays', async () => {
    batchStatus = 409;
    await show();
    await confirm();
    await vi.waitFor(() => expect(undone()).toEqual(['POST /api/v1/changes/5/undo']));
    expect(answers).toEqual([]); // the meal's answer is never given
    await vi.waitFor(() => expect(toasts.current?.message).toBe(COULDNT_COOK));
    await expect.element(page.getByRole('dialog', { name: target.title })).toBeVisible();
    // Pressing Confirm again is possible.
    await expect
      .element(page.getByRole('button', { name: 'Confirm · update pantry' }))
      .toBeEnabled();
  });

  it('the meal answer fails after the pantry worked: both pantry changes are put back, last first', async () => {
    answer = false;
    await show();
    await confirm();
    await vi.waitFor(() =>
      expect(undone()).toEqual(['POST /api/v1/changes/6/undo', 'POST /api/v1/changes/5/undo'])
    );
    await vi.waitFor(() => expect(toasts.current?.message).toBe(COULDNT_COOK));
    await expect.element(page.getByRole('dialog', { name: target.title })).toBeVisible();
  });

  it('if the Undo cannot be done either, each change that stayed has a normal Undo', async () => {
    batchStatus = 409;
    undoStatus = 503;
    await show();
    await confirm();
    await vi.waitFor(() => expect(toasts.current?.action?.label).toBe('Undo'));
    expect(toasts.current?.message).toBe('Cooked 5');
  });
});
