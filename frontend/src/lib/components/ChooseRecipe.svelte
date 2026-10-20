<script lang="ts">
  // The reading pane when no recipe is open (desktop Recipes, at /recipes): a calm line, no
  // button. Words proposed for cabledrawer (docs/dev/words.md, section 14).
  import Icon from './Icon.svelte';
</script>

<section class="choose" aria-labelledby="choose-title">
  <Icon name="recipes" size={32} stroke={1.6} />
  <h2 id="choose-title">Choose a recipe</h2>
  <p>Pick one from the list to read it here.</p>
</section>

<style>
  .choose {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    padding: 20vh var(--space-9) 0;
    color: var(--color-text-muted);
    text-align: center;
  }

  h2 {
    color: var(--color-text);
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  p {
    font-size: var(--text-base);
    line-height: 1.5;
  }
</style>
