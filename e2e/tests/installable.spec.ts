import { test, expect, type Page } from './clock.ts';
import { setAccountTheme } from './a11y.ts';

// The installable app (0.3, PR 5): manifest, icons, theme colour and the service worker
// (sync protocol 11.6, spec "App updates"), against the real server.

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, 'auto');
});

test('the manifest names the app and its icons, and is served as a manifest', async ({
  page,
  request,
}) => {
  await page.goto('/');
  const href = await page.locator('link[rel="manifest"]').getAttribute('href');
  expect(href).toBe('/manifest.webmanifest');
  const response = await request.get('/manifest.webmanifest');
  expect(response.headers()['content-type']).toContain('application/manifest+json');
  const manifest = await response.json();
  expect(manifest).toMatchObject({
    name: 'Mealwright',
    short_name: 'Mealwright',
    start_url: '/',
    display: 'standalone',
  });
  const sizes = manifest.icons.map(
    (i: { sizes: string; purpose: string }) => `${i.sizes} ${i.purpose}`,
  );
  expect(sizes).toEqual(expect.arrayContaining(['192x192 any', '512x512 any', '512x512 maskable']));
  for (const icon of manifest.icons as { src: string; sizes: string }[]) {
    const image = await request.get(icon.src);
    expect(image.status()).toBe(200);
    expect(image.headers()['content-type']).toBe('image/png');
    // A PNG's width and height sit at bytes 16 to 23.
    const bytes = await image.body();
    const [w, h] = [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
    expect(`${w}x${h}`).toBe(icon.sizes);
  }
  const apple = await page.locator('link[rel="apple-touch-icon"]').getAttribute('href');
  const touch = await request.get(apple!);
  expect(touch.status()).toBe(200);
  expect(touch.headers()['content-type']).toBe('image/png');
  expect(((await touch.body()) as Buffer).readUInt32BE(16)).toBe(180);
});

test('the browser bar colour follows the page, light or dark', async ({ page }) => {
  await page.goto('/');
  const colour = () => page.locator('meta[name="theme-color"]').getAttribute('content');
  await page.emulateMedia({ colorScheme: 'light' });
  await expect.poll(colour).toBe('#f5f6f4');
  await page.emulateMedia({ colorScheme: 'dark' });
  await expect.poll(colour).toBe('#111614');
  // A manual choice wins over the device, at start-up and while using the app.
  await setAccountTheme(page, 'light');
  await page.reload();
  await expect.poll(colour).toBe('#f5f6f4');
  await setAccountTheme(page, 'auto');
});

async function underWorker(page: Page) {
  await page.goto('/shopping');
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  await page.reload(); // the first page load is not under the worker; this one is
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
}

test('the service worker keeps only the app, never /api, and leaves the live stream alone', async ({
  page,
}) => {
  const answers: { url: string; fromWorker: boolean }[] = [];
  page.on('response', (r) => answers.push({ url: new URL(r.url()).pathname, fromWorker: r.fromServiceWorker() }));
  await underWorker(page);
  // Use the app a little: lists, pantry, the stream.
  await page.goto('/pantry');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Pantry');
  // Kept: collects every request the app makes in a while; absence of others can only be waited out.
  await page.waitForTimeout(1000);

  const api = answers.filter((a) => a.url.startsWith('/api/'));
  expect(api.length).toBeGreaterThan(0);
  expect(api.map((a) => a.url)).toContain('/api/v1/events');
  expect(api.filter((a) => a.fromWorker), 'no API answer comes from the worker').toEqual([]);
  // The app's own files do come from it (so the app opens offline).
  expect(answers.some((a) => a.fromWorker && a.url.startsWith('/_app/'))).toBe(true);

  const cached = await page.evaluate(async () => {
    const out: Record<string, string[]> = {};
    for (const name of await caches.keys()) {
      out[name] = (await (await caches.open(name)).keys()).map((r) => new URL(r.url).pathname);
    }
    return out;
  });
  const names = Object.keys(cached);
  expect(names.length).toBe(1);
  expect(names[0]).toMatch(/^mealwright-app-/);
  const kept = cached[names[0]!]!;
  expect(kept).toContain('/index.html');
  expect(kept.some((p) => p.startsWith('/_app/immutable/'))).toBe(true);
  expect(kept.filter((p) => p === '/api' || p.startsWith('/api/'))).toEqual([]);
});

test('offline, the app’s own files still load but the API is never answered from a cache', async ({
  page,
  context,
}) => {
  test.skip(test.info().project.use.browserName === 'webkit', "Playwright's WebKit offline switch blocks requests before the service worker sees them (proved 25 Oct); the iPhone hand test covers offline Safari");
  await underWorker(page);
  await context.setOffline(true);
  const result = await page.evaluate(async () => {
    const own = await fetch('/theme.js').then((r) => r.ok);
    const api = await fetch('/api/v1/version').then(
      () => 'answered',
      () => 'failed',
    );
    return { own, api };
  });
  expect(result).toEqual({ own: true, api: 'failed' });
  await context.setOffline(false);
});

test('a new version never takes over by itself (no skipWaiting, no claim, no reload)', async ({
  request,
}) => {
  const response = await request.get('/service-worker.js');
  expect(response.headers()['cache-control']).toBe('no-cache');
  const code = await response.text();
  expect(code).not.toContain('skipWaiting');
  expect(code).not.toContain('.claim(');
  expect(code).not.toMatch(/\.reload\(|navigate\(/);
});
