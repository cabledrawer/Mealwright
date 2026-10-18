import { test, expect, type Page } from "@playwright/test";
import {
  checkPage,
  inTheme,
  isPhone,
  setAccountTheme,
  THEMES,
} from "./a11y.ts";

// The Shopping screen working online (0.3, PR 4), against the real server, on phone and
// desktop. Ticking, put away, "Different pack?" and "Did you buy 2?" need the server's
// action endpoint (PR 3); their browser tests join this file when that is merged.

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
  await expect.poll(async () => (await read()).sizes.map((s) => s.name)).toEqual(["jar"]);
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
