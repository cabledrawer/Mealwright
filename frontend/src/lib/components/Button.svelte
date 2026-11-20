<script lang="ts">
  // The one button (FE16). `main` (the default) is the action the page is for: big, dark on light
  // (light on dark). `quiet` is the other choice beside it, on a soft fill (the onboarding
  // mockup's Back). `danger` is for taking something away. `small` is the same button at the
  // 44 px touch size and the width of its words, for a row or a card. Anything else a button
  // may carry (autofocus, data-testid, aria-*, form, name) is passed straight on.
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  let {
    type = 'button',
    quiet = false,
    danger = false,
    small = false,
    disabled = false,
    onclick,
    children,
    ...rest
  }: Omit<HTMLButtonAttributes, 'children' | 'class' | 'style'> & {
    type?: 'button' | 'submit';
    quiet?: boolean;
    danger?: boolean;
    small?: boolean;
    disabled?: boolean;
    children: Snippet;
  } = $props();
</script>

<button class="mw-button" class:quiet class:danger class:small {type} {disabled} {onclick} {...rest}
  >{@render children()}</button
>

<style>
  .mw-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: 54px;
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .danger {
    background: var(--color-danger);
    color: var(--color-danger-text);
  }

  .small {
    width: auto;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
  }

  .mw-button:disabled {
    cursor: progress;
    opacity: 0.7;
  }
</style>
