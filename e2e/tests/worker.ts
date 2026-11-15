import { expect, type Page } from '@playwright/test';

/**
 * The page is under the service worker with all the app's code on the device. The worker's first
 * install waits for the page to go quiet and then downloads its files (0.9.5 speed work), and it
 * is "ready" only when that is done. Every test that cuts the network after a first visit waits
 * for this first, or the app's code may not be on the device yet ("You're offline.").
 */
export async function workerReady(page: Page) {
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
}

/**
 * The new-ingredient dialog's code is on the page. It is fetched once the page is idle (not in
 * the first page load), so a test that cuts the network and then asks for it waits for this
 * first: in Playwright's WebKit the offline switch blocks a first-use fetch before the worker.
 */
export async function newIngredientDialogReady(page: Page) {
  await expect(page.locator('dialog[data-new-ingredient]')).toBeAttached();
}
