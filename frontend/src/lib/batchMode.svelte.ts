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
  type Progress,
  type Schedule,
  type ScheduleTask
} from './client/batchMode';
import { batchModeKey, forgetBatchMode } from './batchModeStore';
import { rows, timesUp, work, type RecipeRow, type Worked } from './batchModeState';

export type Mark = 'done' | 'undo' | 'timer';
interface Pending {
  mark: Mark;
  task: string;
  at: string;
  /** The `made_at` of the schedule it was made on: a mark for an older schedule (another phone
   *  pressed Plan again) is dropped, never put on the new one's steps (RF3, C8). */
  made_at?: string;
}

/** How soon marks that could not be sent are tried again. */
export const RETRY_MS = 3000;

const KEY = batchModeKey;

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
    this.#stopped = false;
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
    this.#stopped = true;
    this.stopRetrying();
    this.#stop?.();
    this.#stop = null;
  }

  #tick(): void {
    this.nowMs = Date.now() + this.#skew;
    // One chime for however many timers ran out since the last look.
    let ended = false;
    for (const t of this.worked ? timesUp(this.worked) : []) {
      if (!this.#over.has(t.id)) {
        this.#over.add(t.id);
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
    if (this.#forgotten) return;
    this.#skew = Date.parse(next.server_time) - Date.now();
    // Marks made on an older schedule are dropped: its task ids now mean other steps.
    this.pending = this.pending.filter((p) => !p.made_at || same(p.made_at, next.made_at));
    this.schedule = this.#withPending(next);
    this.nowMs = Date.now() + this.#skew;
    // Timers already over when the screen opens do not chime.
    for (const t of this.worked ? timesUp(this.worked) : []) this.#over.add(t.id);
    this.#keep();
  }

  /** The server's schedule with the marks still waiting put over it. */
  #withPending(next: Schedule): Schedule {
    let tasks = next.tasks;
    for (const p of this.pending) tasks = tasks.map((t) => apply(t, p));
    return { ...next, tasks };
  }

  /** The schedule this screen holds with a mark's answer put over it (only where it is up to:
   * the words stay as they are). Null: the answer is for another schedule. */
  #merged(reply: Progress | Schedule): Schedule | null {
    const held = this.schedule;
    if (!held || !same(held.made_at, reply.made_at)) return null;
    // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a lookup made and dropped here
    const by = new Map(reply.tasks.map((t) => [t.id, t]));
    return {
      ...held,
      stale: reply.stale,
      minutes_left: reply.minutes_left,
      now_id: reply.now_id,
      next_id: reply.next_id,
      in_use: reply.in_use,
      done_count: reply.done_count,
      server_time: reply.server_time,
      tasks: held.tasks.map((t) => {
        const found = by.get(t.id);
        return found
          ? {
              ...t,
              state: found.state,
              started_at: found.started_at,
              done_at: found.done_at,
              ends_at: found.ends_at
            }
          : t;
      })
    };
  }

  #forgotten = false;

  /** The session ended (cooked): the phone's copy is removed and nothing writes it again, even a
   * reply that is still on its way (RF3 review r1). */
  forget(): void {
    this.#forgotten = true;
    forgetBatchMode(this.id);
  }

  #keep(): void {
    if (this.#forgotten || this.#stopped) return; // the screen is gone or the session ended
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

  /** The marks kept on this phone that haven't been sent (a reload once back online must not
   *  lose them: RF3, C2). */
  #keptPending(): Pending[] {
    try {
      const text = localStorage.getItem(KEY(this.id));
      const found = text ? (JSON.parse(text) as { pending?: Pending[] }) : null;
      return Array.isArray(found?.pending) ? found.pending : [];
    } catch {
      return [];
    }
  }

  /** Open the screen: start the mode (a schedule made already comes back as it is). The marks
   *  kept on the phone are put over it and sent. */
  async load(planAgain = false): Promise<void> {
    this.loading = true;
    try {
      if (planAgain) this.pending = [];
      else if (!this.pending.length) this.pending = this.#keptPending();
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
    if (this.pending.length || this.#sending || this.#stopped || this.#forgotten) return;
    try {
      this.#take(await getSchedule(this.id));
    } catch {
      // The screen keeps what it has.
    }
  }

  mark(mark: Mark, task: string): void {
    if (!this.schedule) return;
    const p: Pending = {
      mark,
      task,
      // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a moment to write down, not state
      at: new Date(Date.now() + this.#skew).toISOString(),
      made_at: this.schedule.made_at
    };
    this.schedule = { ...this.schedule, tasks: this.schedule.tasks.map((t) => apply(t, p)) };
    this.lastDone = mark === 'done' ? task : null;
    this.pending = [...this.pending, p];
    this.#keep();
    void this.flush();
  }

  #retry: ReturnType<typeof setTimeout> | null = null;
  /** The screen was left: nothing is sent or tried again after that (review B3 r1, fix 5). */
  #stopped = false;

  /** Try the waiting marks again shortly: "back online" can be heard before the connection works,
   * and nothing else would ask again. */
  #retryLater(): void {
    if (this.#stopped || this.#retry !== null) return;
    this.#retry = setTimeout(() => {
      this.#retry = null;
      if (!this.#stopped && this.pending.length) void this.flush();
    }, RETRY_MS);
  }

  stopRetrying(): void {
    if (this.#retry !== null) clearTimeout(this.#retry);
    this.#retry = null;
  }

  /** Send the waiting marks, in order, until one can't be sent. */
  async flush(): Promise<void> {
    if (this.#stopped || this.#sending) return;
    this.#sending = true;
    try {
      while (this.pending.length) {
        if (this.#stopped) return; // left while a mark was on its way: send no more
        const p = this.pending[0]!;
        try {
          // The time it was pressed goes with a done or a timer, so a mark made offline counts
          // from then, not from when the phone reconnects (review B3 r1, fix 4).
          const reply =
            p.mark === 'done'
              ? await markTaskDone(this.id, p.task, p.at, p.made_at)
              : p.mark === 'undo'
                ? await undoTaskDone(this.id, p.task, p.made_at)
                : await startTaskTimer(this.id, p.task, p.at, p.made_at);
          this.pending = this.pending.slice(1);
          this.#skew = Date.parse(reply.server_time) - Date.now();
          const next = this.#merged(reply);
          if (next === null) {
            // Not the schedule this screen holds (made again meanwhile): take the whole one.
            this.pending = [];
            this.#take(await getSchedule(this.id));
          } else {
            this.schedule = this.pending.length ? this.#withPending(next) : next;
          }
          this.#keep();
        } catch (error) {
          if (cantReach(error)) {
            this.#retryLater(); // kept on the phone, sent when the connection is back
            return;
          }
          this.pending = this.pending.slice(1); // refused: the server's own state wins
          this.problem = error instanceof ApiError ? error.detail : cantReachWords();
          if (error instanceof ApiError && error.code === 'schedule_replaced') {
            // Made again on another phone: nothing of ours fits the new one. Take it as it is.
            this.pending = [];
            try {
              this.#take(await getSchedule(this.id));
            } catch {
              // The screen keeps what it has; the next look at the server will take it.
            }
          }
          this.#keep();
        }
      }
    } finally {
      this.#sending = false;
    }
  }
}

/** Whether two moments of the server's are the same one. */
function same(a: string, b: string): boolean {
  return Math.abs(Date.parse(a) - Date.parse(b)) <= 1;
}

/** One waiting mark put on a task (on the screen, before the server has it). */
function apply(task: ScheduleTask, p: Pending): ScheduleTask {
  if (task.id !== p.task) return task;
  if (p.mark === 'done') return { ...task, done_at: task.done_at ?? p.at };
  if (p.mark === 'undo') return { ...task, done_at: null, started_at: null };
  return { ...task, started_at: task.started_at ?? p.at };
}
