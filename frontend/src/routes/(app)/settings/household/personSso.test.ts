// The Person page's "Single sign-on" row (0.9.5 Pe3/M2, mockup Dark-Person095-Phone): an admin
// sees whether the person is linked to an account at the sign-in server, unlinks them, or links
// them by hand to a sign-in that is waiting. Not shown to a member, nor when single sign-on
// isn't set up, nor for a shared login.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Person, PersonLogin, WaitingSignIn } from '#lib/client/people.js';
import { network } from '#lib/network.svelte.js';
import { household } from '#lib/people.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { HOUSEHOLD, people, person } from '#lib/testing/fakePeople.js';
import { undoHistory } from '#lib/undo.svelte.js';
import PersonPage from './[id]/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const params = vi.hoisted(() => ({ id: '2' }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$app/state', () => ({ page: { params, url: new URL('http://x/') } }));

const login = (username: string, extra: Partial<PersonLogin> = {}): PersonLogin => ({
  username,
  role: 'member',
  shared: false,
  has_password: false,
  signs_in: true,
  link_pending: false,
  link_used_at: null,
  reset_pending: false,
  ...extra
});

const SAM = person(1, 'Sam', { is_me: true, login: login('sam', { role: 'admin' }) });
const LORNA = person(2, 'Lorna', {
  colour: 'violet',
  login: login('lorna', { sso_linked: true, sso_username: 'lorna.s' })
});
const NOOR = person(2, 'Noor', { colour: 'amber', login: login('noor') });
const TODAY_2010 = new Date();
TODAY_2010.setHours(20, 10, 0, 0);
const WAITING: WaitingSignIn = {
  id: 7,
  username: 'noor.k',
  signed_in_at: TODAY_2010.toISOString(),
  role: 'member'
};
const ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
const NOT_LINKED =
  'Not linked. Linked automatically when the sign-in server’s username is the same as here; otherwise link by hand.';

describe('Single sign-on on the Person page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(
    list: Person[],
    extra: Parameters<typeof people>[1] = {},
    routes: Parameters<typeof fakeApi>[0] = {}
  ) {
    requests = fakeApi({
      'GET /people': [200, people(list, { single_sign_on: true, ...extra })],
      'GET /household': [200, { ...HOUSEHOLD, time_zone: ZONE }],
      ...routes
    });
    component = mount(PersonPage, { target: document.body });
    flushSync();
  }

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  beforeEach(async () => {
    await page.viewport(390, 844);
    params.id = '2';
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

  it('says who a linked person is at the sign-in server, and Unlink unlinks them', async () => {
    const unlinked = { ...LORNA, login: login('lorna', { sso_linked: false }) };
    open(
      [SAM, LORNA],
      {},
      { 'DELETE /people/2/sso': [200, people([SAM, unlinked], { single_sign_on: true })] }
    );
    await expect.element(page.getByText('Single sign-on')).toBeVisible();
    const line = page.getByText('Linked to lorna.s on your sign-in server');
    await expect.element(line).toBeVisible();
    await expect.element(line.getByText('lorna.s')).toHaveProperty('tagName', 'STRONG');
    await page.getByRole('button', { name: 'Unlink' }).click();
    await expect.element(page.getByText(NOT_LINKED)).toBeVisible();
    expect(sent('DELETE', '/people/2/sso')).toHaveLength(1);
    await expect.element(page.getByRole('button', { name: 'Link…' })).toBeVisible();
  });

  it('shows the server’s refusal to unlink the last admin who can sign in', async () => {
    const detail =
      'Lorna is the household’s only admin who can sign in, and only with single sign-on. Make someone else an admin first, or set a password for Lorna.';
    open(
      [SAM, LORNA],
      {},
      { 'DELETE /people/2/sso': [409, { code: 'last_admin', detail, status: 409 }] }
    );
    await page.getByRole('button', { name: 'Unlink' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent(detail);
    await expect.element(page.getByText('Linked to lorna.s on your sign-in server')).toBeVisible();
  });

  it('Link… links the person to the waiting sign-in picked', async () => {
    const linked = { ...NOOR, login: login('noor', { sso_linked: true, sso_username: 'noor.k' }) };
    open(
      [SAM, NOOR],
      { waiting: [WAITING] },
      {
        'POST /people/sso-accounts/7/link': [
          200,
          people([SAM, linked], { waiting: [], single_sign_on: true })
        ]
      }
    );
    await expect.element(page.getByText(NOT_LINKED)).toBeVisible();
    await page.getByRole('button', { name: 'Link…' }).click();
    const sheet = page.getByRole('dialog', { name: 'Link Noor to a sign-in' });
    await expect.element(sheet).toBeVisible();
    const button = sheet.getByRole('button', { name: 'Choose a sign-in' });
    await expect.element(button).toBeDisabled();
    const pick = sheet.getByRole('radio', { name: /noor\.k/ });
    await expect.element(pick).toHaveTextContent('noor.k signed in today at 20:10');
    await pick.click();
    await sheet.getByRole('button', { name: 'Link to noor.k' }).click();
    await expect.element(sheet).not.toBeInTheDocument();
    expect(sent('POST', '/people/sso-accounts/7/link')[0]!.body).toEqual({ member_id: 2 });
    await expect.element(page.getByText('Linked to noor.k on your sign-in server')).toBeVisible();
  });

  it('Link… with nobody waiting says how to get a sign-in to link, and Esc closes it', async () => {
    open([SAM, NOOR]);
    const link = page.getByRole('button', { name: 'Link…' });
    await link.click();
    const sheet = page.getByRole('dialog', { name: 'Link Noor to a sign-in' });
    await expect
      .element(
        sheet.getByText(
          'Nobody is waiting. Ask Noor to sign in with single sign-on: their sign-in then waits here for you to link it.'
        )
      )
      .toBeVisible();
    await userEvent.keyboard('{Escape}');
    await expect.element(sheet).not.toBeInTheDocument();
    await expect.element(link).toHaveFocus();
  });

  it('an admin’s login is offered only sign-ins the groups make an admin', async () => {
    const admin = person(2, 'Noor', { login: login('noor', { role: 'admin' }) });
    const asAdmin = { ...WAITING, id: 8, username: 'noor.admin', role: 'admin' as const };
    open([SAM, admin], { waiting: [WAITING, asAdmin] });
    await page.getByRole('button', { name: 'Link…' }).click();
    const sheet = page.getByRole('dialog', { name: 'Link Noor to a sign-in' });
    await expect.element(sheet.getByRole('radio', { name: /noor\.admin/ })).toBeVisible();
    await expect.element(sheet.getByRole('radio', { name: /noor\.k/ })).not.toBeInTheDocument();
  });

  it('is not shown to a member, without single sign-on set up, or for a shared login', async () => {
    open([SAM, LORNA], { can_change: false, single_sign_on: false });
    await expect.element(page.getByRole('heading', { name: 'Lorna', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Single sign-on')).not.toBeInTheDocument();
    unmount(component!);
    household.forget();
    open([SAM, LORNA], { single_sign_on: false });
    await expect.element(page.getByRole('heading', { name: 'Lorna', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Single sign-on')).not.toBeInTheDocument();
    unmount(component!);
    household.forget();
    const tablet = person(2, 'Tablet', { login: login('tablet', { shared: true }) });
    open([SAM, tablet]);
    await expect.element(page.getByRole('heading', { name: 'Tablet', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Single sign-on')).not.toBeInTheDocument();
  });
});
