import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { SERVER_DOWN_TRY_LATER } from '#lib/downWords.js';
import { network } from '#lib/network.svelte.js';
import { newIngredient } from '#lib/newIngredient.svelte.js';
import NewIngredient from './NewIngredient.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

// F130: Shopping only chooses, so it works with the server down; the callers that make the
// ingredient on the server keep Add off and say why.
describe('"Pantry keeps it by" with the server down', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(() => {
    // The server is really down: the sheet's "how is it counted?" guess fails too. Left to
    // reach the test server, its answer would mark the network as back and enable Add.
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    network.offline = true;
    network.deviceOffline = false;
    component = mount(NewIngredient, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    newIngredient.cancel();
    if (component) unmount(component);
    network.offline = false;
    network.deviceOffline = false;
    vi.unstubAllGlobals();
  });

  it('choose mode (Shopping): Add works and hands the choice back', async () => {
    const answer = newIngredient.choose('Curry leaves');
    await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    expect(await answer).toMatchObject({ name: 'Curry leaves', counted_as: 'weight' });
  });

  it('ask mode (makes it on the server): Add is off and says why under the button', async () => {
    void newIngredient.ask('Curry leaves');
    await expect.element(page.getByRole('button', { name: 'Add', exact: true })).toBeDisabled();
    await expect.element(page.getByText(SERVER_DOWN_TRY_LATER)).toBeVisible();
  });
});
