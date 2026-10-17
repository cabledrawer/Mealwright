<script lang="ts">
  import { resolve } from '$app/paths';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
</script>

<PageHeader title="Recipes" />

<!-- Phone: Drafts and Ingredients sit at the top of All recipes. Desktop has them in
     the sidebar, under Recipes. -->
<nav class="more" aria-label="Recipes">
  <a href={resolve('/recipes/drafts')}>Drafts</a>
  <a href={resolve('/recipes/ingredients')}>Ingredients</a>
</nav>

<EmptyState title="Nothing here yet">Your recipes will be here.</EmptyState>

<style>
  .more {
    display: flex;
    gap: var(--space-3);
    margin-top: -10px;
  }

  .more a {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .more a:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  @media (min-width: 768px) {
    .more {
      display: none;
    }
  }
</style>
