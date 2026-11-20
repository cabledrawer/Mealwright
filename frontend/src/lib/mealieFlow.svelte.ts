// Import from Mealie's screens (0.9.5, cabledrawer 13 Nov): which step to show, and what each
// button does. One per visit to the screen, shared by the phone's screens and the computer's.
// The import itself runs on the server: while it runs the screen asks how far it has got every
// few seconds, and stops asking when it is left.

import { SvelteSet } from 'svelte/reactivity';

import { ApiError, wordsFor } from './api';
import {
  cancelMealieImport,
  currentMealieImport,
  getMealieImport,
  saveAllMealieDrafts,
  sendMealieFile,
  startMealieImport,
  undoMealieImport,
  type MealieImport,
  type MealieUndone
} from './client/mealie';

import { chosenCount } from './mealieWords';

import { session } from './session.svelte';

export type Step = 'start' | 'preview' | 'running' | 'done';

/** How often the screen asks how far it has got. */
export const POLL_MS = 2000;

const failed = (error: unknown) => wordsFor(error);

/** Which step an import is at. A finished import shows its Done while its Undo works (7 days);
 *  after that, or once it is undone, the screen starts again (proposed, for cabledrawer). */
export function stepOf(job: MealieImport | null, now: number = Date.now()): Step {
  if (!job) return 'start';
  if (job.state === 'ready') return 'preview';
  if (job.state === 'running') return 'running';
  if ((job.state === 'done' || job.state === 'failed') && job.undo_until) {
    return Date.parse(job.undo_until) > now ? 'done' : 'start';
  }
  return 'start';
}

export class MealieFlow {
  job = $state<MealieImport | null>(null);
  loaded = $state(false);
  /** Asked for another file from Done: the start screen, whatever the last import did. */
  again = $state(false);
  /** What went wrong, in words (shown on the step it happened on). */
  problem = $state<string | null>(null);
  /** Sending the file, starting, cancelling or undoing. */
  busy = $state(false);
  sending = $state(false);
  /** The recipes ticked off on the computer's table (Mealie's ids). */
  readonly leaveOut = new SvelteSet<string>();
  photos = $state(true);
  /** What Undo took out, said on the start screen after it. */
  undone = $state<MealieUndone | null>(null);

  #timer: ReturnType<typeof setTimeout> | null = null;
  #stopped = false;

  /** Only the household's admin sends, starts, cancels, undoes or saves all (the server refuses
   *  anyone else); a member sees where the import is, without the buttons. */
  get admin(): boolean {
    return session.me?.role === 'admin';
  }

  get step(): Step {
    return this.again ? 'start' : stepOf(this.job);
  }

  /** The recipes "Bring in" brings in, after the ones ticked off. */
  get chosen(): number {
    return this.job ? chosenCount(this.job.preview, this.leaveOut) : 0;
  }

  async load(): Promise<void> {
    this.problem = null;
    try {
      this.#set((await currentMealieImport()).current);
    } catch (error) {
      this.problem = failed(error);
    }
    this.loaded = true;
  }

  /** Send the chosen file: the answer is what's in it. Nothing is added yet. */
  async send(file: File): Promise<void> {
    if (this.busy) return;
    this.busy = this.sending = true;
    this.problem = null;
    try {
      const job = await sendMealieFile(file);
      this.leaveOut.clear();
      this.photos = true;
      this.undone = null;
      this.again = false;
      this.#set(job);
    } catch (error) {
      this.problem = failed(error);
    } finally {
      this.busy = this.sending = false;
    }
  }

  toggle(key: string, bringIn: boolean): void {
    if (bringIn) this.leaveOut.delete(key);
    else this.leaveOut.add(key);
  }

  /** "Bring in": the server carries on by itself. */
  async start(): Promise<void> {
    const job = this.job;
    if (!job || this.busy) return;
    this.busy = true;
    this.problem = null;
    try {
      this.#set(await startMealieImport(job.id, [...this.leaveOut], this.photos));
    } catch (error) {
      this.problem = failed(error);
      if (error instanceof ApiError && error.status === 409) await this.load();
    } finally {
      this.busy = false;
    }
  }

  /** Cancel on the preview: the file is deleted on the server and nothing was added. */
  async cancel(): Promise<void> {
    const job = this.job;
    if (!job || this.busy) return;
    this.busy = true;
    this.problem = null;
    try {
      await cancelMealieImport(job.id);
      this.#set(null);
    } catch (error) {
      this.problem = failed(error);
      if (error instanceof ApiError && error.status === 409) await this.load();
    } finally {
      this.busy = false;
    }
  }

  async undo(): Promise<void> {
    const job = this.job;
    if (!job || this.busy) return;
    this.busy = true;
    this.problem = null;
    try {
      this.undone = await undoMealieImport(job.id);
      this.#set(null);
    } catch (error) {
      this.problem = failed(error);
    } finally {
      this.busy = false;
    }
  }

  /** "Save all as they are": every draft from Mealie becomes a recipe, its unread lines kept as
   *  plain text (not on the shopping list). */
  async saveAll(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.problem = null;
    try {
      await saveAllMealieDrafts();
      const job = this.job;
      if (job) this.#set(await getMealieImport(job.id));
    } catch (error) {
      this.problem = failed(error);
    } finally {
      this.busy = false;
    }
  }

  /** Done's "Import another file" (proposed, for cabledrawer): back to the start. */
  another(): void {
    this.problem = null;
    this.undone = null;
    this.again = true;
  }

  /** The screen is left: stop asking. */
  stop(): void {
    this.#stopped = true;
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#timer = null;
  }

  #set(job: MealieImport | null): void {
    this.job = job;
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#timer = null;
    if (job?.state === 'running' && !this.#stopped) {
      this.#timer = setTimeout(() => void this.#poll(job.id), POLL_MS);
    }
  }

  async #poll(id: number): Promise<void> {
    this.#timer = null;
    if (this.#stopped) return;
    try {
      this.#set(await getMealieImport(id));
    } catch {
      // A missed answer (a moment offline, a restart): ask again a little later.
      if (!this.#stopped) this.#timer = setTimeout(() => void this.#poll(id), POLL_MS * 3);
    }
  }
}
