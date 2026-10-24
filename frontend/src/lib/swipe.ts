// Swipe a row sideways to show a button behind it (Shopping's red Remove, cabledrawer 20 Oct;
// Pantry's Used… and Binned and Shopping's Move…, cabledrawer 21 Oct). Touch and pen only; a mouse
// has its own buttons, and keyboards and screen readers use the same choices elsewhere in the
// row (see SwipeRow.svelte). A swipe alone never does anything: it only shows the button.
//
//   <div use:swipeToReveal={{ toLeft, toRight, open, enabled, ondrag, onsettle }}>
//
// `toLeft` is how far the row may slide left (to show a button on its right edge), `toRight`
// how far it may slide right (a button on its left edge); 0 turns that side off. `ondrag` gets
// the row's offset in pixels (negative = left) while a finger is moving it, and null when it
// lets go; `onsettle` says which button should now stay shown ('left' = the row is slid left).
// The row itself does the drawing from those two, so nothing moves under reduced motion unless
// the finger moves it.

export type Side = 'left' | 'right' | null;

export interface SwipeOptions {
  /** How far the row slides left, in pixels (0: no swipe left). */
  toLeft: number;
  /** How far the row slides right, in pixels (0: no swipe right). */
  toRight: number;
  /** Which button is showing now? */
  open: Side;
  /** Off on a computer layout. */
  enabled: boolean;
  ondrag: (offset: number | null) => void;
  onsettle: (open: Side) => void;
}

/** A move this far sideways (and more sideways than up or down) starts a swipe. */
const START_PX = 10;

/** Where the row rests for a side. */
export function restOffset(open: Side, toLeft: number, toRight: number): number {
  return open === 'left' ? -toLeft : open === 'right' ? toRight : 0;
}

export function swipeToReveal(node: HTMLElement, options: SwipeOptions) {
  let current = options;
  let tracking = false;
  let swiping = false;
  let startX = 0;
  let startY = 0;
  let from = 0;
  let offset = 0;
  let pointer = -1;
  let swallowClick = false;

  const clamp = (value: number) => Math.min(current.toRight, Math.max(-current.toLeft, value));

  function down(event: PointerEvent) {
    if (!current.enabled || event.pointerType === 'mouse' || !event.isPrimary) return;
    tracking = true;
    swiping = false;
    startX = event.clientX;
    startY = event.clientY;
    from = restOffset(current.open, current.toLeft, current.toRight);
    offset = from;
    pointer = event.pointerId;
  }

  function move(event: PointerEvent) {
    if (!tracking || event.pointerId !== pointer) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!swiping) {
      if (Math.abs(dy) > START_PX && Math.abs(dy) > Math.abs(dx)) {
        tracking = false; // the page is being scrolled
        return;
      }
      if (Math.abs(dx) < START_PX || Math.abs(dx) < Math.abs(dy)) return;
      swiping = true;
      try {
        node.setPointerCapture(event.pointerId);
      } catch {
        // The pointer has gone already: the end below tidies up.
      }
    }
    offset = clamp(from + dx);
    current.ondrag(offset);
  }

  function end(event: PointerEvent) {
    if (!tracking || event.pointerId !== pointer) return;
    tracking = false;
    if (!swiping) return;
    swiping = false;
    // A finger lifted after sliding must not also press whatever it ended on.
    swallowClick = true;
    setTimeout(() => (swallowClick = false), 400);
    current.ondrag(null);
    if (current.toLeft && offset < -current.toLeft / 2) current.onsettle('left');
    else if (current.toRight && offset > current.toRight / 2) current.onsettle('right');
    else current.onsettle(null);
  }

  function click(event: MouseEvent) {
    if (!swallowClick) return;
    swallowClick = false;
    event.stopPropagation();
    event.preventDefault();
  }

  node.addEventListener('pointerdown', down);
  node.addEventListener('pointermove', move);
  node.addEventListener('pointerup', end);
  node.addEventListener('pointercancel', end);
  node.addEventListener('click', click, true);

  return {
    update(next: SwipeOptions) {
      current = next;
    },
    destroy() {
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', end);
      node.removeEventListener('pointercancel', end);
      node.removeEventListener('click', click, true);
    }
  };
}
