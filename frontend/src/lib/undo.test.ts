import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toasts } from './toast.svelte';
import {
  COULDNT_UNDO,
  UNDONE,
  handleUndoKey,
  isTextEntry,
  isUndoKey,
  undoHistory
} from './undo.svelte';

beforeEach(() => {
  undoHistory.clear();
  toasts.dismiss();
});

afterEach(() => {
  document.body.replaceChildren();
});

/** Press a key on an element, the way the browser would. Returns the event. */
function press(target: HTMLElement, init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
  target.addEventListener('keydown', handleUndoKey);
  target.dispatchEvent(event);
  target.removeEventListener('keydown', handleUndoKey);
  return event;
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('undo history', () => {
  it('shows each change with an Undo button', () => {
    undoHistory.record({ label: 'Toor dal moved to Fridge', undo: () => {} });
    expect(toasts.current?.message).toBe('Toor dal moved to Fridge');
    expect(toasts.current?.action?.label).toBe('Undo');
  });

  it("the toast's Undo takes back that change and says so", async () => {
    const undo = vi.fn();
    undoHistory.record({ label: 'Milk used up', undo });
    toasts.act();
    await tick();
    expect(undo).toHaveBeenCalledOnce();
    expect(toasts.current?.message).toBe(UNDONE);
    expect(undoHistory.size).toBe(0);
  });

  it('undoes the most recent change first, one at a time', async () => {
    const done: string[] = [];
    undoHistory.record({ label: 'A', undo: () => void done.push('A') });
    undoHistory.record({ label: 'B', undo: () => void done.push('B') });
    await undoHistory.undoLast();
    expect(done).toEqual(['B']);
    await undoHistory.undoLast();
    expect(done).toEqual(['B', 'A']);
    expect(await undoHistory.undoLast()).toBe(false);
  });

  it('never undoes the same change twice', async () => {
    const undo = vi.fn();
    const entry = { label: 'A', undo };
    undoHistory.record(entry);
    await Promise.all([undoHistory.undo(entry), undoHistory.undo(entry)]);
    expect(undo).toHaveBeenCalledOnce();
  });

  it('shows what Undo could put back when it differs', async () => {
    undoHistory.record({
      label: 'Used 2 packets',
      undo: () => 'Put back 1 packet. The other was used.'
    });
    await undoHistory.undoLast();
    expect(toasts.current?.message).toBe('Put back 1 packet. The other was used.');
  });

  it('keeps a change that failed to undo, and offers Try again', async () => {
    let fail = true;
    const undo = vi.fn(async () => {
      if (fail) throw new Error('offline');
    });
    undoHistory.record({ label: 'A', undo });
    await undoHistory.undoLast();
    expect(toasts.current?.message).toBe(COULDNT_UNDO);
    expect(toasts.current?.tone).toBe('problem');
    expect(undoHistory.size).toBe(1);
    fail = false;
    toasts.act();
    await tick();
    expect(undo).toHaveBeenCalledTimes(2);
    expect(undoHistory.size).toBe(0);
  });

  it('forget() drops a change that never saved', () => {
    const entry = { label: 'A', undo: () => {} };
    undoHistory.record(entry);
    undoHistory.forget(entry);
    expect(undoHistory.size).toBe(0);
  });
});

describe('Ctrl+Z / Cmd+Z', () => {
  it('recognises Ctrl+Z and Cmd+Z, not redo or other keys', () => {
    const key = (init: KeyboardEventInit) => isUndoKey(new KeyboardEvent('keydown', init));
    expect(key({ key: 'z', ctrlKey: true })).toBe(true);
    expect(key({ key: 'z', metaKey: true })).toBe(true);
    expect(key({ key: 'Z', ctrlKey: true })).toBe(true); // Caps Lock
    expect(key({ key: 'z', ctrlKey: true, shiftKey: true })).toBe(false);
    expect(key({ key: 'z', ctrlKey: true, altKey: true })).toBe(false);
    expect(key({ key: 'z' })).toBe(false);
    expect(key({ key: 'y', ctrlKey: true })).toBe(false);
  });

  it('knows where people type', () => {
    const make = (html: string) => {
      document.body.innerHTML = html;
      return document.body.firstElementChild;
    };
    expect(isTextEntry(make('<input>'))).toBe(true);
    expect(isTextEntry(make('<input type="search">'))).toBe(true);
    expect(isTextEntry(make('<input type="number">'))).toBe(true);
    expect(isTextEntry(make('<textarea></textarea>'))).toBe(true);
    expect(isTextEntry(make('<div contenteditable="true"></div>'))).toBe(true);
    expect(isTextEntry(make('<input type="checkbox">'))).toBe(false);
    expect(isTextEntry(make('<button>Used</button>'))).toBe(false);
    expect(isTextEntry(make('<select><option>Fridge</option></select>'))).toBe(false);
    expect(isTextEntry(document.body)).toBe(false);
    expect(isTextEntry(null)).toBe(false);
  });

  it('undoes your last change when focus is not in a text box', async () => {
    const undo = vi.fn();
    undoHistory.record({ label: 'Toor dal moved', undo });
    const event = press(document.body, { key: 'z', ctrlKey: true });
    await tick();
    expect(event.defaultPrevented).toBe(true);
    expect(undo).toHaveBeenCalledOnce();
  });

  it('works with Cmd+Z on a Mac', async () => {
    const undo = vi.fn();
    undoHistory.record({ label: 'Toor dal moved', undo });
    press(document.body, { key: 'z', metaKey: true });
    await tick();
    expect(undo).toHaveBeenCalledOnce();
  });

  it('leaves Ctrl+Z to the browser in a text box, so typing is undone instead', async () => {
    const undo = vi.fn();
    undoHistory.record({ label: 'Toor dal moved', undo });
    for (const html of ['<input>', '<textarea></textarea>', '<div contenteditable="true"></div>']) {
      document.body.innerHTML = html;
      const box = document.body.firstElementChild as HTMLElement;
      box.focus();
      const event = press(box, { key: 'z', ctrlKey: true });
      expect(event.defaultPrevented, html).toBe(false);
    }
    await tick();
    expect(undo).not.toHaveBeenCalled();
    expect(undoHistory.size).toBe(1);
  });

  it('does nothing when there is nothing to undo', () => {
    const event = press(document.body, { key: 'z', ctrlKey: true });
    expect(event.defaultPrevented).toBe(false);
  });

  it('ignores a held-down key repeating', async () => {
    const undo = vi.fn();
    undoHistory.record({ label: 'A', undo });
    undoHistory.record({ label: 'B', undo });
    press(document.body, { key: 'z', ctrlKey: true, repeat: true });
    await tick();
    expect(undo).not.toHaveBeenCalled();
  });
});
