// The ingredient editor's data: one food, loaded from the API, saved as you go (one
// field per request, contract 6.2). Every edit shows at once, goes through save()
// (optimistic, with its change ID and Undo), and is replaced by the server's version
// of the food when the answer arrives.

import { ApiError } from './api';
import { serverUndo } from './client/changes';
import {
  addOtherName,
  addSize,
  addStandIn,
  getFood,
  mergeFood,
  notTheSame,
  patchFood,
  patchSize,
  removeFood,
  removeOtherName,
  removeSize,
  removeStandIn,
  splitFood
} from './client/foods';
import type { Answer, Change as ServerChange, Food, FoodPatch, Ref, Size } from './client/types';
import { kitchen } from './freshness.svelte';
import { save } from './save';
import { toasts } from './toast.svelte';
import { undoneWords } from './undo.svelte';
import { couldntLoad } from './errorWords.js';

type Write = { change: ServerChange | null; food?: Food };

export class FoodModel {
  id: number;
  food = $state<Food | null>(null);
  /** Plain words when the food couldn't be loaded. */
  problem = $state<string | null>(null);
  /** Called when the food has gone (removed), so the editor can close. */
  onGone: (() => void) | null = null;
  /** Called when "name taken" offers to open the other food. */
  onOpenOther: ((id: number) => void) | null = null;

  constructor(id: number) {
    this.id = id;
  }

  /** Counts the loads, so an answer that comes after a newer load began is ignored. */
  #loads = 0;

  /**
   * Fetch the food. If another load began while this one was waiting (Try again, or the food
   * changed from elsewhere), only the newest answer counts: an older one that arrives late,
   * a success or a failure, changes nothing (paper cuts, 0.7).
   */
  async load(): Promise<void> {
    const mine = ++this.#loads;
    try {
      const food = await getFood(this.id);
      if (mine !== this.#loads) return;
      this.food = food;
      this.id = food.id; // a merged-away id answers with the food it went into
      this.problem = null;
    } catch (error) {
      if (mine !== this.#loads) return;
      this.problem =
        error instanceof ApiError && error.status === 404
          ? 'This ingredient isn’t here any more.'
          : couldntLoad('this ingredient');
    }
  }

  /** Change the food on screen. Returns a function that puts it back. */
  #change(edit: (food: Food) => void): () => void {
    const food = this.food;
    if (!food) return () => {};
    const before = $state.snapshot(food) as Food;
    edit(food);
    return () => {
      // Put back only if nothing newer replaced the food meanwhile.
      if (this.food === food) Object.assign(food, before);
    };
  }

  #write<T extends Write>(options: {
    label: string;
    edit?: (food: Food) => void;
    send: (key: string, answers: Answer[]) => Promise<T>;
    undo?: boolean;
    saved?: (value: T) => void;
    /** The answer is about another food (split): stay on this one and fetch it again. */
    keepFood?: boolean;
  }) {
    let putBack = () => {};
    let undoer: (() => Promise<string | void>) | null = null;
    return save<T>({
      apply: () => {
        putBack = options.edit ? this.#change(options.edit) : () => {};
      },
      rollback: () => putBack(),
      send: options.send,
      saved: (value) => {
        if (options.keepFood) void this.load();
        else if (value.food) {
          this.food = value.food;
          this.id = value.food.id;
        }
        kitchen.changed();
        options.saved?.(value);
      },
      undo:
        options.undo === false
          ? undefined
          : {
              label: options.label,
              labelFrom: (value) => value.change?.summary,
              skip: (value) => value.change === null,
              run: (value) => {
                const change = value.change;
                if (!change?.can_undo) return false;
                undoer ??= serverUndo(change.id, () => void this.load());
                return undoer();
              }
            },
      refused: (error) => {
        if (error.code === 'name_taken') {
          const other = (error.body as { food_id?: number } | null)?.food_id;
          toasts.show(error.detail, {
            tone: 'problem',
            action:
              other && this.onOpenOther
                ? { label: 'Open it', run: () => this.onOpenOther?.(other) }
                : undefined
          });
          return true;
        }
        return false;
      }
    });
  }

  /** Save one field (name, staple, place, shop, cup weight…). */
  setField(patch: FoodPatch, edit: (food: Food) => void, label: string) {
    return this.#write({
      label,
      edit,
      send: (key, answers) => patchFood(this.id, patch, key, answers)
    });
  }

  addName(name: string) {
    const trimmed = name.trim();
    if (!trimmed) return;
    return this.#write({
      label: `Added “${trimmed}”`,
      edit: (food) => void food.other_names.push({ id: -Date.now(), name: trimmed }),
      send: (key) => addOtherName(this.id, trimmed, key)
    });
  }

  removeName(name: Ref) {
    return this.#write({
      label: `Removed “${name.name}”`,
      edit: (food) => void (food.other_names = food.other_names.filter((n) => n.id !== name.id)),
      send: (key) => removeOtherName(this.id, name.id, key)
    });
  }

  /** "Make its own ingredient": an other name becomes a food of its own again. */
  split(name: Ref) {
    return this.#write({
      label: `Made ${name.name} its own ingredient`,
      edit: (food) => void (food.other_names = food.other_names.filter((n) => n.id !== name.id)),
      send: (key) => splitFood(this.id, name.id, key),
      keepFood: true
    });
  }

  addSize(name: string, amount: number, unit: string) {
    return this.#write({
      label: `Added a size: ${name}`,
      send: (key, answers) => addSize(this.id, { name, amount: { amount, unit } }, key, answers)
    });
  }

  makeUsual(size: Size) {
    return this.#write({
      label: `${size.name} is the usual size`,
      edit: (food) => food.sizes.forEach((s) => (s.usual = s.id === size.id)),
      send: (key) => patchSize(this.id, size.id, { usual: true }, key)
    });
  }

  removeSize(size: Size) {
    return this.#write({
      label: `Removed the ${size.name} size`,
      edit: (food) => void (food.sizes = food.sizes.filter((s) => s.id !== size.id)),
      send: (key) => removeSize(this.id, size.id, key)
    });
  }

  addStandIn(other: Ref) {
    return this.#write({
      label: `${other.name} can stand in`,
      edit: (food) => void food.stand_ins.push({ ...other, both_ways: false }),
      send: (key) => addStandIn(this.id, other.id, key)
    });
  }

  removeStandIn(other: Ref) {
    return this.#write({
      label: `${other.name} no longer stands in`,
      edit: (food) => void (food.stand_ins = food.stand_ins.filter((s) => s.id !== other.id)),
      send: (key) => removeStandIn(this.id, other.id, key)
    });
  }

  /** Merge this food into another; the editor then shows the one that's left. */
  mergeInto(other: Ref) {
    const name = this.food?.name ?? '';
    return this.#write({
      label: `Merged ${name} into ${other.name}`,
      send: (key, answers) => mergeFood(this.id, other.id, key, answers)
    });
  }

  /** Merge another food into this one (the editor stays on this food). */
  absorb(other: Ref) {
    const name = this.food?.name ?? '';
    return this.#write({
      label: `Merged ${other.name} into ${name}`,
      edit: (food) => void (food.maybe_same = food.maybe_same.filter((m) => m.id !== other.id)),
      send: (key, answers) => mergeFood(other.id, this.id, key, answers)
    });
  }

  /** "Not the same": hides the hint for good. Quiet, with no Undo (contract 7.4). */
  async notTheSame(other: Ref): Promise<void> {
    const putBack = this.#change(
      (food) => void (food.maybe_same = food.maybe_same.filter((m) => m.id !== other.id))
    );
    try {
      await notTheSame(this.id, other.id);
      kitchen.changed();
    } catch (error) {
      putBack();
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t save. Try again.', {
        tone: 'problem'
      });
    }
  }

  /** "Remove from Ingredients": only offered when nothing depends on it. Undoable. */
  remove() {
    const name = this.food?.name ?? '';
    return this.#write({
      label: `Removed ${name} from Ingredients`,
      send: (key) => removeFood(this.id, key),
      saved: () => this.onGone?.()
    });
  }

  /** The household's latest change to this food (the editor's "Undo last change"). */
  async undoLast(): Promise<void> {
    const last = this.food?.last_change;
    if (!last?.can_undo) return;
    try {
      const message = await serverUndo(last.id)();
      toasts.show(message || undoneWords(last.summary));
    } catch (error) {
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t undo. Try again.', {
        tone: 'problem'
      });
    }
    await this.load();
  }
}
