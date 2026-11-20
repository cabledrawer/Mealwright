<script lang="ts" generics="T extends string | number | boolean">
  // One-of-N choice shown as a row of segments (a radiogroup with arrow keys). Use it for two to
  // four short answers that sit in a form or a settings row; use FilterChips to filter a list.
  //   tray: a soft tray with a lifted active segment (Theme in the sidebar, Oven)
  //   pill: the same, fully round (Theme in Settings)
  import type { Snippet } from 'svelte';
  import { radioKeys } from '#lib/radioKeys.js';

  interface Option {
    value: T;
    label: string;
    title?: string;
  }

  let {
    options,
    value,
    onchange,
    label,
    labelledby,
    variant = 'tray',
    disabled = false,
    segment
  }: {
    options: readonly Option[];
    value: T;
    onchange: (value: T) => void;
    /** A name for the group, read out by screen readers. */
    label?: string;
    /** Or the id of the element that names it. */
    labelledby?: string;
    variant?: 'tray' | 'pill';
    /** Nothing can be chosen (while the page is loading). */
    disabled?: boolean;
    /** Content of one segment, when the label alone is not enough (an icon before it). */
    segment?: Snippet<[Option]>;
  } = $props();
</script>

<div
  class="mw-segmented {variant}"
  role="radiogroup"
  aria-label={label}
  aria-labelledby={labelledby}
  style:--segments={options.length}
  use:radioKeys
>
  {#each options as option (String(option.value))}
    <button
      type="button"
      role="radio"
      aria-checked={value === option.value}
      title={option.title}
      {disabled}
      onclick={() => onchange(option.value)}
    >
      {#if segment}{@render segment(option)}{:else}{option.label}{/if}
    </button>
  {/each}
</div>

<style>
  .mw-segmented {
    display: grid;
    grid-template-columns: repeat(var(--segments), minmax(0, 1fr));
    gap: var(--space-1);
    padding: 3px;
    background: var(--color-fill);
    border-radius: var(--radius-md);
  }

  .pill {
    display: inline-grid;
    gap: 0;
    background: var(--color-fill-strong);
    border-radius: var(--radius-full);
  }

  button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-height: 34px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-semibold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }

  .pill button {
    min-height: 32px;
    padding: 0 var(--space-6);
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  button[aria-checked='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  :global([data-theme='dark']) .pill button[aria-checked='true'] {
    background: var(--color-surface);
  }

  /* Bigger targets for fingers (touch screens, tablets). */
  @media (pointer: coarse) {
    button,
    .pill button {
      min-height: var(--touch-target);
    }
  }
</style>
