<script lang="ts">
  // "Check you have these" (mockups Shop, Desktop-Shop and their dark twins): the staples this
  // week's planned recipes use, each with Got it and + Add. Staples are assumed in stock and
  // never put on the list by the plan; this is the one nudge. Online only: the server keeps
  // "Got it". Docs: docs/dev/words.md section 21.
  import { downLine } from '#lib/downWords.js';
  import Icon from '#lib/components/Icon.svelte';
  import { staplesLine, usedIn } from '#lib/shopping/plan.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import { network } from '#lib/network.svelte.js';

  let {
    model,
    foldable = false
  }: {
    model: ShoppingModel;
    /** Plan shopping: folded to "Check you have these · 4  Show" until opened. */
    foldable?: boolean;
  } = $props();
  let folded = $state(true);
  const closed = $derived(foldable && folded);
  const uid = $props.id();
  const offline = $derived(network.offline);
</script>

{#if model.list?.main && model.staples.length}
  <section class="check" aria-labelledby="{uid}-t">
    <div class="head">
      {#if foldable}
        <h2 id="{uid}-t" class="fold">
          <button
            type="button"
            class="toggle"
            aria-expanded={!folded}
            aria-controls="{uid}-list"
            onclick={() => (folded = !folded)}
            ><span>Check you have these · {model.staples.length}</span><span class="word"
              >{folded ? 'Show' : 'Fold'}</span
            ></button
          >
        </h2>
      {:else}
        <div class="words">
          <h2 id="{uid}-t">Check you have these</h2>
          <p>{staplesLine(model.planCard?.days ?? null)}</p>
        </div>
      {/if}
      {#if !closed}
        <button
          type="button"
          class="x"
          aria-label="Dismiss staples check"
          disabled={offline}
          onclick={() => void model.gotAll()}><Icon name="close" size={18} stroke={2} /></button
        >
      {/if}
    </div>
    {#if foldable && !closed}<p class="line">{staplesLine(model.planCard?.days ?? null)}</p>{/if}
    {#if !closed}
      <ul id="{uid}-list">
        {#each model.staples as staple (staple.food.id)}
          <li>
            <span class="name"
              >{staple.food.name}<span class="used">{usedIn(staple.used_in)}</span></span
            >
            <span class="buttons">
              <button
                type="button"
                class="got"
                disabled={offline}
                aria-label="Got it, {staple.food.name}"
                onclick={() => void model.gotIt(staple)}>Got it</button
              >
              <button
                type="button"
                class="add"
                disabled={offline}
                aria-label="+ Add {staple.food.name}"
                onclick={() => void model.addStaple(staple)}>+ Add</button
              >
            </span>
          </li>
        {/each}
      </ul>
    {/if}
    {#if offline && !closed}
      <p class="offline" role="status">
        {downLine(network.deviceOffline, (b) => `Got it and + Add work ${b.when}.`)}
      </p>
    {/if}
  </section>
{/if}

<style>
  .check {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-2xl);
    background: var(--color-check);
    color: var(--color-text);
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  h2 {
    margin: 0;
    color: var(--color-check-title);
    font: var(--weight-extrabold) 1rem var(--font-ui);
  }

  .fold {
    flex: 1;
  }

  .toggle {
    display: flex;
    width: 100%;
    align-items: center;
    justify-content: space-between;
    padding: 0;
    border: none;
    background: transparent;
    font: var(--weight-extrabold) 1rem var(--font-ui);
    text-align: left;
  }

  .toggle .word {
    font-size: var(--text-md);
  }

  .line {
    margin: 0;
    color: var(--color-check-text);
    font-size: var(--text-sm);
  }

  .words p {
    margin: 0;
    color: var(--color-check-text);
    font-size: var(--text-sm);
  }

  ul {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-4);
    min-height: 52px;
  }

  .name {
    display: flex;
    flex: 1 1 8rem;
    flex-direction: column;
    min-width: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .used {
    color: var(--color-check-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .buttons {
    display: flex;
    gap: var(--space-3);
  }

  button {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 14px;
    border-radius: var(--radius-full);
    color: var(--color-check-title);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .got {
    border: 1px solid var(--color-check-border);
    background: transparent;
  }

  .add {
    border: none;
    background: var(--color-check-button);
  }

  .x {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: none;
    background: transparent;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .offline {
    margin: 0;
    color: var(--color-check-text);
    font-size: var(--text-sm);
  }
</style>
