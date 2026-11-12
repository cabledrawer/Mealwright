import { test, expect, type Page } from "./clock.ts";
import { setAccountTheme } from "./a11y.ts";

// "Add a starter pack" on Ingredients (0.8 R4, cabledrawer 7 Nov), against the real server, on a
// phone and on a computer. Every test undoes what it added, so the household the other
// screens share is left as it was. The numbers in the dialog depend on what the household
// already has, so they are matched loosely.

type Row = { id: number; name: string; staple: boolean };

async function foods(page: Page): Promise<Row[]> {
  const response = await page.request.get("/api/v1/foods?limit=500");
  expect(response.status()).toBe(200);
  return ((await response.json()) as { foods: Row[] }).foods;
}

async function pantryItems(page: Page): Promise<number> {
  const response = await page.request.get("/api/v1/pantry");
  return ((await response.json()) as { counts: { items: number } }).counts
    .items;
}

async function openPack(page: Page, pack: string) {
  await page.goto("/recipes/ingredients");
  await page.getByRole("button", { name: "Add a starter pack" }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("heading", { name: "Add a starter pack" }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: new RegExp(`^${pack}`) }).click();
  await expect(
    dialog.getByRole("heading", { name: `${pack} starter pack` }),
  ).toBeVisible();
  return dialog;
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

test("add a pack, untick two, add: the rest come in, then one Undo takes them all away", async ({
  page,
}) => {
  const before = new Set((await foods(page)).map((f) => f.name));
  const stocked = await pantryItems(page);
  const dialog = await openPack(page, "Japanese");
  // Every ingredient is ticked to start with; untick two.
  await expect(
    dialog.getByRole("checkbox", { name: "miso", exact: true }),
  ).toBeChecked();
  await dialog.getByRole("checkbox", { name: "mirin", exact: true }).click();
  await dialog.getByRole("checkbox", { name: "sake", exact: true }).click();
  await expect(
    dialog.getByRole("checkbox", { name: "mirin", exact: true }),
  ).not.toBeChecked();
  const add = dialog.getByRole("button", { name: /^Add \d+ ingredients$/ });
  const count = Number(/\d+/.exec(await add.innerText())![0]);
  await add.click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText(`Added the Japanese starter pack: ${count} ingredients`),
  ).toBeVisible();

  // The toast shows at once and the server answers a moment later: wait for it.
  const newOnes = async () =>
    (await foods(page)).filter((f) => !before.has(f.name));
  await expect.poll(async () => (await newOnes()).length).toBe(count);
  const added = await newOnes();
  const names = added.map((f) => f.name);
  expect(names).toContain("miso");
  expect(names).not.toContain("mirin");
  expect(names).not.toContain("sake");

  // Nothing but ingredients: the pantry is as it was.
  expect(await pantryItems(page)).toBe(stocked);

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(
      async () => (await foods(page)).filter((f) => !before.has(f.name)).length,
    )
    .toBe(0);
  const scrollWidth = await page.evaluate(
    () => document.documentElement.scrollWidth,
  );
  expect(scrollWidth).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test("the dialog's code comes on first opening; Escape closes it, focus goes back to the button, and it opens again", async ({
  page,
}) => {
  // Fetched when first opened (page size limit), so nothing of it is in the page before.
  await page.goto("/recipes/ingredients");
  const opener = page.getByRole("button", { name: "Add a starter pack" });
  await expect(opener).toBeVisible();
  await expect(page.locator("dialog[open]")).toHaveCount(0);
  for (let round = 0; round < 2; round++) {
    await opener.click();
    const dialog = page.getByRole("dialog");
    await expect(
      dialog.getByRole("heading", { name: "Add a starter pack" }),
    ).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: /^Japanese/ }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(opener).toBeFocused();
  }
});

test("an ingredient already there by its other name shows Already have and is skipped", async ({
  page,
}) => {
  // "Katsuobushi" is another name of bonito flakes in the pack-size table.
  const existing = (await foods(page)).find((f) => f.name === "Katsuobushi");
  let made: number | null = null;
  if (!existing) {
    const response = await page.request.post("/api/v1/foods", {
      data: { name: "Katsuobushi", counted_as: "weight" },
      headers: { "idempotency-key": crypto.randomUUID() },
    });
    expect(response.status(), await response.text()).toBe(201);
    made = ((await response.json()) as { food: { id: number } }).food.id;
  }
  const before = new Set((await foods(page)).map((f) => f.name));
  try {
    const dialog = await openPack(page, "Japanese");
    const row = dialog
      .getByRole("listitem")
      .filter({ hasText: "bonito flakes" });
    await expect(row.getByText("Already have as “Katsuobushi”")).toBeVisible();
    await expect(row.getByRole("checkbox")).toBeDisabled();
    await dialog.getByRole("button", { name: /^Add \d+ ingredients$/ }).click();
    await expect(
      page.getByText(/^Added the Japanese starter pack: \d+ ingredients$/),
    ).toBeVisible();
    const after = await foods(page);
    expect(after.some((f) => f.name === "bonito flakes")).toBe(false);
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect
      .poll(
        async () =>
          (await foods(page)).filter((f) => !before.has(f.name)).length,
      )
      .toBe(0);
  } finally {
    if (made !== null) {
      await page.request.delete(`/api/v1/foods/${made}`, {
        headers: { "idempotency-key": crypto.randomUUID() },
      });
    }
  }
});

test("Household items come in as staples", async ({ page }) => {
  const before = new Set((await foods(page)).map((f) => f.name));
  const dialog = await openPack(page, "Household");
  await expect(dialog.getByText(/Don’t count it/)).toBeVisible();
  await dialog.getByRole("button", { name: /^Add \d+ ingredients$/ }).click();
  await expect(
    page.getByText(/^Added the Household starter pack: \d+ ingredients$/),
  ).toBeVisible();
  await expect
    .poll(
      async () => (await foods(page)).filter((f) => !before.has(f.name)).length,
    )
    .toBeGreaterThan(0);
  const added = (await foods(page)).filter((f) => !before.has(f.name));
  expect(added.every((f) => f.staple)).toBe(true);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(
      async () => (await foods(page)).filter((f) => !before.has(f.name)).length,
    )
    .toBe(0);
});

test("Undo of a pack keeps an ingredient a recipe uses and says so (cabledrawer 7 Nov)", async ({
  page,
}) => {
  const before = new Set((await foods(page)).map((f) => f.name));
  const dialog = await openPack(page, "Japanese");
  const add = dialog.getByRole("button", { name: /^Add \d+ ingredients$/ });
  const count = Number(/\d+/.exec(await add.innerText())![0]);
  await add.click();
  await expect(
    page.getByText(`Added the Japanese starter pack: ${count} ingredients`),
  ).toBeVisible();
  // The toast shows at once and the server answers a moment later: wait for it.
  await expect
    .poll(async () => (await foods(page)).some((f) => f.name === "miso"))
    .toBe(true);
  const miso = (await foods(page)).find((f) => f.name === "miso")!;
  const made = await page.request.post("/api/v1/recipes", {
    data: {
      name: "Undo keeps miso",
      lines: [{ words: "miso", food_id: miso.id }],
    },
  });
  expect(made.status()).toBe(201);
  const recipe = (await made.json()) as { id: number };

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(
    page.getByText(
      "Took out what could be: 1 ingredient is already in use, so it stays.",
    ),
  ).toBeVisible();
  const left = (await foods(page)).filter((f) => !before.has(f.name));
  expect(left.map((f) => f.name)).toEqual(["miso"]);

  // Leave the household as it was.
  await page.request.delete(`/api/v1/recipes/${recipe.id}`);
  await page.request.delete(`/api/v1/foods/${miso.id}`);
});

test("F181: a pack card says how many ingredients and how many are already here, with a space before the dot", async ({
  page,
}) => {
  // Make sure the Japanese pack has something already here.
  const made = await page.request.post("/api/v1/foods", {
    data: { name: "miso", counted_as: "weight" },
    headers: { "idempotency-key": crypto.randomUUID() },
  });
  expect([201, 409, 422]).toContain(made.status());
  await page.goto("/recipes/ingredients");
  await page.getByRole("button", { name: "Add a starter pack" }).click();
  const dialog = page.getByRole("dialog");
  const japanese = dialog.getByRole("button", { name: /^Japanese/ });
  await expect(japanese).toBeVisible();
  await expect(japanese).toContainText(/ingredients · \d+ already here/);
  for (const card of await dialog.getByRole("button", { name: /\d+ ingredients/ }).all()) {
    expect(await card.innerText()).not.toMatch(/ingredients·/);
  }
});
