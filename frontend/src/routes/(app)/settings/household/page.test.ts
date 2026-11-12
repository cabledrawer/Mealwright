// Settings → Household (0.9 A1): the people, adding one, the household's name and the
// "Who's this?" switch, for an admin and for a member (who sees it all and changes nothing).

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { goto } from '$app/navigation';
import { network } from '#lib/network.svelte.js';
import { household } from '#lib/people.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { JOSS, HOUSEHOLD, TESS, people, person } from '#lib/testing/fakePeople.js';
import Household from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const CHANGE = (id: number, kind: string, summary: string) => ({
  id,
  kind,
  summary,
  at: '2026-11-11T10:00:00Z',
  who: { login_id: 1, name: 'Tess' },
  lines: [],
  can_undo: true,
  undo_until: null,
  undone: null
});

describe('Settings → Household', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /people': [200, people()],
      'GET /household': [200, HOUSEHOLD],
      ...routes
    });
    component = mount(Household, { target: document.body });
    flushSync();
  }

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    household.forget();
    undoHistory.clear();
    toasts.dismiss();
    vi.mocked(goto).mockClear();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    household.forget();
    undoHistory.clear();
    toasts.dismiss();
  });

  it('lists everyone, with "(you)", their line and a link to each', async () => {
    open();
    await expect.element(page.getByRole('heading', { name: 'Household', level: 1 })).toBeVisible();
    await expect.element(page.getByLabelText('Household name')).toHaveValue('Our kitchen');
    const tess = page.getByRole('link', { name: /Tess \(you\)/ });
    await expect.element(tess).toHaveAttribute('href', '/settings/household/1');
    await expect.element(tess).toHaveTextContent('T Tess (you) Admin · signs in · 1 portion');
    await expect
      .element(page.getByRole('link', { name: /Joss/ }))
      .toHaveTextContent('J Joss Profile only · ½ portion');
    await expect.element(page.getByRole('button', { name: '+ Add a person' })).toBeVisible();
    await expect.element(page.getByRole('switch', { name: 'Ask “Who’s this?”' })).toBeEnabled();
  });

  it('adds a person and opens them, with Undo', async () => {
    const wren = person(4, 'Wren');
    open({
      'POST /people': [
        201,
        people([TESS, JOSS, wren], { change: CHANGE(50, 'person_added', 'Added Wren') })
      ]
    });
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await expect.element(page.getByLabelText('Name', { exact: true })).toHaveFocus();
    await userEvent.keyboard('Wren{Enter}');
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/settings/household/4'));
    expect(sent('POST', '/people')[0]!.body).toEqual({
      name: 'Wren',
      colour: null,
      portion_quarters: 4
    });
    expect(toasts.current?.message).toBe('Added Wren');
  });

  it('says why a person could not be added, and keeps the name', async () => {
    open({
      'POST /people': [409, { code: 'name_taken', detail: 'There’s already someone called Joss.' }]
    });
    await page.getByRole('button', { name: '+ Add a person' }).click();
    await userEvent.keyboard('joss{Enter}');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('There’s already someone called Joss.');
    await expect.element(page.getByLabelText('Name', { exact: true })).toHaveValue('joss');
    expect(goto).not.toHaveBeenCalled();
  });

  it('renames the household when the field is left', async () => {
    open({
      'PATCH /household': [200, { ...HOUSEHOLD, name: 'The flat' }],
      'GET /changes': [200, { changes: [CHANGE(51, 'household_renamed', 'Renamed the household')] }]
    });
    const field = page.getByLabelText('Household name');
    await field.fill('The flat');
    await userEvent.keyboard('{Tab}');
    await vi.waitFor(() => expect(sent('PATCH', '/household')).toHaveLength(1));
    expect(sent('PATCH', '/household')[0]!.body).toEqual({ name: 'The flat' });
    await vi.waitFor(() => expect(toasts.current?.message).toBe('Renamed the household'));
  });

  it('switches "Who\'s this?" on for shared logins', async () => {
    open({
      'PUT /people/ask-whos-this': [
        200,
        people(undefined, {
          ask_whos_this: true,
          change: CHANGE(52, 'whos_this_switch', 'Switched Ask “Who’s this?” on')
        })
      ]
    });
    const ask = page.getByRole('switch', { name: 'Ask “Who’s this?”' });
    await ask.click();
    await vi.waitFor(() => expect(sent('PUT', '/people/ask-whos-this')).toHaveLength(1));
    expect(sent('PUT', '/people/ask-whos-this')[0]!.body).toEqual({ on: true });
    await expect.element(ask).toBeChecked();
  });

  it('puts the switch back and says so when it could not be changed', async () => {
    open({ 'PUT /people/ask-whos-this': [500, { detail: 'Something broke.' }] });
    const ask = page.getByRole('switch', { name: 'Ask “Who’s this?”' });
    await ask.click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('Something broke.');
    await expect.element(ask).not.toBeChecked();
  });

  it('a member sees everyone and changes nothing', async () => {
    open({ 'GET /people': [200, people(undefined, { can_change: false })] });
    await expect.element(page.getByRole('link', { name: /Joss/ })).toBeVisible();
    await expect.element(page.getByLabelText('Household name')).toBeDisabled();
    await expect.element(page.getByRole('switch', { name: 'Ask “Who’s this?”' })).toBeDisabled();
    expect(page.getByRole('button', { name: '+ Add a person' }).query()).toBeNull();
    await expect
      .element(page.getByText('Only admins can add, change or remove people.', { exact: false }))
      .toBeVisible();
    // Nothing reads a person's portion yet, so the note doesn't say it decides amounts.
    await expect
      .element(
        page.getByText('Portions are kept for later: the plan and shopping list don’t', {
          exact: false
        })
      )
      .toBeVisible();
  });

  it('says it cannot be loaded, with Try again', async () => {
    open({ 'GET /people': [500, { detail: 'The server had a problem.' }] });
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('The server had a problem. Try again');
    await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  });
});
