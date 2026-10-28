// Dragging on the Plan, with plain pointer events (no library): a mouse, a finger or a pen.
//   - Press and move a little: the thing is picked up and follows the pointer.
//   - Over a day's meal (Week) or a day (Month) it is highlighted; a meal being moved shows
//     three drop zones: Move, Copy (or hold Alt) and Leftovers here.
//   - Let go: it is dropped. Escape puts it back.
//   - A finger held still for half a second is a long press: the same menu as a click.
// Whatever can be dragged can also be moved with the keyboard: the click / Enter menu
// (PlanSheet) does everything a drag does.

import type { DropMode } from './client/plan';

/** What is being carried, and what happens when it is let go. */
export interface Carried {
  label: string;
  /** A meal or one thing in it can be dropped as a move, a copy or leftovers; a recipe from
   * the tray can only be planned. */
  zones: boolean;
  /** Whether "Leftovers here" is offered over this day and meal (not before the cook meal, not
   * in the past; F50). `slot` is null in the Month view. Left out: always. */
  leftoversOk?: (day: string, slot: number | null) => boolean;
  /** `slot` is null in the Month view, where a drop lands on a whole day. */
  drop: (day: string, slot: number | null, mode: DropMode) => void;
}

/** Where the pointer is, if it is over a place that takes a drop. */
export interface Over {
  day: string;
  slot: number | null;
  mode: DropMode;
}

/** How far the pointer moves before a press becomes a drag. */
export const DRAG_AFTER_PX = 6;
/** How long a finger is held still before it is a long press. */
export const LONG_PRESS_MS = 500;

class Drag {
  carried = $state<Carried | null>(null);
  x = $state(0);
  y = $state(0);
  over = $state<Over | null>(null);
  /** Alt is held: a drop is a copy. */
  alt = $state(false);

  get active(): boolean {
    return this.carried !== null;
  }

  /** Whether this day (and meal) is what the pointer is over. */
  isOver(day: string, slot: number | null): boolean {
    return this.over !== null && this.over.day === day && this.over.slot === slot;
  }

  /** Read the drop place under the pointer. */
  look(x: number, y: number, alt: boolean): void {
    this.x = x;
    this.y = y;
    this.alt = alt;
    let day: string | null = null;
    let slot: number | null = null;
    let zone: DropMode | null = null;
    for (const el of document.elementsFromPoint(x, y)) {
      if (!(el instanceof HTMLElement)) continue;
      const z = el.dataset.dropZone as DropMode | undefined;
      if (z && zone === null) zone = z;
      if (el.dataset.dropDay) {
        day = el.dataset.dropDay;
        slot = el.dataset.dropSlot ? Number(el.dataset.dropSlot) : null;
        break;
      }
    }
    if (!day) {
      this.over = null;
      return;
    }
    // The Move zone is the plain drop (so Alt still copies there); Copy and Leftovers are explicit.
    const plain: DropMode = alt && this.carried?.zones ? 'copy' : 'move';
    const mode: DropMode = zone && zone !== 'move' ? zone : plain;
    this.over = { day, slot, mode };
  }

  begin(carried: Carried, x: number, y: number, alt: boolean): void {
    this.carried = carried;
    this.look(x, y, alt);
  }

  /** Let go: drop it where it is, if it is anywhere. */
  finish(): void {
    const { carried, over } = this;
    this.cancel();
    if (carried && over) carried.drop(over.day, over.slot, over.mode);
  }

  cancel(): void {
    this.carried = null;
    this.over = null;
    this.alt = false;
  }
}

export const drag = new Drag();

export interface PressOptions {
  /** What to carry, or null when this thing can't be dragged (the phone, offline). */
  carry: (() => Carried) | null;
  /** The menu: a click, Enter, or a long press. */
  open: () => void;
}

/**
 * Make an element draggable and openable. Use it on a <button>: a click or Enter calls
 * `open`.
 *   - A mouse picks it up by moving a little.
 *   - A finger never drags at once, so a swipe scrolls the page (or the tray) as usual. Held
 *     still for half a second it is picked up, if it can be carried (a computer or iPad), and
 *     then follows the finger; let go without moving and the menu opens instead. A thing that
 *     can't be carried (the phone) opens its menu after the half second.
 */
export function pressable(node: HTMLElement, options: PressOptions) {
  let current = options;
  let down: { id: number; x: number; y: number; touch: boolean } | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let dragging = false;
  let travelled = false;
  let swallowClick = false;

  const stopTimer = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };

  function onMove(event: PointerEvent) {
    if (!down || event.pointerId !== down.id) return;
    const far = Math.hypot(event.clientX - down.x, event.clientY - down.y) > DRAG_AFTER_PX;
    if (dragging) {
      if (far) travelled = true;
      drag.look(event.clientX, event.clientY, event.altKey);
      return;
    }
    if (!far) return;
    stopTimer();
    if (down.touch || !current.carry) {
      // A finger that moves before the long press is scrolling: leave it to the browser.
      end();
      return;
    }
    travelled = true;
    dragging = true;
    drag.begin(current.carry(), event.clientX, event.clientY, event.altKey);
  }

  function onUp(event: PointerEvent) {
    if (!down || event.pointerId !== down.id) return;
    const was = dragging;
    const still = was && down.touch && !travelled;
    if (still) drag.cancel();
    else if (was) drag.finish();
    end();
    // A drop is not a click.
    swallowClick = was || swallowClick;
    if (was) setTimeout(() => (swallowClick = false), 0);
    // Picked up with a finger and let go in the same place: that was a long press, so the menu.
    if (still) current.open();
  }

  function onCancel(event: PointerEvent) {
    if (!down || event.pointerId !== down.id) return;
    // The browser took the touch to scroll.
    drag.cancel();
    end();
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Escape' && dragging) {
      drag.cancel();
      end();
    }
    if (dragging && event.key === 'Alt') drag.alt = event.type === 'keydown';
  }

  // While a finger is carrying something the page must not scroll under it. The listener is
  // added with the touch (not when the drag starts), because a browser only honours
  // preventDefault from a listener that was there before the scrolling decision.
  function onTouchMove(event: TouchEvent) {
    if (dragging && event.cancelable) event.preventDefault();
  }

  function end() {
    stopTimer();
    dragging = false;
    travelled = false;
    down = null;
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onCancel);
    window.removeEventListener('keydown', onKey);
    window.removeEventListener('keyup', onKey);
    window.removeEventListener('touchmove', onTouchMove);
  }

  function onDown(event: PointerEvent) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    if (down) return;
    const touch = event.pointerType !== 'mouse';
    down = { id: event.pointerId, x: event.clientX, y: event.clientY, touch };
    swallowClick = false;
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onKey);
    if (touch) {
      window.addEventListener('touchmove', onTouchMove, { passive: false });
      timer = setTimeout(() => {
        timer = null;
        swallowClick = true;
        if (current.carry && down) {
          dragging = true;
          travelled = false;
          drag.begin(current.carry(), down.x, down.y, false);
        } else {
          end();
          current.open();
        }
      }, LONG_PRESS_MS);
    }
  }

  function onClick(event: MouseEvent) {
    if (swallowClick) {
      swallowClick = false;
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    current.open();
  }

  // The phone's long press would otherwise open the browser's own menu.
  const onMenu = (event: Event) => event.preventDefault();

  node.addEventListener('pointerdown', onDown);
  node.addEventListener('click', onClick);
  node.addEventListener('contextmenu', onMenu);
  return {
    update(next: PressOptions) {
      current = next;
    },
    destroy() {
      node.removeEventListener('pointerdown', onDown);
      node.removeEventListener('click', onClick);
      node.removeEventListener('contextmenu', onMenu);
      end();
    }
  };
}
