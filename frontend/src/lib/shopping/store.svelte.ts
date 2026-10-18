// The Shopping screen's state and the things a person can do on it. Every write is an
// action (actions.ts) put in the phone's queue through sendAction. The screen shows the copy
// with the queue on top (applyLocal, sync-protocol 11.2), so a change shows at once, stays
// while it can't be sent, and goes only if the server refuses it (UX principle 8). Undo is
// in the toast (principle 6).

import { ApiError } from '$lib/api';
import { kitchen } from '$lib/freshness.svelte';
import { network } from '$lib/network.svelte';
import { newChangeId } from '$lib/changeId';
import { getFood, listFoods } from '$lib/client/foods';
import type { FoodRow } from '$lib/client/types';
import type { Chosen } from '$lib/newIngredient.svelte';
import { COULDNT_SAVE, type Outcome } from '$lib/save';
import { session } from '$lib/session.svelte';
import { toasts } from '$lib/toast.svelte';
import { undoHistory, type UndoEntry } from '$lib/undo.svelte';
import { makeAction, type ActionFields, type ActionResult } from './actions';
import { applyLocal } from './applyLocal';
import { EMPTY_COPY } from './load';
import { sendAction, shoppingSync } from './sync.svelte';
import type { FoodSize, ListItem, ShopFood, Tick } from './types';
import { groupByShop, listCounts, standingTicks, subtitle } from './view';

/** The last thing ticked, for the desktop "Put away" panel and the phone toast. */
export interface Ticked {
  itemId: string;
  tickId: string;
  actionId: string;
  name: string;
}

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
  problem = $state<string | null>(null);
  listId = $state<string | null>(null);
  lastTicked = $state<Ticked | null>(null);

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
  readonly subtitle = $derived(
    this.list
      ? subtitle(
          this.list,
          this.counts.toBuy,
          this.copy.people,
          session.me?.id ?? null,
          network.offline
        )
      : ''
  );
  readonly cards = $derived(
    this.list ? this.copy.questions.filter((q) => q.open && q.list_id === this.list!.id) : []
  );
  readonly notes = $derived(
    this.list ? this.copy.notes.filter((n) => !n.gone && n.list_id === this.list!.id) : []
  );

  countsOf(listId: string) {
    const list = this.copy.lists.find((l) => l.id === listId);
    return list ? listCounts(this.copy, list) : { toBuy: 0, ticked: 0 };
  }

  placeName(id: number | null): string | null {
    return this.copy.places.find((p) => p.id === id)?.name ?? null;
  }

  item(id: string): ListItem | undefined {
    return this.copy.items.find((i) => i.id === id);
  }

  food(id: number): ShopFood | undefined {
    return this.copy.foods.find((f) => f.id === id);
  }

  /** Fetch what changed (or, with `full`, a whole new copy) and merge it in. */
  async load(full = false): Promise<void> {
    try {
      // The first time: send what's waiting on this phone before showing the list (11.6).
      if (!this.loaded) await shoppingSync.start();
      await shoppingSync.refresh(full);
      this.problem = null;
    } catch (error) {
      // Offline: the copy on this phone (if there is one) shows, with the queue on top.
      if (!shoppingSync.copy && !this.loaded) {
        this.problem =
          error instanceof ApiError ? error.detail : 'Couldn’t load your shopping list.';
      }
    }
    this.loaded = true;
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
   * server. Offers Undo at once (unless quiet). Resolves when the server has answered; only a
   * refusal is a failure, and then the change is gone from the screen as it leaves the queue.
   */
  async #act(
    fields: ActionFields,
    options: {
      label?: string;
      /** No Undo toast (the caller shows its own). */
      quiet?: boolean;
      saved?: (result: ActionResult, actionId: string) => void;
    } = {}
  ): Promise<Outcome<ActionResult>> {
    const id = newChangeId();
    const entry: UndoEntry | undefined =
      options.label && !options.quiet
        ? { label: options.label, undo: () => this.undo(id) }
        : undefined;
    const toastId = entry ? undoHistory.record(entry) : undefined;
    try {
      const result = await sendAction(makeAction(fields, id));
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
      // The server said no, with its reason in plain English.
      toasts.show(error instanceof ApiError ? error.detail : COULDNT_SAVE, { tone: 'problem' });
      return { ok: false, error };
    }
  }

  async undo(actionId: string): Promise<string | void> {
    const result = await sendAction(makeAction({ kind: 'undo', undoes: actionId }));
    if (result.changes && result.status !== 'ignored') this.#sync(result);
    else await this.load(true);
    return result.message ?? undefined;
  }

  add(food: Pick<FoodRow, 'id' | 'name'> & Partial<FoodRow>): Promise<unknown> {
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
      { kind: 'add', list_id: list.id, item_id: newChangeId(), food_id: food.id },
      {
        label: `${food.name} added`
      }
    );
  }

  /**
   * A typed name that isn't an ingredient yet: one `add` with `new_food` (sync-protocol 4.4).
   * The packet sizes picked in "How do you count it?" go inside it (`new_food.sizes`), so it
   * works offline too.
   */
  async addNew(chosen: Chosen) {
    const list = this.list;
    if (!list) return null;
    const outcome = await this.#act(
      {
        kind: 'add',
        list_id: list.id,
        item_id: newChangeId(),
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
        saved: () => kitchen.changed()
      }
    );
    return outcome;
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

  tick(item: ListItem) {
    const food = this.food(item.food_id);
    return this.#act(
      { kind: 'tick', item_id: item.id },
      {
        quiet: true,
        saved: (_result, actionId) => {
          this.lastTicked = {
            itemId: item.id,
            tickId: actionId,
            actionId,
            name: food?.name ?? 'Ingredient'
          };
          void this.#afterTick(item, actionId);
        }
      }
    );
  }

  /** Once the tick is saved: say where it went, with Change and Undo (phone toast). */
  async #afterTick(item: ListItem, actionId: string): Promise<void> {
    const row = this.item(item.id);
    const name = this.food(item.food_id)?.name ?? 'Ingredient';
    const tick = row?.ticks.find((t) => t.id === actionId) ?? row?.ticks.find((t) => t.standing);
    const place = this.placeName(tick?.place_id ?? row?.put_away_place_id ?? null);
    const entry = {
      label: place ? `${name} → ${place}` : `${name} ticked`,
      undo: () => this.undo(actionId)
    };
    undoHistory.record(entry, { toast: false });
    toasts.show(entry.label, {
      extra: place ? { label: 'Change', run: () => (this.placing = item.id) } : undefined,
      action: { label: 'Undo', run: () => void undoHistory.undo(entry) },
      duration: 8000
    });
  }

  /** The item whose place is being chosen (the toast's Change, or the place button). */
  placing = $state<string | null>(null);

  untick(item: ListItem) {
    const ids = standingTicks(item).map((t) => t.id);
    if (!ids.length) return Promise.resolve(null);
    return this.#act(
      { kind: 'untick', item_id: item.id, tick_ids: ids },
      {
        label: `${this.food(item.food_id)?.name ?? 'Ingredient'} unticked`
      }
    );
  }

  putAway(item: ListItem, placeId: number) {
    const ids = standingTicks(item).map((t) => t.id);
    const place = this.placeName(placeId) ?? '';
    this.placing = null;
    return this.#act(
      { kind: 'put_away', item_id: item.id, place_id: placeId, tick_ids: ids },
      {
        label: `${this.food(item.food_id)?.name ?? 'Ingredient'} → ${place}`
      }
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
        label: `${name} removed from the list`
      }
    );
  }

  clearTicked(items: ListItem[]) {
    const list = this.list;
    if (!list || !items.length) return Promise.resolve(null);
    const gone = items.map((i) => i.id);
    return this.#act(
      { kind: 'clear_ticked', list_id: list.id, item_ids: gone },
      {
        label: `Cleared ${gone.length} ticked ${gone.length === 1 ? 'item' : 'items'}`
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

  async search(text: string): Promise<FoodRow[]> {
    return (await listFoods({ q: text, limit: 8 })).foods;
  }
}
