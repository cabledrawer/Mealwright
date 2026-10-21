<script lang="ts">
  // "− Serves 4 +" on the recipe page (mockup Recipe; cabledrawer 19 Oct, question 26): whole
  // servings from 1 to 99, on screen only. The page goes back to the recipe's own number when
  // you leave it. Buttons are 44 px, a little larger than the mockup's 36 px (touch targets).
  // A recipe with Makes and no Serves gets the same − / + in whole multiples, from 1× to 99×:
  // "− Makes 400 g +" (spec, recipe page; words.md section 13).
  import { MAX_SERVES, MIN_SERVES } from '$lib/recipeAmounts';

  let {
    value,
    onchange,
    makes = null
  }: {
    /** Servings, or for a recipe without Serves how many times what it makes. */
    value: number;
    onchange: (value: number) => void;
    /** A recipe without Serves: what it makes at `value` times, e.g. "400 g". */
    makes?: string | null;
  } = $props();
</script>

<div class="stepper" role="group" aria-label={makes === null ? 'Servings' : 'How much it makes'}>
  <button
    type="button"
    aria-label={makes === null ? 'Fewer servings' : 'Make less'}
    disabled={value <= MIN_SERVES}
    onclick={() => onchange(value - 1)}>−</button
  >
  <span class="now" aria-live="polite">{makes === null ? `Serves ${value}` : `Makes ${makes}`}</span
  >
  <button
    type="button"
    aria-label={makes === null ? 'More servings' : 'Make more'}
    disabled={value >= MAX_SERVES}
    onclick={() => onchange(value + 1)}>+</button
  >
</div>

<style>
  .stepper {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--reading-chip, var(--color-fill));
  }

  button {
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 1.125rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button:disabled {
    cursor: default;
    opacity: 0.4;
  }

  .now {
    min-width: 4.5em;
    padding: 0 var(--space-3);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: center;
  }
</style>
