import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect, type Page } from "./clock.ts";
import { checkPage, expectNoSidewaysScroll, setAccountTheme } from "./a11y.ts";

// Settings → About → Report a problem (0.9, X2; mockup Dark-Report09-Phone), against the real
// server, signed in as the test admin. The report is shown whole, every line can be changed or
// removed (with Undo), and the person sends it themselves: Open on GitHub is only a link (its
// href is checked here, never opened), Download is a file made in the browser. The server's
// side (personal details removed, admins only for the log's errors, no connection made) is in
// backend/tests/test_problem_report.py.
// Runs in the "phone 0.9 report", "desktop 0.9 report" and "webkit 0.9 report" projects.

const NEW_ISSUE =
  "https://github.com/placeholder_until_1_0/mealwright/issues/new";

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

test.afterEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

// No service worker: on WebKit page.route stops seeing the page's requests once it controls the
// page (as in about.spec.ts); the review pictures use a made-up report.
test.use({ serviceWorkers: "block" });

const line = (page: Page, n: number) =>
  page.getByRole("textbox", { name: `Report line ${n}` });
const github = (page: Page) =>
  page.getByRole("link", { name: "Open on GitHub" });

async function issueBody(page: Page) {
  const href = await github(page).getAttribute("href");
  const url = new URL(href!);
  expect(`${url.origin}${url.pathname}`).toBe(NEW_ISSUE);
  return {
    title: url.searchParams.get("title"),
    body: url.searchParams.get("body"),
  };
}

/** Every request the page makes that leaves this computer. There must be none. */
function outside(page: Page) {
  const seen: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    const local = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
    if (["http:", "https:"].includes(url.protocol) && !local)
      seen.push(request.url());
  });
  return seen;
}

test("About leads to Report a problem: the whole report, changed and sent by the person, nothing sent by the page", async ({
  page,
}) => {
  const left = outside(page);
  await page.goto("/settings/about");
  await expect(
    page.getByRole("heading", { level: 2, name: "Help" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Report a problem" }).click();
  await expect(page).toHaveURL("/settings/about/report");
  await expect(
    page.getByRole("heading", { level: 1, name: "Report a problem" }),
  ).toBeVisible();
  await expect(
    page.getByText("Mealwright never sends this.", { exact: false }),
  ).toBeVisible();

  // The server's report: the version and the browser, then (for an admin) the log's errors or
  // a line saying there were none.
  await expect(line(page, 1)).toHaveValue(/^Mealwright \d+\.\d+\.\d+/);
  await expect(line(page, 2)).toHaveValue(/ · /);
  await expect(line(page, 3)).toBeVisible();
  await expect(
    page.getByText(
      "Already removed: names, recipes, pantry contents and your server’s address.",
    ),
  ).toBeVisible();
  await expectNoSidewaysScroll(page);
  await checkPage(page);

  await page
    .getByRole("textbox", { name: "What were you doing?" })
    .fill("Moving a meal to Friday");
  await line(page, 2).fill("A browser");
  let sent = await issueBody(page);
  expect(sent.title).toBe("Problem: Moving a meal to Friday");
  expect(sent.body).toContain(
    "What were you doing?\nMoving a meal to Friday\n",
  );
  expect(sent.body).toContain("\nA browser\n");
  await expect(github(page)).toHaveAttribute("target", "_blank");
  await expect(github(page)).toHaveAttribute("rel", "noopener noreferrer");

  // Remove the version line, then Undo puts it back.
  const version = await line(page, 1).inputValue();
  await page.getByRole("button", { name: "Remove this line" }).first().click();
  await expect(line(page, 1)).toHaveValue("A browser");
  expect((await issueBody(page)).body).not.toContain(version);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(line(page, 1)).toHaveValue(version);
  sent = await issueBody(page);
  expect(sent.body).toContain(`\n${version}\nA browser\n`);

  // Download is the same text, made in the browser.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(
    /^mealwright-problem-report-\d{4}-\d{2}-\d{2}\.txt$/,
  );
  expect(readFileSync((await file.path())!, "utf8")).toBe(sent.body);

  expect(left).toEqual([]);
});

/** A made-up report with a few error lines, for the review pictures. */
function madeUp() {
  return {
    version: "Mealwright 0.9.0",
    browser: "Safari 18 · iPhone",
    errors: [
      "12 Nov 12:41 UTC mealwright.sync: change for [ingredient] could not be saved (IntegrityError)",
      "12 Nov 12:43 UTC mealwright.imports: reading [link] failed (TimeoutError)",
    ],
    errors_included: true,
    new_issue_page: NEW_ISSUE,
  };
}

// Review pictures for cabledrawer (X2): Report a problem and About, dark, at four widths. Only when
// E2E_X2_SHOTS names a folder, and only on the desktop project.
test("review pictures of Report a problem and About (only with E2E_X2_SHOTS)", async ({
  page,
}, testInfo) => {
  const folder = process.env.E2E_X2_SHOTS;
  test.skip(
    !folder || testInfo.project.name !== "desktop 0.9 report",
    "review pictures only on request",
  );
  mkdirSync(folder!, { recursive: true });
  await setAccountTheme(page, "dark");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.route("**/api/v1/problem-report", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(madeUp()),
    }),
  );
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/settings/about/report");
    await expect(line(page, 4)).toBeVisible();
    await page.screenshot({
      path: join(folder!, `report-${width}.png`),
      fullPage: true,
    });
    await page.goto("/settings/about");
    await expect(
      page.getByRole("link", { name: "Report a problem" }),
    ).toBeVisible();
    await page.screenshot({
      path: join(folder!, `about-${width}.png`),
      fullPage: true,
    });
  }
});
