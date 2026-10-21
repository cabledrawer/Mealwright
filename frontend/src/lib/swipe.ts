// Swipe a row to the left to show a button behind it (Shopping: a red "Remove", cabledrawer
// 20 Oct). Touch and pen only; a mouse has its own button, and keyboards and screen readers
// use the amount box. A swipe alone never does anything: it only shows the button, and
// tapping that asks first.
//
//   <div use:swipeToReveal={{ width: 104, open, enabled, ondrag, onsettle }}>
//
// `ondrag` gets the row's offset in pixels (0 to -width) while a finger is moving it, and
// null when it lets go; `onsettle` says whether the button should now stay shown. The row
// itself does the drawing from those two, so nothing moves under reduced motion unless
// the finger moves it.

export interface SwipeOptions {
  /** How far the row slides to show the button, in pixels. */
  width: number;
  /** Is the button showing now? */
  open: boolean;
  /** Off on a computer layout. */
  enabled: boolean;
  ondrag: (offset: number | null) => void;
  onsettle: (open: boolean) => void;
}

/** A move this far sideways (and more sideways than up or down) starts a swipe. */
const START_PX = 10;

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

  const clamp = (value: number) => Math.min(0, Math.max(-current.width, value));

  function down(event: PointerEvent) {
    if (!current.enabled || event.pointerType === 'mouse' || !event.isPrimary) return;
    tracking = true;
    swiping = false;
    startX = event.clientX;
    startY = event.clientY;
    from = current.open ? -current.width : 0;
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
    current.onsettle(offset < -current.width / 2);
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
