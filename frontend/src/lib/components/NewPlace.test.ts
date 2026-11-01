import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Place } from '#lib/client/types.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import NewPlace from './NewPlace.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

describe('"+ Place"', () => {
  let component: ReturnType<typeof mount> | null = null;
  let added: Place[] = [];
  let cancelled = 0;

  beforeEach(() => {
    added = [];
    cancelled = 0;
    placesAndShops.forget();
    network.offline = false;
    component = mount(NewPlace, {
      target: document.body,
      props: { onadded: (p: Place) => added.push(p), oncancel: () => cancelled++ }
    });
    flushSync();
  });

  afterEach(() => {
    if (component) unmount(component);
    network.offline = false;
    vi.unstubAllGlobals();
  });

  it('asks for a name and "Kept cold?", with Cupboard chosen first', async () => {
    await expect.element(page.getByRole('textbox', { name: 'Place’s name' })).toHaveFocus();
    const group = page.getByRole('radiogroup', { name: 'Kept cold?' });
    await expect.element(group.getByRole('radio', { name: 'Cupboard' })).toBeChecked();
    await expect.element(group.getByRole('radio', { name: 'Fridge' })).not.toBeChecked();
    await expect.element(group.getByRole('radio', { name: 'Freezer' })).not.toBeChecked();
  });

  it('adds the place with the chosen kind and hands it back', async () => {
    const requests = fakeApi({
      'POST /places': [201, { id: 9, name: 'Garage freezer', kind: 'freezer' }]
    });
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('Garage freezer');
    await page.getByRole('radio', { name: 'Freezer' }).click();
    await page.getByRole('button', { name: 'Add place' }).click();
    await vi.waitFor(() => expect(added).toHaveLength(1));
    expect(added[0]).toEqual({ id: 9, name: 'Garage freezer', kind: 'freezer' });
    expect(requests[0]?.body).toEqual({ name: 'Garage freezer', kind: 'freezer' });
  });

  it('Enter adds it too', async () => {
    fakeApi({ 'POST /places': [201, { id: 9, name: 'Larder', kind: 'cupboard' }] });
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('Larder');
    await page.getByRole('textbox', { name: 'Place’s name' }).click();
    await userEvent.keyboard('{Enter}');
    await vi.waitFor(() => expect(added).toHaveLength(1));
  });

  it('a name the household has gives that place, so it is picked', async () => {
    fakeApi({
      'POST /places': [
        409,
        { code: 'place_exists', detail: 'x', place: { id: 1, name: 'Fridge', kind: 'fridge' } }
      ]
    });
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('fridge');
    await page.getByRole('button', { name: 'Add place' }).click();
    await vi.waitFor(() => expect(added).toEqual([{ id: 1, name: 'Fridge', kind: 'fridge' }]));
  });

  it('says why when the household already has 50 places, and picks nothing', async () => {
    const sentence =
      'You have 50 places, the most Mealwright keeps. Rename or remove one in Settings.';
    fakeApi({ 'POST /places': [409, { code: 'too_many_places', detail: sentence }] });
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('One too many');
    await page.getByRole('button', { name: 'Add place' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent(sentence);
    expect(added).toHaveLength(0);
  });

  it('needs a name', async () => {
    const requests = fakeApi({});
    await page.getByRole('button', { name: 'Add place' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('Type a name.');
    expect(requests).toHaveLength(0);
    expect(added).toHaveLength(0);
  });

  it('says it needs the server when offline, and sends nothing', async () => {
    const requests = fakeApi({});
    network.offline = true;
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('Shed');
    await page.getByRole('button', { name: 'Add place' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('A new place needs your Mealwright server. Try again when it answers.');
    expect(requests).toHaveLength(0);
    expect(added).toHaveLength(0);
  });

  it('says the same when the server cannot be reached', async () => {
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('Failed to fetch');
    });
    await page.getByRole('textbox', { name: 'Place’s name' }).fill('Shed');
    await page.getByRole('button', { name: 'Add place' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('A new place needs your Mealwright server. Try again when it answers.');
    expect(added).toHaveLength(0);
  });

  it('Cancel and Escape close it without adding', async () => {
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(cancelled).toBe(1);
    await page.getByRole('textbox', { name: 'Place’s name' }).click();
    await userEvent.keyboard('{Escape}');
    expect(cancelled).toBe(2);
    expect(added).toHaveLength(0);
  });

  it('Escape on Add place or Cancel closes only the box, and focus goes back to the picker (L4)', async () => {
    unmount(component!);
    component = null;
    document.body.replaceChildren();
    const picker = document.createElement('select');
    picker.setAttribute('aria-label', 'Where');
    document.body.append(picker);
    const outside: string[] = [];
    document.body.addEventListener('keydown', (e) => outside.push(e.key));
    for (const button of ['Add place', 'Cancel']) {
      picker.focus();
      component = mount(NewPlace, {
        target: document.body,
        props: { onadded: (p: Place) => added.push(p), oncancel: () => cancelled++ }
      });
      flushSync();
      await expect.element(page.getByRole('textbox', { name: 'Place’s name' })).toHaveFocus();
      (page.getByRole('button', { name: button }).element() as HTMLElement).focus();
      await userEvent.keyboard('{Escape}');
      expect(outside).not.toContain('Escape');
      await expect.element(page.getByLabelText('Where')).toHaveFocus();
      unmount(component);
      component = null;
    }
    expect(cancelled).toBe(2);
  });
});
