// Recent changes says who did a change when it wasn't you, and on a shared login it says the
// person picked in "Who's this?" (0.9 A1).

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { Change } from '#lib/client/types.js';
import { session } from '#lib/session.svelte.js';
import RecentChanges from './RecentChanges.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const change = (id: number, who: Change['who']): Change =>
  ({
    id,
    kind: 'used',
    summary: `Used ${id} g rice`,
    at: '2026-11-11T10:00:00Z',
    who,
    lines: [],
    can_undo: false,
    undone: null
  }) as unknown as Change;

describe('RecentChanges: who did it', () => {
  let component: ReturnType<typeof mount> | null = null;

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    session.me = null;
  });

  function show(changes: Change[]) {
    component = mount(RecentChanges, {
      target: document.body,
      props: { changes, onundo: () => {} }
    });
    flushSync();
  }

  it('names the person picked on a shared login, and nobody for your own', async () => {
    session.me = {
      id: 9,
      name: 'Kitchen tablet',
      username: 'tablet',
      role: 'member',
      theme: 'auto',
      member_id: 9,
      shared: true
    };
    show([
      change(1, { login_id: 9, name: 'Joss', member_id: 3 }),
      change(2, { login_id: 9, name: 'Kitchen tablet', member_id: 9 }),
      change(3, { login_id: 1, name: 'Tess', member_id: 1 })
    ]);
    await expect.element(page.getByText('· Joss')).toBeVisible();
    await expect.element(page.getByText('· Tess')).toBeVisible();
    expect(page.getByText('· Kitchen tablet').query()).toBeNull();
  });

  it('on a login of your own, your changes show no name', async () => {
    session.me = {
      id: 1,
      name: 'Tess',
      username: 'tess',
      role: 'admin',
      theme: 'auto',
      member_id: 1,
      shared: false
    };
    show([change(1, { login_id: 1, name: 'Tess', member_id: 1 })]);
    await expect.element(page.getByText('Used 1 g rice', { exact: false })).toBeVisible();
    expect(page.getByText('· Tess').query()).toBeNull();
  });
});
