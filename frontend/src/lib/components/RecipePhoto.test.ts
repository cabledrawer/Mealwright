import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { PhotoOut } from '#lib/client/recipes.js';
import { network } from '#lib/network.svelte.js';
import RecipePhoto from './RecipePhoto.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const DISH =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGN4VqcERAwQCgAtxgYZHCtf2QAAAABJRU5ErkJggg==';

const photo = (extra: Partial<PhotoOut> = {}): PhotoOut => ({
  id: 5,
  width: 1600,
  height: 1200,
  url: DISH,
  list_width: 208,
  list_height: 156,
  list_url: '/api/v1/recipes/photos/5/list',
  ...extra
});

describe('the recipe page photo', () => {
  let component: ReturnType<typeof mount> | null = null;

  function open(props: { photo: PhotoOut | null; beside?: boolean }) {
    const target = document.body.appendChild(document.createElement('div'));
    component = mount(RecipePhoto, { target, props: { name: 'Sambar', ...props } });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
  });

  afterEach(() => {
    network.reset();
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
  });

  it('shows the large copy in a box 170 px tall with the recipe’s name in its words', async () => {
    open({ photo: photo() });
    const img = document.querySelector('img')!;
    expect(img.getAttribute('src')).toBe(DISH);
    expect(img.getAttribute('alt')).toBe('Photo of Sambar');
    expect(img.getAttribute('width')).toBe('1600');
    expect(img.getAttribute('height')).toBe('1200');
    await expect.poll(() => img.complete && img.naturalWidth).toBe(2);
    expect(getComputedStyle(img).objectFit).toBe('cover');
    const frame = document.querySelector('.frame')!;
    expect(frame.getBoundingClientRect().height).toBe(170);
    expect(getComputedStyle(frame).borderRadius).toBe('20px');
    // The picture fills the box exactly (cropped, not stretched).
    expect(img.getBoundingClientRect().height).toBe(170);
    expect(img.getBoundingClientRect().width).toBe(frame.getBoundingClientRect().width);
  });

  it('is at least 150 px tall beside the figures', () => {
    open({ photo: photo(), beside: true });
    const frame = document.querySelector('.frame')!;
    expect(frame.getBoundingClientRect().height).toBeGreaterThanOrEqual(150);
  });

  it('draws nothing at all without a photo', () => {
    open({ photo: null });
    expect(document.querySelector('.frame')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
  });

  it('draws nothing when the photo can’t be fetched', async () => {
    open({ photo: photo({ url: '/api/v1/recipes/photos/404/large' }) });
    await expect.poll(() => document.querySelector('.frame'), { timeout: 6000 }).toBeNull();
  });

  it('a late error from a photo already gone is ignored, not a crash', () => {
    const errors: unknown[] = [];
    const onError = (event: ErrorEvent) => errors.push(event.error);
    window.addEventListener('error', onError);
    try {
      open({ photo: photo({ url: DISH, list_url: DISH }) });
      const img = document.querySelector('img')!;
      // The first error drops the only copy (the list copy is the same address), so no photo
      // is shown; a second error still queued for that picture must find nothing to fail.
      img.dispatchEvent(new Event('error'));
      flushSync();
      expect(document.querySelector('.frame')).toBeNull();
      img.dispatchEvent(new Event('error'));
      flushSync();
    } finally {
      window.removeEventListener('error', onError);
    }
    expect(errors).toEqual([]);
  });

  it('an error fails the address the picture tried, not the photo shown by then', () => {
    open({ photo: photo({ url: DISH, list_url: '/api/v1/recipes/photos/5/list' }) });
    const img = document.querySelector('img')!;
    // An error that arrives for an earlier address (the photo was replaced meanwhile) must not
    // mark the large copy that is shown now as failed.
    img.setAttribute('src', '/api/v1/recipes/photos/4/large');
    img.dispatchEvent(new Event('error'));
    flushSync();
    expect(document.querySelector('img')!.getAttribute('width')).toBe('1600');
  });

  it('shows the list copy when only the large copy can’t be fetched', async () => {
    open({ photo: photo({ url: '/api/v1/recipes/photos/404/large', list_url: DISH }) });
    await expect
      .poll(() => document.querySelector('img')?.getAttribute('src'), { timeout: 6000 })
      .toBe(DISH);
    const img = document.querySelector('img')!;
    expect(img.getAttribute('alt')).toBe('Photo of Sambar');
    expect(img.getAttribute('width')).toBe('208');
    expect(img.getAttribute('height')).toBe('156');
    await expect.poll(() => img.complete && img.naturalWidth).toBe(2);
    expect(document.querySelector('.frame')!.getBoundingClientRect().height).toBe(170);
  });

  it('tries a failed photo again when the connection comes back', async () => {
    const missing = '/api/v1/recipes/photos/404/large';
    open({ photo: photo({ url: missing }) });
    await expect.poll(() => document.querySelector('.frame'), { timeout: 6000 }).toBeNull();
    network.failed();
    network.succeeded();
    flushSync();
    expect(document.querySelector('img')?.getAttribute('src')).toBe(missing);
    await expect.poll(() => document.querySelector('.frame'), { timeout: 6000 }).toBeNull();
  });
});

describe('the photo full size (F29)', () => {
  let component: ReturnType<typeof mount> | null = null;

  beforeEach(async () => {
    await page.viewport(390, 844);
    const target = document.body.appendChild(document.createElement('div'));
    component = mount(RecipePhoto, { target, props: { name: 'Sambar', photo: photo() } });
    flushSync();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
  });

  it('names the recipe in the button’s words, and the picture keeps its own (L2)', async () => {
    await expect
      .element(page.getByRole('button', { name: 'Show the photo of Sambar full size' }))
      .toBeVisible();
    await expect.element(page.getByRole('img', { name: 'Photo of Sambar' })).toBeInTheDocument();
  });

  it('opens when the photo is tapped, with a Close button', async () => {
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    await page.getByRole('button', { name: 'Show the photo of Sambar full size' }).click();
    await expect.element(page.getByRole('dialog', { name: 'Photo of Sambar' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Close' })).toBeVisible();
  });

  it('closes with Escape, and focus goes back to the photo', async () => {
    const opener = page.getByRole('button', { name: 'Show the photo of Sambar full size' });
    await opener.click();
    await expect.element(page.getByRole('dialog')).toBeVisible();
    await userEvent.keyboard('{Escape}');
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(opener.element());
  });

  it('closes with a tap on the photo, and with Close', async () => {
    const opener = page.getByRole('button', { name: 'Show the photo of Sambar full size' });
    await opener.click();
    await page.getByRole('dialog').getByRole('img').click();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
    await opener.click();
    await page.getByRole('button', { name: 'Close' }).click();
    await expect.element(page.getByRole('dialog')).not.toBeInTheDocument();
  });
});
