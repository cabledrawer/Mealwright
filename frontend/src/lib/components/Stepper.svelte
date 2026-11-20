<script lang="ts">
  // The one "− 3 +" control (FE14, FE18): a labelled group of a "Fewer X" button, the number (or
  // any box that shows it) and a "More X" button, so a screen reader hears what is changing:
  //   <Stepper what="portions" onless={…} onmore={…} lessOff={n <= 1}>{n}</Stepper>
  // The buttons are always named "Fewer <what>" and "More <what>" ("Less <what>" with
  // `less="Less"` for something you can't count, like an amount). Buttons are 44 px.
  // The − and + are plain text glyphs. The look is proposed, for cabledrawer: one shape everywhere.
  import type { Snippet } from 'svelte';

  let {
    what,
    label,
    less = 'Fewer',
    onless,
    onmore,
    lessOff = false,
    moreOff = false,
    children
  }: {
    /** What is counted, lower case: "servings", "portions", "tubs", "hob rings". */
    what: string;
    /** The group's name when it should differ from `what` ("Portions cooked"). */
    label?: string;
    /** "Less" for something that is not counted. */
    less?: 'Fewer' | 'Less';
    onless: () => void;
    onmore: () => void;
    lessOff?: boolean;
    moreOff?: boolean;
    /** The number, or the box that holds it. */
    children: Snippet;
  } = $props();
</script>

<span class="stepper" role="group" aria-label={label ?? what}>
  <button type="button" aria-label="{less} {what}" disabled={lessOff} onclick={onless}>−</button>
  <span class="now" aria-live="polite">{@render children()}</span>
  <button type="button" aria-label="More {what}" disabled={moreOff} onclick={onmore}>+</button>
</span>

<style>
  .stepper {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--reading-chip, var(--color-fill));
  }

  button {
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 1.125rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button:disabled {
    cursor: default;
    opacity: 0.4;
  }

  .now {
    min-width: 2.5em;
    padding: 0 var(--space-3);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: center;
  }

  /* On paper only the words stay. */
  @media print {
    button {
      display: none;
    }
  }
</style>
