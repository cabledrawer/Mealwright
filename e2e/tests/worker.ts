import { expect, type Page } from '@playwright/test';

/**
 * The page is REALLY under the service worker, with all the app's code on the device. The
 * worker's first install waits for the page to go quiet and then downloads its files (0.9.5
 * speed work); only then does it activate and take the page that installed it (`clients.claim()`
 * in its first-install branch). So `navigator.serviceWorker.controller` is set exactly when the
 * files are on the device and this page is served from them. Every test that cuts the network
 * after a first visit waits for this first, or the app's code may not be on the device yet
 * ("You're offline."). A poll, no fixed sleep; no reload is needed.
 */
export async function workerReady(page: Page) {
  await expect
    .poll(() => page.evaluate(() => !!navigator.serviceWorker.controller), {
      message: 'the page is under the service worker',
      timeout: 60_000
    })
    .toBe(true);
}

/**
 * The new-ingredient dialog's code is on the page. It is fetched once the page is idle (not in
 * the first page load), so a test that cuts the network and then asks for it waits for this
 * first: in Playwright's WebKit the offline switch blocks a first-use fetch before the worker.
 */
export async function newIngredientDialogReady(page: Page) {
  await expect(page.locator('dialog[data-new-ingredient]')).toBeAttached();
}
