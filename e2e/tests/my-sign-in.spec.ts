import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { test, expect, request, testNow, type Page } from "./clock.ts";
import { ADMIN } from "./servers.ts";

// Settings → Sign-in (0.9, A2): your password, where you're signed in, signing out one device or
// everywhere else, and Change password. Against the worker's own server, signed in as the admin.
// Changing the password and "Sign out everywhere else" are answered here (page.route) rather than
// by the server: the other tests in this worker sign in with the same password and session. The
// server's side is in backend/tests/test_my_sign_in.py. Runs on phone, desktop and WebKit.

const IPAD =
  "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";

const ago = (minutes: number) =>
  new Date(testNow() - minutes * 60_000).toISOString();

/** What GET /me/sign-in answers in the answered-here tests: this device, an iPad and a PC. */
const THREE = {
  has_password: true,
  password_changed_at: "2026-10-02T10:00:00Z",
  sessions: [
    {
      id: 1,
      device: "iPhone · Safari",
      last_used_at: ago(0),
      remember: true,
      this_device: true,
    },
    {
      id: 2,
      device: "iPad · Safari",
      last_used_at: ago(120),
      remember: true,
      this_device: false,
    },
    {
      id: 3,
      device: null,
      last_used_at: ago(60 * 24 * 3),
      remember: false,
      this_device: false,
    },
  ],
};
const ONLY_HERE = { ...THREE, sessions: THREE.sessions.slice(0, 1) };

const PAUSE_NOTE =
  "Only one wrong-password pause per username, never longer than a minute. Other people can still sign in.";

const places = (page: Page) => page.getByTestId("signed-in-places");
const isPhone = () => test.info().project.name.startsWith("phone");
const thisTag = () => (isPhone() ? "This phone" : "This computer");

async function openSignIn(page: Page) {
  await page.goto("/settings/sign-in");
  await expect(
    page.getByRole("heading", { name: "Where you’re signed in" }),
  ).toBeVisible();
}

function answer(page: Page, body: object) {
  return page.route("**/api/v1/me/sign-in", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    }),
  );
}

test("lists this device first, and signs out another one", async ({
  page,
  app,
}) => {
  // A second sign-in, from an iPad.
  const ipad = await request.newContext({ baseURL: app.url, userAgent: IPAD });
  const signedIn = await ipad.post("/api/v1/session", {
    data: {
      username: ADMIN.username,
      password: ADMIN.password,
      remember: true,
    },
  });
  expect(signedIn.status(), await signedIn.text()).toBe(200);

  await openSignIn(page);
  const rows = places(page);
  await expect(rows.getByText(thisTag(), { exact: true })).toBeVisible();
  const signOutIpad = rows
    .getByRole("button", { name: "Sign out iPad · Safari" })
    .first();
  await expect(signOutIpad).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sign out everywhere else" }),
  ).toBeVisible();

  const before = await rows
    .getByRole("button", { name: "Sign out iPad · Safari" })
    .count();
  await signOutIpad.click();
  await expect(
    rows.getByRole("button", { name: "Sign out iPad · Safari" }),
  ).toHaveCount(before - 1);
  await expect(
    page.getByRole("status").filter({ hasText: "Signed out iPad · Safari." }),
  ).toHaveCount(1);
  // The iPad has to sign in again; this device is still signed in.
  expect((await ipad.get("/api/v1/me")).status()).toBe(401);
  expect((await page.request.get("/api/v1/me")).status()).toBe(200);
  await ipad.dispose();
});

test("shows each device, when it was last used and the password’s date", async ({
  page,
}) => {
  await answer(page, THREE);
  await openSignIn(page);
  await expect(
    page.getByRole("link", { name: /Change password.*Last changed 2 Oct/ }),
  ).toBeVisible();
  const rows = places(page);
  await expect(rows).toContainText("iPhone · Safari");
  await expect(rows).toContainText("Now · remembered for 30 days");
  await expect(rows).toContainText("2 hours ago · remembered for 30 days");
  await expect(rows).toContainText("Unknown device");
  await expect(rows).toContainText("3 days ago");
  await expect(rows.getByText(thisTag(), { exact: true })).toBeVisible();
  await expect(
    rows.getByRole("button", { name: "Sign out Unknown device" }),
  ).toBeVisible();
});

test("Sign out everywhere else leaves only this device", async ({ page }) => {
  await answer(page, THREE);
  let asked = false;
  await page.route("**/api/v1/me/sessions/others", (route) => {
    asked = route.request().method() === "DELETE";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ONLY_HERE),
    });
  });
  await openSignIn(page);
  await page.getByRole("button", { name: "Sign out everywhere else" }).click();
  await expect(
    places(page).getByRole("button", { name: /^Sign out / }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Sign out everywhere else" }),
  ).toHaveCount(0);
  expect(asked).toBe(true);
});

test.describe("Change password", () => {
  test("needs 12 characters and the same new password twice", async ({
    page,
  }) => {
    await answer(page, THREE);
    await openSignIn(page);
    await page.getByRole("link", { name: /Change password/ }).click();
    await expect(page).toHaveURL("/settings/password");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Change password",
    );
    await expect(
      page.getByText(
        "iPad · Safari and Unknown device will need the new password",
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("switch", { name: "Sign out my other devices" }),
    ).toBeChecked();

    const next = page.getByLabel("New password", { exact: true });
    await next.fill("kitchen");
    await expect(
      page.getByText(
        "7 of 12 characters. A short sentence is easiest to remember.",
      ),
    ).toBeVisible();
    await next.fill("a long kitchen sentence");
    await expect(page.getByText("Long enough.")).toBeVisible();
    await page
      .getByLabel("New password again", { exact: true })
      .fill("a different sentence");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(page.getByText("Type your current password.")).toBeVisible();
    await expect(
      page.getByText("The two new passwords aren’t the same."),
    ).toBeVisible();
  });

  test("sends the current password, the new one and the switch", async ({
    page,
  }) => {
    await answer(page, THREE);
    let sent: Record<string, unknown> = {};
    await page.route("**/api/v1/me/password", (route) => {
      sent = route.request().postDataJSON();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...ONLY_HERE,
          password_changed_at: new Date(testNow()).toISOString(),
        }),
      });
    });
    await page.goto("/settings/password");
    await expect(
      page.getByRole("switch", { name: "Sign out my other devices" }),
    ).toBeVisible();
    await page
      .getByLabel("Current password", { exact: true })
      .fill(ADMIN.password);
    await page
      .getByLabel("New password", { exact: true })
      .fill("a long kitchen sentence");
    await page
      .getByLabel("New password again", { exact: true })
      .fill("a long kitchen sentence");
    await page.getByRole("button", { name: "Change password" }).click();
    await expect(
      page.getByText(
        "Password changed. Your other devices are signed out. Your API tokens have stopped.",
      ),
    ).toBeVisible();
    expect(sent).toEqual({
      current_password: ADMIN.password,
      new_password: "a long kitchen sentence",
      sign_out_others: true,
    });
    await expect(
      page.getByLabel("Current password", { exact: true }),
    ).toHaveValue("");
  });

  test("a wrong current password says so; the pause says others can still sign in", async ({
    page,
  }) => {
    await answer(page, ONLY_HERE);
    let tries = 0;
    await page.route("**/api/v1/me/password", (route) => {
      tries += 1;
      return tries === 1
        ? route.fulfill({
            status: 422,
            contentType: "application/json",
            body: JSON.stringify({
              detail: "That isn’t your current password.",
              code: "wrong_password",
            }),
          })
        : route.fulfill({
            status: 429,
            contentType: "application/json",
            headers: { "Retry-After": "30" },
            body: JSON.stringify({
              detail:
                "Too many wrong passwords for tess. Try again in 30 seconds.",
              code: "username_paused",
            }),
          });
    });
    await page.goto("/settings/password");
    // Only this device: no switch.
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Change password",
    );
    await expect(
      page.getByRole("switch", { name: "Sign out my other devices" }),
    ).toHaveCount(0);
    const fill = async () => {
      await page
        .getByLabel("Current password", { exact: true })
        .fill("not my password");
      await page
        .getByLabel("New password", { exact: true })
        .fill("a long kitchen sentence");
      await page
        .getByLabel("New password again", { exact: true })
        .fill("a long kitchen sentence");
      await page.getByRole("button", { name: "Change password" }).click();
    };
    await fill();
    await expect(page.getByRole("alert")).toHaveText(
      "That isn’t your current password.",
    );
    await expect(page.getByText(PAUSE_NOTE)).toHaveCount(0);
    await fill();
    await expect(page.getByRole("alert")).toHaveText(
      "Too many wrong passwords for tess. Try again in 30 seconds.",
    );
    await expect(page.getByText(PAUSE_NOTE)).toBeVisible();
  });
});

/** Dark screenshots at four widths for the review, only when E2E_SHOTS_DIR is set (by hand). */
test("screenshots, dark (by hand only)", async ({ page }) => {
  const dir = process.env.E2E_SHOTS_DIR;
  test.skip(
    !dir || !test.info().project.name.startsWith("desktop"),
    "by hand, desktop project",
  );
  mkdirSync(dir!, { recursive: true });
  await page.emulateMedia({ colorScheme: "dark" });
  await answer(page, THREE);
  for (const width of [428, 768, 1100, 1300]) {
    await page.setViewportSize({ width, height: 900 });
    await openSignIn(page);
    await expect(places(page)).toContainText("iPhone · Safari");
    await page.screenshot({
      path: join(dir!, `my-sign-in-${width}.png`),
      fullPage: true,
    });
  }
});
