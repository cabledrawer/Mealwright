import { test, expect, type Locator, type Page } from "./clock.ts";
import { workerReady } from "./worker.ts";
import {
  expectNoAxeViolations,
  inTheme,
  isPhone,
  setAccountTheme,
} from "./a11y.ts";
import { addDays, key, stamp } from './helpers.ts';

// Cook once, eat for… (0.6, PR 4): the sheet and its preview (add, remove, move a tub), saving
// and Undo; tubs on the week and the day list; Whose tub?, To freezer, back to tubs left, the
// "Tubs left" group in the tray and in + Add; and "Leftovers here" making a tub. Runs on
// Chromium (computer and phone) and WebKit (computer), see playwright.config.ts.
//
// The three projects share one server, and every test plans in weeks of its own (far from
// plan.spec.ts's), named with a word no other test uses. The tests' day is a Saturday, so the
// day after (Sunday) is in the same week and the Monday is in the next.
//
// Weeks ahead of today (the plan accepts 0 to 104), one block per plan spec; the next spec takes
// the free weeks 80 to 83:
//   plan-views Plan it tests 0 and 1 (today's 14 days), plan.spec.ts 2 to 34, plan-cook-once.spec.ts 35 to 64,
//   plan-views.spec.ts 65 to 79, plan-portions.spec.ts 84 to 104.

async function call(
  page: Page,
  method: "POST" | "PUT" | "DELETE" | "PATCH",
  path: string,
  data?: object,
) {
  const response = await page.request.fetch(`/api/v1${path}`, {
    method,
    data,
    headers: key(),
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(
    true,
  );
  return (await response.json()) as Record<string, any>;
}

const INDEX: Record<string, number> = {
  "desktop 0.6 cook once": 0,
  "phone 0.6 cook once": 1,
  "webkit 0.6 cook once": 2,
};
const projectIndex = () => INDEX[test.info().project.name] ?? 0;
/** A Saturday far from the other plan tests' weeks: this project's own, and the test's own (k 0 to 4; two weeks apart, as a test reads 11 days). */
const far = (today: string, k: number) =>
  addDays(today, 7 * (35 + 2 * (5 * projectIndex() + k)));

const weekday = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  timeZone: "UTC",
});
const month = new Intl.DateTimeFormat("en-GB", {
  month: "long",
  timeZone: "UTC",
});
const weekdayShort = new Intl.DateTimeFormat("en-GB", {
  weekday: "short",
  timeZone: "UTC",
});
/** "Sun 18": how the Leftovers sheet writes a day. */
const dayWords = (iso: string) =>
  `${weekdayShort.format(new Date(`${iso}T12:00:00Z`))} ${new Date(`${iso}T12:00:00Z`).getUTCDate()}`;
const dayName = (iso: string) => {
  const d = new Date(`${iso}T12:00:00Z`);
  return `${weekday.format(d)} ${d.getUTCDate()} ${month.format(d)}`;
};

async function setup(page: Page) {
  const household = (await (
    await page.request.get("/api/v1/household")
  ).json()) as { today: string };
  const list = (await (
    await page.request.get("/api/v1/meal-slots")
  ).json()).meal_slots as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<
    string,
    number
  >;
  // Snack is off in a new household; these tests plan it, so they switch it on themselves
  // (they used to rely on plan.spec.ts having run first).
  await call(page, "PATCH", `/meal-slots/${slot.Snack}`, { enabled: true });
  const me = (await (await page.request.get("/api/v1/me")).json()) as {
    name: string;
  };
  return { today: household.today, slot, me: me.name };
}

const makeRecipe = async (page: Page, name: string) =>
  (await call(page, "POST", "/recipes", { name })).id as number;
const planned = async (
  page: Page,
  recipeId: number,
  day: string,
  slotId: number,
) =>
  (await call(page, "POST", "/plan/items", {
    date: day,
    slot_id: slotId,
    recipe_id: recipeId,
  })) as { item_id: number; meal_id: number };

async function planRange(page: Page, from: string, to: string) {
  return (await (
    await page.request.get(`/api/v1/plan?from=${from}&to=${to}`)
  ).json()) as Record<string, any>;
}

async function openWeekOf(page: Page, today: string, day: string) {
  await page.goto("/plan");
  const ahead = Math.round(
    (new Date(`${day}T12:00:00Z`).getTime() -
      new Date(`${today}T12:00:00Z`).getTime()) /
      86_400_000 /
      7,
  );
  for (let i = 0; i < ahead; i++)
    await page.getByRole("button", { name: "Next week" }).click();
}

const cell = (page: Page, day: string, slotId: number) =>
  page.getByTestId(`cell-${day}-${slotId}`);

/** The card or row of a meal: on a computer a card in its cell, on a phone a row in its day. */
function mealButton(
  page: Page,
  day: string,
  slotName: string,
  slotId: number,
  text: string,
): Locator {
  return isPhone(page)
    ? page
        .getByRole("region", { name: dayName(day) })
        .getByRole("button", { name: new RegExp(`^${slotName}: .*${text}`) })
    : cell(page, day, slotId)
        .getByRole("button", { name: new RegExp(`^${text}`) })
        .first();
}

async function centre(locator: Locator, down = 0.5) {
  await locator.scrollIntoViewIfNeeded();
  const box = (await locator.boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height * down };
}

async function mouseDrag(
  page: Page,
  from: Locator,
  to: Locator,
  zone?: "leftovers",
) {
  const a = await centre(from);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(a.x + 12, a.y + 12, { steps: 3 });
  const b = await centre(to, 0.2);
  await page.mouse.move(b.x, b.y, { steps: 10 });
  if (zone) {
    const target = to.locator(`[data-drop-zone="${zone}"]`);
    await expect(target).toBeVisible();
    const z = await centre(target);
    await page.mouse.move(z.x, z.y, { steps: 4 });
  }
  await page.mouse.up();
}

// The phone opens the Plan on Eat; these tests are about the cards, which are Both (0.7, P2).
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem("mealwright.plan-show", "both"),
  );
});

const scriptErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  scriptErrors.length = 0;
  page.on("pageerror", (error) => scriptErrors.push(error.message));
  await setAccountTheme(page, "auto");
});
test.afterEach(() => {
  expect(scriptErrors, "the page raised no script errors").toEqual([]);
});

/** A batch made through the API, spread over lunch and dinner after the cook day. */
async function batchFor(
  page: Page,
  name: string,
  day: string,
  dinner: number,
  tubs = 3,
) {
  const meal = await planned(page, await makeRecipe(page, name), day, dinner);
  const made = await call(page, "POST", `/plan/items/${meal.item_id}/batch`, {
    tub_count: tubs,
    pattern: "lunch_dinner",
  });
  return {
    meal,
    batch: made.batch_id as number,
    change: made.change.id as number,
  };
}

test("Cook once: the sheet previews, a tub is taken out, added and moved; Save makes the tubs; Undo takes them back", async ({
  page,
}) => {
  const { today, slot } = await setup(page);
  const name = `Biryani ${stamp()}`;
  const day = far(today, 0);
  const sun = addDays(day, 1);
  const mon = addDays(day, 2);
  const meal = await planned(
    page,
    await makeRecipe(page, name),
    day,
    slot.Dinner,
  );
  await openWeekOf(page, today, day);
  await mealButton(page, day, "Dinner", slot.Dinner, name).click();
  await page
    .getByRole("dialog", { name })
    .getByRole("button", { name: "Cook once, eat for…" })
    .click();
  const sheet = page.getByRole("dialog", { name: "Cook once, eat for…" });
  await expect(sheet).toBeVisible();
  const summary = sheet.getByTestId("cook-summary");
  await expect(summary).toContainText("4 of 4 placed");
  await expect(sheet.getByTestId("tub-count")).toHaveText("4");
  await sheet.getByRole("button", { name: "One tub more" }).click();
  await expect(summary).toContainText("5 of 5 placed");
  await sheet.getByRole("button", { name: "One tub fewer" }).click();
  await expect(summary).toContainText("4 of 4 placed");

  // Dinners only: Sunday's dinner holds tub 1, Monday's tub 2.
  await sheet.getByRole("button", { name: "Dinners" }).click();
  // The fourth dinner is past the tub's use-by (3 days in the fridge), so tub 4 waits in tubs left.
  await expect(summary).toContainText("3 of 4 placed");
  const sunDinner = sheet.getByTestId(`cook-cell-${sun}-${slot.Dinner}`);
  const monDinner = sheet.getByTestId(`cook-cell-${mon}-${slot.Dinner}`);
  await expect(sunDinner).toContainText("Tub 1");
  await expect(monDinner).toContainText("Tub 2");
  // ✕ sends a tub back to "tubs left"; + Add a tub puts the next one in the meal.
  await sunDinner.getByRole("button", { name: /^Take tub 1 out of/ }).click();
  await expect(summary).toContainText("2 of 4 placed");
  await expect(summary).toContainText("Tubs 1 and 4 → Fridge");
  await expect(sunDinner).not.toContainText("Tub 1");
  await sunDinner.getByRole("button", { name: /^Add a tub to / }).click();
  await expect(summary).toContainText("3 of 4 placed");
  // Tap a tub, then the meal it should go to: a keyboard and finger way to move it.
  await sunDinner.getByRole("button", { name: /^Tub 1.*Move it$/ }).click();
  await monDinner.getByRole("button", { name: /^Put tub 1 in / }).click();
  await expect(monDinner).toContainText("Tub 1");
  await expect(monDinner).toContainText("Tub 2");
  await expect(sunDinner).not.toContainText("Tub 1");
  await expect(summary).toContainText("3 of 4 placed");

  await sheet.getByRole("button", { name: "Add 4 tubs to the plan" }).click();
  await expect(sheet).toBeHidden();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: `Planned ${name} once for 4 tubs` }),
  ).toBeVisible();
  // The toast shows at once; the batch is there when the server has answered.
  await expect
    .poll(
      async () => (await planRange(page, day, addDays(day, 10))).tubs.length,
    )
    .toBe(4);
  const saved = await planRange(page, day, addDays(day, 10));
  expect(
    saved.batch_cooks.filter((b: any) => b.recipe_name === name),
  ).toHaveLength(1);
  expect(saved.tubs).toHaveLength(4);
  expect(saved.batch_cooks[0].pattern).toBe("dinners");
  expect(meal.meal_id).toBeTruthy();

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(
      async () => (await planRange(page, day, addDays(day, 10))).tubs.length,
    )
    .toBe(0);
});

test("Cook once: pattern, who is eating, nothing offline, and the sheet passes the accessibility checks", async ({
  page,
  context,
}) => {
  const { today, slot } = await setup(page);
  const name = `Dal ${stamp()}`;
  const day = far(today, 1);
  await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  await openWeekOf(page, today, day);
  await mealButton(page, day, "Dinner", slot.Dinner, name).click();
  await page
    .getByRole("dialog", { name })
    .getByRole("button", { name: "Cook once, eat for…" })
    .click();
  const sheet = page.getByRole("dialog", { name: "Cook once, eat for…" });
  await expect(sheet.getByTestId("cook-summary")).toContainText(
    "4 of 4 placed",
  );
  // One login: there is nobody to pick, so the question isn't asked.
  await expect(sheet.getByText("Who’s eating?")).toHaveCount(0);
  await sheet.getByRole("button", { name: "I’ll pick" }).click();
  await expect(sheet.getByTestId("cook-summary")).toContainText(
    "0 of 4 placed",
  );
  await expect(sheet.getByTestId("cook-summary")).toContainText(
    "Tubs 1–4 → Fridge",
  );
  await sheet
    .getByRole("switch", { name: "Extra tubs go to the freezer" })
    .click();
  await expect(sheet.getByTestId("cook-summary")).toContainText(
    "Tubs 1–4 → Freezer",
  );
  // The two sentences have their space between them (RF5).
  await expect(sheet.getByTestId("cook-summary")).toContainText(
    "they’ll show in tubs left. The pattern skips meals",
  );
  for (const theme of ["light", "dark"] as const) {
    await inTheme(page, theme);
    await expectNoAxeViolations(page, `Cook once sheet, ${theme}`);
  }
  await inTheme(page, "light");
  if (test.info().project.use.browserName !== "webkit") {
    // Offline, the first try finds out; then nothing on the sheet can change the plan.
    await workerReady(page);
    await context.setOffline(true);
    await sheet.getByRole("button", { name: "One tub more" }).click();
    await expect(
      sheet
        .getByText("You’re offline. Plan changes when you’re back online.")
        .first(),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      sheet.getByRole("button", { name: /^Add \d+ tubs? to the plan$/ }),
    ).toBeDisabled();
    await expect(
      sheet.getByRole("button", { name: "One tub fewer" }),
    ).toBeDisabled();
    await context.setOffline(false);
  }
  await sheet.getByRole("button", { name: "Cancel" }).click();
  await expect(sheet).toBeHidden();
  expect(
    (await planRange(page, day, addDays(day, 10))).batch_cooks,
  ).toHaveLength(0);
});

test("tubs on the plan: Whose tub?, To freezer, back to tubs left, and put one in a meal from tubs left; each with Undo", async ({
  page,
}) => {
  const { today, slot, me } = await setup(page);
  const name = `Chana ${stamp()}`;
  const day = far(today, 2);
  const sun = addDays(day, 1);
  await batchFor(page, name, day, slot.Dinner);
  await openWeekOf(page, today, day);
  const tubName = `${name} tub`;

  // Sunday's lunch holds tub 1: its menu has Whose tub? and To freezer, and no Copy to….
  const lunch = mealButton(page, sun, "Lunch", slot.Lunch, tubName);
  await lunch.click();
  const menu = page.getByRole("dialog", { name: `${name} tub` });
  for (const word of [
    "Whose tub?",
    "Move to…",
    "To freezer",
    "Take off this meal (keep the tub)",
  ])
    await expect(menu.getByRole("button", { name: word })).toBeVisible();
  for (const word of ["Copy to…", "Leftovers on…"])
    await expect(menu.getByRole("button", { name: word })).toHaveCount(0);
  await menu.getByRole("button", { name: "Whose tub?" }).click();
  await menu.getByRole("button", { name: me }).click();
  await expect(
    page.getByRole("status").filter({ hasText: `is ${me}’s` }),
  ).toBeVisible();
  await expect
    .poll(async () => (await planRange(page, sun, sun)).tubs[0].member_id)
    .not.toBeNull();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(async () => (await planRange(page, sun, sun)).tubs[0].member_id)
    .toBeNull();

  // F48: the tub's own use-by can be changed from here, with Undo; days left count from the cook day.
  await lunch.click();
  const useByMenu = page.getByRole("dialog", { name: `${name} tub` });
  await expect(useByMenu).toContainText("3 days left"); // cooked later than today, 3 days in the fridge
  await useByMenu.getByRole("button", { name: "Change use-by date" }).click();
  // Not before the cook day (cabledrawer 29 Oct): Save waits, and the box says why.
  await useByMenu.getByTestId("tub-use-by").fill(addDays(day, -1));
  await expect(
    useByMenu.getByText("Pick the cook day or later."),
  ).toBeVisible();
  await expect(useByMenu.getByRole("button", { name: "Save" })).toBeDisabled();
  const newUseBy = addDays(day, 5);
  await useByMenu.getByTestId("tub-use-by").fill(newUseBy);
  await expect(useByMenu.getByText("Pick the cook day or later.")).toHaveCount(
    0,
  );
  await useByMenu.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "use by" }),
  ).toBeVisible();
  await expect
    .poll(async () => (await planRange(page, sun, sun)).tubs[0].use_by)
    .toBe(newUseBy);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(async () => (await planRange(page, sun, sun)).tubs[0].use_by)
    .toBe(addDays(day, 3));

  // To freezer: the tub leaves its meal and is in the freezer.
  await lunch.click();
  await page
    .getByRole("dialog", { name: `${name} tub` })
    .getByRole("button", { name: "To freezer" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "to the freezer" }),
  ).toBeVisible();
  await expect
    .poll(async () => (await planRange(page, sun, sun)).tubs[0].place_kind)
    .toBe("freezer");
  await expect(mealButton(page, sun, "Lunch", slot.Lunch, tubName)).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(
    mealButton(page, sun, "Lunch", slot.Lunch, tubName),
  ).toBeVisible();

  // Back to tubs left, then into a meal again from "Tubs left".
  await mealButton(page, sun, "Dinner", slot.Dinner, tubName).click();
  await page
    .getByRole("dialog", { name: `${name} tub` })
    .getByRole("button", { name: "Take off this meal (keep the tub)" })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: /back in tubs left/ }),
  ).toBeVisible();
  await expect
    .poll(
      async () =>
        (await (await page.request.get("/api/v1/plan/tubs-left")).json()).tubs
          .length,
    )
    .toBeGreaterThan(0);
  if (isPhone(page)) {
    await page
      .getByRole("region", { name: dayName(sun) })
      .getByRole("button", { name: /^\+ Add dinner|^Add to Dinner/ })
      .first()
      .click();
    const add = page.getByRole("dialog", { name: "Add to the plan" });
    await add
      .getByRole("button", { name: new RegExp(`${name} · tub`) })
      .click();
  } else {
    const tray = page.getByRole("list", { name: "Tubs left" });
    const item = tray.getByRole("button", {
      name: new RegExp(`^${name}, tub`),
    });
    await expect(item).toBeVisible();
    await mouseDrag(page, item, cell(page, sun, slot.Dinner));
  }
  await expect(
    mealButton(page, sun, "Dinner", slot.Dinner, tubName),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: /Put .* tub in Dinner/ }),
  ).toBeVisible();
});

test("Leftovers here makes a tub of the meal’s batch cook; Undo takes it back", async ({
  page,
}) => {
  const { today, slot } = await setup(page);
  const name = `Rasam ${stamp()}`;
  const day = far(today, 3);
  const sun = addDays(day, 1);
  await planned(page, await makeRecipe(page, name), day, slot.Dinner);
  await openWeekOf(page, today, day);
  if (isPhone(page)) {
    await mealButton(page, day, "Dinner", slot.Dinner, name).click();
    const sheet = page.getByRole("dialog", { name });
    await sheet.getByRole("button", { name: "Leftovers on…" }).click();
    // 0.7 P1: tick the meals (several can be ticked at once), then plan them.
    await sheet
      .getByRole("checkbox", { name: `${dayWords(sun)} · Lunch` })
      .check();
    await sheet.getByRole("button", { name: "Plan 1 tub" }).click();
  } else {
    await mouseDrag(
      page,
      mealButton(page, day, "Dinner", slot.Dinner, name),
      cell(page, sun, slot.Lunch),
      "leftovers",
    );
  }
  await expect(
    page.getByRole("status").filter({ hasText: "Leftovers" }),
  ).toBeVisible();
  await expect(
    mealButton(page, sun, "Lunch", slot.Lunch, `${name} tub`),
  ).toBeVisible();
  await expect(
    mealButton(page, day, "Dinner", slot.Dinner, name),
  ).toBeVisible();
  const plan = await planRange(page, day, addDays(day, 3));
  expect(
    plan.batch_cooks.map((b: any) => [b.recipe_name, b.tub_count]),
  ).toEqual([[name, 1]]);
  expect(plan.tubs).toHaveLength(1);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(async () => (await planRange(page, day, addDays(day, 3))).tubs.length)
    .toBe(0);
  await expect(
    mealButton(page, sun, "Lunch", slot.Lunch, `${name} tub`),
  ).toHaveCount(0);
});

test("F50: Leftovers on… and Cook once offer nothing before the cooking or in the past", async ({
  page,
}) => {
  const { today, slot } = await setup(page);
  const name = `Dal ${stamp()}`;
  const day = far(today, 4); // a Saturday of its own
  const before = addDays(day, -1);
  // Cooked at lunch: a new household's Snack and Dinner come after it (no other test needed first).
  const item = await planned(
    page,
    await makeRecipe(page, name),
    day,
    slot.Lunch,
  );
  await openWeekOf(page, today, day);
  await mealButton(page, day, "Lunch", slot.Lunch, name).click();
  const sheet = page.getByRole("dialog", { name });
  await sheet.getByRole("button", { name: "Leftovers on…" }).click();
  // The day before the cooking is not offered; the cook day is, with only the meals after lunch.
  await expect(
    sheet.getByRole("checkbox", { name: new RegExp(`^${dayWords(before)} `) }),
  ).toHaveCount(0);
  for (const word of ["Breakfast", "Lunch"])
    await expect(
      sheet.getByRole("checkbox", { name: `${dayWords(day)} · ${word}` }),
    ).toHaveCount(0);
  for (const word of ["Snack", "Dinner"])
    await expect(
      sheet.getByRole("checkbox", { name: `${dayWords(day)} · ${word}` }),
    ).toBeVisible();
  await expect(
    sheet.getByRole("checkbox", {
      name: `${dayWords(addDays(day, 1))} · Breakfast`,
    }),
  ).toBeVisible();
  // The server says no as well.
  const refused = await page.request.post(
    `/api/v1/plan/items/${item.item_id}/batch`,
    {
      data: {
        tub_count: 1,
        pattern: "pick",
        placements: [{ date: before, slot_id: slot.Lunch }],
      },
      headers: key(),
    },
  );
  expect(refused.status()).toBe(422);
  expect(((await refused.json()) as { code: string }).code).toBe(
    "not_after_cook",
  );
});

/** How many things a day already has, as Month counts them: one chip per item in its meals. */
async function thingsOn(page: Page, day: string): Promise<number> {
  const meals = (await planRange(page, day, day)).meals as {
    date: string;
    items: unknown[];
  }[];
  return meals
    .filter((m) => m.date === day)
    .reduce((n, m) => n + m.items.length, 0);
}

test('F45 and F46: Month shows the cooking first and "+N more", and a batch whose tubs run into the month', async ({
  page,
}) => {
  test.skip(isPhone(page), "the phone Month is a dot grid");
  const { slot } = await setup(page);
  const name = `Stew ${stamp()}`;
  const others = `Rice ${stamp()}`;
  const nov = (n: number) => `2026-11-${String(n).padStart(2, "0")}`;
  const day = nov(8 + 3 * projectIndex()); // this project's own November days
  // In a full run other test files' meals can be on this day too: count them first.
  const before = await thingsOn(page, day);
  const cook = await planned(
    page,
    await makeRecipe(page, name),
    day,
    slot.Lunch,
  );
  for (const s of ["Breakfast", "Dinner", "Snack"])
    await planned(page, await makeRecipe(page, `${others} ${s}`), day, slot[s]);
  const dec = nov(30);
  const late = await planned(
    page,
    await makeRecipe(page, `${name} late`),
    dec,
    slot.Dinner,
  );
  await call(page, "POST", `/plan/items/${late.item_id}/batch`, {
    tub_count: 1,
    pattern: "lunch_dinner",
  });
  await call(page, "POST", `/plan/items/${cook.item_id}/batch`, {
    tub_count: 1,
    pattern: "pick",
  });
  await page.goto("/plan");
  await page
    .getByRole("group", { name: "View" })
    .getByRole("button", { name: "Month" })
    .click();
  await page.getByRole("button", { name: "Next month" }).click(); // October → November
  const cell = page.getByTestId(`day-${day}`);
  const chips = cell.getByRole("button", { name: /Open menu$/ });
  await expect(chips.first()).toContainText(name); // the cooking, though lunch comes after breakfast
  // A day shows three things (cabledrawer 2 Nov: up to 3 a day) and the rest are "+N more".
  await expect(chips).toHaveCount(3);
  const more = cell.getByRole("button", { name: `+${before + 1} more` });
  await expect(more).toBeVisible();
  // December: the batch cooked on 30 November, whose tub is eaten in December, is listed.
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(
    page
      .getByRole("heading", { level: 3, name: "Batches this month" })
      .locator(".."),
  ).toContainText(`${name} late`);
});
