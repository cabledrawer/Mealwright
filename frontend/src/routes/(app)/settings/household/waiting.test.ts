// "Who is this?" on Settings → Household (0.9.5 Pe3/M2, mockup Dark-HouseholdWaiting095-Phone):
// a single sign-on sign-in that matches nobody waits until an admin links it to a person, makes
// a new person for it, or refuses it (cabledrawer 13 Nov). A member never sees it.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Person, WaitingSignIn } from '#lib/client/people.js';
import { network } from '#lib/network.svelte.js';
import { household } from '#lib/people.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { HOUSEHOLD, people, person } from '#lib/testing/fakePeople.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Household from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));

const login = (username: string, role: 'admin' | 'member' = 'member') => ({
  username,
  role,
  shared: false,
  has_password: false,
  signs_in: true,
  link_pending: false,
  link_used_at: null,
  reset_pending: false
});

const SAM = person(1, 'Sam', { is_me: true, login: login('sam', 'admin') });
const LORNA = person(2, 'Lorna', { colour: 'violet', login: login('lorna') });
const NOOR = person(3, 'Noor', { colour: 'amber', portion_quarters: 2 });
const TODAY_2010 = new Date();
TODAY_2010.setHours(20, 10, 0, 0);
const WAITING: WaitingSignIn = {
  id: 7,
  username: 'lorna.s',
  signed_in_at: TODAY_2010.toISOString(),
  role: 'member'
};
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

describe('"Who is this?" on Settings → Household', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(list: Person[], waiting: WaitingSignIn[], routes = {}, canChange = true) {
    requests = fakeApi({
      'GET /people': [200, people(list, { can_change: canChange, waiting })],
      'GET /household': [200, { ...HOUSEHOLD, time_zone: ZONE }],
      ...routes
    });
    component = mount(Household, { target: document.body });
    flushSync();
  }

  const sent = (path: string) => requests.filter((r) => r.method === 'POST' && r.path === path);

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    household.forget();
    undoHistory.clear();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    network.reset();
    household.forget();
    undoHistory.clear();
  });

  it('shows the waiting sign-in, and links it to the person picked', async () => {
    const linked = { ...LORNA, login: { ...login('lorna'), sso_linked: true } };
    open([SAM, LORNA, NOOR], [WAITING], {
      'POST /people/sso-accounts/7/link': [200, people([SAM, linked, NOOR], { waiting: [] })]
    });
    await expect.element(page.getByText('1 sign-in waiting')).toBeVisible();
    await expect
      .element(
        page.getByText(
          'lorna.s signed in with single sign-on at 20:10 and doesn’t match anyone here.'
        )
      )
      .toBeVisible();
    await page.getByRole('button', { name: 'Who is this?' }).click();
    const sheet = page.getByRole('dialog', { name: 'Who is lorna.s?' });
    await expect.element(sheet).toBeVisible();
    await expect
      .element(sheet.getByText(/^Signed in with single sign-on today at 20:10\./))
      .toBeVisible();
    // The admin herself isn't offered: the sign-in server's groups don't make lorna.s an admin.
    const picks = sheet.getByRole('radio');
    // The avatar's letter is hidden from the name, as on the people list.
    await expect.element(picks.nth(0)).toHaveAccessibleName('Lorna username lorna');
    await expect.element(picks.nth(1)).toHaveAccessibleName('Noor no login');
    await expect.element(picks.nth(2)).toHaveAccessibleName('A new person');
    expect(picks.all()).toHaveLength(3);
    await expect.element(sheet.getByRole('button', { name: 'Choose who it is' })).toBeDisabled();
    await picks.nth(0).click();
    await sheet.getByRole('button', { name: 'Link to Lorna' }).click();
    await vi.waitFor(() => expect(sent('/people/sso-accounts/7/link')).toHaveLength(1));
    expect(sent('/people/sso-accounts/7/link')[0]!.body).toEqual({ member_id: 2 });
    await expect.element(page.getByText('1 sign-in waiting')).not.toBeInTheDocument();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
  });

  it('a new person sends no person, and arrows move through the picks', async () => {
    open([SAM, LORNA, NOOR], [WAITING], {
      'POST /people/sso-accounts/7/link': [200, people([SAM, LORNA, NOOR], { waiting: [] })]
    });
    await page.getByRole('button', { name: 'Who is this?' }).click();
    await expect.element(page.getByRole('radio', { name: /Lorna/ })).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}{ArrowDown}');
    await expect.element(page.getByRole('radio', { name: 'A new person' })).toBeChecked();
    await page.getByRole('button', { name: 'Add a new person' }).click();
    await vi.waitFor(() => expect(sent('/people/sso-accounts/7/link')).toHaveLength(1));
    expect(sent('/people/sso-accounts/7/link')[0]!.body).toEqual({ member_id: null });
  });

  it('refuses it, and says the server’s refusal of a link in the sheet', async () => {
    open([SAM, LORNA, NOOR], [WAITING], {
      'POST /people/sso-accounts/7/link': [
        409,
        {
          code: 'linked_already',
          detail:
            'Lorna is linked to another account at your sign-in server. Unlink it on their page first.'
        }
      ],
      'POST /people/sso-accounts/7/refuse': [200, people([SAM, LORNA, NOOR], { waiting: [] })]
    });
    await page.getByRole('button', { name: 'Who is this?' }).click();
    await page.getByRole('radio', { name: /Lorna/ }).click();
    await page.getByRole('button', { name: 'Link to Lorna' }).click();
    await expect
      .element(page.getByRole('dialog').getByRole('alert'))
      .toHaveTextContent(
        'Lorna is linked to another account at your sign-in server. Unlink it on their page first.'
      );
    await page.getByRole('button', { name: 'Not someone I know: refuse' }).click();
    await vi.waitFor(() => expect(sent('/people/sso-accounts/7/refuse')).toHaveLength(1));
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    await expect.element(page.getByText('1 sign-in waiting')).not.toBeInTheDocument();
  });

  it('counts more than one, and a member sees none of it', async () => {
    const noorK = { ...WAITING, id: 8, username: 'noor.k' };
    open([SAM, LORNA, NOOR], [noorK, WAITING]);
    await expect.element(page.getByText('2 sign-ins waiting')).toBeVisible();
    await page.getByRole('button', { name: 'Who is this?' }).click();
    await expect.element(page.getByRole('dialog', { name: 'Who is noor.k?' })).toBeVisible();
    if (component) unmount(component);
    document.body.innerHTML = '';
    household.forget();
    open([SAM, LORNA, NOOR], [], {}, false);
    await expect.element(page.getByText('Lorna')).toBeVisible();
    await expect.element(page.getByText(/sign-ins? waiting/)).not.toBeInTheDocument();
    await expect
      .element(page.getByRole('button', { name: 'Who is this?' }))
      .not.toBeInTheDocument();
  });
});
