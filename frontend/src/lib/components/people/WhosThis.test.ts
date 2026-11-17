// The "Who's this?" sheet's last line: "Turn this off in Settings › People" only for an admin, who
// can open that page (a member isn't shown the Household pages, F252).

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import { session } from '#lib/session.svelte.js';
import { ME } from '#lib/testing/fakeShopping.js';
import WhosThis from './WhosThis.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let view: ReturnType<typeof mount> | undefined;

function open(role: 'admin' | 'member') {
  session.me = { ...ME, role };
  view = mount(WhosThis, { target: document.body, props: { onpick: () => {} } });
  flushSync();
  // The sheet is shut until the app asks; its words are in the page all the same.
  document.querySelector('dialog')?.setAttribute('open', '');
}

afterEach(() => {
  if (view) unmount(view);
  view = undefined;
  document.body.innerHTML = '';
});

describe('the Who’s this? sheet', () => {
  it('points an admin to Settings › People to turn it off', async () => {
    open('admin');
    await expect.element(page.getByText(/Turn this off in Settings › People\./)).toBeVisible();
  });

  it('does not point a member to a page they can’t open', async () => {
    open('member');
    await expect
      .element(page.getByText(/Asked again after 30 minutes without use\./))
      .toBeVisible();
    expect(document.body.textContent).not.toContain('Settings › People');
  });
});
