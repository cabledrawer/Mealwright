import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import ErrorPage from './+error.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// A page whose code can't be fetched (F86): the app's own error page, never a bare "500".
describe('the error page inside the app', () => {
  let component: ReturnType<typeof mount> | null = null;

  const open = () => {
    component = mount(ErrorPage, { target: document.body });
    flushSync();
  };

  beforeEach(() => {
    network.reset();
    // The server doesn't answer.
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('', { status: 502 })));
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  it('server not answering: the Can’t reach note, with Try again and Shopping', async () => {
    open();
    await expect
      .element(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' }))
      .toBeVisible();
    await expect
      .element(page.getByText(/This page isn’t on this device yet\. Try again when it answers\./))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Try again' })).toBeVisible();
    await expect
      .element(page.getByRole('link', { name: 'Shopping' }))
      .toHaveAttribute('href', '/shopping');
    expect(document.body.textContent).not.toMatch(/500|Internal Error/);
  });

  it('no network on the device: the offline words', async () => {
    network.deviceOffline = true;
    open();
    await expect.element(page.getByRole('heading', { name: 'You’re offline.' })).toBeVisible();
    await expect.element(page.getByText(/Try again when you’re back online\./)).toBeVisible();
  });

  it('the server answers and the page still failed: a plain line, never a code', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('{}', { status: 200 })));
    open();
    await expect
      .element(page.getByRole('heading', { name: 'Something went wrong.' }))
      .toBeVisible();
    await expect.element(page.getByText('This page didn’t open. Try again.')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/500|Internal Error/);
  });

  it('says nothing wrong first: until the server has been asked, no “Something went wrong.”', async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', () => new Promise<Response>((done) => (answer = done)));
    open();
    await new Promise((done) => setTimeout(done, 100));
    expect(document.body.textContent).not.toMatch(/Something went wrong/);
    answer(new Response('', { status: 502 }));
    await expect
      .element(page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' }))
      .toBeVisible();
  });

  it('moves focus to the note when it first appears, so it is announced', async () => {
    open();
    const title = page.getByRole('heading', { name: 'Can’t reach your Mealwright server.' });
    await expect.element(title).toBeVisible();
    await vi.waitFor(() => expect(document.activeElement?.id).toBe('error-title'));
  });
});
