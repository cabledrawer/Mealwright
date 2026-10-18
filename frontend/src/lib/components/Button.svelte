<script lang="ts">
  // The main action on a page: big, dark on light (light on dark). `quiet` is the same
  // button for the other choice beside it, on a soft fill (the onboarding mockup's Back).
  import type { Snippet } from 'svelte';

  let {
    type = 'button',
    quiet = false,
    disabled = false,
    onclick,
    children
  }: {
    type?: 'button' | 'submit';
    quiet?: boolean;
    disabled?: boolean;
    onclick?: () => void;
    children: Snippet;
  } = $props();
</script>

<button class="primary" class:quiet {type} {disabled} {onclick}>{@render children()}</button>

<style>
  .primary {
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

  .primary:disabled {
    cursor: progress;
    opacity: 0.7;
  }
</style>
