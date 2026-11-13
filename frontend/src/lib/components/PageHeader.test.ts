// The page header's back link: it can name a section of the parent page (L5, whole-0.9 review), so
// "‹ Sign-in" lands on Settings' Sign-in section, not the top of Settings.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import PageHeader from './PageHeader.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

describe('PageHeader back link', () => {
  it('goes to the parent page, and to the named section of it when there is one', async () => {
    await page.viewport(428, 900);
    component = mount(PageHeader, {
      target: document.body,
      props: {
        title: 'API tokens',
        parent: { href: '/(app)/settings', label: 'Sign-in', section: 'sign-in' }
      }
    });
    flushSync();
    const back = page.getByRole('link', { name: 'Sign-in' }).first();
    await expect.element(back).toHaveAttribute('href', '/settings?section=sign-in');
  });

  it('is the plain parent address without a section', async () => {
    await page.viewport(428, 900);
    component = mount(PageHeader, {
      target: document.body,
      props: { title: 'Privacy', parent: { href: '/(app)/settings', label: 'Settings' } }
    });
    flushSync();
    await expect
      .element(page.getByRole('link', { name: 'Settings' }).first())
      .toHaveAttribute('href', '/settings');
  });
});
