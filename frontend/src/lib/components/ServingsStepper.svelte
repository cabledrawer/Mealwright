<script lang="ts">
  // "− Serves 4 +" on the recipe page (mockup Recipe; cabledrawer 19 Oct, question 26): whole
  // servings from 1 to 99, on screen only. The page goes back to the recipe's own number when
  // you leave it. Buttons are 44 px, a little larger than the mockup's 36 px (touch targets).
  // A recipe with Makes and no Serves gets the same − / + in whole multiples, from 1× to 99×:
  // "− Makes 400 g +" (spec, recipe page; words.md section 13).
  import Stepper from '#lib/components/Stepper.svelte';
  import { MAX_SERVES, MIN_SERVES } from '#lib/recipeAmounts.js';

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

<Stepper
  what={makes === null ? 'servings' : 'batches'}
  label={makes === null ? 'Servings' : 'How much it makes'}
  onless={() => onchange(value - 1)}
  onmore={() => onchange(value + 1)}
  lessOff={value <= MIN_SERVES}
  moreOff={value >= MAX_SERVES}
>
  <span class="words">{makes === null ? `Serves ${value}` : `Makes ${makes}`}</span>
</Stepper>

<style>
  .words {
    display: inline-block;
    min-width: 4.5em;
  }
</style>
