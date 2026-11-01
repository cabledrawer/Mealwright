import { test, expect, type Locator, type Page } from "./clock.ts";
import { setAccountTheme } from "./a11y.ts";

// The Plan's Month and day (0.7, P4): the COOK and Today tags stay inside their day (F84), the
// month fits one screen and a full day shows 3 items then "+N more" (F47), a click anywhere in a
// day opens it (F53) and offers the meal, a recipe, a freezer tub and Cook once here (F52), and
// "Fill from freezer first" says which meals it filled and why, with one Undo.
//
// The days (all far ahead, since a batch's tubs cannot be in the past). Plan weeks 80 to 83 ahead
// are shared with plan-cards.spec.ts (computer only: Sat/Sun, Thu/Fri and, in weeks 80 to 82,
// Mon/Tue), so this spec takes only Wednesdays, and in week 83 the Monday and Tuesday too:
//   computer: A (F84) Wednesday of week 80, B (F47) week 81, D (tub, Cook once here) week 82;
//   WebKit:   A Monday of week 83, B Tuesday of week 83, D Wednesday of week 83;
//   phone:    D Wednesday of week 80 (the phone has no month grid, so no A or B).
// The click-a-day-and-pick-a-recipe test (C) plans on a day in the past (it needs no batch), in a
// week of the project's own: 9, 14 or 19 weeks back. Everything is named with a word no other
// test uses ("Moon…"). The test that mocks "Fill from freezer first" plans nothing.

const key = () => ({ "idempotency-key": crypto.randomUUID() });

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

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

type Which = "A" | "B" | "C" | "D";
const kind = () => {
  const name = test.info().project.name;
  return name.startsWith("phone")
    ? "phone"
    : name.startsWith("webkit")
      ? "webkit"
      : "computer";
};
/** The test's own day. Today is a Saturday, so today + 7 × weeks is one too; Wednesday is 3 before. */
function dayFor(today: string, which: Which): string {
  const wed = (week: number) => addDays(today, 7 * week - 3);
  if (which === "C")
    return addDays(
      today,
      -7 * { computer: 9, webkit: 14, phone: 19 }[kind()] + 1,
    );
  if (kind() === "computer") return wed({ A: 80, B: 81, D: 82 }[which]);
  if (kind() === "webkit")
    return addDays(wed(83), { A: -2, B: -1, D: 0 }[which]);
  return wed(80);
}

const stamp = () => `Moon${kind()}${Date.now().toString(36)}`;

async function setup(page: Page) {
  const household = (await (
    await page.request.get("/api/v1/household")
  ).json()) as { today: string };
  const list = (await (
    await page.request.get("/api/v1/meal-slots")
  ).json()) as { id: number; name: string }[];
  const slot = Object.fromEntries(list.map((s) => [s.name, s.id])) as Record<
    string,
    number
  >;
  await call(page, "PATCH", `/meal-slots/${slot.Snack}`, { enabled: true });
  return { today: household.today, slot };
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
  })) as {
    item_id: number;
    meal_id: number;
  };

/** A batch cooked on `day` at dinner, with its two tubs the next day: lunch and dinner. */
async function batchWithTubs(
  page: Page,
  name: string,
  day: string,
  slot: Record<string, number>,
) {
  const cook = await planned(
    page,
    await makeRecipe(page, name),
    day,
    slot.Dinner,
  );
  const next = addDays(day, 1);
  await call(page, "POST", `/plan/items/${cook.item_id}/batch`, {
    tub_count: 2,
    pattern: "pick",
    placements: [
      { date: next, slot_id: slot.Lunch },
      { date: next, slot_id: slot.Dinner },
    ],
  });
  return { cook, next };
}

/** Month, on the month that holds `day`. */
async function openMonthOf(page: Page, today: string, day: string) {
  await page.goto("/plan");
  await page
    .getByRole("group", { name: "View" })
    .getByRole("button", { name: "Month" })
    .click();
  const months = (iso: string) =>
    Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7));
  const steps = months(day) - months(today);
  for (let i = 0; i < Math.abs(steps); i++) {
    await page
      .getByRole("button", {
        name: steps > 0 ? "Next month" : "Previous month",
      })
      .click();
  }
}

const inside = async (inner: Locator, outer: Locator) => {
  const [a, b] = [await inner.boundingBox(), await outer.boundingBox()];
  expect(a, "inner box").not.toBeNull();
  expect(b, "outer box").not.toBeNull();
  const slack = 0.5;
  return (
    a!.x >= b!.x - slack &&
    a!.y >= b!.y - slack &&
    a!.x + a!.width <= b!.x + b!.width + slack &&
    a!.y + a!.height <= b!.y + b!.height + slack
  );
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem("mealwright.plan-show", "both"),
  );
  await setAccountTheme(page, "auto");
});

test.describe("on a computer", () => {
  test.skip(() => kind() === "phone", "the month grid is the computer’s");

  for (const width of [1280, 1100]) {
    test(`F84: the COOK and Today tags stay inside their own day at ${width} px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      const { today, slot } = await setup(page);
      const day = dayFor(today, "A");
      await batchWithTubs(page, `${stamp()} Curry`, day, slot);

      await openMonthOf(page, today, day);
      const cooking = page.getByTestId(`day-${day}`);
      await expect(cooking.getByText("COOK", { exact: true })).toBeVisible();
      expect(
        await inside(cooking.getByText("COOK", { exact: true }), cooking),
      ).toBe(true);
      expect(
        await inside(
          cooking.getByRole("button", { name: /^Add to / }),
          cooking,
        ),
      ).toBe(true);

      await page.getByRole("button", { name: "Today", exact: true }).click();
      const here = page.getByTestId(`day-${today}`);
      await expect(here.getByText("Today", { exact: true })).toBeVisible();
      expect(await inside(here.getByText("Today", { exact: true }), here)).toBe(
        true,
      );
    });
  }
});
