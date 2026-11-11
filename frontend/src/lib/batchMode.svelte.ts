// Batch cook mode's screen state (Experimental; 0.8 wave 6, B3): the session's schedule, kept on
// the server so a reload, another phone or a closed tab carries on where it was, and worked out
// on the screen from what is marked (`batchModeState`) so timers end and tasks move on by
// themselves.
//
// Offline (as Cook mode is mostly local): the schedule already loaded keeps working, with Done,
// next, Undo and the timers; those marks wait on the phone and are sent, in order, when the
// connection is back. The last schedule is kept on this phone, so a reload while offline carries
// on. Starting for the first time and Cooked it need the server.

import { ApiError, cantReach, cantReachWords } from './api';
import {
  getSchedule,
  markTaskDone,
  startSchedule,
  startTaskTimer,
  undoTaskDone,
  type Schedule,
  type ScheduleTask
} from './client/batchMode';
import { rows, work, type RecipeRow, type Worked } from './batchModeState';

export type Mark = 'done' | 'undo' | 'timer';
interface Pending {
  mark: Mark;
  task: string;
  at: string;
}

const KEY = (id: number) => `mealwright.batchmode.${id}`;

export class BatchModeModel {
  schedule = $state<Schedule | null>(null);
  problem = $state<string | null>(null);
  loading = $state(true);
  /** Marks made while the server couldn't be reached. */
  pending = $state<Pending[]>([]);
  /** The clock, moved on every second. */
  nowMs = $state(Date.now());
  /** The task whose "Done, next" was pressed last, so Undo can take it back. */
  lastDone = $state<string | null>(null);

  #skew = 0;
  #stop: (() => void) | null = null;
  #sending = false;
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- plain bookkeeping, never read by the screen
  #over = new Set<string>();
  readonly #sound: () => void;

  constructor(
    readonly id: number,
    sound: () => void = () => void import('./chime').then((m) => m.playChime())
  ) {
    this.#sound = sound;
  }

  readonly worked: Worked | null = $derived(
    this.schedule ? work(this.schedule.tasks, this.nowMs) : null
  );
  readonly rows: RecipeRow[] = $derived(
    this.schedule && this.worked ? rows(this.schedule.recipes, this.worked, this.nowMs) : []
  );
  readonly finished = $derived(
    this.worked !== null &&
      this.worked.tasks.length > 0 &&
      this.worked.doneCount === this.worked.tasks.length
  );

  /** Start the clock (a screen that comes back to the front looks at it at once). */
  start(): void {
    this.#tick();
    const id = setInterval(() => this.#tick(), 1000);
    const visible = () => {
      if (document.visibilityState === 'visible') this.#tick();
    };
    document.addEventListener('visibilitychange', visible);
    this.#stop = () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', visible);
    };
  }

  stop(): void {
    this.#stop?.();
    this.#stop = null;
  }

  #tick(): void {
    this.nowMs = Date.now() + this.#skew;
    // One chime for however many timers ran out since the last look.
    let ended = false;
    for (const row of this.rows) {
      if (row.kind === 'over' && row.task && !this.#over.has(row.task.id)) {
        this.#over.add(row.task.id);
        ended = true;
      }
    }
    if (ended && this.#primed) this.#sound();
  }

  #primed = false;
  /** From a tap: the only moment a browser lets a page make sound later. */
  prime(): void {
    if (this.#primed) return;
    this.#primed = true;
    void import('./chime').then((m) => m.primeChime());
  }

  #take(next: Schedule): void {
    this.#skew = Date.parse(next.server_time) - Date.now();
    this.schedule = this.#withPending(next);
    this.nowMs = Date.now() + this.#skew;
    // Timers already over when the screen opens do not chime.
    for (const row of this.rows) if (row.kind === 'over' && row.task) this.#over.add(row.task.id);
    this.#keep();
  }

  /** The server's schedule with the marks still waiting put over it. */
  #withPending(next: Schedule): Schedule {
    let tasks = next.tasks;
    for (const p of this.pending) tasks = tasks.map((t) => apply(t, p));
    return { ...next, tasks };
  }

  #keep(): void {
    try {
      localStorage.setItem(
        KEY(this.id),
        JSON.stringify({ schedule: this.schedule, pending: this.pending })
      );
    } catch {
      // Storage blocked: the screen works without it.
    }
  }

  #remembered(): boolean {
    try {
      const text = localStorage.getItem(KEY(this.id));
      if (!text) return false;
      const found = JSON.parse(text) as { schedule?: Schedule; pending?: Pending[] };
      if (!found.schedule) return false;
      this.pending = found.pending ?? [];
      this.schedule = found.schedule;
      this.#skew = 0;
      return true;
    } catch {
      return false;
    }
  }

  /** Open the screen: start the mode (a schedule made already comes back as it is). */
  async load(planAgain = false): Promise<void> {
    this.loading = true;
    try {
      if (planAgain) this.pending = [];
      this.#take(await startSchedule(this.id, planAgain));
      this.problem = null;
      void this.flush();
    } catch (error) {
      if (cantReach(error) && this.#remembered()) this.problem = null;
      else this.problem = error instanceof ApiError ? error.detail : cantReachWords();
    } finally {
      this.loading = false;
    }
  }

  /** Ask again (another phone marked something). Not while marks of this phone are waiting. */
  async refresh(): Promise<void> {
    if (this.pending.length || this.#sending) return;
    try {
      this.#take(await getSchedule(this.id));
    } catch {
      // The screen keeps what it has.
    }
  }

  mark(mark: Mark, task: string): void {
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a moment to write down, not state
    const p: Pending = { mark, task, at: new Date(this.nowMs).toISOString() };
    if (!this.schedule) return;
    this.schedule = { ...this.schedule, tasks: this.schedule.tasks.map((t) => apply(t, p)) };
    this.lastDone = mark === 'done' ? task : null;
    this.pending = [...this.pending, p];
    this.#keep();
    void this.flush();
  }

  /** Send the waiting marks, in order, until one can't be sent. */
  async flush(): Promise<void> {
    if (this.#sending) return;
    this.#sending = true;
    try {
      while (this.pending.length) {
        const p = this.pending[0]!;
        try {
          const call =
            p.mark === 'done' ? markTaskDone : p.mark === 'undo' ? undoTaskDone : startTaskTimer;
          const reply = await call(this.id, p.task);
          this.pending = this.pending.slice(1);
          this.#skew = Date.parse(reply.server_time) - Date.now();
          if (!this.pending.length) this.schedule = reply;
          else this.schedule = this.#withPending(reply);
          this.#keep();
        } catch (error) {
          if (cantReach(error)) return; // kept on the phone, sent when the connection is back
          this.pending = this.pending.slice(1); // refused: the server's own state wins
          this.problem = error instanceof ApiError ? error.detail : cantReachWords();
          this.#keep();
        }
      }
    } finally {
      this.#sending = false;
    }
  }
}

/** One waiting mark put on a task (on the screen, before the server has it). */
function apply(task: ScheduleTask, p: Pending): ScheduleTask {
  if (task.id !== p.task) return task;
  if (p.mark === 'done') return { ...task, done_at: task.done_at ?? p.at };
  if (p.mark === 'undo') return { ...task, done_at: null, started_at: null };
  return { ...task, started_at: task.started_at ?? p.at };
}
