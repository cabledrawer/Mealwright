// The Stocktake screen's state (F118, 0.8): the places, the place on screen, and every answer.
// An answer shows at once and goes to the server on its own (one change, Undo in the toast);
// the server keeps the progress for the household, so another phone carries on from the same
// place. See docs/dev/api-endpoints.md 6.5a.

import { serverUndo } from './client/changes';
import {
  addSomethingElse,
  answerFood,
  finishPlace,
  getStocktake,
  getStocktakePlace,
  makeStapleHere,
  restartStocktake,
  setPackSize,
  type AnswerBody,
  type Stocktake,
  type StocktakePlace,
  type StocktakeRow,
  type StocktakeWrite
} from './client/stocktake';
import type { PackSuggestion } from './client/types';
import { kitchen } from './freshness.svelte';
import { COULDNT_SAVE, save } from './save';
import { toasts } from './toast.svelte';

/** The pick that matches the row now: null while it isn't answered. */
export const fractionOf = (row: StocktakeRow): number | null =>
  row.answer?.fraction != null ? Number(row.answer.fraction) : null;

/** The whole packets besides the open one: the answer's, else what is there now. */
export const moreOf = (row: StocktakeRow): number => row.answer?.more ?? row.more_now;

/** The open packet's share: the answer's, else what is there now (0 when nothing is known). */
export const shareOf = (row: StocktakeRow): number =>
  fractionOf(row) ?? (row.fraction_now != null ? Number(row.fraction_now) : 0);

/** "2 tins", "1 tin", or just "2" when the ingredient has no word of its own. */
export function countWords(row: StocktakeRow, n: number): string {
  const word = n === 1 ? row.count_word : (row.count_word_plural ?? row.count_word);
  return word ? `${n}\u00a0${word}` : String(n);
}

/** How many there are now, for a counted row. */
export const countNowOf = (row: StocktakeRow): number =>
  countOf(row) ?? (row.count_now != null ? Number(row.count_now) : 0);

export const countOf = (row: StocktakeRow): number | null =>
  row.answer?.count != null ? Number(row.answer.count) : null;

export class StocktakeModel {
  overview = $state<Stocktake | null>(null);
  place = $state<StocktakePlace | null>(null);
  /** Nothing to show yet (first load), or the server could not be reached. */
  loading = $state(true);
  failed = $state(false);
  /** The newest tap per ingredient, so a slow answer never undoes a newer tap on screen. */
  #latest: Record<number, number> = {};
  #tap = 0;

  /** Open at the first place not finished (or the last, when all are done). */
  async open(): Promise<void> {
    try {
      const overview = await getStocktake();
      this.overview = overview;
      const wanted =
        overview.current_place_id ?? overview.places[overview.places.length - 1]?.id ?? null;
      if (wanted !== null) this.place = await getStocktakePlace(wanted);
      this.failed = false;
    } catch {
      this.failed = true;
    } finally {
      this.loading = false;
    }
  }

  /** Fetch the place on screen again (another phone answered, or an Undo). */
  async reload(): Promise<void> {
    const id = this.place?.place.id;
    if (id === undefined) return;
    try {
      const [overview, place] = await Promise.all([getStocktake(), getStocktakePlace(id)]);
      // Don't replace rows while an answer is still on its way, nor put back a place the
      // person has already moved on from (Next, Back) while this was being fetched.
      if (Object.keys(this.#latest).length === 0 && this.place?.place.id === id) {
        this.overview = overview;
        this.place = place;
      }
    } catch {
      // The next change or a return to the screen tries again.
    }
  }

  /** Go to a place (Back, or Next once the one before is finished). */
  async goTo(placeId: number): Promise<boolean> {
    try {
      this.place = await getStocktakePlace(placeId);
      this.overview = await getStocktake();
      return true;
    } catch {
      return this.#failed(() => void this.goTo(placeId));
    }
  }

  /** The usual words when something could not be saved or opened, with a real Try again that
   *  asks again (FE11); false, for the caller. */
  #failed(retry: () => void): false {
    toasts.problem(COULDNT_SAVE, retry);
    return false;
  }

  /** "Next: Spice rack →": this place is finished; go on to the next. */
  async next(): Promise<boolean> {
    const here = this.place;
    if (!here) return false;
    try {
      this.overview = await finishPlace(here.place.id);
      if (here.next) this.place = await getStocktakePlace(here.next.id);
      else this.place = { ...here, finished: true };
      kitchen.changed({ elsewhere: true });
      return true;
    } catch {
      return this.#failed(() => void this.next());
    }
  }

  async restart(): Promise<boolean> {
    try {
      this.overview = await restartStocktake();
      const first = this.overview.places[0];
      if (first) this.place = await getStocktakePlace(first.id);
      return true;
    } catch {
      return this.#failed(() => void this.restart());
    }
  }

  #row(foodId: number): StocktakeRow | undefined {
    return this.place?.rows.find((r) => r.food.id === foodId);
  }

  #replace(write: StocktakeWrite): void {
    const place = this.place;
    if (!place) return;
    place.rows = place.rows.map((r) => (r.food.id === write.row.food.id ? write.row : r));
    place.answered = write.answered;
    place.total = write.total;
    const step = this.overview?.places.find((p) => p.id === place.place.id);
    if (step) {
      step.answered = write.answered;
      step.total = write.total;
    }
  }

  /** What an Undo does here: put the place back as the server has it now. */
  #afterUndo = () => void this.reload();

  /** Send one change for one row. `shown` is how the row looks the moment it is tapped. */
  #act(
    foodId: number,
    shown: (row: StocktakeRow) => void,
    send: (key: string) => Promise<StocktakeWrite>,
    label: string
  ) {
    const row = this.#row(foodId);
    if (!row) return Promise.resolve();
    const before = $state.snapshot(row) as StocktakeRow;
    const tap = ++this.#tap;
    this.#latest[foodId] = tap;
    const done = () => {
      if (this.#latest[foodId] === tap) delete this.#latest[foodId];
    };
    let undoer: (() => Promise<string | void>) | null = null;
    return save<StocktakeWrite>({
      apply: () => shown(row),
      rollback: () => {
        done();
        const place = this.place;
        if (place) place.rows = place.rows.map((r) => (r.food.id === foodId ? before : r));
      },
      send: (key) => send(key),
      saved: (write) => {
        const newest = this.#latest[foodId] === tap;
        done();
        if (newest) this.#replace(write);
        else if (write.change) this.#replacePlaceCounts(write);
        kitchen.changed({ elsewhere: true });
      },
      undo: {
        label,
        labelFrom: (write) => write.change?.summary,
        skip: (write) => write.change === null,
        run: (write) =>
          write.change ? (undoer ??= serverUndo(write.change.id, this.#afterUndo))() : false
      }
    });
  }

  #replacePlaceCounts(write: StocktakeWrite): void {
    if (!this.place) return;
    this.place.answered = write.answered;
    this.place.total = write.total;
  }

  /** None · ¼ · ½ · ¾ · Full, with `more` whole packets besides the open one. */
  pick(foodId: number, name: string, fraction: number, more = 0) {
    const place = this.place;
    if (!place) return Promise.resolve();
    return this.#act(
      foodId,
      (row) => {
        row.answered = true;
        row.answer = { fraction: String(fraction), more, count: null };
      },
      (key) => answerFood(place.place.id, foodId, { fraction, more }, key),
      `Stocktake: ${name} in the ${place.place.name}`
    );
  }

  /** The − / + of an ingredient counted one by one. */
  count(foodId: number, name: string, count: number) {
    const place = this.place;
    if (!place) return Promise.resolve();
    const body: AnswerBody = { count };
    return this.#act(
      foodId,
      (row) => {
        row.answered = true;
        row.answer = { fraction: null, more: 0, count: String(count) };
      },
      (key) => answerFood(place.place.id, foodId, body, key),
      `Stocktake: ${name} in the ${place.place.name}`
    );
  }

  /** "It's a staple". */
  staple(foodId: number, name: string) {
    const place = this.place;
    if (!place) return Promise.resolve();
    return this.#act(
      foodId,
      (row) => {
        row.staple = true;
        row.answered = true;
        row.answer = null;
      },
      (key) => makeStapleHere(place.place.id, foodId, key),
      `Stocktake: ${name} is a staple in the ${place.place.name}`
    );
  }

  /** The pack size asked once (a tapped common size, or a typed one). */
  size(
    foodId: number,
    name: string,
    size: { name: string; amount: number | { amount: number; unit: string } },
    choice?: PackSuggestion
  ) {
    const place = this.place;
    if (!place) return Promise.resolve();
    return this.#act(
      foodId,
      (row) => {
        row.pack_suggestions = [];
        if (choice) {
          row.pack = {
            id: 0,
            name: choice.name,
            plural: choice.name,
            amount: choice.amount,
            display: choice.display,
            usual: true,
            added_when_shopping: false
          };
        }
      },
      (key) => setPackSize(place.place.id, foodId, size, key),
      `Stocktake: ${name} pack size`
    );
  }

  /** "+ Something else in the Cupboard": count this ingredient here too. */
  async addHere(foodId: number): Promise<boolean> {
    const place = this.place;
    if (!place) return false;
    let write: StocktakeWrite;
    try {
      write = await addSomethingElse(place.place.id, foodId);
    } catch {
      return this.#failed(() => void this.addHere(foodId));
    }
    if (!place.rows.some((r) => r.food.id === write.row.food.id)) {
      place.rows = [...place.rows, write.row].sort((a, b) =>
        a.food.name.localeCompare(b.food.name, undefined, { sensitivity: 'base' })
      );
    }
    place.answered = write.answered;
    place.total = write.total;
    kitchen.changed({ elsewhere: true });
    return true;
  }
}
