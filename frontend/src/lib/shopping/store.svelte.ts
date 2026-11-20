// The Shopping screen's state and the things a person can do on it. Every write is an
// action (actions.ts) put in the phone's queue through sendAction. The screen shows the copy
// with the queue on top (applyLocal, sync-protocol 11.2), so a change shows at once, stays
// while it can't be sent, and goes only if the server refuses it (UX principle 8). Undo is
// in the toast (principle 6).

import { api, ApiError, cantReach, cantReachWords } from '#lib/api.js';
import { serverUndo } from '#lib/client/changes.js';
import { patchFood } from '#lib/client/foods.js';
import { kitchen } from '#lib/freshness.svelte.js';
import { network } from '#lib/network.svelte.js';
import { placesAndShops } from '#lib/placesAndShops.svelte.js';
import { newChangeId } from '#lib/changeId.js';
import { getFood, listFoods } from '#lib/client/foods.js';
import type { FoodRow } from '#lib/client/types.js';
import type { Chosen } from '#lib/newIngredient.svelte.js';
import { COULDNT_SAVE, save, type Outcome } from '#lib/save.js';
import { session } from '#lib/session.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { COULDNT_UNDO, undoHistory, undoneWords, type UndoEntry } from '#lib/undo.svelte.js';
import { makeAction, type ActionFields, type ActionResult } from './actions';
import { applyLocal } from './applyLocal';
import { EMPTY_COPY } from './load';
import { searchCopy } from './search';
import { putAwayState, type PutAway } from './putAway';
import { sendAction, shoppingSync } from './sync.svelte';
import type { FoodSize, ListItem, ShopFood, Tick } from './types';
import { ANY_SHOP, groupByShop, listCounts, planWords, standingTicks, subtitle } from './view';
import { fromPlan, gotIt, notGotIt, type PlanCard, type Staple } from './plan';
import { plural } from '../words.js';

/** The last thing ticked, for the desktop "Put away" panel and the phone toast. */
export interface Ticked {
  itemId: string;
  tickId: string;
  actionId: string;
  name: string;
  /** Its Undo, as the toast offers it. */
  entry: UndoEntry;
}

/** A toast shown for a change, with its Undo. */
interface Shown {
  entry: UndoEntry;
  toastId: number | undefined;
}

/**
 * Opened offline on a device that has never had the list (spec section 6, cabledrawer 18 Oct):
 * "this phone" with the bottom tabs, "this computer" with the sidebar (by layout).
 */
export const notHereText = (device: 'phone' | 'computer') =>
  `Your shopping list isn’t on this ${device} yet. It’ll be here after you’ve opened it once while connected.`;

export class ShoppingModel {
  /** Ingredients picked in the add box that the copy doesn't have yet. */
  #foods = $state.raw<ShopFood[]>([]);
  /** Packet sizes asked for, for ingredients the copy has none for. */
  #sizes = $state.raw<Record<number, FoodSize[]>>({});

  /** What the screen shows: the copy with this phone's waiting changes on top. */
  readonly copy = $derived(
    applyLocal(shoppingSync.copy ?? EMPTY_COPY, shoppingSync.waitingActions, {
      me: session.me ? { login_id: session.me.id, name: session.me.name } : null,
      foods: this.#foods,
      sizes: this.#sizes
    })
  );
  loaded = $state(false);
  #problem = $state<string | null>(null);
  /** Offline, and this device has never had the list. */
  #notHere = $state(false);
  /** Why the list can't show, worded for this layout. */
  get problem(): string | null {
    return this.#notHere ? notHereText(this.device) : this.#problem;
  }
  listId = $state<string | null>(null);
  /** "phone" with the bottom tabs, "computer" with the sidebar (the offline subtitle). */
  device = $state<'phone' | 'computer'>('phone');
  // Raw: its `entry` must stay the very object the Undo list holds.
  lastTicked = $state.raw<Ticked | null>(null);
  /**
   * The item just ticked with no amount: its row opens "How much?" (F62, cabledrawer 28 Oct).
   * The tick is already in the queue; the answer is a second change (`different_pack`), also
   * queued offline.
   */
  askingHowMuch = $state<string | null>(null);

  // --- Reading -----------------------------------------------------------------------------------

  readonly lists = $derived(
    [...this.copy.lists].filter((l) => !l.removed).sort((a, b) => a.position - b.position)
  );
  readonly list = $derived(
    this.lists.find((l) => l.id === this.listId) ?? this.lists.find((l) => l.main) ?? this.lists[0]
  );
  readonly groups = $derived(this.list ? groupByShop(this.copy, this.list.id) : []);
  readonly counts = $derived(
    this.list ? listCounts(this.copy, this.list) : { toBuy: 0, ticked: 0 }
  );
  /** The list was built from the plan: the main list has lines the plan made. */
  readonly builtFrom = $derived.by(() => {
    const list = this.list;
    if (!list?.main) return null;
    const made = this.copy.items.some(
      (i) => i.list_id === list.id && i.source === 'plan' && !i.deleted && !i.merged_into_id
    );
    return made ? planWords(this.planCard?.days ?? null) : null;
  });
  /** The staples card the server last gave (online only; held in memory, not on the phone). */
  planCard = $state.raw<PlanCard | null>(null);
  /** The staples to show: not the ones already on the list, which a "+ Add" has just put there. */
  readonly staples = $derived(
    (this.planCard?.staples ?? []).filter((s) => this.lineFor(s.food.id) === undefined)
  );
  readonly subtitle = $derived(
    this.list
      ? subtitle(
          this.list,
          this.counts.toBuy,
          this.copy.people,
          session.me?.id ?? null,
          network.offline,
          this.device,
          this.builtFrom
        )
      : ''
  );
  readonly cards = $derived(
    this.list ? this.copy.questions.filter((q) => q.open && q.list_id === this.list!.id) : []
  );
  readonly notes = $derived(
    this.list ? this.copy.notes.filter((n) => !n.gone && n.list_id === this.list!.id) : []
  );

  // --- What only the server's list read says (Plan shopping, S3) -----------------------------

  /** Why each line is there, and whether "Make it a staple?" is offered: from
   * GET /shopping/lists/{id}, worked out from the plan when read. Online only; empty before
   * the first answer and while offline. */
  listRead = $state.raw<Record<string, { why: string; staple_offer: boolean }>>({});

  /** Read the list again for the lines' why. A failure (offline) keeps what is there. */
  async loadListRead(): Promise<void> {
    const list = this.list;
    if (!list || network.offline) return;
    try {
      const view = await api<{
        shops: {
          aisles: { items: { id: string; why: string; staple_offer: boolean }[] }[];
          in_trolley: { id: string; why: string; staple_offer: boolean }[];
        }[];
      }>('GET', `/shopping/lists/${list.id}`);
      const read: Record<string, { why: string; staple_offer: boolean }> = {};
      for (const shop of view.shops) {
        for (const row of [...shop.aisles.flatMap((a) => a.items), ...shop.in_trolley]) {
          read[row.id] = { why: row.why, staple_offer: row.staple_offer };
        }
      }
      this.listRead = read;
    } catch {
      // Keep the last answer.
    }
  }

  /** The words for why a line is there. Offline a typed line still says so. */
  whyOf(item: ListItem): string {
    return this.listRead[item.id]?.why ?? (item.source === 'plan' ? '' : 'Added by you');
  }

  /** "Make it a staple?" is offered on the line (server's rule; never offline). */
  stapleOffered(item: ListItem): boolean {
    return !network.offline && (this.listRead[item.id]?.staple_offer ?? false);
  }

  /** One tap makes the ingredient a staple, with Undo (it leaves the list's offers by itself). */
  async makeStaple(food: ShopFood): Promise<void> {
    let undoer: (() => Promise<string | void>) | null = null;
    const done = await save({
      apply: () => {},
      rollback: () => {},
      send: (key) => patchFood(food.id, { staple: true }, key),
      saved: () => kitchen.changed({ elsewhere: true }),
      undo: {
        label: `${food.name} is now a staple`,
        labelFrom: (result) => result.change?.summary,
        skip: (result) => result.change === null,
        run: (result) => (result.change ? (undoer ??= serverUndo(result.change.id))() : false)
      }
    });
    if (done.ok) void this.loadListRead();
  }

  countsOf(listId: string) {
    const list = this.copy.lists.find((l) => l.id === listId);
    return list ? listCounts(this.copy, list) : { toBuy: 0, ticked: 0 };
  }

  placeName(id: number | null): string | null {
    return this.placeChoices.find((p) => p.id === id)?.name ?? null;
  }

  /** The places to pick from: the copy's, then any made here with "+ Place" that the copy
   * hasn't heard of yet (the next answer from the server has them all). */
  get placeChoices(): { id: number; name: string }[] {
    const known = this.copy.places;
    return [...known, ...placesAndShops.places.filter((p) => !known.some((k) => k.id === p.id))];
  }

  item(id: string): ListItem | undefined {
    return this.copy.items.find((i) => i.id === id);
  }

  food(id: number): ShopFood | undefined {
    return this.copy.foods.find((f) => f.id === id);
  }

  /** Fetch what changed (or, with `full`, a whole new copy) and merge it in. */
  async load(full = false): Promise<void> {
    if (!this.loaded) {
      // The first time: read this phone's copy and queue, and start sending what's waiting
      // before asking for the list (11.6). The copy shows at once, with the queue on top; the
      // server's answer updates it when it comes (cabledrawer 20 Oct, hand test). With no copy
      // here and the browser offline, there's nothing to wait for either.
      await shoppingSync.start();
      if (shoppingSync.copy) {
        this.loaded = true;
      } else if (!navigator.onLine) {
        this.#notHere = true;
        this.loaded = true;
      }
    }
    try {
      await shoppingSync.refresh(full);
      this.#problem = null;
      this.#notHere = false;
    } catch (error) {
      // Offline: the copy on this phone (if there is one) shows, with the queue on top.
      if (!shoppingSync.copy) {
        this.#notHere = cantReach(error);
        this.#problem =
          error instanceof ApiError ? error.detail : 'Couldn’t load your shopping list.';
      }
    }
    this.loaded = true;
  }

  // --- The list from the plan ---------------------------------------------------------------

  /** Opening Shopping: read the list, then bring it up to date with the plan and the pantry (the
   * server does the sums; online only). The list shows at once from this phone's copy, online,
   * slow or offline; the plan's update starts only once the list's own read is over, in the
   * background, and never makes the list wait (cabledrawer 27 Oct). If the plan changed the list,
   * the new lines come down in a second read. */
  async open(): Promise<void> {
    await this.load();
    void this.refreshPlan().then((changed) => (changed ? this.load() : undefined));
  }

  /** Ask the server to update the list from the plan, and keep the staples card it gives.
   * Offline, or when it can't answer, the card stays as it was. Says whether the list changed. */
  async refreshPlan(): Promise<boolean> {
    if (network.offline) return false;
    try {
      const card = await fromPlan();
      this.planCard = card;
      return card.changed;
    } catch {
      return false;
    }
  }

  /** "Got it" on a staple: it leaves the card at once and stays away until the plan's use of it
   * changes. Undo brings it back. */
  async gotIt(staple: Staple): Promise<void> {
    const before = this.planCard;
    if (!before || network.offline) return;
    this.planCard = {
      ...before,
      staples: before.staples.filter((s) => s.food.id !== staple.food.id)
    };
    try {
      this.planCard = await gotIt(staple.food.id);
    } catch (error) {
      this.planCard = before;
      toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
      return;
    }
    toasts.show(`${staple.food.name}: got it`, {
      action: {
        label: 'Undo',
        run: () => void this.#putBack([staple], `${staple.food.name}: got it`)
      }
    });
  }

  /** The card's ✕: "Got it" for every staple on it, with one Undo. */
  async gotAll(): Promise<void> {
    const before = this.planCard;
    const all = this.staples;
    if (!before || !all.length || network.offline) return;
    this.planCard = { ...before, staples: [] };
    try {
      // The card stays empty until the last answer (an early answer would list the rest again).
      let last: PlanCard | null = null;
      for (const staple of all) last = await gotIt(staple.food.id);
      if (last) this.planCard = last;
    } catch (error) {
      void this.refreshPlan();
      toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
      return;
    }
    const label = 'Staples check dismissed';
    toasts.show(label, { action: { label: 'Undo', run: () => void this.#putBack(all, label) } });
  }

  async #putBack(staples: Staple[], label: string): Promise<void> {
    // Not queued: it is a call to the server, so while it can't be reached it says so.
    if (network.offline) {
      toasts.show(cantReachWords());
      return;
    }
    try {
      for (const staple of staples) this.planCard = await notGotIt(staple.food.id);
      toasts.show(undoneWords(label));
    } catch (error) {
      toasts.show(error instanceof ApiError ? error.detail : COULDNT_UNDO, { tone: 'problem' });
    }
  }

  /** "+ Add" on the card: the staple goes on the main list as an ordinary line, the same add
   * as Shopping's add box, with the same Undo. */
  async addStaple(staple: Staple): Promise<void> {
    if (network.offline) return;
    await this.add(
      { id: staple.food.id, name: staple.food.name, staple: true },
      `${staple.food.name} added`
    );
  }

  select(listId: string): void {
    this.listId = listId;
  }

  /** After an action: the changes that came back with it are in the copy already; if it was
   * ignored, get a full copy. */
  #sync(result: ActionResult): void {
    if (result.status === 'ignored') {
      if (result.message) toasts.show(result.message);
      void this.load(true);
    } else if (!result.changes) {
      void this.load();
    }
  }

  /** An ingredient's sizes, asking the server if the copy doesn't have them yet. */
  async sizesOf(foodId: number): Promise<NonNullable<ShopFood['sizes']>> {
    const known = this.food(foodId);
    if (known?.sizes) return known.sizes;
    const full = await getFood(foodId);
    const sizes = full.sizes.map((s) => ({
      id: s.id,
      name: s.name,
      plural: s.plural,
      amount: s.amount,
      usual: s.usual
    }));
    this.#sizes = { ...this.#sizes, [foodId]: sizes };
    return sizes;
  }

  // --- Writing -----------------------------------------------------------------------------------

  /**
   * Make one change: into the queue (so it shows at once, through applyLocal), then to the
   * server. Offers Undo at once (unless quiet: then `queued` may show its own toast, as soon
   * as the change is in the queue). Resolves when the server has answered; only a refusal is
   * a failure, and then the change is gone from the screen as it leaves the queue.
   */
  async #act(
    fields: ActionFields,
    options: {
      label?: string;
      /** No Undo toast here (the caller shows its own, from `queued`). */
      quiet?: boolean;
      /** In the queue (on the screen), not answered yet. May give back the toast it showed. */
      queued?: (actionId: string) => Shown | void;
      saved?: (result: ActionResult, actionId: string) => void;
    } = {}
  ): Promise<Outcome<ActionResult>> {
    const id = newChangeId();
    let entry: UndoEntry | undefined =
      options.label && !options.quiet ? this.#undoEntry(id, options.label) : undefined;
    let toastId = entry ? undoHistory.record(entry) : undefined;
    try {
      const result = await sendAction(makeAction(fields, id), () => {
        const shown = options.queued?.(id);
        if (shown) ({ entry, toastId } = shown);
      });
      this.#sync(result);
      options.saved?.(result, id);
      if (entry && result.status === 'ignored') {
        // Nothing changed, so there's nothing to undo.
        undoHistory.forget(entry);
        if (toastId !== undefined) toasts.dismiss(toastId);
      } else if (entry && result.message) {
        entry.label = result.message;
        if (toastId !== undefined) toasts.update(toastId, result.message);
      }
      return { ok: true, value: result };
    } catch (error) {
      if (entry) undoHistory.forget(entry);
      if (toastId !== undefined) toasts.dismiss(toastId);
      // The server said no, with its reason in plain English.
      toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
      return { ok: false, error };
    }
  }

  /** An entry for the Undo list: Undo of the change with this action ID. */
  #undoEntry(actionId: string, label: string): UndoEntry {
    const entry: UndoEntry = {
      label,
      undo: async () => {
        const result = await this.undo(actionId, entry.label);
        // "Add as bought": one Undo takes back the tick, then the add (no second toast).
        const added = this.#boughtAdds[actionId];
        if (added) {
          delete this.#boughtAdds[actionId];
          void sendAction(makeAction({ kind: 'undo', undoes: added })).then(
            () => void this.load(),
            () => undefined
          );
        }
        // One row for several lines (F198): the same Undo takes back every line's change.
        const others = this.#alsoUndo[actionId];
        if (others) {
          delete this.#alsoUndo[actionId];
          for (const other of others) {
            void sendAction(makeAction({ kind: 'undo', undoes: other })).then(
              () => void this.load(),
              () => undefined
            );
          }
        }
        return result;
      }
    };
    return entry;
  }

  /** One row for several lines (F198): the first change's action ID → the others', so the one
   * toast's Undo takes every line's change back. */
  #alsoUndo: Record<string, string[]> = {};

  /**
   * The same change for every line a trolley row stands for: one toast (the first line's), one
   * Undo for all of them, queued like any change so it works offline too.
   */
  async #together(
    items: ListItem[],
    make: (item: ListItem) => ActionFields,
    label: string
  ): Promise<Outcome<ActionResult> | null> {
    const [head, ...rest] = items;
    if (!head) return null;
    const ids: Promise<string>[] = [];
    const watch = (): ((id: string) => void) => {
      let resolve!: (id: string) => void;
      ids.push(new Promise<string>((r) => (resolve = r)));
      return resolve;
    };
    for (const line of rest) {
      const queued = watch();
      void this.#act(make(line), { quiet: true, queued: (id) => void queued(id) });
    }
    const headQueued = watch();
    const outcome = this.#act(make(head), { label, queued: (id) => void headQueued(id) });
    const all = await Promise.all(ids);
    const headId = all[all.length - 1]!;
    if (rest.length) this.#alsoUndo[headId] = all.slice(0, -1);
    return outcome;
  }

  /** "Add as bought": the tick's action ID → the add's, so one Undo takes both back. */
  #boughtAdds: Record<string, string> = {};

  /**
   * Undo a change: an `undo` action, queued after it (sync-protocol section 9), so it works
   * offline too. "Undone: …" shows as soon as it's in the queue, like any change; when the
   * server answers in its own words (too old, nothing left to undo, part of it used), the
   * toast says those instead, and a refusal says why. Returns false: the toast is shown here.
   */
  async undo(actionId: string, label = ''): Promise<false> {
    let toastId: number | undefined;
    let inQueue!: () => void;
    const queued = new Promise<void>((resolve) => (inQueue = resolve));
    const answered = sendAction(makeAction({ kind: 'undo', undoes: actionId }), () => {
      toastId = toasts.show(undoneWords(label));
      inQueue();
    });
    answered.then(
      (result) => {
        if (result.changes && result.status !== 'ignored') this.#sync(result);
        else void this.load(true);
        if (result.message) this.#say(toastId, result.message);
      },
      (error: unknown) => {
        // Not queued at all (nobody signed in) is the Undo list's to say; a refusal is ours.
        if (toastId === undefined) return;
        toasts.dismiss(toastId);
        toasts.show(error instanceof ApiError ? error.detail : COULDNT_UNDO, { tone: 'problem' });
      }
    );
    await Promise.race([queued, answered]);
    return false;
  }

  /** The server's own words: in the toast still showing, or a new one. */
  #say(toastId: number | undefined, message: string): void {
    if (toastId !== undefined && toasts.current?.id === toastId) toasts.update(toastId, message);
    else toasts.show(message);
  }

  /** Add an ingredient to the open list. `label` is the toast's words ("Oil added to the
   * shopping list"); Shopping's own add box says "Oil added". */
  add(
    food: Pick<FoodRow, 'id' | 'name'> & Partial<FoodRow>,
    label = `${food.name} added`,
    /**
     * For several adds that share one toast and one Undo (a recipe's missing ingredients):
     * `quiet` leaves out this add's own toast, and `queued` hears the action's ID as soon as
     * it is in the queue, so the caller can undo it. What is queued is the same either way.
     */
    group?: { queued: (actionId: string) => void },
    /** A typed amount ("1 l milk"): the add carries it, so it joins a line there already. */
    amount?: { amount: number; sizeId: number | null },
    /** The new line's ID, when the caller needs it (Add as bought ticks that line). */
    itemId: string = newChangeId(),
    /** "Add as bought": the line is its own, never joined into one still to buy. */
    asBought = false
  ): Promise<Outcome<ActionResult> | null> {
    const list = this.list;
    if (!list) return Promise.resolve(null);
    if (!this.food(food.id)) {
      // Not in the copy yet: what the add box knows, so the line shows at once.
      this.#foods = [
        ...this.#foods,
        {
          id: food.id,
          name: food.name,
          other_names: [],
          counted_as: food.counted_as ?? 'weight',
          staple: food.staple ?? false,
          aisle: 'other',
          shop_id: null,
          place_id: food.place?.id ?? null,
          sizes: null
        }
      ];
    }
    return this.#act(
      {
        kind: 'add',
        list_id: list.id,
        item_id: itemId,
        food_id: food.id,
        ...(amount ? { amount: amount.amount, size_id: amount.sizeId } : {}),
        ...(asBought ? { as_bought: true } : {})
      },
      group ? { label, quiet: true, queued: (id) => group.queued(id) } : { label }
    );
  }

  /**
   * A typed name that isn't an ingredient yet: one `add` with `new_food` (sync-protocol 4.4).
   * The packet sizes picked in "Pantry keeps it by" go inside it (`new_food.sizes`), so it
   * works offline too.
   */
  async addNew(
    chosen: Chosen,
    amount?: { amount: number; sizeId: number | null },
    /** "Add as bought" for a brand-new name (F196): an add and a tick, one Undo for both. */
    bought = false
  ) {
    const list = this.list;
    if (!list) return null;
    const itemId = newChangeId();
    let addQueued: Promise<string> | undefined;
    let queued: ((actionId: string) => void) | undefined;
    if (bought) addQueued = new Promise<string>((resolve) => (queued = resolve));
    const outcome = this.#act(
      {
        kind: 'add',
        list_id: list.id,
        item_id: itemId,
        ...(amount ? { amount: amount.amount, size_id: amount.sizeId } : {}),
        ...(bought ? { as_bought: true } : {}),
        new_food: {
          name: chosen.name,
          counted_as: chosen.counted_as,
          staple: chosen.staple,
          ...(chosen.sizes.length
            ? {
                sizes: chosen.sizes.map((z) => ({
                  name: z.name,
                  amount: z.amount * (z.unit === 'kg' || z.unit === 'l' ? 1000 : 1)
                }))
              }
            : {})
        }
      },
      {
        label: `${chosen.name} added`,
        saved: () => kitchen.changed(),
        ...(queued ? { quiet: true, queued } : {})
      }
    );
    if (addQueued) {
      const addId = await addQueued;
      const line = this.item(itemId);
      if (line) void this.tick(line, addId);
    }
    return outcome;
  }

  /**
   * "Add as bought" (F117): an ingredient that was not on the list goes straight into the
   * pantry. It is an add and a tick, one after the other in the queue (so it works offline,
   * like a tick), with one Undo for both. The tick's toast says where it went, with Change.
   */
  async addAsBought(
    food: Pick<FoodRow, 'id' | 'name'> & Partial<FoodRow>,
    amount?: { amount: number; sizeId: number | null }
  ): Promise<void> {
    const itemId = newChangeId();
    const addQueued = new Promise<string>((resolve) => {
      void this.add(food, `${food.name} added`, { queued: resolve }, amount, itemId, true);
    });
    const addId = await addQueued;
    const line = this.item(itemId);
    if (!line) return; // joined a line that was there already: it stays an ordinary add
    const outcome = this.tick(line, addId);
    void outcome;
  }

  /**
   * "Already have it" (F117): what is at home goes into the pantry as found at home, not bought
   * (its own words in Recent changes), and the line goes into the trolley. Works offline.
   */
  foundAtHome(
    item: ListItem,
    found: { amount: number; sizeId: number | null; placeId: number | null; words: string }
  ) {
    const name = this.food(item.food_id)?.name ?? 'Ingredient';
    const place = found.placeId === null ? null : this.placeName(found.placeId);
    return this.#act(
      {
        kind: 'found_at_home',
        item_id: item.id,
        amount: found.amount,
        size_id: found.sizeId,
        place_id: found.placeId
      },
      {
        label: `Found ${name} at home: ${found.words}${place ? ` → ${place}` : ''}`,
        saved: (result) => {
          if (result.status === 'ignored' && result.message) toasts.show(result.message);
        }
      }
    );
  }

  /** A live, unticked line for this ingredient already on the open list, if any. */
  lineFor(foodId: number): ListItem | undefined {
    const list = this.list;
    if (!list) return undefined;
    return this.copy.items.find(
      (i) =>
        i.list_id === list.id &&
        i.food_id === foodId &&
        !i.deleted &&
        !i.merged_into_id &&
        !standingTicks(i).length
    );
  }

  /**
   * Tick an item. As soon as the tick is in the queue (offline too): the toast says where it
   * goes, with Change and Undo, and the desktop Put away panel shows it (UX principle 8).
   * When the server has answered, the toast says where it really went.
   */
  tick(item: ListItem, addedBy?: string) {
    let shown: Shown | undefined;
    let tickId: string | undefined;
    const outcome = this.#act(
      {
        kind: 'tick',
        item_id: item.id,
        // What this phone's line shows is what was bought (RF2 Sh1); no amount, none sent.
        ...(item.amount ? { amount: item.amount, size_id: item.size_id } : {})
      },
      {
        quiet: true,
        queued: (actionId) => {
          tickId = actionId;
          if (addedBy) this.#boughtAdds[actionId] = addedBy;
          // No amount, and not a staple (a staple is only restocked): ask how much.
          if (!item.amount && !this.food(item.food_id)?.staple) this.askingHowMuch = item.id;
          shown = this.#tickToast(item, actionId);
          this.lastTicked = {
            itemId: item.id,
            tickId: actionId,
            actionId,
            name: this.food(item.food_id)?.name ?? 'Ingredient',
            entry: shown.entry
          };
          return shown;
        },
        saved: (result, actionId) => {
          if (!shown || result.status === 'ignored' || result.message) return;
          const label = this.#tickLabel(item, actionId);
          if (label === shown.entry.label) return;
          shown.entry.label = label;
          if (shown.toastId !== undefined) toasts.update(shown.toastId, label);
        }
      }
    );
    return outcome.then((done) => {
      // Refused or ignored: nothing was ticked, so Put away has nothing of it to show.
      const nothing = !done.ok || done.value.status === 'ignored';
      if (nothing && tickId && this.lastTicked?.actionId === tickId) this.lastTicked = null;
      return done;
    });
  }

  /** Where a ticked item goes: its tick's place, the place chosen for it, or its usual one. */
  placeOf(item: ListItem, tickId?: string): number | null {
    const tick = item.ticks.find((t) => t.id === tickId) ?? item.ticks.find((t) => t.standing);
    return (
      tick?.place_id ??
      item.put_away_place_id ??
      this.food(item.food_id)?.place_id ??
      this.#firstCupboard()
    );
  }

  /**
   * Where an ingredient with no usual place goes: the household's first cupboard place, as the
   * server puts it (F199: offline, "→ Cupboard" and not "→ Pantry" until the phone has synced).
   */
  #firstCupboard(): number | null {
    const cupboards = this.copy.places.filter((p) => p.kind === 'cupboard');
    cupboards.sort((a, b) => a.position - b.position || a.id - b.id);
    return cupboards[0]?.id ?? null;
  }

  /**
   * What a tick did, as the toast tells it: "Coriander → Fridge", "Onions ticked" (no amount,
   * or the place isn't known yet), "Salt restocked" (a staple; cabledrawer 20 Oct).
   */
  #tickState(item: ListItem, actionId: string): { label: string; state: PutAway } {
    const row = this.item(item.id) ?? item;
    // The line as it is now: a new ingredient's line gets its real ingredient when the server
    // answers, so the ID the caller holds may be the phone's temporary one (F226).
    const food = this.food(row.food_id) ?? this.food(item.food_id);
    const name = food?.name ?? 'Ingredient';
    const place = this.placeName(this.placeOf(row, actionId));
    const state = putAwayState(
      row,
      food ?? { staple: false },
      row.ticks.find((t) => t.id === actionId),
      this.isWaiting(actionId),
      place
    );
    const label =
      state.kind === 'staple'
        ? `${name} restocked`
        : state.kind === 'amount' && place
          ? `${name} → ${place}`
          : `${name} ticked`;
    return { label, state };
  }

  #tickLabel(item: ListItem, actionId: string): string {
    return this.#tickState(item, actionId).label;
  }

  /** The tick's toast: where it goes, with Change and Undo (phone; desktop has the panel too). */
  #tickToast(item: ListItem, actionId: string): Shown {
    const { label, state } = this.#tickState(item, actionId);
    const entry = this.#undoEntry(actionId, label);
    undoHistory.record(entry, { toast: false });
    const toastId = toasts.show(entry.label, {
      // Change even before the place is known: the server always puts it somewhere (7.1).
      // A staple, or a line with no amount, goes nowhere, so there is nothing to change.
      extra:
        state.kind === 'amount'
          ? { label: 'Change', run: () => (this.placing = item.id) }
          : undefined,
      action: { label: 'Undo', run: () => void undoHistory.undo(entry) },
      duration: 8000
    });
    return { entry, toastId };
  }

  /** Has this phone made the change and not heard back from the server yet? */
  isWaiting(actionId: string): boolean {
    return shoppingSync.waitingActions.some((a) => a.id === actionId);
  }

  /** What a ticked line's tick did, for its row and the Put away panel (cabledrawer 20 Oct). */
  putAwayFor(item: ListItem): PutAway {
    const tick = item.ticks.find((t) => t.standing);
    return putAwayState(
      item,
      this.food(item.food_id) ?? { staple: false },
      tick,
      tick ? this.isWaiting(tick.id) : false,
      this.placeName(this.placeOf(item, tick?.id))
    );
  }

  /** A row's Undo: take that tick back, the same Undo as the toast's. */
  undoTick(item: ListItem): Promise<unknown> {
    const tick = item.ticks.find((t) => t.standing);
    if (!tick) return Promise.resolve();
    if (this.askingHowMuch === item.id) this.askingHowMuch = null;
    if (this.lastTicked?.tickId === tick.id) return this.undoLastTick();
    return this.undo(tick.id, this.#tickLabel(item, tick.id));
  }

  /** The Put away panel's "Undo last tick": the same Undo as the toast's. */
  undoLastTick(): Promise<void> {
    const last = this.lastTicked;
    this.lastTicked = null;
    if (last && this.askingHowMuch === last.itemId) this.askingHowMuch = null;
    return last ? undoHistory.undo(last.entry) : Promise.resolve();
  }

  /** The item whose place is being chosen (the toast's Change, or the place button). */
  placing = $state<string | null>(null);

  untick(item: ListItem) {
    return this.untickAll([item]);
  }

  /** Untick every line of a trolley row: one toast, one Undo (F198). */
  untickAll(items: ListItem[]) {
    for (const item of items) if (this.askingHowMuch === item.id) this.askingHowMuch = null;
    const lines = items.filter((i) => standingTicks(i).length);
    if (!lines.length) return Promise.resolve(null);
    return this.#together(
      lines,
      (item) => ({
        kind: 'untick',
        item_id: item.id,
        tick_ids: standingTicks(item).map((t) => t.id)
      }),
      `${this.food(lines[0]!.food_id)?.name ?? 'Ingredient'} unticked`
    );
  }

  putAway(item: ListItem, placeId: number) {
    return this.putAwayAll([item], placeId);
  }

  /** Change the place of every line of a trolley row: one toast, one Undo (F198). */
  putAwayAll(items: ListItem[], placeId: number) {
    const place = this.placeName(placeId) ?? '';
    this.placing = null;
    return this.#together(
      items,
      (item) => ({
        kind: 'put_away',
        item_id: item.id,
        place_id: placeId,
        tick_ids: standingTicks(item).map((t) => t.id)
      }),
      `${this.food(items[0]?.food_id ?? 0)?.name ?? 'Ingredient'} → ${place}`
    );
  }

  differentPack(item: ListItem, tick: Tick, count: number, pack: number, sizeId?: number | null) {
    return this.#act(
      {
        kind: 'different_pack',
        item_id: item.id,
        tick_id: tick.id,
        count,
        pack,
        size_id: sizeId ?? null
      },
      { label: `${this.food(item.food_id)?.name ?? 'Ingredient'}: pack changed` }
    );
  }

  setAmount(item: ListItem, amount: number, sizeId?: number | null) {
    return this.#act(
      { kind: 'set_amount', item_id: item.id, amount, size_id: sizeId ?? null },
      { label: `${this.food(item.food_id)?.name ?? 'Ingredient'} amount changed` }
    );
  }

  remove(item: ListItem) {
    const name = this.food(item.food_id)?.name ?? 'Ingredient';
    return this.#act(
      { kind: 'delete', item_id: item.id },
      {
        label: `Removed ${name}`
      }
    );
  }

  /** Where a line could go: every shop (and Any shop), then the other lists. */
  movePlaces(item: ListItem) {
    const shops = [...this.copy.shops]
      .sort((a, b) => a.position - b.position || a.id - b.id)
      .map((s) => ({ id: s.id as number | null, name: s.name }));
    return {
      shops: [...shops, { id: null, name: ANY_SHOP }].map((s) => ({
        ...s,
        now:
          s.id ===
          (item.shop_id !== null && shops.some((x) => x.id === item.shop_id) ? item.shop_id : null)
      })),
      lists: this.lists
        .filter((l) => l.id !== item.list_id)
        .map((l) => ({ id: l.id, name: l.name, main: l.main, toBuy: this.countsOf(l.id).toBuy }))
    };
  }

  /**
   * Move a line to another shop (the same list) or another list (the same shop), never ticking
   * it (cabledrawer 22 Oct, question 3). Works offline, like any change; Undo puts it back.
   */
  move(item: ListItem, to: { listId: string; shopId: number | null }) {
    const name = this.food(item.food_id)?.name ?? 'Ingredient';
    const list = this.copy.lists.find((l) => l.id === to.listId);
    const where =
      to.listId !== item.list_id
        ? (list?.name ?? 'the list')
        : to.shopId === null
          ? ANY_SHOP
          : (this.copy.shops.find((s) => s.id === to.shopId)?.name ?? ANY_SHOP);
    return this.#act(
      { kind: 'move', item_id: item.id, list_id: to.listId, shop_id: to.shopId },
      {
        label: `Moved ${name} to ${where}`,
        // Not moved (ticked meanwhile, a list or shop that has gone): say why, in the server's words.
        saved: (result) => {
          if (result.status === 'ignored' && result.message) toasts.show(result.message);
        }
      }
    );
  }

  /** `rows`: how many rows the person saw go (a joined row is several lines but one row). */
  clearTicked(items: ListItem[], rows = items.length) {
    const list = this.list;
    if (!list || !items.length) return Promise.resolve(null);
    const gone = items.map((i) => i.id);
    return this.#act(
      { kind: 'clear_ticked', list_id: list.id, item_ids: gone },
      {
        label: `Cleared ${rows} ticked ${plural(rows, 'item', 'items')}`
      }
    );
  }

  answerCard(questionId: number, answer: 'two' | 'one') {
    return this.#act(
      { kind: 'answer_double_tick', question_id: questionId, answer },
      {
        label: answer === 'two' ? 'Kept both' : 'Took back the extra'
      }
    );
  }

  dismissNote(noteId: number) {
    return this.#act(
      { kind: 'dismiss_note', note_id: noteId },
      {
        quiet: true
      }
    );
  }

  // --- Lists -------------------------------------------------------------------------------------

  async createList(name: string) {
    const listId = newChangeId();
    // It shows at once (from the queue), so open it at once.
    this.listId = listId;
    const outcome = await this.#act(
      { kind: 'create_list', list_id: listId, name },
      {
        label: `Made the list ${name}`
      }
    );
    // Back to the main list if the server refused it.
    if (!outcome.ok && this.listId === listId) this.listId = null;
    return outcome;
  }

  renameList(listId: string, name: string) {
    return this.#act(
      { kind: 'rename_list', list_id: listId, name },
      {
        label: `Renamed the list to ${name}`
      }
    );
  }

  removeList(listId: string) {
    const name = this.copy.lists.find((l) => l.id === listId)?.name ?? 'The list';
    const wasOpen = this.listId === listId;
    return this.#act(
      { kind: 'remove_list', list_id: listId },
      {
        label: `Removed ${name}`,
        saved: () => {
          if (wasOpen) this.listId = null;
        }
      }
    );
  }

  // --- Searching ---------------------------------------------------------------------------------

  /** The add box's matches: from the server, or from the phone's copy while offline (11.1). */
  async search(text: string): Promise<FoodRow[]> {
    if (network.offline) return searchCopy(this.copy, text);
    try {
      return (await listFoods({ q: text, limit: 8 })).foods;
    } catch (error) {
      if (cantReach(error)) return searchCopy(this.copy, text);
      throw error;
    }
  }
}
