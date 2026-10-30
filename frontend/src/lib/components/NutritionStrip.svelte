<script lang="ts">
  // Nutrition per serving as five small figures (mockup Recipe). A figure nobody has typed is
  // "unknown", never 0 (cabledrawer 19 Oct); a recipe with none at all says so in one line.
  // It is per serving, so it does not change when the servings are scaled.
  import { gramsText, kcalText } from '#lib/recipeAmounts.js';

  /** Proposed, for cabledrawer. */
  const NUTRITION_OUT_OF_DATE = 'Nutrition possibly out of date';

  let {
    nutrition,
    outOfDate = false
  }: {
    /** An imported recipe that has been edited since (0.7.0): the figures came from the page. */
    outOfDate?: boolean;
    nutrition: {
      kcal: number | null;
      protein: number | null;
      carbs: number | null;
      fat: number | null;
      fibre: number | null;
    };
  } = $props();

  const figures = $derived([
    { label: 'kcal', value: nutrition.kcal === null ? null : kcalText(nutrition.kcal) },
    { label: 'protein', value: nutrition.protein === null ? null : gramsText(nutrition.protein) },
    { label: 'carbs', value: nutrition.carbs === null ? null : gramsText(nutrition.carbs) },
    { label: 'fat', value: nutrition.fat === null ? null : gramsText(nutrition.fat) },
    { label: 'fibre', value: nutrition.fibre === null ? null : gramsText(nutrition.fibre) }
  ]);
  const none = $derived(figures.every((figure) => figure.value === null));
</script>

{#if none}
  <p class="none">Nutrition unknown</p>
{:else}
  <section class="strip" aria-label="Nutrition per serving">
    {#each figures as figure (figure.label)}
      <div class="figure">
        <span class="value" class:unknown={figure.value === null}>{figure.value ?? 'unknown'}</span>
        <span class="label">{figure.label}</span>
      </div>
    {/each}
  </section>
  <p class="per">per serving</p>
  {#if outOfDate}
    <p class="per">{NUTRITION_OUT_OF_DATE}</p>
  {/if}
{/if}

<style>
  .strip {
    display: grid;
    /* Five across; with large text they wrap onto more rows instead of squeezing. */
    grid-template-columns: repeat(auto-fit, minmax(3.5rem, 1fr));
    gap: var(--space-3);
    padding: var(--space-5) var(--space-3);
    border-radius: var(--radius-xl);
    background: var(--reading-card, var(--color-surface));
  }

  .figure {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 0;
    text-align: center;
  }

  .value {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .value.unknown {
    padding-top: 3px;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .label {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
  }

  .per,
  .none {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .per {
    margin-top: calc(-1 * var(--space-3));
    text-align: center;
  }
</style>
