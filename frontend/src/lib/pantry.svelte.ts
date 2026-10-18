// The Pantry screen's data (contract 6.4): what's where, what to use soon and the
// recent changes, fetched together. Every change shows at once (optimistic), goes
// through save() with its change ID and Undo, and then the screen is fetched again so
// the server's wording ("1½ packets · about 750 g") replaces any guess.

import { ApiError } from './api';
import { listChanges, serverUndo, undoToast } from './client/changes';
import type { UndoResult } from './client/types';
import { createFood, listFoods, patchFood } from './client/foods';
import {
  addStock,
  binnedLot,
  foodLeft,
  foodUsed,
  getPantry,
  getUseSoon,
  moveLot,
  setLeft,
  setUseBy,
  toFreezer,
  usedLot,
  type NewStock
} from './client/stock';
import type {
  AmountIn,
  Answer,
  Change,
  FoodRow,
  Group,
  Pantry,
  PantryFilter,
  Place,
  StockWrite,
  UseSoonLot
} from './client/types';
import { kitchen } from './freshness.svelte';
import { save } from './save';
import { toasts } from './toast.svelte';

/** How many recent changes the Pantry shows (desktop panel; phones show 3). */
export const RECENT = 8;

/** Take a packet off the screen: it was used, binned or moved. */
export function withoutLot(pantry: Pantry, lotId: number): void {
  for (const place of pantry.places) {
    for (const group of place.groups) {
      const before = group.lots.length;
      group.lots = group.lots.filter((lot) => lot.id !== lotId);
      if (group.lots.length !== before) group.lots_count = group.lots.length;
    }
    const groups = place.groups.filter((group) => group.lots_count > 0);
    if (groups.length !== place.groups.length) {
      place.groups = groups;
      place.items = groups.length;
    }
  }
}

/**
 * Put the server's answer on screen: each group it sends replaces that food's group in
 * that place; an emptied one (nothing left, no packets) is taken away.
 */
export function withGroups(pantry: Pantry, groups: Group[]): void {
  for (const group of groups) {
    const place = pantry.places.find((p) => p.id === group.place.id);
    if (!place) continue;
    const others = place.groups.filter((g) => g.food.id !== group.food.id);
    const empty = group.stock.amount === 0 && group.lots.length === 0;
    if (empty) {
      place.groups = others;
    } else {
      const at = place.groups.findIndex((g) => g.food.id === group.food.id);
      if (at === -1) place.groups = [...others, group];
      else place.groups = place.groups.map((g) => (g.food.id === group.food.id ? group : g));
    }
    place.items = place.groups.length;
  }
}

export class PantryModel {
  pantry = $state<Pantry | null>(null);
  useSoon = $state<UseSoonLot[]>([]);
  changes = $state<Change[]>([]);
  filter = $state<PantryFilter>('all');
  /** What is typed in "Find in pantry". */
  query = $state('');
  /** What the pantry on screen was fetched for: while it isn't empty, the screen shows one list of results. */
  searched = $state('');
  /** The foods the search found, best first, with the name that matched (for "also called"). */
  matches = $state<FoodRow[]>([]);
  problem = $state<string | null>(null);

  #asked = 0;

  async load(): Promise<void> {
    const asked = ++this.#asked;
    const query = this.query.trim();
    try {
      const [pantry, useSoon, changes, found] = await Promise.all([
        getPantry(this.filter, this.query),
        getUseSoon(),
        listChanges({ area: 'pantry', limit: RECENT }),
        // Which name matched, for "also called …". Without it the results still show.
        query ? listFoods({ q: query, limit: 500 }).catch(() => null) : null
      ]);
      if (asked !== this.#asked) return; // something newer is on its way
      this.pantry = pantry;
      this.searched = query;
      this.matches = found?.foods ?? [];
      this.useSoon = useSoon.lots;
      this.changes = changes.changes;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem =
        error instanceof ApiError && error.status === 0
          ? error.detail
          : 'Couldn’t load the pantry. Please try again.';
    }
  }

  /** One change: shown at once, saved, offered for Undo, then fetched again. */
  #act(options: {
    label: string;
    edit?: (pantry: Pantry, useSoon: UseSoonLot[]) => UseSoonLot[] | void;
    send: (key: string, answers: Answer[]) => Promise<StockWrite>;
  }) {
    let before: { pantry: Pantry | null; useSoon: UseSoonLot[] } | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save<StockWrite>({
      apply: () => {
        before = {
          pantry: $state.snapshot(this.pantry) as Pantry | null,
          useSoon: $state.snapshot(this.useSoon) as UseSoonLot[]
        };
        if (this.pantry && options.edit) {
          const useSoon = options.edit(this.pantry, this.useSoon);
          if (useSoon) this.useSoon = useSoon;
        }
      },
      rollback: () => {
        if (!before) return;
        this.pantry = before.pantry;
        this.useSoon = before.useSoon;
      },
      send: options.send,
      saved: (value) => {
        if (this.pantry && value.groups?.length) withGroups(this.pantry, value.groups);
        kitchen.changed();
      },
      undo: {
        label: options.label,
        labelFrom: (value) => {
          if (!value.change) return undefined;
          const short = value.short_by ? ` · ${value.short_by.display} more than there was` : '';
          return value.change.summary + short;
        },
        skip: (value) => value.change === null,
        run: (value) => {
          const change = value.change;
          if (!change?.can_undo) return false;
          undoer ??= serverUndo(change.id);
          return undoer();
        }
      }
    });
  }

  #gone(lotId: number) {
    return (pantry: Pantry, useSoon: UseSoonLot[]) => {
      withoutLot(pantry, lotId);
      return useSoon.filter((lot) => lot.id !== lotId);
    };
  }

  used(lotId: number, foodName: string) {
    return this.#act({
      label: `Used ${foodName}`,
      edit: this.#gone(lotId),
      send: (key) => usedLot(lotId, key)
    });
  }

  binned(lotId: number, foodName: string) {
    return this.#act({
      label: `Binned ${foodName}`,
      edit: this.#gone(lotId),
      send: (key) => binnedLot(lotId, key)
    });
  }

  toFreezer(lotId: number, foodName: string) {
    return this.#act({
      label: `${foodName} → Freezer`,
      edit: this.#gone(lotId),
      send: (key) => toFreezer(lotId, key)
    });
  }

  move(lotId: number, foodName: string, place: Place) {
    return this.#act({
      label: `Moved ${foodName} → ${place.name}`,
      edit: (pantry) => withoutLot(pantry, lotId),
      send: (key) => moveLot(lotId, place.id, key)
    });
  }

  /** The ¼ · ½ · ¾ · Full picks (a fraction of the packet), or a typed amount. */
  setLeft(lotId: number, foodName: string, left: { fraction: number } | { amount: AmountIn }) {
    return this.#act({
      label: `${foodName}: what's left changed`,
      send: (key, answers) => setLeft(lotId, left, key, answers)
    });
  }

  setUseBy(lotId: number, foodName: string, useBy: string | null) {
    return this.#act({
      label: useBy ? `${foodName}: new use-by date` : `${foodName}: no use-by date`,
      edit: (pantry) => {
        for (const place of pantry.places)
          for (const group of place.groups)
            for (const lot of group.lots) if (lot.id === lotId) lot.use_by = useBy;
      },
      send: (key) => setUseBy(lotId, useBy, key)
    });
  }

  /** "Used some" on a food in a place. */
  usedSome(foodId: number, foodName: string, amount: AmountIn, placeId: number) {
    return this.#act({
      label: `Used ${amount.amount}${amount.unit === 'count' ? '' : `\u00a0${amount.unit}`} ${foodName}`,
      send: (key, answers) => foodUsed(foodId, amount, placeId, key, answers)
    });
  }

  /** "How many left?" on a food in a place (0 = none left). */
  leftOf(foodId: number, foodName: string, amount: AmountIn, placeId: number) {
    return this.#act({
      label: `${foodName}: ${amount.amount} left`,
      edit:
        amount.amount === 0
          ? (pantry) => {
              for (const place of pantry.places)
                if (place.id === placeId)
                  place.groups = place.groups.filter((g) => g.food.id !== foodId);
            }
          : undefined,
      send: (key, answers) => foodLeft(foodId, amount, placeId, key, answers)
    });
  }

  /** "+ Staple": the food is always assumed in stock from now on. */
  makeStaple(food: { id: number; name: string }) {
    let undoer: (() => Promise<string | void>) | null = null;
    const before = this.pantry?.staples ?? [];
    return save({
      apply: () => {
        if (this.pantry) this.pantry.staples = [...before, { id: food.id, name: food.name }];
      },
      rollback: () => {
        if (this.pantry) this.pantry.staples = before;
      },
      send: (key) => patchFood(food.id, { staple: true }, key),
      saved: () => kitchen.changed(),
      undo: {
        label: `${food.name} is a staple`,
        labelFrom: (value) => value.change?.summary,
        skip: (value) => value.change === null,
        run: (value) =>
          value.change?.can_undo ? (undoer ??= serverUndo(value.change.id))() : false
      }
    });
  }

  /**
   * "+ Staple" with a name nobody has used yet: makes the ingredient with Staple on and
   * puts no stock in the pantry. If there already is one by that name, it just becomes a
   * staple.
   */
  newStaple(name: string) {
    let undoer: (() => Promise<string | void>) | null = null;
    const before = this.pantry?.staples ?? [];
    return save({
      apply: () => {
        if (this.pantry) this.pantry.staples = [...before, { id: -1, name }];
      },
      rollback: () => {
        if (this.pantry) this.pantry.staples = before;
      },
      send: async (key) => {
        try {
          return await createFood({ name, staple: true }, key);
        } catch (error) {
          const id =
            error instanceof ApiError && error.code === 'name_taken'
              ? (error.body as { food_id?: number } | null)?.food_id
              : undefined;
          if (!id) throw error;
          return patchFood(id, { staple: true }, key);
        }
      },
      saved: () => kitchen.changed(),
      undo: {
        label: `${name} is a staple`,
        labelFrom: (value) => value.change?.summary,
        skip: (value) => value.change === null,
        run: (value) =>
          value.change?.can_undo ? (undoer ??= serverUndo(value.change.id))() : false
      }
    });
  }

  add(stock: NewStock, label: string) {
    return this.#act({ label, send: (key, answers) => addStock(stock, key, answers) });
  }

  /** Undo from the Recent changes list (anyone's change, within the undo window). */
  async undo(change: Change): Promise<void> {
    const undone = this.changes;
    this.changes = this.changes.map((c) => (c.id === change.id ? { ...c, can_undo: false } : c));
    try {
      let answer: UndoResult | null = null;
      await serverUndo(change.id, (result) => (answer = result))();
      toasts.show(undoToast(change.summary, answer));
    } catch (error) {
      this.changes = undone;
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t undo — try again', {
        tone: 'problem'
      });
    }
  }
}
