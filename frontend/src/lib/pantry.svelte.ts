// The Pantry screen's data (contract 6.4): what's where, and what to use soon,
// fetched together. Every change shows at once (optimistic), goes
// through save() with its change ID and Undo, and then the screen is fetched again so
// the server's wording ("about 750 g · 1½ packets") replaces any guess.

import { ApiError, cantReachWords, cantReach , wordsFor } from './api';
import { serverUndo } from './client/changes';
import { binTub, placeTub, type PlanWrite } from './client/plan';
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
  FoodRow,
  Group,
  Pantry,
  PantryFilter,
  Place,
  StockWrite,
  UseSoonLot,
  UseSoonTub
} from './client/types';
import { kitchen } from './freshness.svelte';
import { save } from './save';
import { plural } from './words.js';
import { couldntLoad } from './errorWords.js';

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
      place.items = groups.length + place.tubs.length;
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
    place.items = place.groups.length + place.tubs.length;
  }
}

export class PantryModel {
  pantry = $state<Pantry | null>(null);
  useSoon = $state<UseSoonLot[]>([]);
  /** Leftover tubs that are Use soon, as their own cards (cabledrawer 7 Nov). */
  useSoonTubs = $state<UseSoonTub[]>([]);
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
      const [pantry, useSoon, found] = await Promise.all([
        getPantry(this.filter, this.query),
        getUseSoon(),
        // Which name matched, for "also called …". Without it the results still show.
        // Asked again on every reload, even for the same words: a new live or stock change can
        // bring in an ingredient that matches only by another name, which the last answer lacks.
        query ? listFoods({ q: query, limit: 500 }).catch(() => null) : null
      ]);
      if (asked !== this.#asked) return; // something newer is on its way
      this.pantry = pantry;
      this.searched = query;
      this.matches = found?.foods ?? [];
      this.useSoon = useSoon.lots;
      this.useSoonTubs = useSoon.tubs;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem = wordsFor(error, couldntLoad('the pantry'));
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

  #goneAll(lotIds: number[]) {
    return (pantry: Pantry, useSoon: UseSoonLot[]) => {
      for (const id of lotIds) withoutLot(pantry, id);
      return useSoon.filter((lot) => !lotIds.includes(lot.id));
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

  /** Binned / To freezer on a Use soon row (0.8): every packet the row stands for, one Undo. */
  binnedRow(row: UseSoonLot) {
    return this.#act({
      label: `Binned ${row.food.name}`,
      edit: this.#goneAll(row.lot_ids),
      send: (key) => binnedLot(row.id, key, true)
    });
  }

  toFreezerRow(row: UseSoonLot) {
    return this.#act({
      label: `${row.food.name} → Freezer`,
      edit: this.#goneAll(row.lot_ids),
      send: (key) => toFreezer(row.id, key, undefined, true)
    });
  }

  /** "Eat it on…" on a Use soon tub card: its soonest tub goes in that meal, one Undo. */
  eatTubOn(tub: UseSoonTub, day: string, slotId: number, slotName: string) {
    let before: UseSoonTub[] | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save<PlanWrite>({
      apply: () => {
        before = $state.snapshot(this.useSoonTubs) as UseSoonTub[];
        this.useSoonTubs = this.useSoonTubs.flatMap((row) => {
          if (row.tub_id !== tub.tub_id) return [row];
          if (row.tubs <= 1) return [];
          const tubs = row.tubs - 1;
          return [{ ...row, tubs, words: `${tubs} ${plural(tubs, 'tub', 'tubs')}` }];
        });
      },
      rollback: () => {
        if (before) this.useSoonTubs = before;
      },
      send: (key) => placeTub(tub.tub_id, { date: day, slot_id: slotId }, key, true),
      // The tub went into a meal since this card was drawn: the server refuses (the toast says
      // so) and the card is looked at again.
      refused: (error) => {
        if (error.code === 'tub_taken') void this.load();
        return false;
      },
      saved: () => kitchen.changed(),
      undo: {
        label: `Put ${tub.recipe_name} in ${slotName}`,
        labelFrom: (value) => value.change?.summary,
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

  /** "Binned" on a passed tub card (cabledrawer 8 Nov): its soonest tub is thrown away, with Undo. */
  binnedTub(tub: UseSoonTub) {
    let before: UseSoonTub[] | null = null;
    let undoer: (() => Promise<string | void>) | null = null;
    return save<PlanWrite>({
      apply: () => {
        before = $state.snapshot(this.useSoonTubs) as UseSoonTub[];
        this.useSoonTubs = this.useSoonTubs.flatMap((row) => {
          if (row.tub_id !== tub.tub_id) return [row];
          if (row.tubs <= 1) return [];
          const tubs = row.tubs - 1;
          return [{ ...row, tubs, words: `${tubs} ${plural(tubs, 'tub', 'tubs')}` }];
        });
      },
      rollback: () => {
        if (before) this.useSoonTubs = before;
      },
      send: (key) => binTub(tub.tub_id, key),
      // The tub was eaten or put in a meal since this card was drawn: the server refuses (the
      // toast says so) and the card is looked at again.
      refused: (error) => {
        if (error.code === 'tub_eaten' || error.code === 'tub_in_meal') void this.load();
        return false;
      },
      saved: () => kitchen.changed(),
      undo: {
        label: `Binned ${tub.recipe_name} tub`,
        labelFrom: (value) => value.change?.summary,
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
      label: `${foodName}: what’s left changed`,
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
}
