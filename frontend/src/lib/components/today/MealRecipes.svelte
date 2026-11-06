<script lang="ts">
  // Today's lines under a meal with more than one recipe (F160, cabledrawer 6 Nov): one line per
  // recipe. A cooked one has a tick and a Cooked chip; one still to cook has an empty circle and
  // its own Cooked it, which reviews that recipe only.
  import type { Plan, PlanItem, PlanMeal } from '#lib/client/plan.js';
  import { itemName } from '#lib/planMeals.js';

  let {
    meal,
    plan,
    disabled = false,
    oncook
  }: {
    meal: PlanMeal;
    plan: Plan | null;
    disabled?: boolean;
    oncook: (item: PlanItem) => void;
  } = $props();

  const recipes = $derived(meal.items.filter((i) => i.kind === 'recipe'));
</script>

<ul class="parts" data-testid="today-cooked-parts">
  {#each recipes as item (item.id)}
    {@const name = itemName(item, plan)}
    <li>
      {#if item.cooked}
        <span class="tick" aria-hidden="true">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="3"
            stroke-linecap="round"
            stroke-linejoin="round"><path d="M5 12l5 5 9-10"></path></svg
          >
        </span>
        <span class="recipe">{name}</span>
        <span class="chip">Cooked</span>
      {:else}
        <span class="circle" aria-hidden="true"></span>
        <span class="recipe">{name}</span>
        <button
          type="button"
          class="cooked-it"
          aria-label="Cooked it: {name}"
          {disabled}
          onclick={() => oncook(item)}>Cooked it</button
        >
      {/if}
    </li>
  {/each}
</ul>

<style>
  .parts {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 52px;
    padding-block: var(--space-2);
    border-top: 1px solid var(--color-divider);
  }

  .recipe {
    flex: 1;
    min-width: 0;
    font-size: 1rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .tick,
  .circle {
    flex: none;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-full);
    box-sizing: border-box;
  }

  .tick {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .circle {
    border: 2px solid var(--color-border-strong);
  }

  .chip {
    flex: none;
    padding: 6px 12px;
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .cooked-it {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 18px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .cooked-it:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
