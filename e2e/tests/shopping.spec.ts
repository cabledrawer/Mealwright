import { test, expect, type Page } from "./clock.ts";
import { checkPage, isPhone, setAccountTheme } from "./a11y.ts";

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
  await checkPage(page); // both themes
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
  await page.getByRole("button", { name: "Remove", exact: true }).click();
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
  await expect(
    page.getByRole("button", { name: "Remove", exact: true }),
  ).toHaveCount(0);
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
  await checkPage(page); // both themes

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

/** An ingredient measured in millilitres, on the main list with this much. */
async function liquidOnList(page: Page, name: string, amountMl: number) {
  const { food } = await call(page, "POST", "/foods", {
    name,
    counted_as: "volume",
  });
  await call(page, "POST", `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
    amount: { amount: amountMl, unit: "ml" },
  });
}

test("F63: \"2 l milk\" in the add box adds 2 litres of Milk, and joins the 1 L line that is there", async ({
  page,
}) => {
  const name = `Milk ${tag()}`;
  await liquidOnList(page, name, 1000);
  await page.goto("/shopping");
  await page.getByRole("textbox", { name: "Add an item" }).fill(`2 l ${name}`);
  await page
    .getByRole("list", { name: "Matching ingredients" })
    .getByRole("button", { name })
    .click();
  // One line, 3 L: joined, not "already on the list" and not a second line.
  await expect(
    page.getByRole("button", { name: new RegExp(`^Change amount: ${name}, 3`) }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(1);
  await expect(page.getByText(`${name} is already on the list`)).toHaveCount(0);
});

test("F61: the amount box takes \"250 g\" typed with its unit, and the empty box shows a small \"500 g\"", async ({
  page,
}) => {
  const name = `Raisins ${tag()}`;
  const { food } = await call(page, "POST", "/foods", {
    name,
    counted_as: "weight",
  });
  await call(page, "POST", `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
  });
  await page.goto("/shopping");
  await page.getByRole("button", { name, exact: true }).click();
  const box = page.getByRole("form", { name: `Change ${name}` });
  const amount = box.getByRole("textbox", { name: "Amount" });
  await expect(amount).toHaveAttribute("placeholder", "500 g");
  await amount.fill("250 g");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^Change amount: ${name}, 250`) }),
  ).toBeVisible();
  // And in kilos, typed.
  await page.getByRole("button", { name, exact: true }).click();
  await amount.fill("2 kg");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^Change amount: ${name}, 2 kg`) }),
  ).toBeVisible();
});

test("changing the amount of a line", async ({ page }) => {
  const name = `Flour ${tag()}`;
  await onList(page, name, 500);
  await page.goto("/shopping");
  await page
    .getByRole("button", { name: new RegExp(`^Change amount: ${name}, `) })
    .click();
  const box = page.getByRole("form", { name: `Change ${name}` });
  await expect(box.getByRole("textbox", { name: "Amount" })).toHaveValue("500");
  // A new unit keeps the amount: 500 g is 0.5 kg.
  await box.getByRole("combobox", { name: "Unit" }).selectOption("kg");
  await expect(box.getByRole("textbox", { name: "Amount" })).toHaveValue("0.5");
  await box.getByRole("textbox", { name: "Amount" }).fill("2");
  await expect(box.getByRole("textbox", { name: "Amount" })).toHaveValue("2");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Change amount: ${name}, 2`),
    }),
  ).toBeVisible();
});

test("tapping the name opens the amount box without ticking, and − / + step the real amount (checked for 0.5.1)", async ({
  page,
}) => {
  const name = `Oats ${tag()}`;
  const foodId = await onList(page, name, 500);
  await page.goto("/shopping");
  await page.getByRole("button", { name, exact: true }).click();
  const box = page.getByRole("form", { name: `Change ${name}` });
  const amount = box.getByRole("textbox", { name: "Amount" });
  await expect(amount).toHaveValue("500");
  await box.getByRole("button", { name: "More" }).click();
  await expect(amount).toHaveValue("550");
  await box.getByRole("button", { name: "Less" }).click();
  await box.getByRole("button", { name: "Less" }).click();
  await expect(amount).toHaveValue("450");
  await box.getByRole("button", { name: "Done" }).click();
  await expect(
    page.getByRole("button", { name: new RegExp(`^Change amount: ${name}, 450`) }),
  ).toBeVisible();
  // Still not ticked, and nothing went into the pantry.
  await expect(page.getByRole("checkbox", { name: `Tick ${name}` })).not.toBeChecked();
  expect(await stockOf(page, foodId)).toEqual({});
});

test("the amount box’s Edit ingredient saves the box and opens the ingredient editor; offline it isn’t there", async ({
  page,
  context,
}) => {
  const name = `Semolina ${tag()}`;
  await onList(page, name, 500);
  await page.goto("/shopping");
  await page.getByRole("button", { name, exact: true }).click();
  const box = page.getByRole("form", { name: `Change ${name}` });
  await box.getByRole("textbox", { name: "Amount" }).fill("750");
  await box.getByRole("button", { name: "Edit ingredient" }).click();
  const editor = page.getByRole("dialog", { name: `Edit ${name}` });
  await expect(editor).toBeVisible();
  await expect(box).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(editor).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Change amount: ${name}, 750`),
    }),
  ).toBeVisible();

  await context.setOffline(true);
  await expect(
    page.getByTestId(isPhone(page) ? "connection-phone" : "connection-desktop"),
  ).toContainText("Offline");
  await page.getByRole("button", { name, exact: true }).click();
  await expect(
    box.getByRole("button", { name: "Remove from list" }),
  ).toBeVisible();
  await expect(
    box.getByRole("button", { name: "Edit ingredient" }),
  ).toHaveCount(0);
  await context.setOffline(false);
});

test("Ingredients has a New ingredient button that asks How do you count it?", async ({
  page,
}) => {
  const name = `Sumac ${tag()}`;
  await page.goto("/recipes/ingredients");
  // A phone shows a round + (named "New ingredient"), a computer the words.
  await page
    .getByRole(
      "button",
      isPhone(page)
        ? { name: "New ingredient", exact: true }
        : { name: "+ New ingredient" },
    )
    .click();
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
  // A staple chip adds it to the shopping list when tapped (0.3), so that is its name.
  await expect(
    page.getByRole("button", {
      name: `Add ${name} to the shopping list`,
      exact: true,
    }),
  ).toBeVisible();
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
  // The open menu lies over the top rows of the list; axe would count a row it half covers as
  // a too-small target. The rows are checked in the other tests.
  await checkPage(page, { exclude: [".aisles"] }); // both themes
  // Escape closes it and puts focus back on the picker button.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Lists" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^This week/ })).toBeFocused();

  await page.getByRole("button", { name, exact: true }).click();
  await expect(
    page.getByRole("form", { name: `Change ${name}` }),
  ).toBeVisible();
  await checkPage(page); // both themes
});

test("removing a line from the list keeps keyboard focus in the list", async ({
  page,
}) => {
  const first = `Aaa ${tag()}`;
  const second = `Bbb ${tag()}`;
  await onList(page, first);
  await onList(page, second);
  await page.goto("/shopping");
  await page.getByRole("button", { name: first, exact: true }).click();
  await page.getByRole("button", { name: "Remove from list" }).click();
  // Removing asks first (cabledrawer 20 Oct); Keep it leaves the line, Remove takes it off.
  const ask = page.getByRole("alertdialog", {
    name: `Remove ${first} from the shopping list?`,
  });
  await expect(ask).toBeVisible();
  await expect(ask.getByRole("button", { name: "Keep it" })).toBeFocused();
  await ask.getByRole("button", { name: "Keep it" }).click();
  // Keep it leaves the amount box open on the same line.
  await expect(
    page.getByRole("form", { name: `Change ${first}` }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Remove from list" }).click();
  await ask.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: `Removed ${first}` })
      .getByRole("button", { name: "Undo" }),
  ).toBeVisible();
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

test("the toast’s Change moves it to another place", async ({ page }) => {
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
  await row.getByRole("button", { name: `Change where ${name} went` }).click();
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
  // A ticked row's name is plain text (only unticked names are buttons that open the amount).
  const ticked = page.getByRole("checkbox", { name: `Untick ${name}` });
  await expect(ticked).toHaveCount(0);
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect(ticked).toBeVisible();
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
  // The dismiss goes into the phone's queue first, then to the server: wait for it to go.
  const sent = page.waitForResponse(
    (r) =>
      r.url().includes("/api/v1/shopping/actions") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", {
      name: `Dismiss: Your other phone added ${name} too`,
    })
    .click();
  await expect(note).toHaveCount(0);
  await sent;
  await page.reload();
  // The list is showing (not still loading) and the note stays gone.
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
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
  await checkPage(page); // both themes
  // The trolley open, with its ticked row.
  await page.getByRole("button", { name: /^In the trolley/ }).click();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(row.getByText(/^In the Fridge · /)).toBeVisible();
  await row.getByRole("button", { name: `Change where ${name} went` }).click();
  await expect(
    row.getByRole("button", { name: "Different pack?" }),
  ).toBeVisible();
  await checkPage(page); // both themes
  // The Different pack? sheet.
  await row.getByRole("button", { name: "Different pack?" }).click();
  await expect(row.getByText("What did you buy?")).toBeVisible();
  await checkPage(page); // both themes
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
  await checkPage(page); // both themes
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
    const label = page
      .getByRole("listitem")
      .filter({ hasText: name })
      .getByText(name, { exact: true });
    await expect(label).toBeVisible();
    const clipped = await label.evaluate(
      (el) => el.scrollWidth > el.clientWidth + 1,
    );
    expect(clipped).toBe(false);
    const box = await label.boundingBox();
    const line = await page
      .getByRole("group", { name: `Where ${name} went` })
      .boundingBox();
    expect(box!.y + box!.height).toBeLessThanOrEqual(line!.y + 1); // the status line sits under the name
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

test("phone: on a long list, In the trolley stays tappable while the put-away toast is up", async ({
  page,
}) => {
  test.skip(
    !isPhone(page),
    "the toast covers the end of the page on the phone",
  );
  const prefix = `Long ${tag()}`;
  const names = Array.from(
    { length: 25 },
    (_, n) => `${prefix} ${String(n).padStart(2, "0")}`,
  );
  try {
    for (const name of names) await onList(page, name);
    await page.goto("/shopping");
    await page.getByRole("checkbox", { name: `Tick ${names[0]}` }).click();
    const toast = page.getByRole("status").filter({ hasText: names[0] });
    await expect(toast).toBeVisible();
    // The ticked item is in the trolley, at the foot of a long list, with the toast up.
    const fold = page.getByRole("button", { name: /^In the trolley/ });
    await fold.click({ timeout: 5_000 });
    await expect(fold).toHaveAttribute("aria-expanded", "true");
    await expect(toast).toBeVisible();
    // Take the tick back, so removing the items below leaves no "had removed this" note on
    // the list for the tests after this one.
    await toast.getByRole("button", { name: "Undo" }).click();
    await expect(
      page.getByRole("checkbox", { name: `Tick ${names[0]}` }),
    ).toBeVisible();
  } finally {
    // Leave the main list as other tests expect it.
    const view = await (
      await page.request.get(`/api/v1/shopping/lists/${await mainList(page)}`)
    ).json();
    type Line = { id: string; food: { name: string } };
    const lines: Line[] = view.shops.flatMap(
      (shop: { aisles: { items: Line[] }[]; in_trolley: Line[] }) => [
        ...shop.aisles.flatMap((a) => a.items),
        ...shop.in_trolley,
      ],
    );
    for (const line of lines.filter((l) => l.food.name.startsWith(prefix))) {
      await call(page, "DELETE", `/shopping/items/${line.id}`);
    }
  }
});

// --- Rows: the amount box, removing asks first, where a tick went (cabledrawer 20 Oct, hand test) -------

/** A line with no amount, or a staple, made through the API. */
async function plainLine(
  page: Page,
  name: string,
  options: { staple?: boolean } = {},
) {
  const { food } = await call(page, "POST", "/foods", {
    name,
    counted_as: "weight",
    staple: options.staple ?? false,
  });
  await call(page, "POST", `/shopping/lists/${await mainList(page)}/items`, {
    food_id: food.id,
  });
  return food.id as number;
}

test("a ticked row says where it went: with an amount, with none, and a staple", async ({
  page,
}) => {
  await settleCards(page);
  const withAmount = `Amt ${tag()}`;
  const bare = `Bare ${tag()}`;
  const staple = `Stap ${tag()}`;
  const { foodId } = await packs(page, withAmount);
  await plainLine(page, bare);
  await plainLine(page, staple, { staple: true });
  await page.goto("/shopping");
  for (const n of [withAmount, bare, staple]) {
    await page.getByRole("checkbox", { name: `Tick ${n}` }).click();
  }
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Fridge: 400 });
  // The line with no amount asked "How much?", which opened the trolley by itself (F62).
  await expect(page.getByText("How much?")).toBeVisible();
  const row = (n: string) => page.getByRole("listitem").filter({ hasText: n });
  await expect(row(withAmount).getByText(/^In the Fridge · /)).toBeVisible();
  await expect(
    row(bare).getByText("Not in the pantry yet. No amount."),
  ).toBeVisible();
  await expect(
    row(bare).getByRole("button", { name: `Add amount for ${bare}` }),
  ).toBeVisible();
  await expect(
    row(staple).getByText("Restocked · staples aren’t counted"),
  ).toBeVisible();
  // No row says "→ Fridge" or "→ Cupboard" any more.
  for (const n of [withAmount, bare, staple]) {
    await expect(row(n)).not.toContainText("→");
  }
  await checkPage(page); // both themes
  // The line's own Undo takes the tick back out of the pantry.
  await row(withAmount)
    .getByRole("button", { name: `Undo ticking ${withAmount}` })
    .click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({});
});

test("Add amount on a ticked row with no amount gives it a first amount, and Recent changes says so", async ({
  page,
}) => {
  await settleCards(page);
  const name = `First ${tag()}`;
  const foodId = await plainLine(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  const row = page.getByRole("listitem").filter({ hasText: name });
  // F62: ticking a line with no amount asks "How much?" by itself.
  await expect(row.getByText("How much?")).toBeVisible();
  await row.getByRole("radio", { name: "Other…" }).click();
  await row.getByRole("textbox", { name: "Size of one" }).fill("1");
  await row.getByRole("combobox", { name: "Unit" }).selectOption("kg");
  await row.getByRole("button", { name: "Done" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Cupboard: 1000 });
  const { changes } = await (
    await page.request.get(`/api/v1/changes?food_id=${foodId}&limit=20`)
  ).json();
  const summaries = changes.map((c: { summary: string }) => c.summary);
  expect(summaries.join("\n")).toContain("(first amount)");
  expect(summaries.join("\n")).not.toContain("instead of");
});

test("F62: leaving \"How much?\" for later keeps Add amount on the ticked row; picking 500 g files it", async ({
  page,
}) => {
  await settleCards(page);
  const name = `Later ${tag()}`;
  const foodId = await plainLine(page, name);
  await page.goto("/shopping");
  await page.getByRole("checkbox", { name: `Tick ${name}` }).click();
  const row = page.getByRole("listitem").filter({ hasText: name });
  await expect(row.getByText("How much?")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(row.getByText("How much?")).toHaveCount(0);
  expect(await stockOf(page, foodId)).toEqual({});
  await row.getByRole("button", { name: `Add amount for ${name}` }).click();
  await row.getByRole("radio", { name: "500 g" }).click();
  await row.getByRole("button", { name: "Done" }).click();
  await expect.poll(() => stockOf(page, foodId)).toEqual({ Cupboard: 500 });
});

test("removing asks first: Keep it keeps the line; Remove takes it off, with Undo", async ({
  page,
}) => {
  const name = `Ask ${tag()}`;
  await onList(page, name);
  await page.goto("/shopping");
  await page
    .getByRole("button", { name: new RegExp(`^Change amount: ${name}, `) })
    .click();
  await page.getByRole("button", { name: "Remove from list" }).click();
  const ask = page.getByRole("alertdialog", {
    name: `Remove ${name} from the shopping list?`,
  });
  await expect(ask).toBeVisible();
  await expect(ask.getByText("Nothing goes into the pantry.")).toBeVisible();
  await checkPage(page); // both themes
  await ask.getByRole("button", { name: "Keep it" }).click();
  // Keep it leaves the amount box open on the same line.
  await expect(
    page.getByRole("form", { name: `Change ${name}` }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Remove from list" }).click();
  await ask.getByRole("button", { name: "Remove", exact: true }).click();
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  const toast = page.getByRole("status").filter({ hasText: `Removed ${name}` });
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
});

test("desktop: a keyboard alone opens the amount box, saves it, and answers the question", async ({
  page,
}) => {
  test.skip(isPhone(page), "the computer layout");
  const name = `Keys ${tag()}`;
  await onList(page, name, 500);
  await page.goto("/shopping");
  // The name is a button: Enter opens the box, with the amount selected.
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
  const amount = page.getByRole("textbox", { name: "Amount" });
  await expect(amount).toBeFocused();
  await page.keyboard.type("750");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", {
      name: new RegExp(`^Change amount: ${name}, 750`),
    }),
  ).toBeVisible();
  // Focus is back on the name; Tab reaches the amount, then the ⋯ button.
  await expect(page.getByRole("button", { name, exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  const more = page.getByRole("button", { name: `More for ${name}` });
  await expect(more).toBeFocused();
  await expect(more).toBeVisible();
  // Enter opens its menu on Change amount; the arrow keys reach Remove from list….
  const removeItem = page.getByRole("menuitem", { name: "Remove from list…" });
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("menuitem", { name: "Change amount" }),
  ).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect(removeItem).toBeFocused();
  await page.keyboard.press("Enter");
  const ask = page.getByRole("alertdialog", {
    name: `Remove ${name} from the shopping list?`,
  });
  await expect(ask.getByRole("button", { name: "Keep it" })).toBeFocused();
  // Tab reaches Remove and Shift+Tab goes back; Escape keeps the line and gives the focus back.
  await page.keyboard.press("Tab");
  await expect(
    ask.getByRole("button", { name: "Remove", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(ask.getByRole("button", { name: "Keep it" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(ask).toHaveCount(0);
  await expect(more).toBeFocused();
  // Enter on Remove removes it.
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
});

/** A finger sliding sideways over a row, for real: touch events through the browser. */
async function swipeLeft(page: Page, name: string) {
  const row = page
    .getByRole("button", { name, exact: true })
    .locator("xpath=ancestor::div[contains(@class,'slide')]");
  // Mid-screen, clear of the fixed header and the bottom tabs.
  await row.evaluate((el) => el.scrollIntoView({ block: "center" }));
  const box = (await row.boundingBox())!;
  const y = box.y + box.height / 2;
  const from = box.x + box.width - 40;
  const cdp = await page.context().newCDPSession(page);
  const send = (type: "touchStart" | "touchMove" | "touchEnd", x?: number) =>
    cdp.send("Input.dispatchTouchEvent", {
      type,
      touchPoints: x === undefined ? [] : [{ x, y }],
    });
  await send("touchStart", from);
  for (let i = 1; i <= 8; i++) await send("touchMove", from - i * 14);
  await send("touchEnd");
  await cdp.detach();
}

test("F77 phone: swiping a row left shows a red Remove; a swipe alone removes nothing, and Remove goes at once with Undo", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone swipe");
  const name = `Swipe ${tag()}`;
  await onList(page, name);
  await page.goto("/shopping");
  await swipeLeft(page, name);
  const red = page.getByRole("button", {
    name: `Remove ${name} from the list`,
  });
  await expect(red).toBeVisible();
  // The swipe alone changed nothing, and nothing asks.
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(
    page.getByRole("checkbox", { name: `Tick ${name}` }),
  ).not.toBeChecked();
  await checkPage(page); // both themes
  await red.click();
  // Gone at once, no question first (cabledrawer 28 Oct), with Undo.
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  const toast = page.getByRole("status").filter({ hasText: `Removed ${name}` });
  await expect(toast).toBeVisible();
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
});

test("F73 phone: while a row is swiped, its name and its amount stay on screen beside the button", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone swipe");
  const name = `Bananas ${tag()}`;
  await onList(page, name, 472);
  await page.goto("/shopping");
  const viewport = page.viewportSize()!;
  const nameButton = page.getByRole("button", { name, exact: true });
  const pill = page.getByRole("button", {
    name: new RegExp(`^Change amount: ${name}, `),
  });
  /** The name and the amount are whole on screen and clear of the button that was shown. */
  const clearOf = async (button: ReturnType<Page["getByRole"]>, side: "left" | "right") => {
    await expect
      .poll(async () => {
        const [b, n, a] = await Promise.all([
          button.boundingBox(),
          nameButton.boundingBox(),
          pill.boundingBox(),
        ]);
        if (!b || !n || !a) return "missing";
        if (n.x < 0 || a.x < 0 || a.x + a.width > viewport.width) return "off screen";
        const edge = side === "left" ? b.x : b.x + b.width;
        const clear = (box: { x: number; width: number }) =>
          side === "left" ? box.x + box.width <= edge + 1 : box.x >= edge - 1;
        return clear(n) && clear(a) ? "clear" : "under the button";
      })
      .toBe("clear");
  };
  await swipeLeft(page, name);
  const red = page.getByRole("button", { name: `Remove ${name} from the list` });
  await expect(red).toBeVisible();
  await clearOf(red, "left");
  await red.evaluate(() => (document.activeElement as HTMLElement)?.blur());
  // Close it with a tap elsewhere, then the other way.
  await nameButton.click();
  await expect(red).toHaveCount(0);
  await swipeRight(page, name);
  const blue = page.getByRole("button", {
    name: `Move… ${name} to another shop or list`,
  });
  await expect(blue).toBeVisible();
  await clearOf(blue, "right");
  await checkPage(page); // both themes
});

test("phone: the row is a pill, the box is big enough to tap, and nothing sideways scrolls at 200% text", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone layout");
  const name = `Large type ${tag()} with a rather long ingredient name`;
  await onList(page, name);
  await page.goto("/shopping");
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  await checkPage(page);
  await page.getByRole("button", { name, exact: true }).click();
  await expect(
    page.getByRole("form", { name: `Change ${name}` }),
  ).toBeVisible();
  await checkPage(page);
});

/** A finger sliding right over a row, for real: touch events through the browser. */
async function swipeRight(page: Page, name: string) {
  const row = page
    .getByRole("button", { name, exact: true })
    .locator("xpath=ancestor::div[contains(@class,'slide')]");
  await row.evaluate((el) => el.scrollIntoView({ block: "center" }));
  const box = (await row.boundingBox())!;
  const y = box.y + box.height / 2;
  const from = box.x + 40;
  const cdp = await page.context().newCDPSession(page);
  const send = (type: "touchStart" | "touchMove" | "touchEnd", x?: number) =>
    cdp.send("Input.dispatchTouchEvent", {
      type,
      touchPoints: x === undefined ? [] : [{ x, y }],
    });
  await send("touchStart", from);
  for (let i = 1; i <= 8; i++) await send("touchMove", from + i * 14);
  await send("touchEnd");
  await cdp.detach();
}

async function aShop(page: Page, name: string) {
  const made = await call(page, "POST", "/shops", { name });
  return made.id as number;
}

test("phone: swiping a row right shows a blue Move…, which moves it to another shop without ticking it", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone swipe");
  const name = `Moving ${tag()}`;
  const shop = `Lidl ${tag()}`;
  await onList(page, name);
  await aShop(page, shop);
  await page.goto("/shopping");
  await swipeRight(page, name);
  const blue = page.getByRole("button", { name: new RegExp(`^Move… ${name}`) });
  await expect(blue).toBeVisible();
  await checkPage(page); // both themes
  await blue.click();
  const sheet = page.getByRole("dialog", { name: `Move ${name} to…` });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("radio", { name: /Any shop/ })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await checkPage(page);
  await sheet.getByRole("radio", { name: shop }).click();
  // It is under the new shop's heading, not ticked, and the toast offers Undo.
  await expect(
    page.getByRole("heading", { name: shop, level: 2 }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: `Tick ${name}` }),
  ).not.toBeChecked();
  const toast = page
    .getByRole("status")
    .filter({ hasText: `Moved ${name} to ${shop}` });
  await expect(toast).toBeVisible();
  await toast.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("heading", { name: shop, level: 2 })).toHaveCount(
    0,
  );
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
});

test("desktop: Move to… sits in the row's ⋯ menu, moves to another list, and Ctrl+Z takes it back", async ({
  page,
}) => {
  test.skip(isPhone(page), "the computer layout");
  const name = `Moving ${tag()}`;
  const other = `Party ${tag()}`;
  await onList(page, name);
  await call(page, "POST", "/shopping/lists", { name: other });
  await page.goto("/shopping");
  await page.getByRole("button", { name: `More for ${name}` }).click();
  await page.getByRole("menuitem", { name: "Move to…" }).click();
  const menu = page.getByRole("dialog", { name: `Move ${name} to…` });
  await expect(menu).toBeVisible();
  await checkPage(page); // both themes
  await menu.getByRole("button", { name: new RegExp(other) }).click();
  await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("status").filter({ hasText: `Moved ${name} to ${other}` }),
  ).toBeVisible();
  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
});

test("the Move picker at 200% text: nothing scrolls sideways and it passes the accessibility checks in both themes", async ({
  page,
}) => {
  const name = `Large move ${tag()} with a rather long ingredient name`;
  await onList(page, name);
  await call(page, "POST", "/shopping/lists", { name: `Party ${tag()}` });
  await aShop(page, `Lidl ${tag()}`);
  await page.goto("/shopping");
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
  if (isPhone(page)) {
    await swipeRight(page, name);
    await page
      .getByRole("button", { name: new RegExp(`^Move… ${name}`) })
      .click();
  } else {
    await page.getByRole("button", { name: `More for ${name}` }).click();
    await page.getByRole("menuitem", { name: "Move to…" }).click();
  }
  const picker = page.getByRole("dialog", { name: `Move ${name} to…` });
  await expect(picker).toBeVisible();
  await expect(picker.getByRole("button", { name: "Cancel" })).toBeVisible();
  await checkPage(page); // both themes
  // Every choice stays inside the window.
  const inside = await picker.evaluate((el) => {
    const box = el.getBoundingClientRect();
    return (
      box.left >= 0 &&
      box.right <= innerWidth &&
      box.top >= 0 &&
      box.bottom <= innerHeight
    );
  });
  expect(inside).toBe(true);
});
