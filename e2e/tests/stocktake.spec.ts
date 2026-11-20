import { test, expect, testNow, type Page } from "./clock.ts";
import { key, stamp } from './helpers.ts';
import { checkPage, setAccountTheme } from "./a11y.ts";

// The Stocktake (0.8 S6, F118): place by place, None · ¼ · ½ · ¾ · Full, a count, a staple, the
// pack size asked once, Stop and carry on later, and Undo of one answer. Runs on the phone
// (390 px) and the computer (1280 px) projects. The household's stocktake is shared, so each test
// starts a new one and makes its own places (and, in the end, removes them), with names no other
// test uses; every other place is marked finished, so the screen opens at the test's own.

async function api(
  page: Page,
  method: "POST" | "PATCH" | "DELETE",
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
  return response.json();
}

const get = async (page: Page, path: string) =>
  (await page.request.get(`/api/v1${path}`)).json();

interface Mine {
  places: { id: number; name: string }[];
}

let made: { page: Page; ids: number[] }[] = [];

/** A new stocktake with these places of the test's own, and every other place finished. */
async function start(page: Page, names: string[]): Promise<Mine> {
  await api(page, "POST", "/stocktake/restart", {});
  const places: Mine["places"] = [];
  for (const name of names) {
    const place = await api(page, "POST", "/places", {
      name: `${name} ${stamp()}`,
      kind: "cupboard",
    });
    places.push({ id: place.id, name: place.name });
  }
  made.push({ page, ids: places.map((p) => p.id) });
  const everything = (await get(page, "/stocktake")) as {
    places: { id: number }[];
  };
  for (const other of everything.places) {
    if (!places.some((p) => p.id === other.id))
      await api(page, "POST", `/stocktake/places/${other.id}/finish`, {});
  }
  return { places };
}

test.afterEach(async ({ page }) => {
  // The places made here go, with what is in them moved to the Cupboard (as other tests leave
  // their own unique ingredients there); the next test starts a new stocktake anyway.
  const mine = made;
  made = [];
  if (!mine.length) return;
  const all = (
    (await get(page, "/places")) as { places: { id: number; name: string }[] }
  ).places;
  const cupboard = all.find((p) => p.name === "Cupboard")!.id;
  for (const { ids } of mine)
    for (const id of ids)
      if (all.some((p) => p.id === id))
        await page.request.fetch(`/api/v1/places/${id}?move_to=${cupboard}`, {
          method: "DELETE",
          headers: key(),
        });
  await api(page, "POST", "/stocktake/restart", {});
});

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

async function food(
  page: Page,
  name: string,
  placeId: number,
  extra: {
    size?: { name: string; amount: number };
    counted_as?: "weight" | "volume" | "count";
    staple?: boolean;
  } = {},
) {
  const unique = `${name} ${stamp()}`;
  const { food: found } = await api(page, "POST", "/foods", {
    name: unique,
    place_id: placeId,
    ...(extra.counted_as ? { counted_as: extra.counted_as } : {}),
    ...(extra.staple ? { staple: true } : {}),
  });
  if (extra.size)
    await api(page, "POST", `/foods/${found.id}/sizes`, extra.size);
  return { id: found.id as number, name: unique };
}

/** How much of a food is in a place, in its base unit (g, ml or items). */
async function amountIn(page: Page, foodId: number, placeId: number) {
  const pantry = await get(page, "/pantry");
  const place = pantry.places.find((p: { id: number }) => p.id === placeId);
  const group = place?.groups.find(
    (g: { food: { id: number } }) => g.food.id === foodId,
  );
  return (group?.stock.amount ?? 0) as number;
}

const item = (page: Page, name: string) =>
  page.getByRole("listitem").filter({ hasText: name });

async function openStocktake(page: Page) {
  await page.goto("/pantry");
  await page.getByRole("link", { name: "Stocktake", exact: true }).click();
  await expect(page).toHaveURL(/\/pantry\/stocktake$/);
}

test("the Stocktake button is in the Pantry header and opens the screen", async ({
  page,
}) => {
  const mine = await start(page, ["Button shelf"]);
  await page.goto("/pantry");
  const button = page.getByRole("link", { name: "Stocktake", exact: true });
  await expect(button).toBeVisible();
  // In the header, level with the title (and the Add to pantry button).
  const header = page.locator("header.page-header");
  await expect(header.getByRole("link", { name: "Stocktake" })).toBeVisible();
  await button.click();
  await expect(
    page.getByRole("heading", { name: `Stocktake · ${mine.places[0]!.name}` }),
  ).toBeVisible();
  await expect(page.getByText(/^Place \d+ of \d+$/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Stop, carry on later" }),
  ).toBeVisible();
});

test("a whole place: picks, a count, a staple, then on to the end", async ({
  page,
}) => {
  const mine = await start(page, ["Whole shelf"]);
  const shelf = mine.places[0]!;
  const dal = await food(page, "Whole dal", shelf.id, {
    size: { name: "bag", amount: 1000 },
  });
  const eggs = await food(page, "Whole eggs", shelf.id, {
    counted_as: "count",
  });
  const sambar = await food(page, "Whole sambar", shelf.id, {
    size: { name: "jar", amount: 200 },
  });
  const rice = await food(page, "Whole rice", shelf.id, { staple: true });

  await openStocktake(page);
  await expect(
    page.getByRole("heading", { name: `Stocktake · ${shelf.name}` }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "How much is there? A best guess is fine. 0 of 3 done here.",
    ),
  ).toBeVisible();

  // Rows A to Z: a staple says so, with no picks.
  await expect(item(page, rice.name)).toContainText("A staple: not counted.");
  await expect(item(page, rice.name).getByRole("radio")).toHaveCount(0);

  // A pick: ½ of a 1 kg bag, saved at once, with Undo in the toast.
  await item(page, dal.name).getByRole("radio", { name: "½ left" }).click();
  await expect(
    item(page, dal.name).getByRole("radio", { name: "½ left" }),
  ).toHaveAttribute("aria-checked", "true");
  await expect(
    page.getByText(/Stocktake: .* ½ bag in the Whole shelf/),
  ).toBeVisible();
  await expect.poll(() => amountIn(page, dal.id, shelf.id)).toBe(500);

  // Another bag besides the open one.
  const more = item(page, dal.name).getByRole("group", {
    name: `${dal.name}: more packets`,
  });
  await more.getByRole("button", { name: "More bags" }).click();
  await expect(more).toContainText("1");
  await expect.poll(() => amountIn(page, dal.id, shelf.id)).toBe(1500);

  // A count, with − and +.
  const count = item(page, eggs.name).getByRole("group", {
    name: `${eggs.name}: how many`,
  });
  await expect(count.getByRole("button", { name: `Fewer ${eggs.name}` })).toBeDisabled();
  await count.getByRole("button", { name: `More ${eggs.name}` }).click();
  await count.getByRole("button", { name: `More ${eggs.name}` }).click();
  await expect(count).toContainText("2");
  await expect.poll(() => amountIn(page, eggs.id, shelf.id)).toBe(2);
  await count.getByRole("button", { name: `Fewer ${eggs.name}` }).click();
  await expect.poll(() => amountIn(page, eggs.id, shelf.id)).toBe(1);

  // None.
  await item(page, sambar.name).getByRole("radio", { name: "None" }).click();
  await expect(
    item(page, sambar.name).getByRole("radio", { name: "None" }),
  ).toHaveAttribute("aria-checked", "true");

  await expect(
    page.getByText(
      /^How much is there\? A best guess is fine\. 3 of 3 done here\.$/,
    ),
  ).toBeVisible();
  await checkPage(page); // both themes, with answers and a staple on screen

  // The end: a place is finished with the last button, and the stocktake with it.
  await page.getByRole("button", { name: /^(Next: .* →|Finish)$/ }).click();
  await expect(
    page.getByRole("heading", { name: "Stocktake finished" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Back to Pantry" }),
  ).toBeVisible();
});

test("a new pack size is asked once, then the picks work", async ({ page }) => {
  const mine = await start(page, ["Size shelf"]);
  const shelf = mine.places[0]!;
  const tamarind = await food(page, "Size tamarind", shelf.id);
  const jaggery = await food(page, "Size jaggery", shelf.id);

  await openStocktake(page);
  const row = item(page, tamarind.name);
  await expect(row).toContainText("no pack size yet");
  await expect(row).toContainText("What does it come in? Asked once.");
  // The picks wait for a size; None doesn't need one.
  await expect(row.getByRole("radio", { name: "½ left" })).toBeDisabled();
  await expect(row.getByRole("radio", { name: "None" })).toBeEnabled();

  // A common size: 500 g becomes the Usual size.
  await row.getByRole("button", { name: "500 g", exact: true }).click();
  await expect(row).toContainText(/pack · 500\sg/);
  await expect(row).not.toContainText("What does it come in?");
  await expect(row.getByRole("radio", { name: "¼ left" })).toBeEnabled();
  await row.getByRole("radio", { name: "¼ left" }).click();
  await expect.poll(() => amountIn(page, tamarind.id, shelf.id)).toBe(125);
  const sizes = (await get(page, `/foods/${tamarind.id}`)).sizes as {
    usual: boolean;
    amount: number;
  }[];
  expect(sizes.map((s) => [s.usual, s.amount])).toEqual([[true, 500]]);

  // Other…: type a size.
  const other = item(page, jaggery.name);
  await other.getByRole("button", { name: "Other…" }).click();
  await other.getByLabel(`${jaggery.name}: size of one pack`).fill("750");
  await other.getByRole("button", { name: "Use this size" }).click();
  await expect(other).toContainText(/pack · 750\sg/);
  const typed = (await get(page, `/foods/${jaggery.id}`)).sizes as {
    usual: boolean;
    amount: number;
  }[];
  expect(typed.map((s) => [s.usual, s.amount])).toEqual([[true, 750]]);
  await checkPage(page);
});

test("It’s a staple turns an ingredient into one, and Undo turns it back", async ({
  page,
}) => {
  const mine = await start(page, ["Staple shelf"]);
  const shelf = mine.places[0]!;
  const powder = await food(page, "Staple powder", shelf.id, {
    size: { name: "jar", amount: 200 },
  });
  await openStocktake(page);
  const row = item(page, powder.name);
  await row.getByRole("button", { name: "It’s a staple" }).click();
  await expect(row).toContainText("A staple: not counted.");
  await expect(row.getByRole("radio")).toHaveCount(0);
  await expect(
    page.getByText(/Stocktake: .* is a staple in the Staple shelf/),
  ).toBeVisible();
  await expect
    .poll(async () => (await get(page, `/foods/${powder.id}`)).staple)
    .toBe(true);

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(row.getByRole("radio", { name: "None" })).toBeVisible();
  await expect(row).not.toContainText("A staple: not counted.");
  await expect
    .poll(async () => (await get(page, `/foods/${powder.id}`)).staple)
    .toBe(false);
});

test("Undo of one answer puts the amount back and the row to unanswered", async ({
  page,
}) => {
  const mine = await start(page, ["Undo shelf"]);
  const shelf = mine.places[0]!;
  const dal = await food(page, "Undo dal", shelf.id, {
    size: { name: "bag", amount: 1000 },
  });
  const rice = await food(page, "Undo rice", shelf.id, {
    size: { name: "bag", amount: 1000 },
  });
  await openStocktake(page);
  await item(page, rice.name).getByRole("radio", { name: "Full" }).click();
  await expect.poll(() => amountIn(page, rice.id, shelf.id)).toBe(1000);
  await item(page, dal.name).getByRole("radio", { name: "¾ left" }).click();
  await expect.poll(() => amountIn(page, dal.id, shelf.id)).toBe(750);
  await expect(
    page.getByText(
      /^How much is there\? A best guess is fine\. 2 of 2 done here\.$/,
    ),
  ).toBeVisible();

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => amountIn(page, dal.id, shelf.id)).toBe(0);
  for (const radio of await item(page, dal.name).getByRole("radio").all()) {
    await expect(radio).toHaveAttribute("aria-checked", "false");
  }
  await expect(
    page.getByText(
      /^How much is there\? A best guess is fine\. 1 of 2 done here\.$/,
    ),
  ).toBeVisible();
  // The other answer stays.
  expect(await amountIn(page, rice.id, shelf.id)).toBe(1000);
  await expect(
    item(page, rice.name).getByRole("radio", { name: "Full" }),
  ).toHaveAttribute("aria-checked", "true");
});

test("Something else joins the place", async ({ page }) => {
  const mine = await start(page, ["Else shelf"]);
  const shelf = mine.places[0]!;
  const fridge = (
    (await get(page, "/places")) as { places: { id: number; name: string }[] }
  ).places.find((p) => p.name === "Fridge")!;
  const jam = await food(page, "Else jam", fridge.id);
  await openStocktake(page);
  await expect(item(page, jam.name)).toHaveCount(0);
  await page
    .getByRole("button", { name: `+ Something else in the ${shelf.name}` })
    .click();
  const box = page.getByRole("searchbox", {
    name: `Find an ingredient to count in the ${shelf.name}`,
  });
  await box.fill(jam.name);
  // The ingredient itself (exact name): not "+ New ingredient", which shows first while the
  // search is still answering.
  await page.getByRole("button", { name: jam.name, exact: true }).click();
  await expect(item(page, jam.name)).toBeVisible();
  await expect(item(page, jam.name)).toContainText("no pack size yet");
});

test("Stop, carry on later reopens at the first place not finished, also on a second phone", async ({
  page,
  browser,
  baseURL,
  storageState,
}) => {
  const mine = await start(page, ["First shelf", "Second shelf"]);
  const [first, second] = mine.places as [
    { id: number; name: string },
    { id: number; name: string },
  ];
  const dal = await food(page, "Carry dal", first.id, {
    size: { name: "bag", amount: 1000 },
  });
  await food(page, "Carry rice", second.id, {
    size: { name: "bag", amount: 1000 },
  });

  await openStocktake(page);
  await expect(
    page.getByRole("heading", { name: `Stocktake · ${first.name}` }),
  ).toBeVisible();
  await item(page, dal.name).getByRole("radio", { name: "½ left" }).click();
  await expect.poll(() => amountIn(page, dal.id, first.id)).toBe(500);
  await page.getByRole("button", { name: `Next: ${second.name} →` }).click();
  await expect(
    page.getByRole("heading", { name: `Stocktake · ${second.name}` }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: `← ${first.name}` }),
  ).toBeVisible();

  // The server has the first place as finished (Next saves a moment after the screen moves on).
  await expect
    .poll(async () => {
      const all = (await get(page, "/stocktake")) as {
        places: { id: number; finished: boolean }[];
      };
      return all.places.find((p) => p.id === first.id)?.finished;
    })
    .toBe(true);
  // Stop: leave. Opening Stocktake again goes to the first place not finished: the second.
  await page.getByRole("link", { name: "Stop, carry on later" }).click();
  await expect(page).toHaveURL(/\/pantry$/);
  await page.getByRole("link", { name: "Stocktake", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: `Stocktake · ${second.name}` }),
  ).toBeVisible();

  // A second phone (its own browser, the same household) carries on from the same place.
  const context = await browser.newContext({
    storageState,
    baseURL,
    viewport: page.viewportSize() ?? undefined,
  });
  await context.clock.install({ time: testNow() });
  const phone = await context.newPage();
  await phone.goto("/pantry");
  await phone.getByRole("link", { name: "Stocktake", exact: true }).click();
  await expect(
    phone.getByRole("heading", { name: `Stocktake · ${second.name}` }),
  ).toBeVisible();
  // And what the first place was left at is kept: its answer stands.
  await phone.getByRole("button", { name: `← ${first.name}` }).click();
  await expect(
    item(phone, dal.name).getByRole("radio", { name: "½ left" }),
  ).toHaveAttribute("aria-checked", "true");
  await context.close();
});
