<script lang="ts">
  // The Pack column on Ingredients (F121; mockup Dark-IngredientsPack08-Desktop): the Usual
  // size ("jar · 500 g"), "+1" when there are other sizes (their names on hover, and on a tap),
  // and with no size at all "Add a pack" with the common sizes from Mealwright's own table: a
  // tap on one makes it the Usual size, "Other…" opens the editor. The same cell sits on its own
  // line under the name on a phone. A button inside a row sits above the row's click area.
  import { serverUndo } from '#lib/client/changes.js';
  import { addSuggestedSize } from '#lib/client/foods.js';
  import type { FoodRow, FoodWrite, PackSuggestion } from '#lib/client/types.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { save } from '#lib/save.js';

  let { food, onother }: { food: FoodRow; onother: () => void } = $props();

  let choosing = $state(false);
  let showOthers = $state(false);

  const pack = $derived(food.pack ?? null);
  const others = $derived(food.more_sizes ?? []);
  const suggestions = $derived(food.pack_suggestions ?? []);

  /** "jar · 500 g": the size's own words without the "Jar = ". */
  const text = (size: { name: string; display: string }) =>
    `${size.name} · ${size.display.split(' = ')[1] ?? ''}`;
  const alsoText = $derived(`Also: ${others.map(text).join(', ')}`);

  function pick(choice: PackSuggestion) {
    choosing = false;
    let undoer: (() => Promise<string | void>) | null = null;
    void save<FoodWrite>({
      apply: () => {},
      rollback: () => {},
      send: (key) => addSuggestedSize(food.id, choice, key),
      saved: () => kitchen.changed({ elsewhere: true }),
      undo: {
        label: `${food.name}: added ${choice.display}`,
        labelFrom: (result) => result.change?.summary,
        skip: (result) => result.change === null,
        run: (result) => (result.change ? (undoer ??= serverUndo(result.change.id))() : false)
      }
    });
  }
</script>

{#if food.staple && !pack}
  <!-- A staple with no pack has nothing to show (cabledrawer 7 Nov: one with a pack shows it). -->
{:else if pack}
  <span class="pack">
    <span class="size">{text(pack)}</span>
    {#if others.length}
      <button
        type="button"
        class="plus"
        title={alsoText}
        aria-label={alsoText}
        aria-expanded={showOthers}
        onclick={() => (showOthers = !showOthers)}>+{others.length}</button
      >
      {#if showOthers}<span class="also">{alsoText}</span>{/if}
    {/if}
  </span>
{:else if suggestions.length || !network.offline}
  {#if choosing}
    <span class="chips" role="group" aria-label="Common sizes for {food.name}">
      <span class="lead">Common sizes:</span>
      {#each suggestions as choice (choice.amount)}
        <button type="button" class="chip" disabled={network.offline} onclick={() => pick(choice)}
          >{choice.amount_text}</button
        >
      {/each}
      <button type="button" class="chip" onclick={onother}>Other…</button>
    </span>
  {:else}
    <button
      type="button"
      class="add"
      aria-label="Add a pack for {food.name}"
      onclick={() => (choosing = true)}>Add a pack</button
    >
  {/if}
{/if}

<style>
  .pack {
    position: relative;
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    font-weight: var(--weight-bold);
    font-size: var(--text-sm);
    color: var(--color-text-soft);
  }

  .plus,
  .add,
  .chip {
    position: relative; /* above the row’s click area */
    border: none;
    cursor: pointer;
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
  }

  .plus {
    min-height: 28px;
    padding: 0 var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-soft);
  }

  /* A phone has no hover: "+1" is a tap, so a full touch target (review r1 L3). */
  @media (max-width: 767px) {
    .plus {
      min-height: var(--touch-target);
    }
  }

  .also {
    flex-basis: 100%;
    font-weight: var(--weight-medium);
    color: var(--color-text-muted);
  }

  .add {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-divider);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-accent);
  }

  .chips {
    position: relative;
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .lead {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .chip:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
