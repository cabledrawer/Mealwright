// Speed baseline, step 2: time the main pages and actions, in a browser held to an older phone
// (or a desktop), against the seeded server (docs/dev/performance.md). Not part of ./check: the
// normal Playwright run only reads e2e/tests/.
//
//   cd e2e
//   node perf/measure.ts --profile phone   --runs 5 --out perf/results-phone.json
//   node perf/measure.ts --profile desktop --runs 5 --out perf/results-desktop.json
//   node perf/table.ts perf/results-phone.json perf/results-desktop.json     # the markdown tables
//
// A page's time is from asking for it until its own "ready" signal is drawn (a heading, a list, a
// recipe name): never `networkidle`, because the live updates connection keeps the network busy.
import { writeFileSync, readFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { chromium, expect, request, type Browser, type BrowserContext, type BrowserContextOptions, type Page } from '@playwright/test';

const { values } = parseArgs({
  options: {
    profile: { type: 'string', default: 'phone' },
    runs: { type: 'string', default: '5' },
    state: { type: 'string', default: 'perf/.state.json' },
    out: { type: 'string', default: 'perf/results.json' },
    only: { type: 'string' }, // a comma-separated list of step names, to re-run a few
  },
});
const RUNS = Number(values.runs);
const state = JSON.parse(readFileSync(values.state!, 'utf8')) as {
  base: string;
  admin: { username: string; password: string };
  today: string;
  recipeIds: number[];
  list: string;
  storage: NonNullable<BrowserContextOptions['storageState']>;
};
const BASE = state.base;

/** The two profiles. Phone: 428 px wide, CPU 4x slower and Chrome's "Slow 4G" network, as used here
 *  (not checked against the current DevTools preset): 1.6 Mbit/s down x 0.9, 750 kbit/s up x 0.9, 562.5 ms added delay. */
const PROFILES = {
  phone: {
    context: { viewport: { width: 428, height: 926 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
    cpuRate: 4,
    network: { offline: false, latency: 562.5, downloadThroughput: (1.6 * 1000 * 1000 * 0.9) / 8, uploadThroughput: (750 * 1000 * 0.9) / 8 },
  },
  desktop: { context: { viewport: { width: 1440, height: 900 } }, cpuRate: 1, network: null },
} as const;
const profile = PROFILES[values.profile as keyof typeof PROFILES];
if (!profile) throw new Error('--profile is phone or desktop');

async function slowDown(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  if (profile.cpuRate > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: profile.cpuRate });
  if (profile.network) {
    await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions', profile.network);
  }
}

// --- The signed-in names the ready signals use -------------------------------------------------------
const api = await request.newContext({ baseURL: BASE, storageState: state.storage });
const get = async (path: string) => (await api.get(`/api/v1${path}`)).json();
const someRecipe = (await get(`/recipes/${state.recipeIds[7]}`)) as { id: number; name: string };
const todayPlan = (await get(`/plan?from=${state.today}&to=${state.today}`)) as { meals: { items: { name?: string; recipe_name?: string }[] }[] };
const plannedName = JSON.stringify(todayPlan).match(/"(?:recipe_name|name)":"([^"]+)"/g)?.[0]?.split('":"')[1]?.slice(0, -1) ?? '';

// --- What a page counts as ready ---------------------------------------------------------------------
type Ready = (page: Page) => Promise<unknown>;
const h1 = (name: string | RegExp): Ready => (p) => p.getByRole('heading', { level: 1, name }).waitFor();
const PAGES: { name: string; path: string; ready: Ready }[] = [
  { name: 'Today', path: '/', ready: h1('Today') },
  { name: 'Recipe list', path: '/recipes', ready: async (p) => { await h1('Recipes')(p); await p.getByText(/^\d+ recipes?$/).waitFor(); await p.locator('li a, li button').first().waitFor(); } },
  { name: 'One recipe', path: `/recipes/${someRecipe.id}`, ready: (p) => p.getByRole('heading', { level: 1, name: someRecipe.name }).waitFor() },
  { name: 'Plan (week)', path: '/plan', ready: async (p) => { await h1('Plan')(p); await p.getByText(plannedName).first().waitFor(); } },
  { name: 'Shopping list', path: '/shopping', ready: async (p) => { await h1(/^(Plan s|S)hopping$/)(p); await p.getByText(/\d+ to buy/).first().waitFor(); } },
  { name: 'Pantry', path: '/pantry', ready: async (p) => { await h1('Pantry')(p); await p.locator('main li').first().waitFor(); } },
];

const ms = (t0: number) => Math.round(performance.now() - t0);
type Sample = { ms: number; api: { path: string; wait: number }[] };

/** The /api/v1 calls a page made, with the wait before each answer began (browser's own timing). */
function watchApi(page: Page) {
  const calls: { path: string; wait: number }[] = [];
  page.on('requestfinished', async (req) => {
    if (!req.url().includes('/api/v1/')) return;
    const t = req.timing();
    if (t.responseStart > 0 && t.requestStart > 0) calls.push({ path: new URL(req.url()).pathname.replace('/api/v1', ''), wait: Math.round(t.responseStart - t.requestStart) });
  });
  return calls;
}

async function newPage(browser: Browser, signedIn = true): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: BASE, ...profile.context, ...(signedIn ? { storageState: state.storage } : {}) });
  const page = await context.newPage();
  await slowDown(page);
  return { context, page };
}

const results: Record<string, Record<string, Sample[]>> = { first: {}, repeat: {}, action: {} };
const wanted = (name: string) => !values.only || values.only.split(',').includes(name);

const browser = await chromium.launch();
try {
  // Sign in: a first visit to the sign-in page, typing the name and password, until Today is drawn.
  if (wanted('Sign in')) {
    results.first['Sign in'] = [];
    for (let i = 0; i < RUNS; i++) {
      const { context, page } = await newPage(browser, false);
      const calls = watchApi(page);
      const t0 = performance.now();
      await page.goto('/sign-in');
      await page.getByLabel('Username').fill(state.admin.username);
      await page.getByLabel('Password', { exact: true }).fill(state.admin.password);
      await page.getByRole('button', { name: 'Sign in', exact: true }).click();
      await h1('Today')(page);
      results.first['Sign in']!.push({ ms: ms(t0), api: calls });
      await context.close();
    }
  }

  for (const step of PAGES.filter((s) => wanted(s.name))) {
    // First load: nothing cached (a new browser profile each run), already signed in.
    results.first[step.name] = [];
    for (let i = 0; i < RUNS; i++) {
      const { context, page } = await newPage(browser);
      const calls = watchApi(page);
      const t0 = performance.now();
      await page.goto(step.path);
      await step.ready(page);
      results.first[step.name]!.push({ ms: ms(t0), api: calls });
      await context.close();
    }
    // Repeat load: one visit first (not timed, and the service worker is given time to settle),
    // then the same page asked for again with what the browser kept.
    results.repeat[step.name] = [];
    const { context, page } = await newPage(browser);
    await page.goto(step.path);
    await step.ready(page);
    await page.evaluate(() => navigator.serviceWorker?.ready.then(() => undefined)).catch(() => undefined);
    await page.waitForTimeout(1500);
    const calls = watchApi(page);
    for (let i = 0; i < RUNS; i++) {
      calls.length = 0;
      const t0 = performance.now();
      await page.goto(step.path);
      await step.ready(page);
      results.repeat[step.name]!.push({ ms: ms(t0), api: [...calls] });
    }
    await context.close();
  }

  // Plan, month view: the plan page, then Month, until the month's meals are drawn.
  if (wanted('Plan (month)')) {
    const open = async (page: Page) => {
      await page.goto('/plan');
      await h1('Plan')(page);
      await page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' }).click();
      await expect(page.getByRole('group', { name: 'View' }).getByRole('button', { name: 'Month' })).toHaveAttribute('aria-pressed', 'true');
      await page.getByText(plannedName).first().waitFor();
    };
    results.first['Plan (month)'] = [];
    for (let i = 0; i < RUNS; i++) {
      const { context, page } = await newPage(browser);
      const calls = watchApi(page);
      const t0 = performance.now();
      await open(page);
      results.first['Plan (month)']!.push({ ms: ms(t0), api: calls });
      await context.close();
    }
    results.repeat['Plan (month)'] = [];
    const { context, page } = await newPage(browser);
    await open(page);
    await page.waitForTimeout(1500);
    const calls = watchApi(page);
    for (let i = 0; i < RUNS; i++) {
      calls.length = 0;
      const t0 = performance.now();
      await open(page);
      results.repeat['Plan (month)']!.push({ ms: ms(t0), api: [...calls] });
    }
    await context.close();
  }

  // --- Actions, each on a page that is already open --------------------------------------------------
  async function action(name: string, open: string, ready: Ready, doIt: (page: Page) => Promise<unknown>, prepare?: (page: Page, i: number) => Promise<void>) {
    if (!wanted(name)) return;
    results.action[name] = [];
    const { context, page } = await newPage(browser);
    const calls = watchApi(page);
    await page.goto(open);
    await ready(page);
    for (let i = 0; i < RUNS; i++) {
      if (prepare) await prepare(page, i);
      calls.length = 0;
      const t0 = performance.now();
      await doIt(page);
      results.action[name]!.push({ ms: ms(t0), api: [...calls] });
      await page.waitForTimeout(800);
    }
    await context.close();
  }

  // Tick a shopping line: from the tap until the line no longer shows as still to buy (it is ticked, or moved to the trolley).
  await action('Tick a shopping line', '/shopping', PAGES[4]!.ready, async (page) => {
    const box = page.getByRole('checkbox', { checked: false }).first();
    const label = await box.getAttribute('aria-label');
    await box.click();
    await page.getByRole('checkbox', { name: label ?? undefined, checked: false }).first().waitFor({ state: 'hidden' });
  });

  // Search recipes: from typing a recipe's name until the list has shrunk to the matches.
  const rows = (page: Page) => page.locator('main li');
  await action('Search recipes', '/recipes', PAGES[1]!.ready, async (page) => {
    await page.getByRole('searchbox', { name: 'Search recipes' }).fill(someRecipe.name);
    await expect(rows(page)).toHaveCount(1);
  }, async (page) => {
    await page.getByRole('searchbox', { name: 'Search recipes' }).fill('');
    await expect.poll(() => rows(page).count()).toBeGreaterThan(10);
  });

  // Add a recipe to the plan: open an empty meal's Add (some weeks on), search, pick the first recipe, until the plan says "Planned".
  await action('Add a recipe to the plan', '/plan', PAGES[3]!.ready, async (page) => {
    await page.getByRole('dialog', { name: 'Add to the plan' }).getByRole('searchbox', { name: 'Find a recipe or an ingredient' }).fill('curry');
    const first = page.getByRole('list', { name: 'Results' }).getByRole('button').first();
    await first.waitFor();
    const name = ((await first.innerText()).split('\n')[0] ?? '').trim();
    const before = await page.getByText(name).count();
    await first.click();
    // Done when the dialog has closed and the recipe's name is drawn in the meal (the dialog's own
    // result row held one copy of the name before, so the count is the same afterwards).
    await page.getByRole('dialog', { name: 'Add to the plan' }).waitFor({ state: 'hidden' });
    await expect.poll(() => page.getByText(name).count(), { intervals: [20] }).toBeGreaterThanOrEqual(before);
  }, async (page, i) => {
    // The month is fully planned, so go on to the weeks after it: empty meals to add to.
    if (i === 0) for (let w = 0; w < 6; w++) await page.getByRole('button', { name: 'Next week' }).click();
    await page.getByRole('button', { name: /^(\+ Add \w+|Add to (?!the plan).*)$/ }).first().click();
    await page.getByRole('dialog', { name: 'Add to the plan' }).waitFor();
  });

  // Stocktake save: leave the first place (its answers are saved), until the next place is drawn.
  // Each run starts a new stocktake first, so it is always the first place that is saved.
  await action('Pantry stocktake save', '/pantry/stocktake', async (p) => { await p.getByRole('heading', { name: /^Stocktake · / }).waitFor(); }, async (page) => {
    const heading = await page.getByRole('heading', { name: /^Stocktake · / }).innerText();
    await page.getByRole('button', { name: /^(Next: .* →|Finish)$/ }).click();
    await expect(page.getByRole('heading', { name: /^Stocktake · |^Stocktake finished/ })).not.toHaveText(heading);
  }, async (page) => {
    await page.request.post('/api/v1/stocktake/restart', { headers: { 'Idempotency-Key': crypto.randomUUID() } });
    await page.goto('/pantry/stocktake');
    await page.getByRole('heading', { name: /^Stocktake · / }).waitFor();
  });
} finally {
  await browser.close();
}

// --- The server's own answer time: loopback, no slowing, 5 calls each -----------------------------------
const week = (d: string, n: number) => new Date(Date.parse(`${d}T12:00:00Z`) + n * 86_400_000).toISOString().slice(0, 10);
const API = [
  ['GET /today', '/today'],
  ['GET /recipes (first 50)', '/recipes?limit=50'],
  ['GET /recipes?q=garlic', '/recipes?q=garlic'],
  ['GET /recipes/{id}', `/recipes/${someRecipe.id}`],
  ['GET /plan (7 days)', `/plan?from=${state.today}&to=${week(state.today, 6)}`],
  ['GET /plan (42 days)', `/plan?from=${state.today}&to=${week(state.today, 41)}`],
  ['GET /shopping/lists/{id}', `/shopping/lists/${state.list}`],
  ['GET /pantry', '/pantry'],
  ['GET /stocktake', '/stocktake'],
] as const;
const server: Record<string, number[]> = {};
for (const [name, path] of API) {
  server[name] = [];
  for (let i = 0; i < RUNS + 1; i++) {
    const t0 = performance.now();
    const res = await api.get(`/api/v1${path}`);
    await res.body();
    if (i > 0) server[name]!.push(ms(t0)); // the first call is a warm-up, not counted
    if (!res.ok()) throw new Error(`${path} → ${res.status()}`);
  }
}
await api.dispose();
writeFileSync(values.out!, JSON.stringify({ profile: values.profile, runs: RUNS, when: new Date().toISOString().slice(0, 10), results, server }, null, 1));
console.log(`written ${values.out}`);
