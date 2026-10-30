// Every screen tests "can't reach the server" the same way, with cantReach() (spec section 6,
// "Server down (F67's cause)", cabledrawer 28 Oct): no answer at all, and a 502, 503 or 504 from
// the reverse proxy, give the same words on every page.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, cantReachWords, cantReach } from './api';
import { IngredientChanges } from './ingredientChanges.svelte';
import { IngredientsList } from './ingredients.svelte';
import { network } from './network.svelte';
import { PantryModel } from './pantry.svelte';
import { PlanModel } from './plan.svelte';
import { privacy } from './privacy.svelte';
import { RecipeView } from './recipePage.svelte';
import { RecipeList } from './recipes.svelte';
import { session } from './session.svelte';
import { COPY_KEY, TodayModel } from './today.svelte';
import type { TodayData } from './client/today';

/** Every request is answered the same way: by the proxy, or not at all. */
function server(answer: number | 'none') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      if (answer === 'none') throw new TypeError('Failed to fetch');
      // Caddy's own 502 has an empty body; nothing in it is Mealwright's sentence.
      return new Response('', { status: answer });
    })
  );
}

const ANSWERS = [502, 503, 504, 'none'] as const;

beforeEach(() => {
  network.reset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  network.reset();
});

describe('cantReach()', () => {
  it('is no answer, or a 502, 503 or 504 from the proxy; nothing else', () => {
    for (const status of [0, 502, 503, 504]) expect(cantReach(new ApiError(status, ''))).toBe(true);
    for (const status of [400, 401, 404, 409, 422, 500])
      expect(cantReach(new ApiError(status, ''))).toBe(false);
    expect(cantReach(new Error('x'))).toBe(false);
  });

  it('the words are those of the word list (section 7, Connection)', () => {
    expect(cantReachWords()).toBe('Can’t reach your Mealwright server. Check your connection.');
  });
});

describe('one wording on every page when the server can’t be reached (F67)', () => {
  const pages: [string, () => { load(): Promise<void>; problem: string | null }][] = [
    ['Ingredients', () => new IngredientsList()],
    ['Ingredients, recent changes', () => new IngredientChanges()],
    ['Pantry', () => new PantryModel()],
    ['Recipes', () => new RecipeList()],
    ['a recipe', () => new RecipeView(7)],
    ['Plan', () => new PlanModel()],
    ['Today', () => new TodayModel()]
  ];
  for (const answer of ANSWERS) {
    for (const [name, make] of pages) {
      it(`${name}, ${answer === 'none' ? 'no answer' : `the proxy answering ${answer}`}`, async () => {
        server(answer);
        const page = make();
        await page.load();
        expect(page.problem).toBe(cantReachWords());
      });
    }
  }

  it('Privacy, loading: the same words', async () => {
    server(502);
    await privacy.load();
    expect(privacy.problem).toBe(cantReachWords());
    privacy.forget();
  });
});

describe('Today with the server down behind the proxy (F67)', () => {
  const data = (): TodayData => ({
    today: '2026-10-17',
    first_day: false,
    slots: [],
    plan: { start: '2026-10-10', end: '2026-10-23', meals: [], batch_cooks: [], tubs: [] },
    people: [],
    waiting: [],
    tubs_left: [],
    tubs_left_more: false,
    use_soon_lots: [],
    use_soon_tubs: [],
    next_cook: null
  });

  beforeEach(() => {
    session.me = { id: 1, name: 'K', username: 'k', role: 'admin', theme: 'auto' };
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 2, login_id: 1, data: data() }));
  });

  afterEach(() => {
    localStorage.removeItem(COPY_KEY);
    session.me = null;
  });

  it('shows the copy saved last time, as when offline, not "Couldn’t load Today"', async () => {
    server(502);
    const model = new TodayModel();
    await model.load();
    expect(model.problem).toBeNull();
    expect(model.fromCopy).toBe(true);
    expect(model.data?.today).toBe('2026-10-17');
  });
});
