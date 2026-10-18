import { test, expect, type Page } from "@playwright/test";
import {
  checkPage,
  inTheme,
  isPhone,
  setAccountTheme,
  THEMES,
} from "./a11y.ts";

// The Shopping screen working online (0.3, PR 4), against the real server, on phone and
// desktop: lists, adding, ticking, put away, "Different pack?", "Did you buy 2?" and notes.

const key = () => ({ "idempotency-key": crypto.randomUUID() });
const tag = () => `${test.info().project.name.replace(/\W/g, "")}${Date.now()}`;

async function call(
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

async function mainList(page: Page): Promise<string> {
  const { lists } = await (
    await page.request.get("/api/v1/shopping/lists")
  ).json();
  return lists.find((l: { main: boolean }) => l.main).id;
}

/** An ingredient on the main list (by weight, in grams). */
async function onList(page: Page, name: string, amountG = 500) {
  const { food } = await call(page, "POST", "/foods", {
    name,
    counted_as: "weight",
  });
  await call(page, "POST", `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: amountG, unit: "g" },
  });
  return food.id as number;
}

/** The food with this name, once the server has it. */
async function foodNamed(page: Page, name: string) {
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(
              `/api/v1/foods?q=${encodeURIComponent(name)}`,
            )
          ).json()
        ).foods.length,
    )
    .toBe(1);
  return (
    await (
      await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)
    ).json()
  ).foods[0];
}

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

test("Shopping shows the list by shop and aisle, and passes the accessibility checks", async ({
  page,
}) => {
  const name = `Basmati ${tag()}`;
  await onList(page, name);
  await page.goto("/shopping");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Shopping");
  await expect(page.getByText(/\d+ to buy/).first()).toBeVisible();
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 3, name: "Other" }).first(),
  ).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
});

test("the list picker makes, renames and removes an extra list, with Undo", async ({
  page,
}) => {
  const list = `Party ${tag()}`;
  await page.goto("/shopping");
  await page.getByRole("button", { name: /^This week/ }).click();
  await page.getByRole("button", { name: "+ New list" }).click();
  await page.getByRole("textbox", { name: "New list name" }).fill(list);
  await page.getByRole("button", { name: "Make list" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^${list}`) }),
  ).toBeVisible();
  await expect(
    page.getByText(/^Extra list · \d+ · ticked items still go to the pantry$/),
  ).toBeVisible();

  const renamed = `${list} two`;
  await page.getByRole("button", { name: new RegExp(`^${list}`) }).click();
  await page.getByRole("button", { name: `${list} options` }).click();
  await page.getByRole("button", { name: "Rename" }).click();
  await page.getByRole("textbox", { name: "List name" }).fill(renamed);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^${renamed}`) }),
  ).toBeVisible();

  await page.getByRole("button", { name: new RegExp(`^${renamed}`) }).click();
  await page.getByRole("button", { name: `${renamed} options` }).click();
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByRole("button", { name: /^This week/ })).toBeVisible();
  const toast = page
    .getByRole("status")
    .filter({ hasText: `Removed ${renamed}` });
  await expect(toast).toBeVisible();
  await toast.getByRole("button", { name: "Undo" }).click();
  await page.getByRole("button", { name: /^This week/ }).click();
  await expect(
    page
      .getByRole("group", { name: "Lists" })
      .getByRole("button", { name: new RegExp(`^${renamed} Extra list`) }),
  ).toBeVisible();
});

test("the main list can be renamed but not removed", async ({ page }) => {
  await page.goto("/shopping");
  await page.getByRole("button", { name: /^This week/ }).click();
  await page.getByRole("button", { name: /^This week options/ }).click();
  await expect(page.getByRole("button", { name: "Rename" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Remove" })).toHaveCount(0);
});

test("a typed name that is not an ingredient asks How do you count it?, with packet sizes up front", async ({
  page,
}) => {
  const name = `tahini ${tag()}`;
  await page.goto("/shopping");
  await page.getByRole("textbox", { name: "Add an item" }).fill(name);
  await page
    .getByRole("button", { name: `+ New ingredient: “${name}”` })
    .click();
  const dialog = page.getByRole("dialog", { name: "How do you count it?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("radio")).toHaveText([
    /By weight/,
    /By volume/,
    /One by one/,
    /Don’t count it/,
  ]);
  await expect(
    dialog.getByRole("radio", { name: /By weight/ }),
  ).toHaveAttribute("aria-checked", "true");
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }

  await dialog.getByRole("button", { name: "+ Add a size" }).click();
  await dialog.getByRole("textbox", { name: "Name" }).fill("jar");
  await dialog.getByRole("textbox", { name: "Amount" }).fill("250");
  await dialog.getByRole("button", { name: "Add size" }).click();
  await expect(dialog.getByText("jar = 250 g")).toBeVisible();
  await dialog.getByRole("button", { name: "Add", exact: true }).click();

  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  const id = (await foodNamed(page, name)).id;
  const read = async () =>
    (await (await page.request.get(`/api/v1/foods/${id}`)).json()) as {
      counted_as: string;
      sizes: { name: string }[];
    };
  expect((await read()).counted_as).toBe("weight");
  // The sizes are a separate online step after the item is added.
  await expect
    .poll(async () => (await read()).sizes.map((s) => s.name))
    .toEqual(["jar"]);
});

test("adding something already on the list says so instead of adding it twice", async ({
  page,
}) => {
  const name = `Yoghurt ${tag()}`;
  await onList(page, name);
  await page.goto("/shopping");
  await page.getByRole("textbox", { name: "Add an item" }).fill(name);
  await page
    .getByRole("list", { name: "Matching ingredients" })
    .getByRole("button", { name })
    .click();
  await expect(page.getByText(`${name} is already on the list`)).toBeVisible();
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(1);
});

test("changing the amount of a line", async ({ page }) => {
  const name = `Flour ${tag()}`;
  await onList(page, name, 500);
  await page.goto("/shopping");
  await page.getByRole("button", { name: new RegExp(`^${name}: `) }).click();
  await page
    .getByRole("textbox", { name: new RegExp(`How much ${name}`) })
    .fill("2 kg");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^${name}: 2`) }),
  ).toBeVisible();
});

test("Ingredients has a New ingredient button that asks How do you count it?", async ({
  page,
}) => {
  const name = `Sumac ${tag()}`;
  await page.goto("/recipes/ingredients");
  await page.getByRole("button", { name: "+ New ingredient" }).click();
  const dialog = page.getByRole("dialog", { name: "How do you count it?" });
  await dialog.getByRole("textbox", { name: "Name" }).fill(name);
  await dialog.getByRole("radio", { name: /One by one/ }).click();
  await dialog.getByRole("button", { name: "Add", exact: true }).click();
  const made = await foodNamed(page, name);
  expect(made.counted_as).toBe("count");
});

test("phone: + Staple adds a brand-new staple and puts nothing in the pantry", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone is where this was missing");
  const name = `Salt ${tag()}`;
  await page.goto("/pantry");
  await page.getByRole("button", { name: "+ Staple" }).click();
  await page
    .getByRole("searchbox", { name: "Make an ingredient a staple" })
    .fill(name);
  await page
    .getByRole("button", { name: `+ New ingredient: “${name}”` })
    .click();
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  expect((await foodNamed(page, name)).staple).toBe(true);
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  const stocked = pantry.places
    .flatMap((p: { groups: { food: { name: string } }[] }) => p.groups)
    .map((g: { food: { name: string } }) => g.food.name);
  expect(stocked).not.toContain(name);
});

test("the list picker open and the amount editor open pass the accessibility checks in both themes", async ({
  page,
}) => {
  const name = `Lentils ${tag()}`;
  await onList(page, name);
  await page.goto("/shopping");
  await page.getByRole("button", { name: /^This week/ }).click();
  await expect(page.getByRole("group", { name: "Lists" })).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
  // Escape closes it and puts focus back on the picker button.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Lists" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^This week/ })).toBeFocused();

  await page.getByRole("button", { name: new RegExp(`^${name}: `) }).click();
  await expect(
    page.getByRole("textbox", { name: new RegExp(`How much ${name}`) }),
  ).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
});

test("removing a line from the list keeps keyboard focus in the list", async ({
  page,
}) => {
  const first = `Aaa ${tag()}`;
  const second = `Bbb ${tag()}`;
  await onList(page, first);
  await onList(page, second);
  await page.goto("/shopping");
  await page.getByRole("button", { name: new RegExp(`^${first}: `) }).click();
  await page.getByRole("button", { name: "Remove from list" }).click();
  await expect(
    page.getByRole("button", { name: first, exact: true }),
  ).toHaveCount(0);
  const active = await page.evaluate(() => document.activeElement?.tagName);
  expect(active).not.toBe("BODY");
});

// --- Ticking, put away, Different pack?, "Did you buy 2?", notes (PR 3's actions) ------------------

async function place(page: Page, name: string): Promise<number> {
  const places = (await (await page.request.get("/api/v1/places")).json()) as {
    id: number;
    name: string;
  }[];
  return places.find((p) => p.name === name)!.id;
}

/** An ingredient by weight, usual place Fridge, with a 200 g pack, 2 packs on the list. */
async function packs(page: Page, name: string) {
  const { food } = await call(page, "POST", "/foods", {
    name,
    counted_as: "weight",
    place_id: await place(page, "Fridge"),
  });
  await call(page, "POST", `/foods/${food.id}/sizes`, {
    name: "pack",
    amount: 200,
  });
  const item = crypto.randomUUID();
  await act(page, {
    kind: "add",
    list_id: await mainList(page),
    item_id: item,
    food_id: food.id,
    amount: 400,
  });
  return { foodId: food.id as number, item };
}

let myLogin = 0;
/** Send an action as another device of the same login (the way a second phone would). */
async function act(
  page: Page,
  fields: Record<string, unknown>,
  device = "11111111-2222-4333-8444-555555555555",
) {
  if (!myLogin)
    myLogin = (await (await page.request.get("/api/v1/me")).json()).id;
  const response = await page.request.post("/api/v1/shopping/actions", {
    data: {
      protocol: 1,
      device_id: device,
      login_id: myLogin,
      since: 0,
      sent_at: new Date().toISOString(),
      actions: [
        {
          id: crypto.randomUUID(),
          made_at: new Date().toISOString(),
          seen: 0,
          ...fields,
        },
      ],
    },
  });
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()).results[0];
}

/** Answer every open "Did you buy 2?" left by other tests, so a test sees only its own card. */
async function settleCards(page: Page) {
  const copy = await (
    await page.request.get("/api/v1/shopping/changes?since=0")
  ).json();
  for (const q of copy.questions.filter((x: { open: boolean }) => x.open)) {
    await act(page, {
      kind: "answer_double_tick",
      question_id: q.id,
      answer: "two",
    });
  }
}

/** Where a food is in the pantry: place name → grams. */
async function stockOf(
  page: Page,
  foodId: number,
): Promise<Record<string, number>> {
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  const out: Record<string, number> = {};
  for (const p of pantry.places)
    for (const g of p.groups)
      if (g.food.id === foodId) out[p.name] = g.stock.amount;
  return out;
}

test("ticking puts the item into the pantry, and Undo takes it out", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone toast");
  const name = `Tick ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  const toast = page
    .getByRole("status")
    .filter({ hasText: `${name} → Fridge` });
  await expect(toast).toBeVisible();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({});
  await expect(
    page.getByRole("checkbox", { name: `Tick ${name}` }),
  ).not.toBeChecked();
});

test("the toast's Change moves it to another place", async ({ page }) => {
  test.skip(!isPhone(page), "the phone toast");
  const name = `Change ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await page
    .getByRole("status")
    .getByRole("button", { name: "Change" })
    .click();
  await page.getByRole("radio", { name: "Freezer" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Freezer: 400 });
});

test("desktop: the Put away panel moves the last ticked item, and Undo last tick", async ({
  page,
}) => {
  test.skip(isPhone(page), "the desktop panel");
  const name = `Panel ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect(page.getByRole("heading", { name: "Put away" })).toBeVisible();
  await page.getByRole("combobox", { name: "Where" }).selectOption("Freezer");
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Freezer: 400 });
  await page.getByRole("button", { name: "Undo last tick" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({});
});

test("unticking takes it back out of the pantry", async ({ page }) => {
  const name = `Untick ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  await page.getByRole("button", { name: /^In the trolley/ }).click();
  await page.getByRole("checkbox", { name: `Untick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({});
});

test("Different pack? changes what the pantry got, and Undo puts it back", async ({
  page,
}) => {
  const name = `Pack ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  await page.getByRole("button", { name: /^In the trolley/ }).click();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await row.getByRole("button", { name: "Different pack?" }).click();
  await row.getByRole("radio", { name: "Other…" }).click();
  await row.getByRole("textbox", { name: "Size of one" }).fill("1");
  await row.getByRole("combobox", { name: "Unit" }).selectOption("kg");
  await expect(row.getByText("Pantry gets 1 pack · 1 kg.")).toBeVisible();
  await row.getByRole("button", { name: "Done" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 1000 });
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
});

test("Clear ticked takes the ticked items off the list, and Undo brings them back", async ({
  page,
}) => {
  const name = `Clear ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  await page.getByRole("button", { name: /^In the trolley/ }).click();
  await page.getByRole("button", { name: "Clear ticked" }).click();
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
});

test("two phones tick the same item: the card asks Did you buy 2?, and Yes keeps both", async ({
  page,
}) => {
  const name = `Twice ${tag()}`;
  await settleCards(page);
  const { foodId, item } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  // The other phone ticks it too (it hadn't seen the first tick).
  await act(
    page,
    { kind: "tick", item_id: item },
    "99999999-8888-4777-8666-555555555555",
  );
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 800 });
  await page.reload();
  const card = page.getByRole("region", { name: "Did you buy 2?" }).first();
  await expect(card).toBeVisible();
  await expect(card).toContainText("ticked on two phones");
  await card.getByRole("button", { name: "Yes, 2" }).click();
  await expect(card).toHaveCount(0);
  expect(await stockOf(page, foodId)).toEqual({ Fridge: 800 });
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click(); // brings the card back
  await expect(card).toBeVisible();
});

test("two phones tick the same item: Just 1 takes the extra back out", async ({
  page,
}) => {
  const name = `Once ${tag()}`;
  await settleCards(page);
  const { foodId, item } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await act(
    page,
    { kind: "tick", item_id: item },
    "99999999-8888-4777-8666-555555555555",
  );
  await page.reload();
  await page
    .getByRole("region", { name: "Did you buy 2?" })
    .getByRole("button", { name: "Just 1" })
    .click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
});

test("a quiet note can be dismissed", async ({ page }) => {
  const name = `Note ${tag()}`;
  const { foodId, item } = await packs(page, name);
  // The other phone adds the same ingredient without having seen the line: note N2.
  await act(
    page,
    {
      kind: "add",
      list_id: await mainList(page),
      item_id: crypto.randomUUID(),
      food_id: foodId,
      amount: 200,
    },
    "99999999-8888-4777-8666-555555555555",
  );
  await page.goto("/shopping");
  const note = page.getByText(new RegExp(`added ${name} too`));
  await expect(note).toBeVisible();
  await page
    .getByRole("button", { name: /^Dismiss: .*added .* too/ })
    .first()
    .click();
  await expect(note).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(new RegExp(`added ${name} too`))).toHaveCount(0);
  void item;
});

// --- Review round 2 -----------------------------------------------------------------------------

test("opening Shopping asks for the list once and then goes quiet", async ({
  page,
}) => {
  let asked = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/shopping/changes")) asked++;
  });
  await page.goto("/shopping");
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  expect(asked).toBe(1);
});

test("ticked states pass the accessibility checks in both themes", async ({
  page,
}) => {
  await settleCards(page);
  const name = `Looks ${tag()}`;
  const { foodId, item } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  // The put-away toast (phone) or the Put away panel (desktop) is showing.
  if (isPhone(page)) {
    await expect(
      page.getByRole("status").filter({ hasText: `${name} → Fridge` }),
    ).toBeVisible();
  } else {
    await expect(page.getByRole("heading", { name: "Put away" })).toBeVisible();
  }
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
  // The trolley open, with its ticked row.
  await page.getByRole("button", { name: /^In the trolley/ }).click();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(
    row.getByRole("button", { name: "Different pack?" }),
  ).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
  // The Different pack? sheet.
  await row.getByRole("button", { name: "Different pack?" }).click();
  await expect(row.getByText("What did you buy?")).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
  // The "Did you buy 2?" card.
  await act(
    page,
    { kind: "tick", item_id: item },
    "99999999-8888-4777-8666-555555555555",
  );
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Did you buy 2?" }).first(),
  ).toBeVisible();
  for (const theme of THEMES) {
    await inTheme(page, theme);
    await checkPage(page);
  }
});

test("phone: a ticked row keeps the whole item name at 320 and 390 px", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone layout");
  const name = `A rather long ingredient name ${tag()}`;
  await packs(page, name);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto("/shopping");
    if (width === 320)
      await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
    await page.getByRole("button", { name: /^In the trolley/ }).click();
    const label = page.getByRole("button", { name, exact: true });
    await expect(label).toBeVisible();
    const clipped = await label.evaluate(
      (el) => el.scrollWidth > el.clientWidth + 1,
    );
    expect(clipped).toBe(false);
    const box = await label.boundingBox();
    const pill = await page
      .getByRole("button", { name: "Different pack?" })
      .first()
      .boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(pill!.y + 1); // the buttons sit under the name
  }
});

test("Undo of Just 1 brings the card and the second purchase back", async ({
  page,
}) => {
  await settleCards(page);
  const name = `JustOne ${tag()}`;
  const { foodId, item } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await act(
    page,
    { kind: "tick", item_id: item },
    "99999999-8888-4777-8666-555555555555",
  );
  await page.reload();
  await page
    .getByRole("region", { name: "Did you buy 2?" })
    .first()
    .getByRole("button", { name: "Just 1" })
    .click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 800 });
  await expect(
    page.getByRole("region", { name: "Did you buy 2?" }).first(),
  ).toBeVisible();
});

test("phone: Undo of a put-away (the toast after Change) moves it back", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone toast");
  const name = `Moved ${tag()}`;
  const { foodId } = await packs(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  await page
    .getByRole("status")
    .getByRole("button", { name: "Change" })
    .click();
  await page.getByRole("radio", { name: "Freezer" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Freezer: 400 });
  await page
    .getByRole("status")
    .filter({ hasText: `${name} → Freezer` })
    .getByRole("button", { name: "Undo" })
    .click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
});
