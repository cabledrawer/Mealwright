<script lang="ts" module>
  import type { Name } from './Icon.svelte';

  /** A button a swipe shows. Every action must also be a visible button somewhere in the row. */
  export interface SwipeAction {
    /** The button's words: "Used…", "Binned", "Remove", "Move…". */
    label: string;
    /** Said by screen readers after the label, hidden on screen: "Spinach", "Yoghurt from the list". */
    describe?: string;
    icon: Name;
    /** Its colour: green, blue or red. */
    tone: 'used' | 'move' | 'danger';
    run: () => void;
  }
</script>

<script lang="ts">
  // One row you can swipe on a phone (cabledrawer 21 Oct, spec "Phone swipes"): swipe RIGHT shows the
  // `right` button on the row's left edge, swipe LEFT shows the `left` button on its right edge
  // (mockups PantrySwipe-Phone, ShopMove-Phone). A swipe alone never does anything: it shows
  // the button, and the button does the thing. The next tap anywhere on a swiped row closes it.
  //
  // Touch and pen only. On a computer the row is not swipeable (`enabled` is false) and the same
  // choices are buttons and menus in the row itself; the same holds for keyboards and screen
  // readers on a phone, so whoever uses this puts each action somewhere in the row as a button
  // too (Pantry: the pack menu and the Use soon pills; Shopping: the amount box). Under
  // "reduce motion" nothing slides on its own: the row only moves under the finger.
  import { untrack, type Snippet } from 'svelte';
  import { restOffset, swipeToReveal, type Side } from '#lib/swipe.js';
  import Icon from './Icon.svelte';

  const WIDTH = 104;

  let {
    right,
    left,
    enabled = true,
    bleed = 0,
    open = $bindable(null),
    children
  }: {
    /** Shown by swiping right. */
    right?: SwipeAction;
    /** Shown by swiping left. */
    left?: SwipeAction;
    enabled?: boolean;
    /** Pixels the row's own padding is given back to the card around it (the card's padding). */
    bleed?: number;
    /** Which button is showing: 'right' = the row is slid right, to show the `right` button. */
    open?: Side;
    children: Snippet;
  } = $props();

  // Side names: 'left' means the row is slid LEFT (the `left` action's button shows).
  const toLeft = $derived(left ? WIDTH : 0);
  const toRight = $derived(right ? WIDTH : 0);
  let drag = $state<number | null>(null);
  const live = $derived(enabled && (toLeft > 0 || toRight > 0));
  const offset = $derived(drag ?? restOffset(open, toLeft, toRight));

  // Gone from a phone layout (turned to landscape, window made wider): nothing stays open.
  $effect(() => {
    if (!live) {
      untrack(() => (open = null));
      drag = null;
    }
  });

  function press(action: SwipeAction) {
    open = null;
    action.run();
  }
</script>

<div class="swipe" style:margin={bleed ? `0 -${bleed}px` : undefined}>
  {#if live && offset > 0 && right}
    <button type="button" class="act on-left" data-tone={right.tone} onclick={() => press(right)}>
      <Icon name={right.icon} size={20} stroke={2.3} />{right.label}{#if right.describe}<span
          class="visually-hidden"
        >
          {right.describe}</span
        >{/if}
    </button>
  {/if}
  {#if live && offset < 0 && left}
    <button type="button" class="act on-right" data-tone={left.tone} onclick={() => press(left)}>
      <Icon name={left.icon} size={20} stroke={2.3} />{left.label}{#if left.describe}<span
          class="visually-hidden"
        >
          {left.describe}</span
        >{/if}
    </button>
  {/if}
  <div
    class="slide"
    class:dragging={drag !== null}
    style:transform={offset ? `translateX(${offset}px)` : undefined}
    style:padding={bleed ? `0 ${bleed}px` : undefined}
    use:swipeToReveal={{
      toLeft,
      toRight,
      open,
      enabled: live,
      ondrag: (value) => (drag = value),
      onsettle: (side) => (open = side)
    }}
    onclickcapture={(event) => {
      // A swiped row closes on the next tap, whatever it lands on.
      if (!open) return;
      event.stopPropagation();
      event.preventDefault();
      open = null;
    }}
  >
    {@render children()}
  </div>
</div>

<style>
  .swipe {
    position: relative;
    overflow: hidden;
  }

  .slide {
    position: relative;
    background: var(--color-surface);
    /* Sideways belongs to the swipe; up and down still scroll the page. */
    touch-action: pan-y;
    transition: transform 0.18s ease;
  }

  .slide.dragging {
    transition: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .slide {
      transition: none;
    }
  }

  .act {
    position: absolute;
    top: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    width: 104px;
    padding: 0;
    border: none;
    background: var(--color-danger);
    color: var(--color-danger-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .on-left {
    left: 0;
  }

  .on-right {
    right: 0;
  }

  .act[data-tone='used'] {
    background: var(--color-swipe-used);
    color: var(--color-swipe-text);
  }

  .act[data-tone='move'] {
    background: var(--color-swipe-move);
    color: var(--color-swipe-text);
  }

  .visually-hidden {
    position: absolute;
    left: -9999px;
  }
</style>
