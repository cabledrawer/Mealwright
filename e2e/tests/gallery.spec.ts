// The component gallery exists only in development builds (spec "Keeping the UI good",
// item 3). The built app must hold none of it, and /dev/gallery there must be "not found".
// ./check's "image: no gallery" step does the same search inside the Docker image.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from './clock.ts';

const FRONTEND = join(import.meta.dirname, '..', '..', 'frontend');
const PAGE = join(FRONTEND, 'src', 'routes', 'dev', 'gallery', 'Gallery.svelte');

/** The marker text and a sentence from the gallery page, read from its source. */
function galleryText(): string[] {
  const source = readFileSync(PAGE, 'utf8');
  const marker = /MARKER = '([^']+)'/.exec(source)?.[1];
  const sentence = /Development builds only\. Every shared component/.exec(source)?.[0];
  expect(marker, 'the gallery page has its marker').toBeTruthy();
  expect(sentence, 'the gallery page has its intro sentence').toBeTruthy();
  return [marker!, sentence!];
}

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else yield path;
  }
}

test('the built web app contains no gallery code', () => {
  const needles = galleryText();
  const text = /\.(js|css|html|json|webmanifest|svg)$/;
  let looked = 0;
  for (const file of walk(join(FRONTEND, 'build'))) {
    if (!text.test(file)) continue;
    looked++;
    const content = readFileSync(file, 'utf8');
    for (const needle of needles) {
      expect(content.includes(needle), `${file} must not contain "${needle}"`).toBe(false);
    }
  }
  expect(looked, 'searched the build').toBeGreaterThan(20);
});

test('/dev/gallery in the built app is not the gallery', async ({ page }) => {
  const response = await page.goto('/dev/gallery');
  // The backend serves the app for every page; the app itself says "not found".
  expect(response?.ok()).toBe(true);
  await expect(page.getByText('Not found')).toBeVisible();
  await expect(page.locator('[data-gallery]')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Component gallery' })).toHaveCount(0);
});
