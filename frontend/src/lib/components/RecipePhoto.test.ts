import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
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
    await expect.poll(() => document.querySelector('.frame')).toBeNull();
  });

  it('shows the list copy when only the large copy can’t be fetched', async () => {
    open({ photo: photo({ url: '/api/v1/recipes/photos/404/large', list_url: DISH }) });
    await expect.poll(() => document.querySelector('img')?.getAttribute('src')).toBe(DISH);
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
    await expect.poll(() => document.querySelector('.frame')).toBeNull();
    network.failed();
    network.succeeded();
    flushSync();
    expect(document.querySelector('img')?.getAttribute('src')).toBe(missing);
    await expect.poll(() => document.querySelector('.frame')).toBeNull();
  });
});
