import { test, expect, type Page } from "./clock.ts";
import { checkPage, isPhone, setAccountTheme } from "./a11y.ts";

// The Pantry (0.2), against the real server, on phone and desktop. Each test makes its
// own foods with unique names, so tests don't trip over each other.

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

/** A food sold in packets, with stock in the fridge (or another place). */
async function stocked(
  page: Page,
  name: string,
  useByDays: number | null = 1,
  placeName = "Fridge",
) {
  const unique = `${name} ${test.info().project.name.replace(/\W/g, "")} ${Date.now()}`;
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
  const { today } = await (await page.request.get("/api/v1/household")).json();
  const useBy = new Date(`${today}T12:00:00Z`);
  useBy.setUTCDate(useBy.getUTCDate() + (useByDays ?? 0));
  const added = await api(page, "POST", "/stock", {
    food_id: food.id,
    amount: { amount: 1, unit: "pack" },
    place_id: where,
    ...(useByDays === null ? {} : { use_by: useBy.toISOString().slice(0, 10) }),
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

test.beforeEach(async ({ page }) => {
  await setAccountTheme(page, "auto");
});

test("the Pantry shows what is where, and passes the accessibility checks", async ({
  page,
}) => {
  const food = await stocked(page, "Paneer");
  // A second place with something in it, so the phone has jump chips.
  await stocked(page, "Lentils", null, "Cupboard");
  await page.goto("/pantry");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Pantry");
  if (isPhone(page)) {
    // cabledrawer 24 Oct, question 37: no place tabs on a phone; a card per place and jump chips.
    await expect(
      page.getByRole("navigation", { name: "Jump to a place" }),
    ).toBeVisible();
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await expect(page.getByRole("tab")).toHaveCount(0);
  } else {
    for (const place of ["Fridge", "Freezer", "Cupboard", "Spice rack"]) {
      await expect(
        page.getByRole("heading", { name: place, level: 2 }),
      ).toBeVisible();
    }
  }
  await checkPage(page);
  // With a full household the new row can be behind "+ N more", so find it by searching.
  await findRow(page, food.name);
  await expect(
    page.getByRole("button", { name: new RegExp(`^${food.name}`) }).first(),
  ).toBeVisible();
});

test("phone: no place tabs; every place has a card or a chip, and both lead to its ingredients", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone Pantry");
  await stocked(page, "Frozen peas", null, "Freezer");
  await stocked(page, "Lentils", null, "Cupboard");
  await page.goto("/pantry");
  await expect(
    page.getByRole("navigation", { name: "Jump to a place" }),
  ).toBeVisible();
  await expect(page.getByRole("tablist")).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveCount(0);
  const places = (await (await page.request.get("/api/v1/places")).json()) as {
    name: string;
  }[];
  const chips = page
    .getByRole("navigation", { name: "Jump to a place" })
    .getByRole("button");
  for (const { name } of places) {
    // A card with its heading, or (when empty) one folded line saying so.
    const card = page.locator(".place-card h2, .folded-name").filter({
      hasText: new RegExp(`^${name}$`),
    });
    await expect(card, `${name} is on screen`).toHaveCount(1);
    if (
      await page
        .locator(".place-card h2")
        .filter({ hasText: new RegExp(`^${name}$`) })
        .count()
    ) {
      // A place with ingredients also has its chip, which goes to the card.
      const chip = chips.filter({ hasText: new RegExp(`^${name} · \\d+$`) });
      await expect(chip, `${name} has a chip`).toHaveCount(1);
      await chip.click();
      await expect(page.getByRole("heading", { name, level: 2 })).toBeFocused();
    }
  }
});

test("each place’s count stays on one line, apart from its name, at 100% and 200% text", async ({
  page,
}) => {
  await stocked(page, "Paneer");
  await page.goto("/pantry");
  const heads = page.locator(".place-head:not(.visually-hidden)");
  await expect(heads.first()).toBeVisible();
  for (const size of ["100%", "200%"]) {
    await page.evaluate(
      (s) => (document.documentElement.style.fontSize = s),
      size,
    );
    const problems = await heads.evaluateAll((all) =>
      all.flatMap((head) => {
        const name = head.querySelector("h2")!;
        const count = head.querySelector(".count")!;
        const n = name.getBoundingClientRect();
        const c = count.getBoundingClientRect();
        const lines = count.getClientRects().length;
        const style = getComputedStyle(count);
        const lineHeight =
          parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.3;
        const oneLine = lines === 1 && c.height < lineHeight * 1.5;
        // Beside the name with a gap, or on a line of its own under it.
        const apart = c.left >= n.right + 4 || c.top >= n.bottom - 1;
        const inside = c.right <= head.getBoundingClientRect().right + 0.5;
        return oneLine && apart && inside
          ? []
          : [`${name.textContent}: “${count.textContent}”`];
      }),
    );
    expect(problems, `at ${size} text`).toEqual([]);
  }
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("phone: the Pantry cards and chips pass the accessibility checks at 200% text, both themes", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone Pantry");
  await stocked(page, "Paneer");
  await stocked(page, "Lentils", null, "Cupboard");
  await page.goto("/pantry");
  await expect(
    page.getByRole("navigation", { name: "Jump to a place" }),
  ).toBeVisible();
  await page.evaluate(() => (document.documentElement.style.fontSize = "200%"));
  // Both themes, and the 44 px targets and no sideways scroll, with the text doubled.
  await checkPage(page);
});

test("Used from Use soon takes it out, and Undo puts it back", async ({
  page,
}) => {
  const food = await stocked(page, "Spinach", 0);
  await page.goto("/pantry");
  await expect(
    page.getByRole("heading", { name: /^Use soon · \d+$/, level: 2 }),
  ).toBeVisible();
  // The phone shows 3 rows and the computer 4 cards until "Show all N".
  const all = page.getByRole("button", { name: /^Show all \d+$/ });
  if (await all.count()) await all.first().click();
  const row = page
    .getByRole("listitem")
    .filter({ hasText: food.name })
    .filter({ has: page.getByRole("button", { name: "Used…" }) });
  await row.first().getByRole("button", { name: "Used…" }).click();
  await page.getByRole("radio", { name: "All" }).click();
  await page.getByRole("button", { name: "Used all of it" }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test("Add to pantry adds what was chosen, where it lives", async ({ page }) => {
  const food = await stocked(page, "Yoghurt", null);
  await page.goto("/pantry");
  await page
    .getByRole("button", { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole("dialog", { name: "Add to pantry" });
  await sheet
    .getByRole("searchbox", { name: "Find an ingredient" })
    .fill(food.name);
  await sheet
    .getByRole("button", { name: new RegExp(`^${food.name}`) })
    .click();
  await sheet.getByRole("radio", { name: "2 packs" }).click();
  await sheet.getByRole("radio", { name: "+1 week" }).click();
  await expect(sheet.getByLabel(/^Where/)).toHaveValue(/\d+/);
  await sheet.getByRole("button", { name: "Add to pantry" }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(3);
  await expect(
    page.getByRole("status").getByText(/Added 2\s+packs/),
  ).toBeVisible();
});

test("F101: + Place in Add to pantry makes the place and puts the stock there", async ({
  page,
}) => {
  const food = await stocked(page, "Barley", null);
  const where = `Shed ${Date.now() % 1_000_000}`;
  await page.goto("/pantry");
  await page
    .getByRole("button", { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole("dialog", { name: "Add to pantry" });
  await sheet
    .getByRole("searchbox", { name: "Find an ingredient" })
    .fill(food.name);
  await sheet
    .getByRole("button", { name: new RegExp(`^${food.name}`) })
    .click();
  await sheet.getByLabel(/^Where/).selectOption({ label: "+ Place" });
  const box = sheet.getByRole("group", { name: "New place" });
  await box.getByRole("textbox", { name: "Place’s name" }).fill(where);
  // Cupboard is the first choice.
  await expect(box.getByRole("radio", { name: "Cupboard" })).toBeChecked();
  await box.getByRole("radio", { name: "Freezer" }).click();
  await box.getByRole("button", { name: "Add place" }).click();
  await expect(box).toHaveCount(0);
  await expect(sheet.getByLabel(/^Where/).locator("option:checked")).toHaveText(
    where,
  );
  await sheet.getByRole("button", { name: "Add to pantry" }).click();
  await expect(
    page.getByRole("status").getByText(new RegExp(`→ ${where}`)),
  ).toBeVisible();
  const places = (await (await page.request.get("/api/v1/places")).json()) as {
    name: string;
    kind: string;
  }[];
  expect(places.at(-1)).toMatchObject({ name: where, kind: "freezer" });
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  const shed = pantry.places.find((p: { name: string }) => p.name === where);
  expect(shed.groups.map((g: { food: { id: number } }) => g.food.id)).toContain(
    food.id,
  );
});

test("F101: + Place in Add to pantry can be cancelled, and a name the household has picks that place", async ({
  page,
}) => {
  const food = await stocked(page, "Millet", null);
  const before = (await (await page.request.get("/api/v1/places")).json())
    .length;
  await page.goto("/pantry");
  await page
    .getByRole("button", { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole("dialog", { name: "Add to pantry" });
  await sheet
    .getByRole("searchbox", { name: "Find an ingredient" })
    .fill(food.name);
  await sheet
    .getByRole("button", { name: new RegExp(`^${food.name}`) })
    .click();
  const where = sheet.getByLabel(/^Where/);
  const usual = await where.locator("option:checked").textContent();
  await where.selectOption({ label: "+ Place" });
  const box = sheet.getByRole("group", { name: "New place" });
  await box.getByRole("button", { name: "Cancel" }).click();
  await expect(box).toHaveCount(0);
  // Cancelled: the sheet is still open and shows where it was.
  await expect(sheet).toBeVisible();
  await expect(where.locator("option:checked")).toHaveText(usual!);
  await where.selectOption({ label: "+ Place" });
  await box.getByRole("textbox", { name: "Place’s name" }).fill("spice RACK");
  await box.getByRole("button", { name: "Add place" }).click();
  await expect(where.locator("option:checked")).toHaveText("Spice rack");
  expect((await (await page.request.get("/api/v1/places")).json()).length).toBe(
    before,
  );
});

test("Ctrl+Z undoes a pantry change on desktop", async ({ page }) => {
  test.skip(isPhone(page), "Ctrl+Z is a desktop keyboard shortcut");
  const food = await stocked(page, "Coriander", 0);
  // Use soon holds only Use by packets (S5), and the bundled table says coriander is best
  // before: make this one Use by so it has a Binned button in the strip.
  await api(page, "PATCH", `/foods/${food.id}`, { date_kind: "use_by" });
  await page.goto("/pantry");
  const side = page.getByRole("region", { name: /^Use soon · \d+$/ });
  // Four cards show until "Show all N", and earlier tests left packets that are soon too.
  await expect(
    side.getByRole("heading", { name: /^Use soon · \d+$/ }),
  ).toBeVisible();
  const all = side.getByRole("button", { name: /^Show all \d+$/ });
  if (await all.count()) await all.click();
  await side
    .getByRole("listitem")
    .filter({ hasText: food.name })
    .getByRole("button", { name: "Binned" })
    .click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.locator("h1").click();
  await page.keyboard.press("ControlOrMeta+z");
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test("Find in pantry finds an ingredient by its other name", async ({
  page,
}) => {
  test.skip(isPhone(page), "the search box is on desktop");
  const food = await stocked(page, "Toordal", null);
  await api(page, "POST", `/foods/${food.id}/other-names`, {
    name: "thuvaram paruppu",
  });
  await page.goto("/pantry");
  await page
    .getByRole("searchbox", { name: "Find in pantry" })
    .fill("thuvaram");
  // One list: the food with its place, and the other name that matched.
  await expect(
    page.getByRole("button", { name: new RegExp(`^${food.name} · \\w`) }),
  ).toBeVisible();
  await expect(page.getByText("also called thuvaram paruppu")).toBeVisible();
  await page.getByRole("searchbox", { name: "Find in pantry" }).fill("zzzz");
  await expect(page.getByText("Nothing called “zzzz”.")).toHaveCount(1);
  await expect(page.getByText(/^Nothing in the/)).toHaveCount(0);
  // The header counts match: "0 ingredients" everywhere while nothing is found.
  await expect(page.getByText(/^[1-9]\d* ingredients?$/)).toHaveCount(0);
});

test("+ Staple makes a new ingredient, with no stock", async ({ page }) => {
  test.skip(isPhone(page), "the Staples panel is on desktop");
  const name = `Pepper ${Date.now()}`;
  await page.goto("/pantry");
  await page.getByRole("button", { name: "+ Staple" }).click();
  await page
    .getByRole("searchbox", { name: "Make an ingredient a staple" })
    .fill(name);
  await page
    .getByRole("button", { name: `+ New ingredient: “${name}”` })
    .click();
  await expect(page.getByRole("button", { name })).toBeVisible();
  // The screen shows the new staple at once (optimistic); the server has it a moment later.
  await expect
    .poll(async () => {
      const found = await (
        await page.request.get(`/api/v1/foods?q=${encodeURIComponent(name)}`)
      ).json();
      return found.foods[0]?.staple;
    })
    .toBe(true);
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  expect(JSON.stringify(pantry.places)).not.toContain(name);
});

test("the pack lines open the pack menu, with the choices for a full pack", async ({
  page,
}) => {
  const food = await stocked(page, "Cheese", 3);
  // Not a plain click on the row: on desktop a place shows only its first 8 rows, and by now
  // the earlier tests have filled the Fridge with rows that come before this one.
  await openRow(page, food.name);
  const pack = page
    .getByRole("list", { name: `Packets of ${food.name}` })
    .getByRole("button");
  await expect(pack).toHaveCount(1);
  // Wait for the opened row to settle at its full height, then check it.
  await expect
    .poll(async () => (await pack.boundingBox())?.height ?? 0)
    .toBeGreaterThanOrEqual(44);
  await pack.click();
  const menu = page.getByRole("dialog", { name: new RegExp(food.name) });
  await expect(menu.getByRole("radio", { name: "Full" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await expect(menu.getByRole("radio", { name: "½ left" })).toBeVisible();
  await checkPage(page);
});

test("Add to pantry has a Today use-by", async ({ page }) => {
  const food = await stocked(page, "Milk", null);
  await page.goto("/pantry");
  await page
    .getByRole("button", { name: /Add to pantry/ })
    .first()
    .click();
  const sheet = page.getByRole("dialog", { name: "Add to pantry" });
  await sheet
    .getByRole("searchbox", { name: "Find an ingredient" })
    .fill(food.name);
  await sheet
    .getByRole("button", { name: new RegExp(`^${food.name}`) })
    .click();
  await sheet.getByRole("radio", { name: "1 pack" }).click();
  await sheet.getByRole("radio", { name: "Today" }).click();
  await sheet.getByRole("button", { name: "Add to pantry" }).click();
  const { today } = await (await page.request.get("/api/v1/household")).json();
  await expect
    .poll(async () => {
      const pantry = await (await page.request.get("/api/v1/pantry")).json();
      const lots = pantry.places
        .flatMap(
          (p: {
            groups: { food: { id: number }; lots: { use_by: string }[] }[];
          }) => p.groups,
        )
        .filter((g: { food: { id: number } }) => g.food.id === food.id)
        .flatMap((g: { lots: { use_by: string }[] }) => g.lots);
      return lots
        .map((l: { use_by: string | null }) => l.use_by)
        .filter(Boolean);
    })
    .toEqual([today]);
});

const SIZES = [320, 390] as const;
for (const width of SIZES) {
  for (const theme of ["light", "dark"] as const) {
    test(`the Add to pantry "Pick a date" chip fits a ${width} px phone, ${theme} theme`, async ({
      page,
    }) => {
      test.skip(!isPhone(page), "the bottom sheet is the phone layout");
      await page.emulateMedia({ colorScheme: theme }); // the account is on Auto
      await page.setViewportSize({ width, height: 800 });
      const food = await stocked(page, "Lentils", null);
      const { today } = await (
        await page.request.get("/api/v1/household")
      ).json();
      await page.goto("/pantry");
      await page
        .getByRole("button", { name: /Add to pantry/ })
        .first()
        .click();
      const sheet = page.getByRole("dialog", { name: "Add to pantry" });
      await sheet
        .getByRole("searchbox", { name: "Find an ingredient" })
        .fill(food.name);
      await sheet
        .getByRole("button", { name: new RegExp(`^${food.name}`) })
        .click();

      const chip = sheet.getByRole("radio", { name: "Pick a date" });
      await expect(chip).toBeVisible();
      // On a touch screen the see-through date input lies exactly over the chip, so a tap
      // lands on the input itself and the phone opens its date picker straight away.
      const overChip = await chip.evaluate((el) => {
        const box = el.getBoundingClientRect();
        const hit = document.elementFromPoint(
          box.x + box.width / 2,
          box.y + box.height / 2,
        );
        const input = el.parentElement!.querySelector('input[type="date"]')!;
        const field = input.getBoundingClientRect();
        return {
          hitsInput: hit === input,
          sameBox:
            Math.abs(field.x - box.x) < 1 &&
            Math.abs(field.y - box.y) < 1 &&
            Math.abs(field.width - box.width) < 1 &&
            Math.abs(field.height - box.height) < 1,
        };
      });
      expect(overChip).toEqual({ hitsInput: true, sameBox: true });
      await page.screenshot({
        path: `review-shots/paper-cuts/date-chip-before-${width}-${theme}.png`,
      });

      // Choose a date the way the phone's picker does: set the value, send "change".
      const [year, month, day] = (today as string).split("-").map(Number);
      const later = new Date(Date.UTC(year!, month! - 1, day! + 10))
        .toISOString()
        .slice(0, 10);
      await sheet.locator('input[type="date"]').fill(later);
      const chosen = sheet.getByRole("radio", {
        checked: true,
        name: /^\w{3} \d{1,2} \w{3}$/,
      });
      await expect(chosen).toBeVisible();
      await expect(chosen.locator("svg")).toBeVisible();
      const fits = await sheet.evaluate((dialog) => {
        const chips = [
          ...dialog.querySelectorAll<HTMLElement>('[role="radio"]'),
        ];
        const box = dialog.getBoundingClientRect();
        return {
          scrollWidth: dialog.scrollWidth,
          clientWidth: dialog.clientWidth,
          outside: chips.filter((c) => {
            const r = c.getBoundingClientRect();
            return r.right > box.right || r.left < box.left;
          }).length,
        };
      });
      expect(fits.scrollWidth).toBeLessThanOrEqual(fits.clientWidth);
      expect(fits.outside).toBe(0);
      await page.screenshot({
        path: `review-shots/paper-cuts/date-chip-after-${width}-${theme}.png`,
      });
    });
  }
}

/** What is left of a food, in its base unit (grams), summed over its packets. */
const amountLeft = async (page: Page, foodId: number) => {
  const pantry = await (await page.request.get("/api/v1/pantry")).json();
  return pantry.places
    .flatMap(
      (p: {
        groups: {
          food: { id: number };
          lots: { stock: { amount: number } }[];
        }[];
      }) => p.groups,
    )
    .filter((g: { food: { id: number } }) => g.food.id === foodId)
    .flatMap((g: { lots: { stock: { amount: number } }[] }) => g.lots)
    .reduce(
      (sum: number, l: { stock: { amount: number } }) => sum + l.stock.amount,
      0,
    );
};

/**
 * Find a row the way a person does with a full pantry: by searching for it. A place shows
 * only its first few rows (a phone card six, with "+ N more in the Fridge"), and other tests
 * fill the household, so a new row can be behind "more". The search is one list across places.
 */
async function findRow(page: Page, name: string) {
  await page.goto("/pantry");
  await page
    .getByRole("searchbox", {
      name: isPhone(page) ? "Search pantry" : "Find in pantry",
    })
    .fill(name);
  // The list is replaced by the search results a moment later. Wait for them, or the click
  // that follows lands on a row that is about to be thrown away and the row closes again.
  await expect(
    page.getByRole("list", { name: "Found in the pantry" }),
  ).toBeVisible();
}

async function openRow(page: Page, name: string) {
  await findRow(page, name);
  await page
    .getByRole("button", { name: new RegExp(`^${name}`) })
    .first()
    .click();
}

test("an opened single-packet row shows the marks; ½ sets the amount and Undo restores it", async ({
  page,
}) => {
  const food = await stocked(page, "Paneer", 5);
  await openRow(page, food.name);
  const marks = page.getByRole("radiogroup", { name: /How much is left/ });
  await expect(marks.getByRole("radio")).toHaveCount(4);
  await expect(marks.getByRole("radio", { name: "Full" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  expect(await amountLeft(page, food.id)).toBe(200);

  await marks.getByRole("radio", { name: "½ left" }).click();
  await expect(marks.getByRole("radio", { name: "½ left" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  await expect.poll(() => amountLeft(page, food.id)).toBe(100);

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => amountLeft(page, food.id)).toBe(200);
  await expect(marks.getByRole("radio", { name: "Full" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

test("on desktop the marks in the opened row fit their column and pass the accessibility checks", async ({
  page,
}) => {
  test.skip(isPhone(page), "the desktop layout");
  const food = await stocked(page, "Yoghurt", 5);
  await openRow(page, food.name);
  const marks = page.getByRole("radiogroup", { name: /How much is left/ });
  await expect(marks).toBeVisible();
  for (const radio of await marks.getByRole("radio").all()) {
    const size = await radio.evaluate((el) => ({
      width: el.getBoundingClientRect().width,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(size.width).toBeGreaterThanOrEqual(44);
    expect(size.scrollWidth).toBeLessThanOrEqual(size.clientWidth);
  }
  await page.screenshot({ path: "review-shots/pack-marks/desktop-row.png" });
  await checkPage(page);
});

test('"200 g left · type it instead" (a full pack) opens What\'s left in the packet menu', async ({
  page,
}) => {
  const food = await stocked(page, "Halloumi", 5);
  await openRow(page, food.name);
  const link = page.getByRole("button", { name: /^type it instead/ });
  await expect(link.locator("..")).toHaveText(
    /^200\sg left · type it instead$/,
  );
  await link.click();
  const dialog = page.getByRole("dialog", { name: new RegExp(food.name) });
  const box = dialog.getByRole("textbox", { name: /What’s left/ });
  await expect(box).toBeFocused();
  await box.fill("150");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => amountLeft(page, food.id)).toBe(150);
});

test("F122: a weight packet with no size, not open, can have its amount set (What's left), with Undo", async ({
  page,
}) => {
  const unique = `Ghee ${test.info().project.name.replace(/\W/g, "")} ${Date.now()}`;
  const { food } = await api(page, "POST", "/foods", {
    name: unique,
    counted_as: "weight",
  });
  await api(page, "POST", "/stock", {
    food_id: food.id,
    amount: { amount: 38, unit: "g" },
  });
  await openRow(page, unique);
  // No size: no ¼ ½ ¾ Full, but "What's left" can still be typed, beside "Used some".
  await expect(page.getByRole("radiogroup")).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: /^Used some/ })).toBeVisible();
  await page.getByRole("button", { name: /^type it instead/ }).click();
  const dialog = page.getByRole("dialog", { name: new RegExp(unique) });
  const box = dialog.getByRole("textbox", { name: /What’s left/ });
  await expect(box).toBeFocused();
  await box.fill("20");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect.poll(() => amountLeft(page, food.id)).toBe(20);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => amountLeft(page, food.id)).toBe(38);
});

test("a row with several packets shows no marks in the row", async ({
  page,
}) => {
  const food = await stocked(page, "Rice", 5);
  await api(page, "POST", "/stock", {
    food_id: food.id,
    amount: { amount: 1, unit: "pack" },
  });
  await openRow(page, food.name);
  await expect(
    page.getByRole("list", { name: `Packets of ${food.name}` }),
  ).toBeVisible();
  await expect(page.getByRole("radiogroup")).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "Full" })).toHaveCount(0);
  // The marks are still in the pack line's menu.
  await page
    .getByRole("list", { name: `Packets of ${food.name}` })
    .getByRole("button")
    .first()
    .click();
  await expect(
    page
      .getByRole("dialog", { name: new RegExp(food.name) })
      .getByRole("radio", { name: "Full" }),
  ).toBeVisible();
});

for (const width of SIZES) {
  for (const theme of ["light", "dark"] as const) {
    test(`the marks in the opened row fit a ${width} px phone, ${theme} theme`, async ({
      page,
    }) => {
      test.skip(!isPhone(page), "the phone layout");
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: 800 });
      const food = await stocked(page, "Tofu", 5);
      await openRow(page, food.name);
      const marks = page.getByRole("radiogroup", { name: /How much is left/ });
      await expect(marks).toBeVisible();
      for (const radio of await marks.getByRole("radio").all()) {
        expect((await radio.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      }
      const fits = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(fits.scrollWidth).toBeLessThanOrEqual(fits.clientWidth);
      await page.screenshot({
        path: `review-shots/pack-marks/row-${width}-${theme}.png`,
      });
      await checkPage(page);
    });
  }
}

/** A finger sliding sideways over a row, for real: touch events through the browser. */
async function swipeRow(page: Page, name: string, dx: number) {
  const row = page
    .getByRole("button", { name: new RegExp(`^${name}`) })
    .first()
    .locator("xpath=ancestor::div[contains(@class,'slide')]");
  await row.evaluate((el) => el.scrollIntoView({ block: "center" }));
  const box = (await row.boundingBox())!;
  const y = box.y + box.height / 2;
  const from = box.x + (dx > 0 ? 40 : box.width - 40);
  const cdp = await page.context().newCDPSession(page);
  const send = (type: "touchStart" | "touchMove" | "touchEnd", x?: number) =>
    cdp.send("Input.dispatchTouchEvent", {
      type,
      touchPoints: x === undefined ? [] : [{ x, y }],
    });
  await send("touchStart", from);
  const step = dx / 8;
  for (let i = 1; i <= 8; i++) await send("touchMove", from + i * step);
  await send("touchEnd");
  await cdp.detach();
}

test("phone: swipe right is Used…, swipe left is Binned with an Undo toast and no question", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone swipes");
  const food = await stocked(page, "Swipe spinach", null);
  await findRow(page, food.name);
  await swipeRow(page, food.name, 110);
  const used = page.getByRole("button", { name: `Used… ${food.name}` });
  await expect(used).toBeVisible();
  await checkPage(page); // both themes
  await used.click();
  const sheet = page.getByRole("dialog", {
    name: `How much ${food.name} did you use?`,
  });
  await expect(sheet).toBeVisible();
  await checkPage(page);
  await sheet.getByRole("button", { name: "Cancel" }).click();
  expect(await lotsOf(page, food.id)).toBe(1); // nothing changed
  await swipeRow(page, food.name, -110);
  await page.getByRole("button", { name: `Binned ${food.name}` }).click();
  await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(
    page.getByRole("status").filter({ hasText: /^Binned/ }),
  ).toBeVisible();
  // The toast shows at once and the save follows (about 30 ms later), so wait for it.
  await expect.poll(() => lotsOf(page, food.id)).toBe(0);
  await page.getByRole("status").getByRole("button", { name: "Undo" }).click();
  await expect.poll(() => lotsOf(page, food.id)).toBe(1);
});

test("phone: a row behind “+ N more” in a place’s card opens its marks and swipes like any other", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone cards");
  // More than six in the Fridge, so at least one is behind "+ N more in the Fridge".
  const made: { id: number; name: string }[] = [];
  for (let i = 0; i < 7; i++)
    made.push(await stocked(page, `Card row ${i}`, null));
  const openFridge = async () => {
    await page.goto("/pantry");
    const fridge = page.locator(".place-card").filter({
      has: page.getByRole("heading", { name: "Fridge", level: 2 }),
    });
    await expect(fridge).toBeVisible();
    const hidden = [];
    for (const food of made) {
      const shown = await fridge
        .getByRole("button", { name: new RegExp(`^${food.name}`) })
        .count();
      if (!shown) hidden.push(food);
    }
    expect(hidden.length).toBeGreaterThan(0);
    await fridge
      .getByRole("button", { name: /^\+ \d+ more in the Fridge$/ })
      .click();
    return hidden[0]!;
  };

  let food = await openFridge();
  await page
    .getByRole("button", { name: new RegExp(`^${food.name}`) })
    .first()
    .click();
  const marks = page.getByRole("radiogroup", { name: /How much is left/ });
  await expect(marks.getByRole("radio")).toHaveCount(4);
  await marks.getByRole("radio", { name: "½ left" }).click();
  await expect.poll(() => amountLeft(page, food.id)).toBe(100);

  food = await openFridge();
  await swipeRow(page, food.name, 110);
  await expect(
    page.getByRole("button", { name: `Used… ${food.name}` }),
  ).toBeVisible();
});

test("Use soon buttons are big enough to touch, and the + sits in the middle of its circle (0.5.1, 0.8)", async ({
  page,
}) => {
  for (const n of ["Gap lemon", "Gap milk", "Gap paneer"])
    await stocked(page, n, 1);
  await page.goto("/pantry");
  await expect(
    page.getByRole("heading", { name: /^Use soon · \d+$/, level: 2 }),
  ).toBeVisible();
  if (isPhone(page)) {
    const plus = await page
      .getByRole("button", { name: "Add to pantry" })
      .evaluate((b) => {
        const box = b.getBoundingClientRect();
        const icon = b.querySelector("svg")!.getBoundingClientRect();
        return Math.abs(
          (box.top + box.bottom) / 2 - (icon.top + icon.bottom) / 2,
        );
      });
    expect(plus).toBeLessThan(1);
  }
  const heights = await page.evaluate(() =>
    [...document.querySelectorAll(".rows .pill, .strip .pill")]
      .filter((b) => (b as HTMLElement).offsetParent)
      .map((b) => b.getBoundingClientRect().height),
  );
  expect(heights.length).toBeGreaterThanOrEqual(3);
  for (const height of heights) expect(height).toBeGreaterThanOrEqual(43.5);
});

test("F194: on the phone Pantry's count line has its own line, with Stocktake at its right, dropping under it when too narrow", async ({
  page,
}) => {
  test.skip(!isPhone(page), "the phone's header");
  await stocked(page, "Header yoghurt");
  await page.goto("/pantry");
  const header = page.locator("header.page-header");
  const title = header.getByRole("heading", { level: 1, name: "Pantry" });
  const add = header.getByRole("button", { name: "Add to pantry" });
  const count = header.getByText(/\d+ ingredients?/);
  const stocktake = header.getByRole("link", { name: "Stocktake", exact: true });
  await expect(count).toBeVisible();
  const box = async (locator: typeof title) => (await locator.boundingBox())!;
  // The title row holds the title and its round buttons only: Stocktake and the count are below.
  const row = await box(title);
  expect((await box(add)).y).toBeLessThan(row.y + row.height);
  expect((await box(count)).y).toBeGreaterThanOrEqual(row.y + row.height - 1);
  expect((await box(stocktake)).y).toBeGreaterThanOrEqual(row.y + row.height - 1);
  // Stocktake is on the right of the count, on the same line.
  const c = await box(count);
  const s = await box(stocktake);
  expect(s.x).toBeGreaterThan(c.x + c.width - 1);
  expect(Math.abs(s.y + s.height / 2 - (c.y + c.height / 2))).toBeLessThan(20);
  // Too narrow for both on one line: Stocktake drops under the count.
  await page.setViewportSize({ width: 250, height: 800 });
  await expect.poll(async () => (await box(stocktake)).y).toBeGreaterThan((await box(count)).y + 10);
});
