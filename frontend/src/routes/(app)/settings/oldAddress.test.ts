// FE25/F263 (0.9.5-beta.3): the three Settings pages that moved answer at their old addresses
// by sending the person on, inside the app, to a place fixed by the page: never one read from
// the address (no open redirect), and only an anchor the new page has.

import { flushSync, mount, unmount, type Component } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { goto } from '$app/navigation';
import OldPerson from './household/[id]/+page.svelte';
import OldPeople from './household/+page.svelte';
import OldKitchen from './kitchen/+page.svelte';
import OldPrivacy from './privacy/+page.svelte';

const params = vi.hoisted(() => ({ id: '7' }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$app/state', () => ({ page: { params, url: new URL('http://x/') } }));

describe('old Settings addresses', () => {
  let component: ReturnType<typeof mount> | null = null;
  const before = location.pathname + location.search;

  function open(page: Component, tail = '') {
    history.replaceState(history.state, '', `${before}${tail}`);
    component = mount(page, { target: document.body });
    flushSync();
  }

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    history.replaceState(history.state, '', before);
    vi.mocked(goto).mockClear();
    params.id = '7';
  });

  it.each([
    [OldPrivacy, '/settings/outside-connections'],
    [OldPeople, '/settings/people'],
    [OldKitchen, '/settings/your-kitchen']
  ])('goes on to the new address, in place of the old one', async (page, to) => {
    open(page as Component);
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith(to, { replace: true }));
  });

  it('keeps an anchor of the new page, and nothing else from the old address', async () => {
    open(OldPrivacy, '?next=https://elsewhere.example/#your-own-network');
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/settings/outside-connections#your-own-network', {
        replace: true
      })
    );
  });

  it('drops an anchor the new page does not have', async () => {
    open(OldPrivacy, '#//elsewhere.example');
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/settings/outside-connections', { replace: true })
    );
  });

  it('never follows the query string', async () => {
    open(OldPeople, '?to=//elsewhere.example&next=/sign-in');
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/settings/people', { replace: true })
    );
  });

  it("a person's old page goes to their new one", async () => {
    open(OldPerson as Component);
    await vi.waitFor(() =>
      expect(goto).toHaveBeenCalledWith('/settings/people/7', { replace: true })
    );
  });

  it.each(['..', '7/../../sign-in', '%2F%2Felsewhere.example', 'x7'])(
    'an old person address that is not a number (%s) goes to the People list',
    async (id) => {
      params.id = id;
      open(OldPerson as Component);
      await vi.waitFor(() =>
        expect(goto).toHaveBeenCalledWith('/settings/people', { replace: true })
      );
    }
  );
});
