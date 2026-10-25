<script lang="ts">
  // All recipes (mockups Recipes-Phone and Dark-Recipes-Phone, spec "Recipes navigation" and
  // cabledrawer's answers of 19 and 20 Oct): the count in the title, the Ingredients button,
  // search, the filter row (All · Can cook now · the household's tags) and the list A to Z.
  // Each row says how long it takes, its calories and what is in stock.
  //
  // Two settings. On a phone (and a tablet held upright) it is a page of its own, with the
  // page header. In the desktop's three panes (`pane`: mockups Desktop-Recipe and Dark-Recipe)
  // it is the middle pane: its own title, no Ingredients button (the sidebar has it), the open
  // recipe's row marked, and it scrolls on its own. The panes' layout keeps this component
  // alive while recipes open beside it, so the search, the filter and the scroll stay.
  //
  // Each row opens the recipe page; "New recipe" opens the editor (under the search on a phone,
  // under the title in the pane, as the mockups have it). The phone's Drafts button (with the
  // number of drafts, as the mockup has it) is back with 0.5's import. Hidden until it works,
  // not stubbed: "Planned Sun" (0.6). Online only, like Pantry (cabledrawer 19 Oct).
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { tick, untrack } from 'svelte';
  import EmptyState from './EmptyState.svelte';
  import FilterChips from './FilterChips.svelte';
  import Icon from './Icon.svelte';
  import OfflineNote from './OfflineNote.svelte';
  import PageHeader from './PageHeader.svelte';
  import RecipeListRow from './RecipeListRow.svelte';
  import { drafts } from '#lib/drafts.svelte.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { RecipeList, searchOf, type RecipeFilter } from '#lib/recipes.svelte.js';

  let {
    pane = false,
    currentId = null,
    alone,
    list = new RecipeList()
  }: {
    /** The middle pane of the desktop's three. */
    pane?: boolean;
    /** The recipe open beside the list: its row is marked. */
    currentId?: number | null;
    /** Nothing is open beside the pane, so its title is the page's main heading. */
    alone?: boolean;
    /** The list's state; the panes' layout passes its own, so the page beside can see it too. */
    list?: RecipeList;
  } = $props();

  let root = $state<HTMLElement>();

  const filters = $derived<{ value: RecipeFilter; label: string }[]>([
    { value: 'all', label: 'All' },
    { value: 'cook', label: 'Can cook now' },
    { value: 'soon', label: 'Use soon' },
    ...list.tags.map((tag) => ({ value: `tag:${tag.name}` as const, label: tag.name }))
  ]);

  // "Use soon" lives in the address (?filter=use-soon): a chip tap changes it without adding a
  // history step, and the list follows the address when it changes (Back, Forward, a link).
  const soonInUrl = () => page.url.searchParams.get('filter') === 'use-soon';
  let seenSoon = untrack(soonInUrl);
  $effect(() => {
    const soon = soonInUrl();
    if (soon === seenSoon) return;
    seenSoon = soon;
    untrack(() => {
      if (soon && list.filter !== 'soon') list.filter = 'soon';
      else if (!soon && list.filter === 'soon') list.filter = 'all';
    });
  });

  function choose(value: RecipeFilter) {
    list.filter = value;
    const search = searchOf(value);
    if (search === page.url.search) return;
    // Quietly: this page again, in the same history step, with no scroll and no focus move.
    const id = page.params.id;
    const here = id ? resolve('/(app)/recipes/[id]', { id }) : resolve('/(app)/recipes');
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- here is resolve()'s answer, plus this page's own ?filter=
    goto(here + search, { replace: true, reset: false }).catch(() => {
      // No router (a component test): the address stays as it is.
    });
  }

  // Search as you type (after a short pause), and fetch again whenever something changed
  // here, in the pantry on another phone, or when coming back to the tab.
  $effect(() => {
    void list.query;
    void list.filter;
    void kitchen.version;
    void live.pantry;
    // Not `loaded` itself: the first answer setting it would fetch everything a second time.
    const timer = setTimeout(() => void list.load(), untrack(() => list.loaded) ? 200 : 0);
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

  // Opening the page at a recipe (a reload, a link): bring its row into view, once.
  let shown = false;
  $effect(() => {
    if (shown || !pane || currentId === null || !list.loaded) return;
    shown = true;
    void tick().then(() =>
      root?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: 'nearest' })
    );
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
        : list.filter === 'soon'
          ? 'No recipe uses anything that needs using up soon.'
          : 'No recipes with that tag.'
  );
</script>

<svelte:document onvisibilitychange={onVisible} />

{#snippet newRecipe()}
  <div class="starts">
    <a class="new" href={resolve('/(app)/recipes/new')}
      ><Icon name="plus" size={20} stroke={2.4} />New recipe</a
    >
    <a class="import" href={resolve('/(app)/recipes/import')}
      ><Icon name="link" size={20} stroke={2.2} />Import a recipe</a
    >
  </div>
{/snippet}

{#snippet found()}
  {#if none}
    <EmptyState title="No recipes yet">Recipes you add will show here.</EmptyState>
    {#if !pane}{@render newRecipe()}{/if}
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

      {#if !pane}{@render newRecipe()}{/if}

      {#if list.loaded && !list.problem}
        <FilterChips options={filters} selected={list.filter} label="Show" onselect={choose} />
      {/if}

      <div class="card" aria-busy={!list.loaded}>
        {#if list.recipes.length}
          <ul>
            {#each list.recipes as recipe (recipe.id)}
              <li>
                <RecipeListRow
                  {recipe}
                  {pane}
                  current={recipe.id === currentId}
                  search={pane ? searchOf(list.filter) : ''}
                />
              </li>
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
{/snippet}

{#if pane}
  <!-- Offline, the panes' layout shows the one note for both panes and hides this one (but not
       beside the editor, which stays in view with what was typed: this list then stays as it was). -->
  <section class="pane" aria-label="Recipe list" bind:this={root}>
    <header>
      {#if count}<p class="overline">{count}</p>{/if}
      <svelte:element this={(alone ?? currentId === null) ? 'h1' : 'h2'}>Recipes</svelte:element>
    </header>
    {@render newRecipe()}
    {@render found()}
  </section>
{:else}
  <PageHeader title="Recipes" overline={network.offline ? undefined : count} />

  {#if network.offline}
    <OfflineNote screen="Recipes" />
  {:else}
    <!-- Phone: the Drafts and Ingredients buttons sit at the top of All recipes. Desktop has
         them in the sidebar, under Recipes. -->
    <nav class="more" aria-label="Recipes">
      <a href={resolve('/(app)/recipes/drafts')}
        >Drafts{#if drafts.count}<span class="drafts-count">{drafts.count}</span>{/if}</a
      >
      <a href={resolve('/(app)/recipes/ingredients')}>Ingredients</a>
    </nav>
    {@render found()}
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

  .drafts-count {
    margin-left: var(--space-3);
    padding: 1px 7px;
    border-radius: var(--radius-full);
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
  }

  .more a:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  /* New recipe and Import a recipe: two buttons, side by side when there is room. */
  .starts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .starts > a {
    flex: 1 1 11rem;
  }

  .import {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    min-height: 52px;
    padding: 0 18px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-field);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .import:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  /* The mockups' dark button, as wide as the column. */
  .new {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    min-height: 52px;
    padding: 0 18px;
    border-radius: var(--radius-field);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .new:hover {
    color: var(--color-inverse-text);
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

  /* The middle pane of the three: on the page's ground, scrolling on its own. */
  .pane {
    position: relative;
    flex: 0 0 clamp(300px, 24vw, 380px);
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
    height: 100%;
    padding: var(--space-10) var(--space-6) var(--space-9) var(--space-9);
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    box-sizing: border-box;
  }

  .pane header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  .pane :is(h1, h2) {
    font-size: 1.75rem;
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    word-spacing: normal;
    line-height: 1.15;
    overflow-wrap: anywhere;
  }

  .pane .screen {
    gap: var(--space-5);
    max-width: none;
  }

  /* The rows sit straight on the ground; the open one is lifted onto a white card. */
  .pane .card {
    padding: 0;
    background: transparent;
  }

  .pane ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .pane li {
    border-bottom: none;
  }
</style>
