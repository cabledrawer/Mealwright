// The one toast (UX principle 6): a short, calm message at the bottom of the screen,
// usually with an Undo button. One at a time: a new one replaces the last. It goes
// away by itself after a few seconds, and waits while the pointer or keyboard focus
// is on it, so there's time to reach the button.

export interface ToastAction {
  /** The button's words: "Undo", "Try again". */
  label: string;
  run: () => void;
}

export interface Toast {
  id: number;
  message: string;
  action?: ToastAction;
  /** A second button before the main one ("Change", beside "Undo"). */
  extra?: ToastAction;
  /** "problem" for something that didn't work (still calm, never alarming). */
  tone: 'calm' | 'problem';
}

/** How long a toast stays, in milliseconds. */
export const TOAST_MS = 6000;
/** After a pause, at least this long is left, so it doesn't vanish the moment you look away. */
const MIN_AFTER_PAUSE_MS = 2000;

class Toaster {
  current = $state<Toast | null>(null);

  #nextId = 1;
  #timer: ReturnType<typeof setTimeout> | null = null;
  #remaining = 0;
  #startedAt = 0;
  #paused = false;

  /** Show a message. Returns its id, for dismiss(). */
  show(
    message: string,
    options: {
      action?: ToastAction;
      extra?: ToastAction;
      tone?: Toast['tone'];
      duration?: number;
    } = {}
  ): number {
    const id = this.#nextId++;
    this.current = {
      id,
      message,
      action: options.action,
      extra: options.extra,
      tone: options.tone ?? 'calm'
    };
    this.#paused = false;
    this.#start(options.duration ?? TOAST_MS);
    return id;
  }

  /** Change the words of a toast that's still showing (e.g. to the server's own summary). */
  update(id: number, message: string): void {
    if (this.current?.id === id) this.current = { ...this.current, message };
  }

  /** Close the toast (only if it's still the one with this id, when given). */
  dismiss(id?: number): void {
    if (id !== undefined && this.current?.id !== id) return;
    this.#stop();
    this.#paused = false;
    this.current = null;
  }

  /** The person pressed the toast's button. */
  act(): void {
    const action = this.current?.action;
    this.dismiss();
    action?.run();
  }

  /** The person pressed the toast's extra button. */
  actExtra(): void {
    const extra = this.current?.extra;
    this.dismiss();
    extra?.run();
  }

  /** Hold the toast while someone is looking at or about to use it. */
  pause(): void {
    if (!this.current || this.#paused) return;
    this.#paused = true;
    if (this.#timer) {
      this.#remaining -= Date.now() - this.#startedAt;
      this.#stop();
    }
  }

  resume(): void {
    if (!this.current || !this.#paused) return;
    this.#paused = false;
    this.#start(Math.max(this.#remaining, MIN_AFTER_PAUSE_MS));
  }

  #start(ms: number): void {
    this.#stop();
    this.#remaining = ms;
    this.#startedAt = Date.now();
    const id = this.current?.id;
    this.#timer = setTimeout(() => this.dismiss(id), ms);
  }

  #stop(): void {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = null;
  }
}

export const toasts = new Toaster();
