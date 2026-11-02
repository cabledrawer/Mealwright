<script lang="ts">
  // The phone's Pantry · Ingredients switch, at the top of the Pantry tab (spec F76, N1). Two
  // links, the current one marked; the choice is remembered, so the Pantry tab opens where you
  // left it (pantrySide.ts). Phones only: a computer has Ingredients in the sidebar.
  import { resolve } from '$app/paths';
  import { FROM_PANTRY, rememberSide, type PantrySide } from '#lib/pantrySide.svelte.js';

  let { current }: { current: PantrySide } = $props();
</script>

<nav class="switch" aria-label="Pantry or Ingredients">
  <a
    href={resolve('/(app)/pantry')}
    aria-current={current === 'pantry' ? 'page' : undefined}
    onclick={() => rememberSide('pantry')}>Pantry</a
  >
  <a
    href="{resolve('/(app)/recipes/ingredients')}?{FROM_PANTRY}"
    aria-current={current === 'ingredients' ? 'page' : undefined}
    onclick={() => rememberSide('ingredients')}>Ingredients</a
  >
</nav>

<style>
  .switch {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-1);
    padding: var(--space-1);
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  a {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: var(--touch-target);
    border-radius: var(--radius-full);
    color: var(--color-text-soft);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  a[aria-current='page'] {
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-switch-knob);
  }

  @media (min-width: 768px) {
    .switch {
      display: none;
    }
  }
</style>
