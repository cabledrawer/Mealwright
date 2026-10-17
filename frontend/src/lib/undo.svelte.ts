// Undo, not "Are you sure?" (UX principle 6). Every change the person makes on this
// device goes on a list; the toast's Undo button, and Ctrl+Z / Cmd+Z on desktop, take
// back the most recent. (The household's shared history, with Undo for 7 days on
// anyone's change, is the Recent changes list, which comes from the server.)

import { worthRetrying, ApiError } from './api';
import { toasts } from './toast.svelte';

export interface UndoEntry {
  /** What happened, in plain words. Shown in the toast: "Toor dal moved to Fridge". */
  label: string;
  /**
   * Take the change back. Return a message to show instead of "Undone" (e.g. "Put back
   * 1 packet. The rest was used."), or false to show nothing.
   */
  undo: () => Promise<string | void | false> | string | void | false;
}

/** How many of your own changes Ctrl+Z can walk back through. */
const KEEP = 50;

export const UNDONE = 'Undone';
export const COULDNT_UNDO = 'Couldn’t undo — try again';

class UndoHistory {
  /** How many changes can be undone (for an "Undo last change" button). */
  size = $state(0);

  #entries: UndoEntry[] = [];

  /**
   * When this device's list is empty (e.g. after a reload), where Ctrl+Z finds your last
   * change instead: the server's list of your own changes.
   */
  fallback: (() => Promise<UndoEntry | null>) | null = null;

  /**
   * Remember a change, and (unless `toast` is false) show it with an Undo button.
   * Returns the toast's id, so its words can be updated.
   */
  record(entry: UndoEntry, options: { toast?: boolean } = {}): number | undefined {
    this.#entries.push(entry);
    if (this.#entries.length > KEEP) this.#entries.shift();
    this.size = this.#entries.length;
    if (options.toast === false) return undefined;
    return toasts.show(entry.label, {
      action: { label: 'Undo', run: () => void this.undo(entry) }
    });
  }

  /** Drop a change from the list (it didn't save, so there's nothing to undo). */
  forget(entry: UndoEntry): void {
    const i = this.#entries.lastIndexOf(entry);
    if (i === -1) return;
    this.#entries.splice(i, 1);
    this.size = this.#entries.length;
  }

  /** Undo the most recent change. False when there's nothing to undo. */
  async undoLast(): Promise<boolean> {
    let entry = this.#entries.at(-1);
    if (!entry && this.fallback) {
      try {
        entry = (await this.fallback()) ?? undefined;
      } catch {
        toasts.show(COULDNT_UNDO, { tone: 'problem' });
        return false;
      }
      if (entry) {
        this.#entries.push(entry);
        this.size = this.#entries.length;
      }
    }
    if (!entry) return false;
    await this.undo(entry);
    return true;
  }

  /** Undo one change. If it fails, it stays on the list and the toast offers Try again. */
  async undo(entry: UndoEntry): Promise<void> {
    if (!this.#entries.includes(entry)) return; // already undone
    this.forget(entry);
    try {
      const message = await entry.undo();
      if (message !== false) toasts.show(message || UNDONE);
    } catch (error) {
      // "Already undone", "Too old to undo": the server's own words; nothing to retry.
      if (!worthRetrying(error)) {
        if (!(error instanceof ApiError && error.status === 401)) {
          toasts.show(error instanceof ApiError ? error.detail : COULDNT_UNDO, { tone: 'problem' });
        }
        return;
      }
      this.#entries.push(entry);
      this.size = this.#entries.length;
      toasts.show(COULDNT_UNDO, {
        tone: 'problem',
        action: { label: 'Try again', run: () => void this.undo(entry) }
      });
    }
  }

  /** Forget everything (on signing out). */
  clear(): void {
    this.#entries = [];
    this.size = 0;
  }
}

export const undoHistory = new UndoHistory();

// Inputs where nobody types, so Ctrl+Z there is ours, not the browser's.
const NOT_TYPED = new Set([
  'button',
  'checkbox',
  'color',
  'file',
  'hidden',
  'image',
  'radio',
  'range',
  'reset',
  'submit'
]);

/** Whether the keyboard focus is somewhere you type, where Ctrl+Z undoes typing. */
export function isTextEntry(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLInputElement) return !NOT_TYPED.has(target.type);
  return false;
}

/** Ctrl+Z (Windows, Linux) or Cmd+Z (Mac). Not with Shift: that's redo. */
export function isUndoKey(event: KeyboardEvent): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === 'z'
  );
}

/**
 * The page's keydown handler: Ctrl+Z / Cmd+Z undoes your own last change, except in
 * a text box, where the browser undoes the typing as normal (spec, History and undo).
 */
export function handleUndoKey(event: KeyboardEvent): void {
  if (event.defaultPrevented || event.repeat || !isUndoKey(event)) return;
  if (isTextEntry(event.target)) return;
  if (undoHistory.size === 0 && !undoHistory.fallback) return;
  event.preventDefault();
  void undoHistory.undoLast();
}
