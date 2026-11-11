// What the Shopping screen shows, worked out from the copy (sync-protocol section 13):
// shops in order, each with its aisles, items by name within an aisle (Other for no aisle),
// "Any shop" last, and ticked items folded into "In the trolley" at the end of each shop.

import { AISLES, AISLE_NAMES } from './aisles';
import type { ListItem, ListRow, Note, Person, ShopFood, ShoppingCopy, Tick } from './types';

export interface ViewItem {
  item: ListItem;
  food: ShopFood;
  /** Ticks that still count (not taken back). */
  ticks: Tick[];
  /**
   * In the trolley, the other lines of the same ingredient folded into this one row (F198,
   * cabledrawer 8 Nov: "one trolley row per ingredient"); this view is the most recently ticked.
   */
  more?: ViewItem[];
}

/** The row's lines: itself, then the ones folded into it. */
export function linesOf(view: ViewItem): ViewItem[] {
  return [view, ...(view.more ?? [])];
}

/** One trolley row per ingredient: the lines of the same ingredient fold into the first of them
 * (the list is already most recently ticked first). */
export function joinTrolley(views: ViewItem[]): ViewItem[] {
  // Rows that already carry folded lines are taken apart first, so every line is counted once
  // and joining twice gives the same rows as joining once.
  const rows = new Map<number, ViewItem>();
  const seen = new Set<string>();
  for (const line of views.flatMap(linesOf)) {
    if (seen.has(line.item.id)) continue;
    seen.add(line.item.id);
    const bare: ViewItem = { ...line, more: undefined };
    const first = rows.get(line.food.id);
    if (first) first.more = [...(first.more ?? []), bare];
    else rows.set(line.food.id, bare);
  }
  return [...rows.values()];
}

/** "1" and "1" are "2"; anything with units is joined: "200 g + 1 packet". */
export function joinAmounts(displays: string[]): string {
  if (displays.every((d) => /^\d+$/.test(d))) {
    return String(displays.reduce((sum, d) => sum + Number(d), 0));
  }
  return displays.join(' + ');
}

export interface AisleGroup {
  key: string;
  name: string;
  items: ViewItem[];
}

/** A note for an item that is no longer on the list: a faint row where it was (spec L311). */
export interface Ghost {
  note: Note;
  /** "Paneer · removed by Wren" when the server told us who; else the note's own words. */
  text: string;
}

export interface ShopGroup {
  /** null: "Any shop". */
  shopId: number | null;
  name: string;
  aisles: AisleGroup[];
  trolley: ViewItem[];
  ghosts: Ghost[];
  toBuy: number;
}

export const ANY_SHOP = 'Any shop';

const byName = new Intl.Collator('en', { sensitivity: 'base', numeric: true });

export function standingTicks(item: ListItem): Tick[] {
  return item.ticks.filter((t) => t.standing);
}

/** Items on a list that the screen shows (not deleted, not merged away, ingredient known). */
export function liveItems(copy: ShoppingCopy, listId: string): ViewItem[] {
  const foods = new Map(copy.foods.map((f) => [f.id, f]));
  const out: ViewItem[] = [];
  for (const item of copy.items) {
    if (item.list_id !== listId || item.deleted || item.merged_into_id) continue;
    const food = foods.get(item.food_id);
    if (!food) continue;
    out.push({ item, food, ticks: standingTicks(item) });
  }
  return out;
}

/** Notes about an item that has gone from the list, with the shop it was in. */
export function ghostsOf(
  copy: ShoppingCopy,
  listId: string
): { ghost: Ghost; shopId: number | null }[] {
  const live = new Set(liveItems(copy, listId).map((v) => v.item.id));
  const known = new Set(copy.shops.map((s) => s.id));
  const out: { ghost: Ghost; shopId: number | null }[] = [];
  for (const note of copy.notes) {
    if (note.gone || note.list_id !== listId || !note.item_id || live.has(note.item_id)) continue;
    const gone = copy.removed[note.item_id];
    const food = copy.foods.find((f) => f.id === (gone?.food_id ?? note.food_id));
    const wanted = gone ? gone.shop_id : (food?.shop_id ?? null);
    const shopId = wanted !== null && known.has(wanted) ? wanted : null;
    const name = food?.name ?? 'That ingredient';
    const text = gone?.removed_by
      ? `${name} · removed by ${gone.removed_by}`
      : `${name} · ${note.text}`;
    out.push({ ghost: { note, text }, shopId });
  }
  return out;
}

export function groupByShop(copy: ShoppingCopy, listId: string): ShopGroup[] {
  const ghosts = ghostsOf(copy, listId);
  const shops = [...copy.shops].sort((a, b) => a.position - b.position || a.id - b.id);
  const known = new Set(shops.map((s) => s.id));
  const buckets = new Map<number | null, ViewItem[]>();
  for (const view of liveItems(copy, listId)) {
    const key =
      view.item.shop_id !== null && known.has(view.item.shop_id) ? view.item.shop_id : null;
    const list = buckets.get(key) ?? [];
    list.push(view);
    buckets.set(key, list);
  }
  for (const { shopId } of ghosts) if (!buckets.has(shopId)) buckets.set(shopId, []);
  const groups: ShopGroup[] = [];
  const order: (number | null)[] = [...shops.map((s) => s.id), null];
  for (const id of order) {
    const views = buckets.get(id);
    if (!views) continue;
    const shop = shops.find((s) => s.id === id);
    const sorted = [...views].sort(
      (a, b) => byName.compare(a.food.name, b.food.name) || a.item.id.localeCompare(b.item.id)
    );
    const own = (shop?.aisle_order ?? []).filter((k) => k in AISLE_NAMES);
    const keys = [...own, ...AISLES.map((a) => a.key).filter((k) => !own.includes(k))];
    const aisles: AisleGroup[] = [];
    for (const key of keys) {
      const items = sorted.filter(
        (v) => !v.ticks.length && (v.food.aisle in AISLE_NAMES ? v.food.aisle : 'other') === key
      );
      if (items.length) aisles.push({ key, name: AISLE_NAMES[key]!, items });
    }
    const ticked = sorted.filter((v) => v.ticks.length > 0);
    const trolley = joinTrolley(inTrolleyOrder(ticked));
    groups.push({
      shopId: id,
      name: shop?.name ?? ANY_SHOP,
      aisles,
      trolley,
      ghosts: ghosts.filter((g) => g.shopId === id).map((g) => g.ghost),
      toBuy: sorted.length - ticked.length
    });
  }
  return groups;
}

/** When a line was last ticked (its newest standing tick), as a number to compare. */
function lastTicked(view: ViewItem): number {
  return Math.max(0, ...view.ticks.map((t) => tickTime(t.at)));
}

/** A tick's time as milliseconds, always read as UTC: the server's times have no zone ("…T10:05:00",
 * which `Date.parse` would take as this phone's local time), a queued tick's end in Z. */
export function tickTime(at: string): number {
  const zoned = /(?:Z|[+-]\d\d:?\d\d)$/i.test(at);
  return Date.parse(zoned ? at : `${at}Z`) || 0;
}

/** The trolley: most recently ticked first (F173, cabledrawer 7 Nov); a tie keeps a steady order. */
export function inTrolleyOrder(views: ViewItem[]): ViewItem[] {
  return [...views].sort(
    (a, b) => lastTicked(b) - lastTicked(a) || a.item.id.localeCompare(b.item.id)
  );
}

/** How many on a list still need buying, and how many are in the trolley. */
export function listCounts(copy: ShoppingCopy, list: ListRow): { toBuy: number; ticked: number } {
  const views = liveItems(copy, list.id);
  const ticked = views.filter((v) => v.ticks.length).length;
  return { toBuy: views.length - ticked, ticked };
}

/** Wren · Wren and Arlo · Wren and 2 others (the people other than you; spec new L301). */
export function syncedWith(people: Person[], meId: number | null): string | null {
  const others = people.filter((p) => p.login_id !== meId);
  if (others.length === 0) return null;
  if (others.length === 1) return others[0]!.name;
  if (others.length === 2) return `${others[0]!.name} and ${others[1]!.name}`;
  return `${others[0]!.name} and ${others.length - 1} others`;
}

/** "this week’s plan" for the usual 7 days, otherwise the number of days looked ahead; "the
 * plan" while that isn't known (offline, before the server has answered). */
export function planWords(days: number | null): string {
  if (days === null) return 'the plan';
  if (days === 7) return 'this week’s plan';
  if (days === 1) return 'today’s plan';
  return `the plan for the next ${days} days`;
}

/** The line above the title. */
export function subtitle(
  list: ListRow,
  toBuy: number,
  people: Person[] | null,
  meId: number | null,
  offline = false,
  /** Where the changes are kept: "phone" with the bottom tabs, "computer" with the sidebar. */
  device: 'phone' | 'computer' = 'phone',
  /** `planWords(...)`, when the plan made some of the lines (docs/dev/words.md section 21). */
  builtFrom: string | null = null
): string {
  // Offline, extra lists stay this short (cabledrawer 18 Oct, spec section 6).
  if (!list.main) {
    return offline
      ? `Extra list · ${toBuy} · offline`
      : `Extra list · ${toBuy} · ticked items still go to the pantry`;
  }
  const count =
    builtFrom === null ? `${toBuy} to buy` : `${toBuy} to buy · built from ${builtFrom}`;
  // Changes made offline are kept in the phone's queue (sync-protocol 11.4).
  if (offline) return `${count} · offline, saving on this ${device}`;
  if (!people) return count;
  const who = syncedWith(people, meId);
  return who ? `${count} · synced with ${who}` : `${count} · saved`;
}
