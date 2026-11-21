import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test, expect, type Page } from "./clock.ts";
import {
  checkPage,
  expectNoSidewaysScroll,
  isPhone,
  setAccountTheme,
} from "./a11y.ts";

// Settings › About, the update parts (0.9, X1; mockup Dark-About09-Phone), and the "Check for
// updates daily" switch in Privacy (Dark-Privacy09-Phone), against the real server, signed in as
// the test admin. The real server is never let out: Check now runs for real only while the
// release list is still the placeholder (it answers "couldn't check" and connects nowhere; Check
// now works with the switch off, cabledrawer 12 Nov); the answers that need GitHub ("a newer version is
// out", an old version) are made up in the browser. The server's own rules (one plain request
// through the outbound gate, admins only, the daily check only with the switch on) are in
// backend/tests/test_updates.py.
// Runs in the "phone 0.9 about", "desktop 0.9 about" and "webkit 0.9 about" projects.

const DAILY = "Check for updates daily";
const PAGE = "https://github.com/cabledrawer/mealwright/releases";

async function switchOff(page: Page) {
  const response = await page.request.put(
    "/api/v1/privacy/switches/update_check",
    { data: { on: false } },
  );
  expect(response.ok(), await response.text()).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
  await switchOff(page);
});

test.afterEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
  await switchOff(page);
});

// No service worker here: on WebKit, once it controls the page, page.route no longer sees the
// page's requests, so a second visit would show the real server's answer, not the made-up one
// (as in import-pints.spec.ts). "New version ready" itself is covered by newVersion.test.ts.
test.use({ serviceWorkers: "block" });

/** The server's answer to GET /updates (or POST /updates/check), made up in the browser. */
function updates(over: Record<string, unknown> = {}) {
  return {
    version: "0.9.0",
    released_on: "2026-10-01",
    releases_page: PAGE,
    can_check: true,
    daily: true,
    last: null,
    ...over,
  };
}

const newer = () =>
  updates({
    last: {
      outcome: "newer",
      latest: "v0.9.1",
      checked_at: new Date().toISOString(),
    },
  });

async function fake(
  page: Page,
  path: "/updates" | "/updates/check",
  body: unknown,
) {
  await page.route(`**/api/v1${path}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    }),
  );
}

test("Settings leads to About: the version, its release day and the admins’ Updates card; Check now works with the switch off", async ({
  page,
}) => {
  await page.goto("/settings");
  // A computer opens Appearance first, with the list beside it (F252).
  if (!isPhone(page)) await expect(page).toHaveURL("/settings/appearance");
  await page.locator('a[href="/settings/about"]:visible').first().click();
  await expect(page).toHaveURL("/settings/about");
  await expect(
    page.getByRole("heading", { level: 1, name: "About" }),
  ).toBeVisible();
  await expect(page.getByText(/^Mealwright \d+\.\d+\.\d+/)).toBeVisible();
  await expect(
    page.getByText(/^Released \d{1,2} [A-Z][a-z]{2} \d{4}$/),
  ).toBeVisible();
  // A version released after the tests' fixed day is not old: no note.
  await expect(page.getByText(/months? old|years? old/)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 2, name: "Updates (admins)" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /^Daily check/ })).toContainText(
    "Off",
  );
  await expectNoSidewaysScroll(page);
  await checkPage(page);

  const check = page.waitForResponse((r) =>
    r.url().endsWith("/api/v1/updates/check"),
  );
  await page.getByRole("button", { name: "Check now" }).click();
  expect((await (await check).json()).last.outcome).toBe("failed");
  await expect(
    page.getByText("Couldn’t check for updates", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(/Privacy first/)).toHaveCount(0);
  await page.getByRole("link", { name: /^Daily check/ }).click();
  await expect(page).toHaveURL("/settings/outside-connections#outside-connections");
  await expect(page.getByRole("switch", { name: DAILY })).not.toBeChecked();
});

test("the daily check is its own Privacy switch, off at first; About says when it is on", async ({
  page,
}) => {
  await page.goto("/settings/outside-connections");
  const daily = page.getByRole("switch", { name: DAILY });
  await expect(daily).not.toBeChecked();
  await expect(
    page.getByText(
      "Asks GitHub’s public release list once a day. Sends nothing about you or this server",
    ),
  ).toBeVisible();
  await daily.click();
  await expect(daily).toBeChecked();
  await expect
    .poll(
      async () =>
        (await (await page.request.get("/api/v1/privacy/switches")).json())
          .switches,
    )
    .toContainEqual({ connection: "update_check", on: true });
  await page.goto("/settings/about");
  await expect(page.getByRole("link", { name: /^Daily check/ })).toContainText(
    "Once a day · change in Outside connections",
  );
  await expect(page.getByRole("link", { name: /^Daily check/ })).toContainText(
    "On",
  );
  await page.goto("/settings/outside-connections");
  await daily.click();
  await expect(daily).not.toBeChecked();
  await page.reload();
  await expect(page.getByRole("switch", { name: DAILY })).not.toBeChecked();
});

test('a newer version found shows "Update available" by About and the version on About links to the releases page', async ({
  page,
}) => {
  await fake(page, "/updates", newer());
  await page.goto("/settings");
  if (isPhone(page)) {
    await expect(page.getByRole("link", { name: /^About/ })).toContainText(
      "Update available",
    );
  } else {
    await expect(
      page
        .getByRole("navigation", { name: "Settings", exact: true })
        .getByRole("link", { name: /^About/ }),
    ).toContainText("Update available");
  }
  await page.goto("/settings/about");
  const row = page.getByRole("link", { name: /^Mealwright 0\.9\.1 is out/ });
  await expect(row).toContainText("Update");
  await expect(row).toHaveAttribute("href", PAGE);
  await expect(row).toHaveAttribute("target", "_blank");
  await checkPage(page);
});

test("an old version says how old it is, with the releases link", async ({
  page,
}) => {
  await fake(page, "/updates", updates({ released_on: "2026-01-10" }));
  await page.goto("/settings/about");
  await expect(page.getByText(/^This version is 9 months old\./)).toBeVisible();
  await expect(
    page.getByRole("link", { name: "github.com/…/mealwright/releases" }),
  ).toHaveAttribute("href", PAGE);
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

test("Licences and credits (U1): the licence, the source link, the USDA credit and the fonts, with no outside request", async ({
  page,
}) => {
  const outside: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      !["localhost", "127.0.0.1"].includes(url.hostname) &&
      !request.url().startsWith("data:")
    )
      outside.push(request.url());
  });
  await page.goto("/settings/about");
  await expect(
    page.getByRole("heading", { level: 2, name: "Licences and credits" }),
  ).toBeVisible();
  await expect(page.getByText("AGPL-3.0", { exact: true })).toBeVisible();
  // The real address: the source row is a plain link the person may click.
  await expect(
    page.getByRole("link", { name: /^Source code \(AGPL-3\.0\)/ }),
  ).toHaveAttribute(
    "href",
    /^https:\/\/github\.com\/cabledrawer\/mealwright\/tree\/v/,
  );
  await expect(
    page.getByText("USDA FoodData Central (public domain)"),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Plus Jakarta Sans · Newsreader · SIL Open Font License 1.1",
    ),
  ).toBeVisible();
  expect(outside).toEqual([]);
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

test("Licences and credits (16g): with a real address, the source row links to the source at this version", async ({
  page,
}) => {
  await fake(
    page,
    "/updates",
    updates({
      version: "0.9.5",
      released_on: "2026-11-13",
      releases_page: "https://github.com/sam-kitchen/mealwright/releases",
    }),
  );
  await page.goto("/settings/about");
  const source = page.getByRole("link", { name: /^Source code \(AGPL-3\.0\)/ });
  await expect(source).toHaveAttribute(
    "href",
    "https://github.com/sam-kitchen/mealwright/tree/v0.9.5",
  );
  await expect(source).toHaveAttribute("target", "_blank");
  await expect(source).toContainText("The exact code of this version");
  await expectNoSidewaysScroll(page);
  await checkPage(page);
});

// Review pictures for cabledrawer (X1): the changed parts of About and Privacy, dark, at four widths.
// Only when E2E_X1_SHOTS names a folder, and only on the desktop project.
test("review pictures of About and Privacy (only with E2E_X1_SHOTS)", async ({
  page,
}, testInfo) => {
  const folder = process.env.E2E_X1_SHOTS;
  test.skip(
    !folder || testInfo.project.name !== "desktop 0.9 about",
    "review pictures only on request",
  );
  mkdirSync(folder!, { recursive: true });
  await setAccountTheme(page, "dark");
  await page.emulateMedia({ colorScheme: "dark" });
  await fake(
    page,
    "/updates",
    updates({ released_on: "2026-01-10", daily: true, last: newer().last }),
  );
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/settings/about");
    await expect(
      page.getByRole("link", { name: /^Mealwright 0\.9\.1 is out/ }),
    ).toBeVisible();
    await page.screenshot({
      path: join(folder!, `about-${width}.png`),
      fullPage: true,
    });
    await page.goto("/settings/outside-connections#outside-connections");
    const daily = page.getByRole("switch", { name: DAILY });
    await expect(daily).toBeVisible();
    await daily.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(folder!, `privacy-${width}.png`) });
  }
});
