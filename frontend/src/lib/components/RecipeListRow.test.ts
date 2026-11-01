import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import type { PhotoOut, RecipeRow } from '#lib/client/recipes.js';
import { network } from '#lib/network.svelte.js';
import RecipeListRow from './RecipeListRow.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

/** A 2 × 2 pixel PNG, so a photo really loads in the test. */
const DISH =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGN4VqcERAwQCgAtxgYZHCtf2QAAAABJRU5ErkJggg==';

const photo = (extra: Partial<PhotoOut> = {}): PhotoOut => ({
  id: 5,
  width: 1600,
  height: 1200,
  url: '/api/v1/recipes/photos/5/large',
  list_width: 208,
  list_height: 156,
  list_url: DISH,
  ...extra
});

const row = (extra: Partial<RecipeRow> = {}): RecipeRow => ({
  id: 1,
  name: 'Sambar',
  description: null,
  makes: null,
  photo: null,
  version: 1,
  time_minutes: 50,
  serves: 4,
  tags: [],
  ingredient_count: 7,
  kcal: 320,
  stock: null,
  use_soon: null,
  stock_unchecked: false,
  ...extra
});

describe('a recipe row', () => {
  let component: ReturnType<typeof mount> | null = null;

  function open(recipe: RecipeRow, pane = false) {
    const target = document.body.appendChild(document.createElement('div'));
    component = mount(RecipeListRow, { target, props: { recipe, pane } });
    flushSync();
  }

  const square = () => document.querySelector<HTMLElement>('.square')!;
  const pictures = () => document.querySelectorAll('img');

  beforeEach(async () => {
    await page.viewport(390, 844);
  });

  afterEach(() => {
    network.reset();
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
  });

  it('fills the square with the small copy of the photo', async () => {
    open(row({ photo: photo() }));
    const img = pictures()[0]!;
    expect(pictures().length).toBe(1);
    expect(img.getAttribute('src')).toBe(DISH);
    // Decorative (the row says the name), sized so nothing jumps, and lazy.
    expect(img.getAttribute('alt')).toBe('');
    expect(img.getAttribute('width')).toBe('208');
    expect(img.getAttribute('height')).toBe('156');
    expect(img.getAttribute('loading')).toBe('lazy');
    await expect.poll(() => img.complete && img.naturalWidth).toBe(2);
    // Cropped to fill the 52 px square, never stretched.
    expect(getComputedStyle(img).objectFit).toBe('cover');
    const box = img.getBoundingClientRect();
    expect([box.width, box.height]).toEqual([52, 52]);
    expect(getComputedStyle(square()).overflow).toBe('hidden');
  });

  it('keeps the plain square when there is no photo', () => {
    open(row());
    expect(pictures().length).toBe(0);
    const box = square().getBoundingClientRect();
    expect([box.width, box.height]).toEqual([52, 52]);
  });

  it('goes back to the plain square when the photo can’t be fetched', async () => {
    open(row({ photo: photo({ list_url: '/api/v1/recipes/photos/404/list' }) }));
    await expect.poll(() => pictures().length).toBe(0);
    const box = square().getBoundingClientRect();
    expect([box.width, box.height]).toEqual([52, 52]);
  });

  it('an error fails the address the picture tried, not the photo shown by then', () => {
    open(row({ photo: photo() }));
    const img = pictures()[0]!;
    // An error that arrives for an earlier address (the photo was replaced meanwhile) must not
    // take away the photo shown now.
    img.setAttribute('src', '/api/v1/recipes/photos/4/list');
    img.dispatchEvent(new Event('error'));
    flushSync();
    expect(pictures().length).toBe(1);
  });

  it('tries a failed photo again when the connection comes back', async () => {
    const missing = '/api/v1/recipes/photos/404/list';
    open(row({ photo: photo({ list_url: missing }) }));
    await expect.poll(() => pictures().length).toBe(0);
    // No second try while nothing has changed.
    await new Promise((done) => setTimeout(done, 100));
    expect(pictures().length).toBe(0);
    network.failed();
    network.succeeded();
    flushSync();
    expect(pictures()[0]?.getAttribute('src')).toBe(missing);
    // Still missing: back to the plain square, until the next time.
    await expect.poll(() => pictures().length).toBe(0);
  });

  it('centres the square beside a short name', () => {
    open(row());
    const link = document.querySelector('a')!.getBoundingClientRect();
    const box = square().getBoundingClientRect();
    expect(link.height).toBe(72);
    expect(box.top - link.top).toBe(link.bottom - box.bottom);
  });

  it('keeps the square at the top when the name wraps', () => {
    open(row({ name: 'Spiced roasted cauliflower with tahini and pomegranate seeds '.repeat(3) }));
    const link = document.querySelector('a')!.getBoundingClientRect();
    const box = square().getBoundingClientRect();
    expect(link.height).toBeGreaterThan(110);
    expect(box.top - link.top).toBe(10);
  });
});
