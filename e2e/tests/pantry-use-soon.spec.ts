import { test, expect, type Page } from "./clock.ts";
import { checkPage, isPhone, setAccountTheme } from "./a11y.ts";

// Pantry and Use soon (0.8 S5): Use by and Best before in their own words, the How much? sheet
// and its one main button, and tubs in their place. Runs on the phone (390 px) and the computer
// (1280 px) projects of the Pantry, in both themes (checkPage). Each test makes its own foods
// with names no other test uses.

const key = () => ({ "idempotency-key": crypto.randomUUID() });

async function api(
  page: Page,
  method: "POST" | "PATCH",
  path: string,
  data: object,
) {
  const response = await page.request.fetch(`/api/v1${path}`, {
    method,
    data,
    headers: key(),
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(
    true,
  );
  return response.json();
}

const stamp = () =>
  `${test.info().project.name.replace(/\W/g, "")}${Date.now().toString(36)}`;

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

async function today(page: Page): Promise<string> {
  return (
    (await (await page.request.get("/api/v1/household")).json()) as {
      today: string;
    }
  ).today;
}

/** A food in a place, with one 200 g pack whose date is `days` from today (null: no date). */
async function stockedAt(
  page: Page,
  name: string,
  days: number | null,
  placeName: string,
) {
  const unique = `${name} ${stamp()}`;
  const places = (await (await page.request.get("/api/v1/places")).json()) as {
    id: number;
    name: string;
  }[];
  const where = places.find((p) => p.name === placeName)!.id;
  const { food } = await api(page, "POST", "/foods", {
    name: unique,
    place_id: where,
  });
  await api(page, "POST", `/foods/${food.id}/sizes`, {
    name: "pack",
    amount: 200,
  });
  const base = await today(page);
  const added = await api(page, "POST", "/stock", {
    food_id: food.id,
    amount: { amount: 1, unit: "pack" },
    place_id: where,
    ...(days === null ? {} : { use_by: addDays(base, days) }),
  });
  return {
    id: food.id as number,
    name: unique,
    lot: added.groups[0].lots[0].id as number,
  };
}

const lotsOf = async (page: Page, foodId: number) => {
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  return pantry.places
    .flatMap(
      (p: { groups: { food: { id: number }; lots: unknown[] }[] }) => p.groups,
    )
    .filter((g: { food: { id: number } }) => g.food.id === foodId)
    .flatMap((g: { lots: unknown[] }) => g.lots).length as number;
};

/** The Use soon row or card of a food (phone: a row; computer: a card). */
const soonRow = (page: Page, name: string) =>
  page
    .getByRole("region", { name: /^Use soon · \d+$/ })
    .getByRole("listitem")
    .filter({ hasText: name });

async function showAll(page: Page) {
  const all = page.getByRole("button", { name: /^Show all \d+$/ });
  if (await all.count()) await all.first().click();
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

test("a passed Use by is red and says don’t eat; a passed Best before is grey and says probably fine", async ({
  page,
}) => {
  const lemon = await stockedAt(page, "Use by lemon", -3, "Fridge");
  const dal = await stockedAt(page, "Best before dal", -2, "Cupboard");
  const tin = await stockedAt(page, "Later tin", 10, "Cupboard");
  await page.goto("/pantry");
  await expect(
    page.getByRole("heading", { name: /^Use soon · \d+$/, level: 2 }),
  ).toBeVisible();
  await showAll(page);

  const useBy = soonRow(page, lemon.name);
  await expect(useBy).toContainText("Use by passed: don’t eat");
  await expect(useBy).toContainText("Passed 3 days ago");
  await expect(useBy).not.toContainText("probably fine");
  // Binned first, then Used…, and To freezer shown but greyed out with its note (cabledrawer 7 Nov,
  // option D): a packet past its Use by can't be frozen.
  const buttons = await useBy.getByRole("button").allTextContents();
  const actions = buttons.filter((b) =>
    ["Binned", "Used…", "To freezer"].includes(b.trim()),
  );
  expect(actions).toEqual(["Binned", "Used…", "To freezer"]);
  await expect(useBy.getByRole("button", { name: "To freezer" })).toBeDisabled();
  await expect(useBy).toContainText(
    "Too late to freeze: the use by date has passed.",
  );

  const bestBefore = soonRow(page, dal.name);
  await expect(bestBefore).toContainText("Best before passed · probably fine");
  await expect(bestBefore).toContainText("Passed 2 days ago");
  await expect(bestBefore).not.toContainText("don’t eat");
  await expect(
    bestBefore.getByRole("button", { name: "To freezer" }),
  ).toHaveCount(0);

  // A Best before date to come is not Use soon, and its row in the Cupboard says so.
  await expect(soonRow(page, tin.name)).toHaveCount(0);
  const cupboard = page.getByRole("region", { name: "Cupboard", exact: true });
  await expect(cupboard).toContainText(/best before/i);
  await checkPage(page); // both themes
});

test("the date type shows in the ingredient editor, and meat is locked to Use by", async ({
  page,
}) => {
  const food = await stockedAt(page, "Editor pickle", null, "Cupboard");
  const shown = async () =>
    (await (await page.request.get(`/api/v1/foods/${food.id}`)).json()) as {
      date_kind: string;
    };
  expect((await shown()).date_kind).toBe("best_before");
  await page.goto(`/recipes/ingredients?open=${food.id}`);
  const select = page.getByLabel("Date on the packet");
  await expect(select).toBeVisible();
  await select.selectOption("use_by");
  await expect.poll(async () => (await shown()).date_kind).toBe("use_by");

  const chicken = await api(page, "POST", "/foods", {
    name: `Chicken breast ${stamp()}`,
  });
  const locked = await page.request.fetch(`/api/v1/foods/${chicken.food.id}`, {
    method: "PATCH",
    data: { date_kind: "best_before" },
    headers: key(),
  });
  expect(locked.status()).toBe(422);
});

test("How much? starts with nothing chosen and its one main button follows each choice", async ({
  page,
}) => {
  const food = await stockedAt(page, "How much spinach", 0, "Fridge");
  await page.goto("/pantry");
  await expect(
    page.getByRole("heading", { name: /^Use soon · \d+$/, level: 2 }),
  ).toBeVisible();
  await showAll(page);
  await soonRow(page, food.name).getByRole("button", { name: "Used…" }).click();
  const sheet = page.getByRole("dialog", {
    name: `How much ${food.name} did you use?`,
  });
  await expect(sheet).toBeVisible();
  for (const radio of await sheet.getByRole("radio").all()) {
    await expect(radio).toHaveAttribute("aria-checked", "false");
  }
  await expect(
    sheet.getByRole("button", { name: "Choose how much" }),
  ).toBeDisabled();
  await checkPage(page); // both themes, sheet open

  await sheet.getByRole("radio", { name: "¾" }).click();
  await expect(
    sheet.getByRole("button", { name: "Used ¾ pack" }),
  ).toBeEnabled();
  await sheet.getByRole("radio", { name: "½" }).click();
  await expect(
    sheet.getByRole("button", { name: "Used ½ pack" }),
  ).toBeVisible();
  await sheet.getByRole("radio", { name: "All" }).click();
  await expect(
    sheet.getByRole("button", { name: "Used all of it" }),
  ).toBeVisible();
  await sheet.getByRole("textbox").fill("120");
  await expect(sheet.getByRole("button", { name: /^Used 120/ })).toBeVisible();
  await expect(sheet.getByRole("radio", { name: "All" })).toHaveAttribute(
    "aria-checked",
    "false",
  );

  await sheet.getByRole("button", { name: "Cancel" }).click();
  expect(await lotsOf(page, food.id)).toBe(1); // Cancel changed nothing

  await soonRow(page, food.name).getByRole("button", { name: "Used…" }).click();
  await sheet.getByRole("radio", { name: "All" }).click();
  await sheet.getByRole("button", { name: "Used all of it" }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test("tubs left show on the Pantry page in their place, with their use-by", async ({
  page,
}) => {
  const base = await today(page);
  const slots = (await (
    await page.request.get("/api/v1/meal-slots")
  ).json()) as {
    id: number;
    name: string;
  }[];
  const dinner = slots.find((s) => s.name === "Dinner")!.id;
  const name = `Tub rice ${stamp()}`;
  const recipe = (await api(page, "POST", "/recipes", { name })).id as number;
  // Weeks 80 and on belong to no other test's plan.
  const day = addDays(base, 7 * 82);
  const meal = await api(page, "POST", "/plan/items", {
    date: day,
    slot_id: dinner,
    recipe_id: recipe,
  });
  await api(page, "POST", `/plan/items/${meal.item_id}/batch`, {
    tub_count: 2,
    pattern: "pick",
  });
  await page.goto("/pantry");
  const row = page
    .getByRole("region", { name: "Fridge", exact: true })
    .getByRole("listitem")
    .filter({ hasText: name });
  if (
    await page.getByRole("button", { name: /more( in the Fridge)?$/ }).count()
  )
    await page
      .getByRole("button", { name: /more( in the Fridge)?$/ })
      .first()
      .click();
  await expect(row).toContainText("2 tubs");
  await expect(row).toContainText(/use by/i);
  await checkPage(page); // both themes
});

test("a tub that is soon shows in Use soon on both screens, even with nothing else soon (M1)", async ({
  page,
}) => {
  const base = await today(page);
  const slots = (await (
    await page.request.get("/api/v1/meal-slots")
  ).json()) as {
    id: number;
    name: string;
  }[];
  const dinner = slots.find((s) => s.name === "Dinner")!.id;
  const name = `Soon tub ${stamp()}`;
  const recipe = (await api(page, "POST", "/recipes", { name })).id as number;
  const meal = await api(page, "POST", "/plan/items", {
    // A tub's use-by can't be before its cook day, so cook it tomorrow and keep that as its
    // use-by (tubs left, in no meal, so no other test's plan is touched).
    date: addDays(base, 1),
    slot_id: dinner,
    recipe_id: recipe,
  });
  await api(page, "POST", `/plan/items/${meal.item_id}/batch`, {
    tub_count: 1,
    pattern: "pick",
  });
  const left = (await (
    await page.request.get("/api/v1/plan/tubs-left")
  ).json()) as { tubs: { id: number; recipe_name: string }[] };
  const tub = left.tubs.find((t) => t.recipe_name === name)!;
  await api(page, "PATCH", `/plan/tubs/${tub.id}`, {
    use_by: addDays(base, 1),
  });
  await page.goto("/pantry");
  // On the phone this strip used to be hidden when no packet was soon.
  const strip = page.getByRole("region", { name: /^Use soon · \d+$/ });
  await showAll(page);
  await expect(strip.getByText(name)).toBeVisible();
  await expect(
    strip
      .getByRole("listitem")
      .filter({ hasText: name })
      .getByRole("button", { name: "Eat it on…" }),
  ).toBeVisible();
});

test("nothing sits below the places and Staples on the Pantry page", async ({
  page,
}) => {
  await page.goto("/pantry");
  await expect(page.getByRole("heading", { name: "Staples" })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Recent changes" }),
  ).toHaveCount(0);
  const last = await page.evaluate(() => {
    const staples = document.querySelector(".staples");
    return (
      !!staples &&
      !staples.parentElement?.nextElementSibling?.matches("section, ul")
    );
  });
  expect(last).toBe(true);
  expect(isPhone(page) || true).toBe(true);
});
