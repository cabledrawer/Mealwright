// Full Onboarding (0.9 U2): after first-run setup the admin comes here once. The phone shows one
// step per screen, a computer one page of cards. Skip passes over one step (the last one's Skip, and Finish
// setup and Go to Today, mark it done for the household and go to Today); anyone else, or a household that has finished, goes straight
// to Today.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { goto } from '$app/navigation';
import { network } from '#lib/network.svelte.js';
import { household as people } from '#lib/people.svelte.js';
import { session } from '#lib/session.svelte.js';
import { starterPacks } from '#lib/starterPacks.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { TESS, people as peopleList, person } from '#lib/testing/fakePeople.js';
import { ME } from '#lib/testing/fakeShopping.js';
import Onboarding from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(async () => {}) }));

const household = (extra: Record<string, unknown> = {}) => ({
  name: 'Home',
  pints: 'uk',
  amounts_shown: 'as_written',
  onboarding_done: false,
  undo_days: 7,
  ...extra
});

let component: ReturnType<typeof mount> | null = null;
let requests: FakeRequest[] = [];

function open(routes: Parameters<typeof fakeApi>[0] = {}) {
  requests = fakeApi({
    'GET /household': [200, household()],
    'PATCH /household': (request) => [200, household(request.body as Record<string, unknown>)],
    'GET /people': [200, peopleList([TESS])],
    'GET /shops': [200, []],
    'GET /places': [200, []],
    ...routes
  });
  component = mount(Onboarding, {
    target: document.body.appendChild(document.createElement('div'))
  });
  flushSync();
}

const patches = () => requests.filter((r) => r.method === 'PATCH').map((r) => r.body);

beforeEach(() => {
  session.me = { ...ME };
  network.reset();
  people.forget();
  vi.mocked(goto).mockClear();
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  network.reset();
  people.forget();
  starterPacks.close();
});

describe('on the phone', () => {
  beforeEach(() => page.viewport(428, 900));

  it('starts at step 2 of 6, saves the Amounts choice, and Skip passes over just that step', async () => {
    open();
    await expect.element(page.getByText('Step 2 of 6')).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'How do you measure?' })).toBeVisible();
    expect(document.documentElement.hasAttribute('data-full-page')).toBe(true);
    await expect
      .element(page.getByRole('radio', { name: 'As the recipe says (cups stay cups)' }))
      .toBeChecked();
    await expect
      .element(page.getByText(/Cups and ounces as a choice come after version 1\.0\./))
      .toBeVisible();
    await page.getByRole('radio', { name: 'Metric: grams and ml' }).click();
    await vi.waitFor(() => expect(patches()).toEqual([{ amounts_shown: 'metric' }]));

    await page.getByRole('button', { name: 'Skip' }).click();
    await expect.element(page.getByText('Step 3 of 6')).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'Who eats here?' })).toHaveFocus();
    expect(goto).not.toHaveBeenCalled();
    expect(patches()).toEqual([{ amounts_shown: 'metric' }]);
    await page.getByRole('button', { name: 'Back' }).click();
    await expect.element(page.getByText('Step 2 of 6')).toBeVisible();
  });

  it('Skip on the last step that has one (5) finishes setup', async () => {
    open();
    for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Next' }).click();
    await expect.element(page.getByText('Step 5 of 6')).toBeVisible();
    await page.getByRole('button', { name: 'Skip' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(patches()).toEqual([{ onboarding_done: true }]);
  });

  it('goes through every step with Next and Back, and Go to Today finishes it', async () => {
    open();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect.element(page.getByText('Step 3 of 6')).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'Who eats here?' })).toHaveFocus();
    await expect.element(page.getByText('Tess (you)')).toBeVisible();
    await page.getByRole('button', { name: 'Back' }).click();
    await expect.element(page.getByText('Step 2 of 6')).toBeVisible();
    // Step 2 has no Back: the account (step 1) is already made.
    await expect.element(page.getByRole('button', { name: 'Back' })).not.toBeInTheDocument();
    for (const [step, title] of [
      [3, 'Who eats here?'],
      [4, 'Where do you shop?'],
      [5, 'Start with common ingredients?'],
      [6, 'You’re set']
    ] as const) {
      await page.getByRole('button', { name: 'Next' }).click();
      await expect.element(page.getByText(`Step ${step} of 6`)).toBeVisible();
      await expect.element(page.getByRole('heading', { name: title })).toBeVisible();
    }
    // The last step has no Skip: Go to Today finishes it.
    await expect.element(page.getByRole('button', { name: 'Skip' })).not.toBeInTheDocument();
    await expect
      .element(page.getByText(/Nothing connects outside until you switch it on in\s+Privacy\./))
      .toBeVisible();
    await page.getByRole('button', { name: 'Go to Today' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(patches()).toEqual([{ onboarding_done: true }]);
  });

  it('adds a person by name only', async () => {
    const wren = person(4, 'Wren');
    open({ 'POST /people': [201, peopleList([TESS, wren])] });
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await expect.element(page.getByLabelText('Name', { exact: true })).toHaveFocus();
    await userEvent.keyboard('Wren{Enter}');
    await expect.element(page.getByText('Wren', { exact: true })).toBeVisible();
    const added = requests.find((r) => r.method === 'POST' && r.path === '/people');
    expect(added?.body).toMatchObject({ name: 'Wren' });
    expect(added?.body).not.toHaveProperty('login');
  });

  it('adds a shop and takes one away', async () => {
    open({
      'GET /shops': [200, [{ id: 1, name: 'Supermarket' }]],
      'POST /shops': [201, { id: 2, name: 'Indian grocer' }],
      'DELETE /shops/1': [200, { change: null }]
    });
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await expect.element(page.getByText('Supermarket')).toBeVisible();
    await page.getByRole('button', { name: '+ Add a shop' }).click();
    await userEvent.keyboard('Indian grocer{Enter}');
    await expect.element(page.getByText('Indian grocer')).toBeVisible();
    expect(requests.find((r) => r.method === 'POST' && r.path === '/shops')?.body).toEqual({
      name: 'Indian grocer'
    });
    await page.getByRole('button', { name: 'Remove Supermarket' }).click();
    await expect.element(page.getByText('Supermarket')).not.toBeInTheDocument();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.method === 'DELETE' && r.path === '/shops/1')).toBe(true)
    );
  });

  it('Next adds a name that was typed but not added, then moves on', async () => {
    const wren = person(4, 'Wren');
    open({ 'POST /people': [201, peopleList([TESS, wren])] });
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await userEvent.keyboard('Wren');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect.element(page.getByText('Step 4 of 6')).toBeVisible();
    expect(requests.find((r) => r.method === 'POST' && r.path === '/people')?.body).toMatchObject({
      name: 'Wren'
    });
  });

  it('Skip also adds a typed shop first; a shop that can’t be added keeps you on the step', async () => {
    open({
      'POST /shops': [201, { id: 2, name: 'Indian grocer' }]
    });
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: '+ Add a shop' }).click();
    await userEvent.keyboard('Indian grocer');
    await page.getByRole('button', { name: 'Skip' }).click();
    await expect.element(page.getByText('Step 5 of 6')).toBeVisible();
    expect(requests.find((r) => r.method === 'POST' && r.path === '/shops')?.body).toEqual({
      name: 'Indian grocer'
    });
  });

  it('stays on the step and says so when the typed shop can’t be added', async () => {
    open({ 'POST /shops': [400, { detail: 'That shop is already there.' }] });
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: '+ Add a shop' }).click();
    await userEvent.keyboard('Aldi');
    await page.getByRole('button', { name: 'Next' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('That shop is already there.');
    await expect.element(page.getByText('Step 4 of 6')).toBeVisible();
  });

  it('opens the same starter-pack picker as Ingredients', async () => {
    open();
    for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Add a starter pack' }).click();
    expect(starterPacks.open).toBe(true);
  });

  it('says so and stays when the last Skip can’t be saved', async () => {
    open({ 'PATCH /household': [403, { detail: 'Only the household’s admin can change this.' }] });
    for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Next' }).click();
    await page.getByRole('button', { name: 'Skip' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Only the household’s admin can change this.');
    expect(goto).not.toHaveBeenCalled();
  });
});

describe('on a computer', () => {
  beforeEach(() => page.viewport(1300, 900));

  it('shows one page of cards, and Finish setup ends it for good', async () => {
    open();
    await expect
      .element(page.getByRole('heading', { name: 'Welcome to Mealwright. Five quick things.' }))
      .toBeVisible();
    for (const card of [
      '1 · Your account',
      '2 · Amounts',
      '3 · Shops',
      '4 · Who eats here?',
      '5 · Start with common ingredients?'
    ]) {
      await expect.element(page.getByRole('heading', { name: card })).toBeVisible();
    }
    await expect.element(page.getByText('Step 2 of 6')).not.toBeInTheDocument();
    // The desktop mockup draws no Skip: the page has Finish setup only.
    await expect.element(page.getByRole('button', { name: 'Skip' })).not.toBeInTheDocument();
    await page.getByRole('button', { name: 'Finish setup' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(patches()).toEqual([{ onboarding_done: true }]);
  });

  it('Finish setup adds a typed name and a typed shop first', async () => {
    const wren = person(4, 'Wren');
    open({
      'POST /people': [201, peopleList([TESS, wren])],
      'POST /shops': [201, { id: 2, name: 'Aldi' }]
    });
    await page.getByRole('button', { name: '+ Add a shop' }).click();
    await userEvent.keyboard('Aldi');
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await userEvent.keyboard('Wren');
    await page.getByRole('button', { name: 'Finish setup' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(requests.some((r) => r.method === 'POST' && r.path === '/shops')).toBe(true);
    expect(requests.some((r) => r.method === 'POST' && r.path === '/people')).toBe(true);
  });
});

describe('only once, and only for the admin', () => {
  it('goes straight to Today once the household has finished it', async () => {
    open({ 'GET /household': [200, household({ onboarding_done: true })] });
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(page.getByText('Step 2 of 6').query()).toBeNull();
    expect(patches()).toEqual([]);
  });

  it('sends a member to Today without asking the server', async () => {
    session.me = { ...ME, role: 'member' };
    open();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/', { replace: true }));
    expect(requests.filter((r) => r.path === '/household')).toEqual([]);
  });
});
