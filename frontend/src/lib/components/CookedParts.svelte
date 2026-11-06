<script lang="ts">
  // Today's line under a meal cooked in parts (F157): which of its recipes are done.
  // Proposed, for cabledrawer.
  import type { Plan, PlanMeal } from '#lib/client/plan.js';
  import { cookedTitle } from '#lib/cookTargets.js';
  import { itemName } from '#lib/planMeals.js';

  let { meal, plan }: { meal: PlanMeal; plan: Plan | null } = $props();
</script>

{#if meal.status === 'planned' && meal.items.some((i) => i.cooked)}
  <p class="muted" data-testid="today-cooked-parts">
    {cookedTitle(meal.items.filter((i) => i.cooked).map((i) => itemName(i, plan)))}
  </p>
{/if}

<style>
  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    margin: 0;
  }
</style>
