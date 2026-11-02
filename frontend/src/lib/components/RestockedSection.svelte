<script lang="ts">
  // A staple's restock date in the ingredient editor (0.7 K5): the date it was last restocked
  // (a day field that stops at today, the household's own) and a "Restocked" button that sets
  // it to today. Each saves as you go, with Undo. Both send the same thing, `restocked_on`.
  // (The editor itself is fetched when one is first opened, see IngredientSheet.)
  import { getHousehold } from '#lib/client/household.js';
  import type { Food } from '#lib/client/types.js';
  import { addDays, dayMonthWords } from '#lib/dates.js';
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

  /** A whole day in this century, not after the household's today (when that is known). */
  function plausible(day: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return false;
    if (Number(day.slice(0, 4)) < 2000 || Number.isNaN(Date.parse(`${day}T12:00:00Z`)))
      return false;
    if (addDays(day, 0) !== day) return false; // 2026-02-31 is no day
    return !householdToday || day <= householdToday;
  }

  // Chrome fires "change" with every key typed in a date field, so a typed date is saved when
  // the field is left or Enter is pressed; a day picked from the calendar saves at once.
  let typing = false;

  function commit(input: HTMLInputElement) {
    typing = false;
    const day = input.value;
    if (day === (food.restocked_on ?? '')) return;
    if (!plausible(day)) {
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

  async function restockedToday() {
    const day = householdToday ?? (await getHousehold()).today;
    householdToday = day;
    void model.setField(
      { restocked_on: day },
      (f) => {
        f.restocked_on = day;
        f.restocked_days_ago = null;
      },
      `${food.name} restocked`
    );
  }

  /** How long ago, worked out here from the household's today while a save is on its way. */
  const daysAgo = $derived.by(() => {
    if (food.restocked_days_ago !== null) return food.restocked_days_ago;
    if (!food.restocked_on || !householdToday) return null;
    return Math.max(
      Math.round(
        (Date.parse(`${householdToday}T12:00:00Z`) - Date.parse(`${food.restocked_on}T12:00:00Z`)) /
          86_400_000
      ),
      0
    );
  });
</script>

<section aria-labelledby="{uid}-restocked">
  <h3 id="{uid}-restocked">Restocked</h3>
  <div class="row">
    <input
      type="date"
      aria-label="Date restocked"
      max={householdToday}
      value={food.restocked_on ?? ''}
      disabled={network.offline}
      onkeydown={(event) => {
        if (event.key === 'Enter') commit(event.currentTarget);
        else if (event.key !== 'Tab') typing = true;
      }}
      onchange={(event) => {
        if (!typing) commit(event.currentTarget);
      }}
      onblur={(event) => commit(event.currentTarget)}
    />
    <button type="button" disabled={network.offline} onclick={() => void restockedToday()}
      >Restocked</button
    >
  </div>
  <p class="hint" aria-live="polite">
    {#if food.restocked_on && daysAgo !== null}
      {columnWords(daysAgo)} · {fullDateWords(food.restocked_on)}
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
