<script lang="ts">
  // Plan it on the recipe page (spec "Plan views and cards", cabledrawer 31 Oct): the next 14 days from
  // today in two rows of seven. Loaded when Plan it is first pressed, so the Plan's own page does
  // not carry it (size limit).
  import type { PlanModel } from '#lib/plan.svelte.js';
  import { addDays, dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';

  let {
    model,
    day = $bindable(null),
    slotId = $bindable(null)
  }: { model: PlanModel; day: string | null; slotId: number | null } = $props();

  const days = $derived(
    model.today ? Array.from({ length: 14 }, (_, i) => addDays(model.today, i)) : []
  );
</script>

<div class="days" role="group" aria-label="Day">
  {#each days as d (d)}
    <button type="button" aria-pressed={day === d} aria-label={dayFull(d)} onclick={() => (day = d)}
      ><span>{dayShort(d)}</span><b>{dayOfMonth(d)}</b></button
    >
  {/each}
</div>
<div class="slots" role="group" aria-label="Meal">
  {#each model.slotsOn as slot (slot.id)}
    <button
      type="button"
      aria-pressed={slotId === slot.id}
      aria-label={slot.name}
      onclick={() => (slotId = slot.id)}><span>{slot.name}</span></button
    >
  {/each}
</div>

<style>
  .days {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .days button {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 54px;
    padding: var(--space-3) 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .days b {
    font-size: var(--text-lg);
  }

  .slots {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .slots button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    max-width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-2) var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: left;
  }

  .days button[aria-pressed='true'],
  .slots button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }
</style>
