<script lang="ts">
  import { plural } from '#lib/words.js';
  // How many recipes use an ingredient, at the end of its row in Ingredients (mockups
  // Ingredients-Phone and Ingredients-Desktop): "5 recipes" on a phone, just "5" in the
  // Recipes column on a computer. A screen reader hears "Used in 5 recipes" on both. Says
  // nothing when no recipe uses it.
  let { count }: { count: number } = $props();

  // Spaces at the edge of an element are dropped by the template, so these are strings.
  const USED_IN = 'Used in ';
  const word = $derived(plural(count, ' recipe', ' recipes'));
</script>

{#if count > 0}
  <span class="used"
    ><span class="visually-hidden">{USED_IN}</span>{count}<span class="word">{word}</span></span
  >
{/if}

<style>
  .used {
    position: relative;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  @media (min-width: 768px) {
    /* A column of numbers under "Recipes"; the word is still read out. */
    .used {
      color: var(--color-text);
      font-size: var(--text-base);
    }

    .word {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  }
</style>
