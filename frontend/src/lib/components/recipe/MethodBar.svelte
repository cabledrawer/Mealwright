<script lang="ts">
  // Two ways of cooking it, in the recipe editor (M2, mockup RecipeMethods08): "+ Add a second way
  // of cooking it", then a switch between the two, a name for the one being edited, and Remove.
  // The Time, ingredients and steps boxes are always the way on show. Words are proposed, for
  // cabledrawer (docs/dev/words.md, two cooking methods).
  import '#lib/styles/fields.css';
  import type { RecipeDraft } from '#lib/recipes/draft.svelte.js';

  let { draft, errors }: { draft: RecipeDraft; errors: Record<string, string> } = $props();
  const uid = $props.id();
  const shownName = $derived(draft.names[draft.at]);
</script>

<section class="methods" aria-label="Ways of cooking it">
  {#if draft.hidden}
    <div class="switch" role="group" aria-label="Method">
      {#each [0, 1] as const as position (position)}
        <button
          type="button"
          aria-pressed={draft.at === position}
          onclick={() => draft.showMethod(position)}
          >{draft.names[position].trim() || (position === 0 ? 'First way' : 'Second way')}</button
        >
      {/each}
    </div>
    <div class="mw-field">
      <label class="mw-label" for="{uid}-name"> Name of this way of cooking it </label>
      <input
        id="{uid}-name"
        class="mw-input"
        type="text"
        maxlength="60"
        placeholder={draft.at === 0 ? 'Stovetop' : 'Instant Pot'}
        aria-invalid={errors[`method${draft.at}`] ? true : undefined}
        value={shownName}
        oninput={(e) => {
          draft.names[draft.at] = e.currentTarget.value;
        }}
      />
      {#if errors[`method${draft.at}`]}
        <p class="mw-error">{errors[`method${draft.at}`]}</p>
      {/if}
    </div>
    <p class="note">The time, ingredients and steps below are for this way of cooking it.</p>
    <button type="button" class="mw-add" onclick={() => draft.removeShownMethod()}
      >Remove this way of cooking it</button
    >
  {:else}
    <button type="button" class="mw-add" onclick={() => draft.addSecondMethod()}
      >+ Add a second way of cooking it</button
    >
  {/if}
</section>

<style>
  .methods {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .switch {
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  .switch button {
    min-height: 40px;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .switch button[aria-pressed='true'] {
    background: var(--color-segment-active);
    font-weight: var(--weight-extrabold);
  }

  .note {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }
</style>
