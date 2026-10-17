import { test, expect, type Page, type Route } from '@playwright/test';

// Spec section 7 and the 0.1 "Done when" list: a test proves the Content Security
// Policy blocks an external script. The test page is served at Mealwright's own
// address with Mealwright's real response headers, then we watch what the browser does.

const TEST_PAGE = `<!doctype html>
<html><head><title>CSP test</title></head><body>
<script src="https://cdn.example.invalid/tracker.js"></script>
<script>window.inlineRan = true;</script>
<p id="done">loaded</p>
</body></html>`;

type Violation = { blockedURI: string; directive: string };

async function openTestPage(page: Page, baseURL: string, keepPolicy: boolean) {
  // Safety net: record and refuse anything aimed outside the app, so nothing can
  // leave the machine even if the policy were wrong. (.invalid never resolves anyway.)
  const outside: string[] = [];
  await page.route(
    (url) => url.origin !== baseURL,
    (route: Route) => {
      outside.push(route.request().url());
      return route.abort();
    },
  );
  await page.route(`${baseURL}/csp-test-page`, async (route) => {
    const real = await route.fetch({ url: `${baseURL}/api/v1/version` });
    const headers = Object.fromEntries(
      Object.entries(real.headers()).filter(
        ([name]) =>
          name !== 'content-length' && (keepPolicy || name !== 'content-security-policy'),
      ),
    );
    await route.fulfill({
      status: 200,
      headers: { ...headers, 'content-type': 'text/html; charset=utf-8' },
      body: TEST_PAGE,
    });
  });
  await page.addInitScript(() => {
    const seen: Violation[] = [];
    (window as unknown as { violations: Violation[] }).violations = seen;
    document.addEventListener('securitypolicyviolation', (event) => {
      seen.push({ blockedURI: event.blockedURI, directive: event.effectiveDirective });
    });
  });
  await page.goto('/csp-test-page');
  await expect(page.locator('#done')).toHaveText('loaded');
  const result = await page.evaluate(() => {
    const w = window as unknown as { violations: Violation[]; inlineRan?: boolean };
    return { violations: w.violations, inlineRan: w.inlineRan === true };
  });
  return { outside, ...result };
}

test('the policy blocks a script from another site, and inline scripts', async ({
  page,
  baseURL,
}) => {
  const { outside, violations, inlineRan } = await openTestPage(page, baseURL!, true);

  // The browser never even asked for the outside script...
  expect(outside).toEqual([]);
  // ...because the policy refused it, and said so.
  expect(violations).toContainEqual({
    blockedURI: 'https://cdn.example.invalid/tracker.js',
    directive: 'script-src-elem',
  });
  // The inline script was refused too.
  expect(inlineRan).toBe(false);
  expect(violations).toContainEqual({ blockedURI: 'inline', directive: 'script-src-elem' });
});

test('control: without the policy, the same page would load the outside script', async ({
  page,
  baseURL,
}) => {
  // Proves the test above can fail: with the header removed, the browser tries to
  // fetch the outside script (our safety net refuses it) and runs the inline script.
  const { outside, violations, inlineRan } = await openTestPage(page, baseURL!, false);
  expect(outside).toEqual(['https://cdn.example.invalid/tracker.js']);
  expect(violations).toEqual([]);
  expect(inlineRan).toBe(true);
});
