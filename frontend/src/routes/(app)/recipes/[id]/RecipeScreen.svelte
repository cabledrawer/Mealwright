<script lang="ts">
  // The recipe page on the phone (mockups Recipe and Dark-Phone-Recipe, spec section 6 "Recipes"
  // and "Stock", cabledrawer's answers of 19 and 20 Oct): the name, the time, whether the screen
  // may sleep, nutrition per serving, the ingredients with where each one is and a − / + for
  // servings (on screen only), "N missing · Add to the list", the method, tags and where it
  // came from. Online only, like Pantry and All recipes (question 33).
  //
  // Hidden until they work, not stubbed: Plan it (0.6), Start cooking and Cook once (0.7), the
  // Edit button and Delete (the editor), the photo (the photos pull request), and "From: <site>"
  // (imports, 0.5; a typed-in recipe's source note is shown as typed).
  import { resolve } from '$app/paths';
  import { onDestroy, untrack } from 'svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import KeepAwake from '$lib/components/KeepAwake.svelte';
  import MissingBar from '$lib/components/MissingBar.svelte';
  import NutritionStrip from '$lib/components/NutritionStrip.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import RecipeIngredient from '$lib/components/RecipeIngredient.svelte';
  import ServingsStepper from '$lib/components/ServingsStepper.svelte';
  import { kitchen } from '$lib/freshness.svelte';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import { live } from '$lib/live.svelte';
  import { network } from '$lib/network.svelte';
  import { PantryList } from '$lib/pantryList.svelte';
  import { lineAmount, makesAmount } from '$lib/recipeAmounts';
  import { RecipeView, stepGroups } from '$lib/recipePage.svelte';
  import { markFor, toAdd } from '$lib/recipeStock';
  import { ScreenAwake } from '$lib/screenAwake.svelte';

  let { id }: { id: number } = $props();

  const view = new RecipeView(untrack(() => id));
  const shopping = new PantryList();
  const awake = new ScreenAwake();

  // Fetch again after any change in the kitchen (an ingredient edited from here, an Undo),
  // when the pantry changed on another phone, and when this page comes back to the front.
  $effect(() => {
    void kitchen.version;
    void live.pantry;
    untrack(() => void view.load());
  });

  // What is on the shopping list, for "On list" and the missing line: as the Pantry does.
  $effect(() => {
    void kitchen.version;
    untrack(() => void shopping.refresh());
  });
  $effect(() => {
    const heard = live.shopping;
    untrack(() => {
      if (shopping.loaded && heard > shopping.cursor) void shopping.refresh();
    });
  });

  let wasOffline = false;
  $effect(() => {
    if (network.offline) wasOffline = true;
    else if (wasOffline) {
      wasOffline = false;
      void view.load();
      void shopping.refresh();
    }
  });

  function onVisible() {
    if (document.visibilityState !== 'visible') return;
    void view.load();
    void shopping.refresh();
    void awake.comeBack();
  }

  // Leaving the page: the screen may sleep again (the switch always starts off).
  onDestroy(() => void awake.leave());

  const recipe = $derived(view.recipe);
  const factor = $derived(view.factor);
  const stockOf = $derived(new Map((view.stock?.lines ?? []).map((s) => [s.line_id, s])));
  const adding = $derived(view.stock ? toAdd(view.stock.lines, (f) => shopping.onList(f)) : []);
  const steps = $derived(stepGroups(recipe?.steps ?? []));
  const meta = $derived.by(() => {
    if (!recipe) return [];
    const parts: string[] = [];
    if (recipe.description) parts.push(recipe.description);
    if (recipe.time_minutes !== null) parts.push(`${recipe.time_minutes}\u00a0min`);
    return parts;
  });
  const makes = $derived(recipe?.makes ? `Makes ${makesAmount(recipe.makes, factor)}` : null);
  const empty = $derived(recipe !== null && !recipe.lines.length && !recipe.steps.length);
  const name = $derived(recipe?.name ?? 'Recipe');
</script>

<svelte:document onvisibilitychange={onVisible} />
<svelte:head><title>{name} · Mealwright</title></svelte:head>

<div class="page">
  <div class="top">
    <a class="back" href={resolve('/recipes')}><Icon name="back" size={18} stroke={2.4} />Recipes</a
    >
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href={resolve('/recipes')}>Recipes</a>
      <span class="sep" aria-hidden="true">›</span>
      <span aria-current="page">{recipe ? recipe.name : ''}</span>
    </nav>
  </div>

  {#if network.offline}
    <OfflineNote screen="Recipes" />
  {:else if recipe}
    <article class="recipe">
      <header>
        <h1>{recipe.name}</h1>
        {#if meta.length || makes}
          <p class="meta">{[...meta, ...(makes ? [makes] : [])].join(' · ')}</p>
        {/if}
      </header>

      <KeepAwake {awake} />

      <NutritionStrip nutrition={recipe.nutrition} />

      {#if empty}
        <p class="quiet">Nothing written down yet.</p>
      {/if}

      {#if recipe.lines.length}
        <section aria-labelledby="ingredients-title">
          <div class="head">
            <h2 id="ingredients-title">Ingredients</h2>
            {#if view.servesNow !== null}
              <ServingsStepper value={view.servesNow} onchange={(n) => view.setServes(n)} />
            {/if}
          </div>
          <ul class="card lines">
            {#each recipe.lines as line (line.id)}
              <li>
                {#if line.kind === 'heading'}
                  <h3>{line.words}</h3>
                {:else}
                  <RecipeIngredient
                    {line}
                    amount={lineAmount(line, factor)}
                    mark={markFor(
                      stockOf.get(line.id),
                      stockOf.get(line.id) ? shopping.onList(stockOf.get(line.id)!.food.id) : false
                    )}
                    onopen={(foodId) => ingredientEditor.open(foodId)}
                  />
                {/if}
              </li>
            {/each}
          </ul>
          {#if adding.length}
            <MissingBar count={adding.length} onadd={() => void shopping.tapMany(adding)} />
          {/if}
        </section>
      {/if}

      {#if steps.length}
        <section aria-labelledby="method-title">
          <h2 id="method-title">Method</h2>
          <div class="card method">
            {#each steps as group, i (i)}
              {#if group.heading}<h3>{group.heading}</h3>{/if}
              {#if group.steps.length}
                <ol start={group.start}>
                  {#each group.steps as text, j (j)}<li>{text}</li>{/each}
                </ol>
              {/if}
            {/each}
          </div>
        </section>
      {/if}

      {#if recipe.tags.length}
        <ul class="tags" aria-label="Tags">
          {#each recipe.tags as tag (tag)}<li>{tag}</li>{/each}
        </ul>
      {/if}

      {#if recipe.source_note}
        <p class="source">Source: {recipe.source_note}</p>
      {/if}
    </article>
  {:else if view.gone}
    <EmptyState title="Recipe not found">
      This recipe isn’t here any more. It may have been deleted.
    </EmptyState>
  {:else if view.problem}
    <div class="failed" role="alert">
      <p>{view.problem}</p>
      <button type="button" onclick={() => void view.load()}>Try again</button>
    </div>
  {:else}
    <p class="quiet loading" aria-busy="true">Loading…</p>
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 760px;
  }

  .top {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
  }

  .back {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--touch-target);
    margin-left: calc(-1 * var(--space-2));
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .crumbs {
    display: none;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .crumbs a {
    text-decoration: none;
  }

  .crumbs .sep,
  .crumbs [aria-current] {
    color: var(--color-text-muted);
  }

  .crumbs [aria-current] {
    overflow-wrap: anywhere;
  }

  @media (min-width: 768px) {
    .back {
      display: none;
    }
    .crumbs {
      display: flex;
    }
  }

  .recipe {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  h1 {
    font-family: var(--font-reading);
    font-size: 2.125rem;
    font-weight: var(--weight-semibold);
    letter-spacing: -0.01em;
    line-height: 1.1;
    word-spacing: normal;
    overflow-wrap: anywhere;
  }

  .meta {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  h2 {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  h3 {
    padding-top: var(--space-5);
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .card {
    padding: var(--space-2) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lines li {
    border-bottom: 1px solid var(--color-divider);
  }

  .lines li:last-child {
    border-bottom: none;
  }

  /* A heading in the list (For the tempering) sits close to the lines it names. */
  .lines li:has(h3) {
    border-bottom: none;
  }

  .method {
    display: flex;
    flex-direction: column;
    padding-bottom: var(--space-7);
  }

  .method ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    margin: var(--space-5) 0 0;
    padding-left: 1.4em;
    font-family: var(--font-reading);
    font-size: 1.125rem;
    line-height: 1.45;
    word-spacing: normal;
  }

  .method li {
    padding-left: var(--space-2);
    overflow-wrap: anywhere;
    white-space: pre-line;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .tags li {
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .source,
  .quiet {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    overflow-wrap: anywhere;
  }

  .loading {
    padding: var(--space-8) 0;
    text-align: center;
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

  .failed button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
