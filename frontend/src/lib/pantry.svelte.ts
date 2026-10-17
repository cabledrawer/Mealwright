// The Pantry screen's data (contract 6.4): what's where, what to use soon and the
// recent changes, fetched together. Every change shows at once (optimistic), goes
// through save() with its change ID and Undo, and then the screen is fetched again so
// the server's wording ("1½ packets · about 750 g") replaces any guess.

import { ApiError } from './api';
import { listChanges, serverUndo } from './client/changes';
import { patchFood } from './client/foods';
import {
  addStock,
  binnedLot,
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

export class PantryModel {
  pantry = $state<Pantry | null>(null);
  useSoon = $state<UseSoonLot[]>([]);
  changes = $state<Change[]>([]);
  filter = $state<PantryFilter>('all');
  problem = $state<string | null>(null);

  #asked = 0;

  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const [pantry, useSoon, changes] = await Promise.all([
        getPantry(this.filter),
        getUseSoon(),
        listChanges({ area: 'pantry', limit: RECENT })
      ]);
      if (asked !== this.#asked) return; // something newer is on its way
      this.pantry = pantry;
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
      saved: () => kitchen.changed(),
      undo: {
        label: options.label,
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

  #gone(lotId: number) {
    return (pantry: Pantry, useSoon: UseSoonLot[]) => {
      withoutLot(pantry, lotId);
      return useSoon.filter((lot) => lot.id !== lotId);
    };
  }

  used(lotId: number, foodName: string) {
    return this.#act({
      label: `Used ${foodName.toLocaleLowerCase()}`,
      edit: this.#gone(lotId),
      send: (key) => usedLot(lotId, key)
    });
  }

  binned(lotId: number, foodName: string) {
    return this.#act({
      label: `Binned ${foodName.toLocaleLowerCase()}`,
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
      label: `Moved ${foodName.toLocaleLowerCase()} → ${place.name}`,
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

  add(stock: NewStock, label: string) {
    return this.#act({ label, send: (key, answers) => addStock(stock, key, answers) });
  }

  /** Undo from the Recent changes list (anyone's change, within the undo window). */
  async undo(change: Change): Promise<void> {
    const undone = this.changes;
    this.changes = this.changes.map((c) => (c.id === change.id ? { ...c, can_undo: false } : c));
    try {
      const message = await serverUndo(change.id)();
      toasts.show(message || `Undone: ${change.summary}`);
    } catch (error) {
      this.changes = undone;
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t undo — try again', {
        tone: 'problem'
      });
    }
  }
}
