<script lang="ts">
  // "Make this its own recipe" under a section heading on Check (F190, cabledrawer 8 Nov; mockups
  // Dark-CheckSections08-Phone and Dark-CheckOwnRecipe08-Phone). Chosen by hand, never automatic.
  // Used under the heading in See all and above a line in One at a time. Once chosen it says so, and
  // can be changed or put back. The sheet that asks the name loads when first opened.
  import { tick } from 'svelte';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import { MAX_OWN, ownLineWords, sectionOf } from '#lib/importOwn.js';

  let { flow, heading }: { flow: ImportFlow; heading: number } = $props();

  const review = $derived(flow.review!);
  const own = $derived(review.lines[heading]?.own ?? null);
  const lines = $derived(sectionOf(review, heading).lines.length);
  /** A section with no lines has nothing to make; at most five sections can be made one. */
  const offered = $derived(own === null && lines > 0 && flow.ownParts.length < MAX_OWN);
  let asking = $state(false);
  let root: HTMLElement | undefined = $state();

  async function closed() {
    asking = false;
    await tick();
    root?.querySelector('button')?.focus();
  }

  async function keepIn() {
    const { keepInMain } = await import('#lib/importOwnEdits.js');
    keepInMain(flow, heading);
    await tick();
    root?.querySelector('button')?.focus();
  }
</script>

{#if own || offered}
  <div class="own" bind:this={root}>
    {#if own}
      <p class="said">Its own recipe: <b>{ownLineWords(own)}</b></p>
      <span class="buttons">
        <button type="button" onclick={() => (asking = true)}>Change</button>
        <button type="button" onclick={() => void keepIn()}>Keep in this recipe</button>
      </span>
    {:else}
      <button type="button" class="make" onclick={() => (asking = true)}
        >Make this its own recipe</button
      >
    {/if}
  </div>
{/if}

{#if asking}
  <!-- Loaded when first needed, so the page stays small. -->
  {#await import('./OwnRecipeSheet.svelte') then { default: OwnRecipeSheet }}
    <OwnRecipeSheet {flow} {heading} onclose={() => void closed()} />
  {/await}
{/if}

<style>
  .own {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3) var(--space-5);
    margin-bottom: var(--space-3);
  }

  .said {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .said b {
    color: var(--color-text);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: 10px;
    background: transparent;
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .make {
    border: none;
    padding: 0;
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }
</style>
