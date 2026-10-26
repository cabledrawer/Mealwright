import { afterEach, describe, expect, it, vi } from 'vitest';
import { DRAG_AFTER_PX, LONG_PRESS_MS, drag, pressable } from './planDrag.svelte';

let cleanup: (() => void)[] = [];

afterEach(() => {
  for (const undo of cleanup) undo();
  cleanup = [];
  drag.cancel();
  document.body.innerHTML = '';
  vi.useRealTimers();
});

/** A button to press, and a drop place beside it. */
function setup(options: { carry: boolean }) {
  document.body.innerHTML = `
    <button id="card" style="position:fixed;left:0;top:0;width:100px;height:50px">Dosa</button>
    <div id="cell" data-drop-day="2026-10-20" data-drop-slot="4"
      style="position:fixed;left:200px;top:0;width:200px;height:200px">
      <span id="zone" data-drop-zone="leftovers" style="position:absolute;left:0;top:100px;width:200px;height:50px"></span>
    </div>`;
  const card = document.getElementById('card') as HTMLButtonElement;
  const opened = vi.fn();
  const dropped = vi.fn();
  const action = pressable(card, {
    carry: options.carry
      ? () => ({ label: 'Dosa', zones: true, drop: (...args) => dropped(...args) })
      : null,
    open: opened
  });
  cleanup.push(() => action.destroy());
  return { card, opened, dropped };
}

function pointer(
  target: EventTarget,
  type: string,
  x: number,
  y: number,
  kind = 'mouse',
  alt = false
) {
  target.dispatchEvent(
    new PointerEvent(type, {
      pointerId: 1,
      pointerType: kind,
      isPrimary: true,
      clientX: x,
      clientY: y,
      altKey: alt,
      bubbles: true,
      cancelable: true,
      button: 0
    })
  );
}

describe('pressable', () => {
  it('opens the menu on a click', () => {
    const { card, opened } = setup({ carry: true });
    card.click();
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it('carries a card to a place and drops it as a move', () => {
    const { card, opened, dropped } = setup({ carry: true });
    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 10 + DRAG_AFTER_PX + 4, 10);
    expect(drag.active).toBe(true);
    pointer(window, 'pointermove', 250, 20);
    expect(drag.over).toEqual({ day: '2026-10-20', slot: 4, mode: 'move' });
    pointer(window, 'pointerup', 250, 20);
    expect(dropped).toHaveBeenCalledWith('2026-10-20', 4, 'move');
    expect(drag.active).toBe(false);
    card.click(); // the click a browser sends after the drop is not a press
    expect(opened).not.toHaveBeenCalled();
  });

  it('holding Alt makes the drop a copy, and the Leftovers zone plans leftovers', () => {
    const { card, dropped } = setup({ carry: true });
    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 40, 10);
    pointer(window, 'pointermove', 250, 20, 'mouse', true);
    expect(drag.over?.mode).toBe('copy');
    pointer(window, 'pointerup', 250, 20, 'mouse', true);
    expect(dropped).toHaveBeenLastCalledWith('2026-10-20', 4, 'copy');

    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 40, 10);
    pointer(window, 'pointermove', 250, 120);
    expect(drag.over?.mode).toBe('leftovers');
    pointer(window, 'pointerup', 250, 120);
    expect(dropped).toHaveBeenLastCalledWith('2026-10-20', 4, 'leftovers');
  });

  it('drops nothing when let go away from any place, and Escape puts it back', () => {
    const { card, dropped } = setup({ carry: true });
    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 40, 10);
    expect(drag.over).toBeNull();
    pointer(window, 'pointerup', 40, 10);
    expect(dropped).not.toHaveBeenCalled();

    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 250, 20);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(drag.active).toBe(false);
    pointer(window, 'pointerup', 250, 20);
    expect(dropped).not.toHaveBeenCalled();
  });

  it('a finger moved a little is still a press; one that moves a lot carries', () => {
    const { card, dropped } = setup({ carry: true });
    pointer(card, 'pointerdown', 10, 10, 'touch');
    pointer(window, 'pointermove', 12, 11, 'touch');
    expect(drag.active).toBe(false);
    pointer(window, 'pointermove', 250, 20, 'touch');
    expect(drag.active).toBe(true);
    pointer(window, 'pointerup', 250, 20, 'touch');
    expect(dropped).toHaveBeenCalledWith('2026-10-20', 4, 'move');
  });

  it('a held finger opens the menu, once, and the click after it is not a second press', () => {
    vi.useFakeTimers();
    const { card, opened } = setup({ carry: true });
    pointer(card, 'pointerdown', 10, 10, 'touch');
    vi.advanceTimersByTime(LONG_PRESS_MS + 50);
    expect(opened).toHaveBeenCalledTimes(1);
    pointer(window, 'pointerup', 10, 10, 'touch');
    card.click();
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it('a finger that moves off before half a second is not a long press', () => {
    vi.useFakeTimers();
    const { card, opened } = setup({ carry: false });
    pointer(card, 'pointerdown', 10, 10, 'touch');
    pointer(window, 'pointermove', 60, 10, 'touch'); // scrolling, on a phone
    vi.advanceTimersByTime(LONG_PRESS_MS + 50);
    expect(opened).not.toHaveBeenCalled();
    expect(drag.active).toBe(false);
  });

  it('a card that cannot be carried (the phone, offline) is not picked up by a mouse either', () => {
    const { card, dropped } = setup({ carry: false });
    pointer(card, 'pointerdown', 10, 10);
    pointer(window, 'pointermove', 250, 20);
    pointer(window, 'pointerup', 250, 20);
    expect(drag.active).toBe(false);
    expect(dropped).not.toHaveBeenCalled();
  });
});
