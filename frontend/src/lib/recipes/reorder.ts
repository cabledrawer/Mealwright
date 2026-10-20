// Putting ingredient lines and steps in a new order (cabledrawer 19 Oct, editor brief): drag the
// handle with a finger or the mouse, or use the keyboard on the handle (Alt+↑ / Alt+↓, or just
// the arrow keys). Rows are the direct children of one list element marked data-reorder-row.

import { tick } from 'svelte';

/** Move one entry of a list to a new place. */
export function move<T>(list: T[], from: number, to: number): void {
  if (from === to || to < 0 || to >= list.length) return;
  const [item] = list.splice(from, 1);
  list.splice(to, 0, item!);
}

export interface ReorderOptions {
  /** Where this row is now. */
  index: () => number;
  count: () => number;
  /** Move the row (the list is changed by the caller). */
  move: (from: number, to: number) => void;
  /** Said to screen readers after a move: "Moved to 3 of 12". */
  announce?: (message: string) => void;
}

/** Edge of the screen where dragging scrolls the page, in pixels. */
const EDGE = 72;

/** For the handle button of a row. */
export function reorder(handle: HTMLElement, initial: ReorderOptions) {
  let options = initial;
  let dragging = false;
  let busy = false;
  let pointerY = 0;
  let frame = 0;

  const rowOf = () => handle.closest<HTMLElement>('[data-reorder-row]');
  const rowsOf = () =>
    [...(rowOf()?.parentElement?.children ?? [])].filter((el): el is HTMLElement =>
      el.hasAttribute('data-reorder-row')
    );

  async function moveTo(to: number, keepFocus: boolean) {
    const from = options.index();
    if (to === from || to < 0 || to >= options.count()) return;
    options.move(from, to);
    options.announce?.(`Moved to ${to + 1} of ${options.count()}`);
    if (!keepFocus) return;
    await tick();
    rowsOf()[to]?.querySelector<HTMLElement>('[data-reorder-handle]')?.focus();
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    void moveTo(options.index() + (event.key === 'ArrowUp' ? -1 : 1), true);
  }

  /** The row the pointer is over, as a place in the list. */
  function placeUnder(y: number): number {
    const rows = rowsOf();
    const found = rows.findIndex((row) => y < row.getBoundingClientRect().bottom);
    return found === -1 ? rows.length - 1 : found;
  }

  async function follow() {
    if (!dragging || busy) return;
    busy = true;
    const to = placeUnder(pointerY);
    if (to !== options.index()) {
      await moveTo(to, false);
      await tick();
    }
    busy = false;
  }

  function scrollNearEdge() {
    if (!dragging) return;
    if (pointerY < EDGE) window.scrollBy(0, -14);
    else if (pointerY > window.innerHeight - EDGE) window.scrollBy(0, 14);
    void follow();
    frame = requestAnimationFrame(scrollNearEdge);
  }

  function onmove(event: PointerEvent) {
    pointerY = event.clientY;
    void follow();
  }

  function stop() {
    dragging = false;
    cancelAnimationFrame(frame);
    rowOf()?.removeAttribute('data-dragging');
    window.removeEventListener('pointermove', onmove);
    window.removeEventListener('pointerup', stop);
    window.removeEventListener('pointercancel', stop);
    handle.focus({ preventScroll: true });
  }

  function onpointerdown(event: PointerEvent) {
    if (event.button !== 0) return;
    event.preventDefault();
    dragging = true;
    pointerY = event.clientY;
    rowOf()?.setAttribute('data-dragging', '');
    window.addEventListener('pointermove', onmove);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
    frame = requestAnimationFrame(scrollNearEdge);
  }

  handle.addEventListener('keydown', onkeydown);
  handle.addEventListener('pointerdown', onpointerdown);
  return {
    update(next: ReorderOptions) {
      options = next;
    },
    destroy() {
      if (dragging) stop();
      handle.removeEventListener('keydown', onkeydown);
      handle.removeEventListener('pointerdown', onpointerdown);
    }
  };
}
