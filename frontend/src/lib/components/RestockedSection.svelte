<script lang="ts">
  // A staple's restock date in the ingredient editor (0.7 K5): the date it was last restocked
  // (a day field that stops at today, the household's own) and a "Restocked" button that sets
  // it to now. Each saves as you go, with Undo. Loaded by IngredientEditor only when a staple is
  // open, so none of this is in every page's code (the page size limit).
  import { getHousehold } from '#lib/client/household.js';
  import type { Food } from '#lib/client/types.js';
  import { dayMonthWords } from '#lib/dates.js';
  import type { FoodModel } from '#lib/foodEditor.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { columnWords, fullDateWords } from '#lib/restockWords.js';

  let { food, model }: { food: Food; model: FoodModel } = $props();

  const uid = $props.id();

  let householdToday = $state<string>();
  $effect(() => {
    if (householdToday) return;
    getHousehold()
      .then((h) => (householdToday = h.today))
      .catch(() => {});
  });

  function pickRestocked(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const day = input.value;
    if (!day || day === food.restocked_on) {
      input.value = food.restocked_on ?? '';
      return;
    }
    void model.setField(
      { restocked_on: day },
      (f) => {
        f.restocked_on = day;
        f.restocked_days_ago = null;
      },
      `${food.name} restocked ${dayMonthWords(day)}`
    );
  }
</script>

<section aria-labelledby="{uid}-restocked">
  <h3 id="{uid}-restocked">Restocked</h3>
  <div class="row">
    <input
      type="date"
      aria-label="Date restocked"
      max={householdToday}
      value={food.restocked_on ?? ''}
      onchange={pickRestocked}
    />
    <button type="button" disabled={network.offline} onclick={() => void model.restocked()}
      >Restocked</button
    >
  </div>
  <p class="hint" aria-live="polite">
    {#if food.restocked_on && food.restocked_days_ago !== null}
      {columnWords(food.restocked_days_ago)} · {fullDateWords(food.restocked_on)}
    {:else}
      Not restocked yet. Ticking it off the shopping list or tapping Restocked sets the date.
    {/if}
  </p>
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
  }

  input {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }
</style>
