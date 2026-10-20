<script lang="ts">
  // All recipes (mockups Recipes-Phone and Dark-Recipes-Phone, spec "Recipes navigation" and
  // cabledrawer's answers of 19 and 20 Oct): the count in the title, the Ingredients button,
  // search, the filter row (All · Can cook now · the household's tags) and the list A to Z.
  // Each row says how long it takes, its calories and what is in stock.
  //
  // Hidden until they work, not stubbed: "+ New recipe" (the editor, PR 5), the Drafts
  // button (drafts only come from 0.5's import; agreed by cabledrawer 20 Oct), the recipe page
  // that rows open (PR 3b), "Planned Sun" (0.6). Online only, like Pantry (cabledrawer 19 Oct).
  import { resolve } from '$app/paths';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import FilterChips from '$lib/components/FilterChips.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import RecipeListRow from '$lib/components/RecipeListRow.svelte';
  import { kitchen } from '$lib/freshness.svelte';
  import { live } from '$lib/live.svelte';
  import { network } from '$lib/network.svelte';
  import { RecipeList, type RecipeFilter } from '$lib/recipes.svelte';

  const list = new RecipeList();

  const filters = $derived<{ value: RecipeFilter; label: string }[]>([
    { value: 'all', label: 'All' },
    { value: 'cook', label: 'Can cook now' },
    ...list.tags.map((tag) => ({ value: `tag:${tag.name}` as const, label: tag.name }))
  ]);

  // Search as you type (after a short pause), and fetch again whenever something changed
  // here, in the pantry on another phone, or when coming back to the tab.
  $effect(() => {
    void list.query;
    void list.filter;
    void kitchen.version;
    void live.pantry;
    const timer = setTimeout(() => void list.load(), list.loaded ? 200 : 0);
    return () => clearTimeout(timer);
  });

  // Recipes need the server (cabledrawer 19 Oct, question 33): offline shows a note pointing to
  // Shopping, and fetches again once the connection is back.
  let wasOffline = false;
  $effect(() => {
    if (network.offline) wasOffline = true;
    else if (wasOffline) {
      wasOffline = false;
      void list.load();
    }
  });

  function onVisible() {
    if (document.visibilityState === 'visible') void list.load();
  }

  const count = $derived(
    list.loaded && !list.problem
      ? `${list.all} ${list.all === 1 ? 'recipe' : 'recipes'}`
      : undefined
  );
  const searching = $derived(list.query.trim() !== '');
  const none = $derived(list.loaded && !list.problem && list.all === 0);

  /** Why a search or filter found nothing. */
  const nothing = $derived(
    searching
      ? `No recipe matches “${list.query.trim()}”.`
      : list.filter === 'cook'
        ? 'No recipe can be cooked with what is in stock right now.'
        : 'No recipes with that tag.'
  );
</script>

<svelte:document onvisibilitychange={onVisible} />

<PageHeader title="Recipes" overline={network.offline ? undefined : count} />

{#if network.offline}
  <OfflineNote screen="Recipes" />
{:else}
  <!-- Phone: the Ingredients button sits at the top of All recipes. Desktop has it in the
       sidebar, under Recipes. -->
  <nav class="more" aria-label="Recipes">
    <a href={resolve('/recipes/ingredients')}>Ingredients</a>
  </nav>

  {#if none}
    <EmptyState title="No recipes yet">Recipes you add will show here.</EmptyState>
  {:else}
    <div class="screen">
      <label class="search">
        <Icon name="search" size={18} stroke={2.2} />
        <input
          type="search"
          placeholder="Search recipes"
          aria-label="Search recipes"
          bind:value={list.query}
        />
      </label>

      {#if list.loaded && !list.problem}
        <FilterChips
          options={filters}
          selected={list.filter}
          label="Show"
          onselect={(value) => (list.filter = value)}
        />
      {/if}

      <div class="card" aria-busy={!list.loaded}>
        {#if list.recipes.length}
          <ul>
            {#each list.recipes as recipe (recipe.id)}
              <li><RecipeListRow {recipe} /></li>
            {/each}
          </ul>
          {#if list.moreProblem}
            <p class="more-problem" role="alert">{list.moreProblem}</p>
          {/if}
          {#if list.next}
            <button type="button" class="more-button" onclick={() => void list.more()}
              >{list.moreProblem ? 'Try again' : 'Show more'}</button
            >
          {/if}
        {:else if list.problem}
          <div class="failed" role="alert">
            <p>{list.problem}</p>
            <button type="button" class="again" onclick={() => void list.load()}>Try again</button>
          </div>
        {:else if !list.loaded}
          <p class="nothing">Loading…</p>
        {:else}
          <p class="nothing">{nothing}</p>
        {/if}
      </div>
    </div>
  {/if}
{/if}

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

  .screen {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 760px;
  }

  .search {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 48px;
    padding: 0 14px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text-muted);
  }

  .search:focus-within {
    outline: 2px solid var(--color-focus);
    outline-offset: 1px;
  }

  .search input {
    flex: 1;
    min-width: 0;
    min-height: 44px;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .search input:focus {
    outline: none;
  }

  .card {
    padding: var(--space-2) var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    border-bottom: 1px solid var(--color-divider);
  }

  li:last-child {
    border-bottom: none;
  }

  .nothing {
    padding: var(--space-8) 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  .more-problem {
    margin: 0;
    padding: var(--space-4) 0;
    border-top: 1px solid var(--color-divider);
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  .more-problem + .more-button {
    border-top: none;
  }

  .failed {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-8) 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  .again,
  .more-button {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .again {
    padding: 0 var(--space-7);
  }

  .more-button {
    width: 100%;
    border-top: 1px solid var(--color-divider);
  }
</style>
