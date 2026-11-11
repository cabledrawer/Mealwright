// The "Cook once, eat for…" sheet's state (docs/dev/api-0.2.md 6.3a): the choices, and the
// server's preview of where the tubs land. The server works the preview out (the screen and the
// saved batch then agree); every change to a choice asks it again.

import { ApiError } from './api';
import {
  getPlan,
  previewBatch,
  type BatchBody,
  type BatchPreview,
  type Pattern,
  type Person,
  type Plan,
  type Spot
} from './client/plan';
import { addDays } from './planDates';

/** The most tubs in a batch (the server's cap). */
export const MOST_TUBS = 12;
/** How far ahead the grid can be shown. */
const MOST_DAYS = 28;

export const PATTERNS: { value: Pattern; label: string }[] = [
  { value: 'lunches', label: 'Lunches' },
  { value: 'lunch_dinner', label: 'Lunch & dinner' },
  { value: 'dinners', label: 'Dinners' },
  { value: 'pick', label: 'I’ll pick' }
];

/** "Tub 5", "Tubs 5–6", "Tubs 2, 4 and 6": the numbers of tubs in words. */
export function tubNumbers(numbers: number[]): string {
  if (numbers.length === 0) return '';
  if (numbers.length === 1) return `Tub ${numbers[0]}`;
  const sorted = [...numbers].sort((a, b) => a - b);
  const run = sorted.every((n, i) => i === 0 || n === (sorted[i - 1] ?? 0) + 1);
  if (run) return `Tubs ${sorted[0]}–${sorted.at(-1)}`;
  return `Tubs ${sorted.slice(0, -1).join(', ')} and ${sorted.at(-1)}`;
}

/** "410 kcal · 12 g protein · 6 g fibre", or null when none is known. */
export function perTubWords(per: BatchPreview['per_tub']): string | null {
  const parts = [
    per.kcal !== null ? `${per.kcal} kcal` : null,
    per.protein_g !== null ? `${per.protein_g} g protein` : null,
    per.fibre_g !== null ? `${per.fibre_g} g fibre` : null
  ].filter((p): p is string => p !== null);
  return parts.length ? parts.join(' · ') : null;
}

/** "amounts × 1.5": how much more (or less) than the recipe's own serves the batch makes. The
 * cook-day meal counts as a portion with the tubs (cabledrawer 28 Oct, F58), and the shopping list
 * buys exactly this. */
export function timesWords(tubs: number, serves: number | null): string | null {
  if (!serves) return null;
  const times = Math.round(((tubs + 1) / serves) * 100) / 100;
  return `× ${times}`;
}

/**
 * One sheet of a Batch cook session (B2): the recipe is not in the plan yet, so the server
 * previews it with the recipes before it, and Save hands the choices back (nothing is saved
 * until the last sheet). Cancel stops the whole thing and plans nothing.
 */
export interface Ahead {
  name: string;
  day: string;
  slotId: number;
  /** "1 of 3". */
  position: string;
  /** The last sheet says "Plan this batch"; the others "Next recipe". */
  last: boolean;
  preview: (body: BatchBody) => Promise<BatchPreview>;
  save: (body: BatchBody) => void;
}

export class CookOnceModel {
  count = $state(4);
  pattern = $state<Pattern>('lunch_dinner');
  /** 'all' (the tubs go round everyone), one login's id, or null when there is one login only. */
  who = $state<'all' | number>('all');
  extras = $state(false);
  prepNote = $state('');
  /** The person's own choice of places, once they add, remove or move a tub. */
  placements = $state<(Spot | null)[] | null>(null);
  preview = $state<BatchPreview | null>(null);
  plan = $state<Plan | null>(null);
  problem = $state<string | null>(null);
  /** Extra days shown after the first few, a week at a time. */
  more = $state(0);

  readonly itemId: number;
  readonly cookDate: string;
  people: Person[];
  #asked = 0;
  /** Asks for the preview a different way (a Batch cook session's sheets). */
  readonly #preview: (body: BatchBody) => Promise<BatchPreview>;

  constructor(
    itemId: number,
    cookDate: string,
    people: Person[],
    preview?: (body: BatchBody) => Promise<BatchPreview>
  ) {
    this.itemId = itemId;
    this.cookDate = cookDate;
    this.people = people;
    this.#preview = preview ?? ((body) => previewBatch(itemId, body));
    if (people.length < 2) this.who = 'all';
  }

  get loginIds(): number[] {
    if (this.people.length < 2) return [];
    return this.who === 'all' ? this.people.map((p) => p.login_id) : [this.who];
  }

  body(): BatchBody {
    const body: BatchBody = {
      tub_count: this.count,
      pattern: this.pattern,
      member_login_ids: this.loginIds,
      extras_to_freezer: this.extras
    };
    if (this.prepNote.trim()) body.prep_note = this.prepNote.trim();
    if (this.placements) body.placements = this.placements;
    return body;
  }

  /** Ask the server where the tubs land, with the choices as they are now. */
  async refresh(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const [preview, plan] = await Promise.all([
        this.#preview(this.body()),
        this.plan
          ? Promise.resolve(this.plan)
          : getPlan(this.cookDate, addDays(this.cookDate, MOST_DAYS + 6))
      ]);
      if (asked !== this.#asked) return;
      this.preview = preview;
      this.plan = plan;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      this.problem =
        error instanceof ApiError
          ? error.detail
          : 'Couldn’t work out where the tubs go. Try again.';
    }
  }

  // --- The choices: the pattern picks again, so the person's own places are dropped ----------

  setCount(count: number): void {
    this.count = Math.min(MOST_TUBS, Math.max(1, count));
    this.placements = null;
    void this.refresh();
  }

  setPattern(pattern: Pattern): void {
    this.pattern = pattern;
    this.placements = null;
    void this.refresh();
  }

  setWho(who: 'all' | number): void {
    this.who = who;
    void this.refresh();
  }

  setExtras(extras: boolean): void {
    this.extras = extras;
    void this.refresh();
  }

  // --- The person's own places ---------------------------------------------------------------

  #current(): (Spot | null)[] {
    return (this.preview?.tubs ?? []).map((t) =>
      t.date !== null && t.slot_id !== null ? { date: t.date, slot_id: t.slot_id } : null
    );
  }

  /** The number of the first tub that is in no meal, or null when every tub has one. */
  get nextFree(): number | null {
    const at = this.#current().findIndex((s) => s === null);
    return at < 0 ? null : at + 1;
  }

  /** "+ Add a tub": the next free tub goes in this meal. */
  addTub(spot: Spot): void {
    const free = this.nextFree;
    if (free === null) return;
    this.#set(free, spot);
  }

  removeTub(number: number): void {
    this.#set(number, null);
  }

  moveTub(number: number, spot: Spot): void {
    this.#set(number, spot);
  }

  #set(number: number, spot: Spot | null): void {
    const next = this.#current();
    next[number - 1] = spot;
    this.placements = next;
    void this.refresh();
  }

  // --- Reading ---------------------------------------------------------------------------------

  /** The days the grid shows: from the cook day to a little past the last tub. */
  get days(): string[] {
    const last = Math.max(
      3,
      ...(this.preview?.tubs ?? []).map((t) =>
        t.date ? Math.round((Date.parse(t.date) - Date.parse(this.cookDate)) / 86_400_000) + 1 : 0
      )
    );
    const count = Math.min(MOST_DAYS, last + 1 + this.more);
    return Array.from({ length: count }, (_, i) => addDays(this.cookDate, i));
  }

  get canShowMore(): boolean {
    return this.days.length < MOST_DAYS;
  }

  showMore(): void {
    this.more += 7;
  }

  /** The tubs of the preview that are in a day and meal. */
  tubsAt(day: string, slotId: number) {
    return (this.preview?.tubs ?? []).filter((t) => t.date === day && t.slot_id === slotId);
  }

  /** Tubs in no meal: they wait in the fridge, or go in the freezer. */
  get unplaced() {
    return (this.preview?.tubs ?? []).filter((t) => t.date === null);
  }
}
