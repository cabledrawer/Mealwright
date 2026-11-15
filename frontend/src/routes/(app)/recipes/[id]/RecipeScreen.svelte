<script lang="ts">
  import { timeParts, timeWords, waitLength, waitName } from '#lib/timeWords.js';
  // The recipe page on the phone (mockups Recipe and Dark-Phone-Recipe, spec section 6 "Recipes"
  // and "Stock", cabledrawer's answers of 19 and 20 Oct): the name, the time, Cook now, nutrition per serving, the ingredients with where each one
  // is and a − / + for servings (on screen only), "N missing · Add to the list", the method, tags and where it
  // came from. Online only, like Pantry and All recipes (question 33).
  //
  // Edit, at the top on the right, opens the editor; the ⋯ beside it has Delete recipe (as the
  // editor does; mockups RecipeDelete-*). The photo is
  // above the name on a phone and beside the nutrition figures in the desktop's reading pane;
  // a recipe without one has no box. Hidden until they
  // work, not stubbed: Cook once (0.7). Plan it opens the Plan's day-and-meal picker. "From: <site> ·
  // by <author>" shows for an imported recipe (0.5); a typed-in recipe's source note is shown as
  // typed, as a link if it is a web address.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { onDestroy, tick, untrack } from 'svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import MissingBar from '#lib/components/MissingBar.svelte';
  import NutritionStrip from '#lib/components/NutritionStrip.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import RecipePhoto from '#lib/components/RecipePhoto.svelte';
  import RecipeIngredient from '#lib/components/RecipeIngredient.svelte';
  import RowMenu from '#lib/components/shopping/RowMenu.svelte';
  import ServingsStepper from '#lib/components/ServingsStepper.svelte';
  import { cookNow } from '#lib/cookNow.svelte.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { drafts } from '#lib/drafts.svelte.js';
  import { nextDraft, oldestDraft } from '#lib/nextDraft.svelte.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { PantryList } from '#lib/pantryList.svelte.js';
  import type { PlanModel } from '#lib/plan.svelte.js';
  import type { PlanActions, PlanTarget } from '#lib/planActions.js';
  import { recipePanes } from '#lib/recipePanes.svelte.js';
  import { recipePeek } from '#lib/recipePeek.js';
  import { go, RECIPES, editPage } from '#lib/recipes/paths.js';
  import { newChangeId } from '#lib/changeId.js';
  import { duplicateRecipe } from '#lib/client/recipes.js';
  import { removeRecipe } from '#lib/recipes/remove.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { ApiError } from '#lib/api.js';
  import { printing, watchPrinting } from '#lib/printing.svelte.js';
  import { lineAmount, makesAmount } from '#lib/recipeAmounts.js';
  import { RecipeView, stepGroups } from '#lib/recipePage.svelte.js';
  import { markFor, toAdd } from '#lib/recipeStock.js';

  /** A source note that is just a web address shows as a link (the person opens it). */
  const webAddress = (note: string) => /^https?:\/\/\S+$/i.test(note);

  let { id }: { id: number } = $props();

  // Cook now plans the recipe into today's next meal first (with Undo), then opens Cook mode for
  // that meal so "Cooked it" is there. A click that opens a new tab or window goes the plain way.
  async function cookNowClicked(event: MouseEvent) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (cookNow.busy) return;
    await cookNow.start(id);
    const to = resolve('/(app)/recipes/[id]/cook', { id: String(id) });
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
    await goto(cookNow.mealId ? `${to}?meal=${cookNow.mealId}` : to);
  }

  // Plan it: the Plan's own day-and-meal picker, then the recipe is planned there with an Undo
  // (the toast), like everywhere on the Plan. The plan is read when the button is pressed, so
  // the meals that are on, and today, are the household's.
  // The picker's code is fetched when Plan it is first pressed (size limit).
  let planModel: PlanModel | null = null;
  let planActions = $state<PlanActions | null>(null);
  let planning = $state<PlanTarget | null>(null);
  let planBusy = $state(false);

  /** The page was left (or its recipe changed) while something was still being waited for. */
  let left = false;
  const stale = (wanted: number) => left || recipe?.id !== wanted;

  async function planIt() {
    if (!recipe || planBusy) return;
    planBusy = true;
    const [wanted, wantedName] = [recipe.id, recipe.name];
    try {
      if (!planModel || !planActions) {
        const [{ PlanModel }, { pickerActions }] = await Promise.all([
          import('#lib/plan.svelte.js'),
          import('#lib/planActions.js')
        ]);
        if (stale(wanted)) return;
        planModel = new PlanModel();
        planActions = pickerActions(planModel, () => network.offline);
      }
      await planModel.loadAhead();
      if (stale(wanted)) return;
      if (!planModel.loaded) {
        toasts.show(planModel.problem ?? 'Couldn’t load the plan. Try again.', { tone: 'problem' });
        return;
      }
      planning = { kind: 'recipe', recipe: { id: wanted, name: wantedName }, ahead: true };
    } finally {
      planBusy = false;
    }
  }

  const view = new RecipeView(untrack(() => id));
  const shopping = new PantryList();

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
    // `down`, not `offline`: the note shows from the first failure, so the page fetches again
    // when anything answers, even before the bar came (F67 review).
    if (network.down) wasOffline = true;
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
  }

  onDestroy(() => {
    left = true;
    view.stop();
  });

  // Next draft (F212): shown only on the visit right after a Save from Check, and only while
  // another draft is waiting. The Drafts list is fetched again so the answer is the server's.
  $effect(() => {
    const mine = id;
    return () => nextDraft.clear(mine);
  });
  $effect(() => {
    if (nextDraft.savedId === id && !network.offline) untrack(() => void drafts.load());
  });
  const upNext = $derived(
    nextDraft.savedId === id ? oldestDraft(drafts.drafts, nextDraft.fromDraftId) : null
  );

  // In the desktop's three panes this is the reading pane (mockups Desktop-Recipe and
  // Dark-Recipe): wider, ingredients beside the method when there is room, and focus comes
  // to the recipe's heading when it opens, so the screen reader says its name and Tab goes on
  // from there.
  const panes = $derived(recipePanes.fits);
  let root = $state<HTMLElement>();
  let focused = false;
  $effect(() => {
    if (!panes || focused || !view.loaded || network.offline) return;
    focused = true;
    void tick().then(() => {
      // The recipe's name, or "Recipe not found"; a failure has no heading and says itself.
      const heading = root?.querySelector<HTMLElement>('h1, h2');
      if (!heading) return;
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    });
  });

  const recipe = $derived(view.recipe);
  const factor = $derived(view.factor);
  const stockOf = $derived(new Map((view.stockNow?.lines ?? []).map((s) => [s.line_id, s])));
  // "Add to the list" is for what the recipe needs: an Optional line is left out (R3; the plan's
  // question puts the ones a meal will use on the list).
  const adding = $derived(
    view.stockNow
      ? toAdd(
          view.stockNow.lines.filter(
            (l) => !recipe?.lines.some((line) => line.id === l.line_id && line.optional)
          ),
          (f) => shopping.onList(f)
        )
      : []
  );
  // On paper the footer line exists (the print layout, Print-Recipe095-A4).
  $effect(() => watchPrinting());
  const steps = $derived(stepGroups(recipe?.steps ?? []));
  const meta = $derived.by(() => {
    if (!recipe) return [];
    const parts: string[] = [];
    if (recipe.description) parts.push(recipe.description);
    const { active } = timeParts(recipe.time_minutes, recipe.wait);
    if (active) parts.push(active);
    return parts;
  });
  /** Before the recipe has come: the list's row it was opened from, if any (recipePeek.ts). */
  const peeked = $derived(!recipe && !view.gone && !view.problem ? recipePeek.of(id) : null);
  const peekedMeta = $derived.by(() => {
    if (!peeked) return '';
    const { active } = timeParts(peeked.time_minutes, peeked.wait);
    return [peeked.description, active].filter(Boolean).join(' · ');
  });
  /** "plus 4 h – overnight marinating": the recipe's waits, after its active time (M1). */
  const waitText = $derived(timeParts(recipe?.time_minutes ?? null, recipe?.wait).wait);
  const makesNow = $derived(recipe?.makes ? makesAmount(recipe.makes, factor) : null);
  /** Without Serves, "Makes …" sits between − and + instead of in the quiet line. */
  const makesStepper = $derived(
    view.timesNow !== null && recipe !== null && recipe.lines.length > 0
  );
  const makes = $derived(makesNow && !makesStepper ? `Makes ${makesNow}` : null);
  const empty = $derived(recipe !== null && !recipe.lines.length && !recipe.steps.length);
  const name = $derived(recipe?.name ?? 'Recipe');

  /**
   * Duplicate: the server makes "Sambar (copy)" (everything but cooked history and the plan)
   * and the editor opens on it. The key is kept while a press is waiting, so a double press
   * or a retry makes one copy.
   */
  let duplicating = false;
  async function duplicate() {
    if (!recipe || duplicating) return;
    duplicating = true;
    try {
      const copy = await duplicateRecipe(recipe.id, newChangeId());
      kitchen.changed();
      void go(editPage(copy.id));
    } catch (error) {
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t duplicate. Try again.', {
        tone: 'problem'
      });
    } finally {
      duplicating = false;
    }
  }

  /** Delete recipe: gone at once with "Deleted Sambar" and Undo, then the Recipes list. */
  async function remove() {
    if (!recipe) return;
    try {
      await removeRecipe(recipe.id, recipe.name);
      void go(RECIPES);
    } catch (error) {
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t delete. Try again.', {
        tone: 'problem'
      });
    }
  }
</script>

<svelte:document onvisibilitychange={onVisible} />
<svelte:head><title>{name} · Mealwright</title></svelte:head>

<div class="page" class:panes bind:this={root}>
  <div class="top">
    <a class="back" href={resolve('/(app)/recipes')}
      ><Icon name="back" size={18} stroke={2.4} />Recipes</a
    >
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href={resolve('/(app)/recipes')}>Recipes</a>
      <span class="sep" aria-hidden="true">›</span>
      <span aria-current="page">{recipe ? recipe.name : ''}</span>
    </nav>
    {#if recipe && !network.offline}
      <a class="edit" href={resolve('/(app)/recipes/[id]/edit', { id: String(recipe.id) })}>Edit</a>
      <RowMenu
        name={recipe.name}
        items={[
          { label: 'Duplicate', run: () => void duplicate() },
          { label: 'Delete recipe', danger: true, divider: true, run: () => void remove() }
        ]}
      />
    {/if}
  </div>

  {#if upNext && !network.offline}
    <a class="next-draft" href={resolve('/(app)/recipes/drafts/[id]', { id: String(upNext.id) })}>
      <span class="next-title">Next draft</span>
      <span class="next-name">{upNext.name}</span>
    </a>
  {/if}

  {#if !recipe && network.down}
    <!-- In the three panes, when the list couldn't load either, the layout shows its one note
         and hides this pane; otherwise this pane says why the recipe isn't here. -->
    <OfflineNote screen="Recipes" />
  {:else if recipe}
    <article class="recipe">
      {#if !panes}<RecipePhoto photo={recipe.photo} name={recipe.name} />{/if}
      <header>
        <h1>{recipe.name}</h1>
        {#if meta.length || makes || waitText}
          <p class="meta">
            {[...meta, ...(makes ? [makes] : [])].join(' · ')}{#if waitText}{meta.length || makes
                ? ' · '
                : ''}<span class="waits">{waitText}</span>{/if}
          </p>
        {/if}
      </header>

      {#if recipe.methods && recipe.methods.length > 1}
        <!-- Two ways of cooking it (M2, mockup RecipeMethods08): the switch changes the
             ingredients, the steps and the time together. -->
        <div class="method-switch" role="group" aria-label="Method">
          {#each recipe.methods as way (way.id)}
            <button
              type="button"
              aria-pressed={(view.methodId ?? recipe.methods[0]?.id) === way.id}
              onclick={() => view.setMethod(way.id)}
              >{way.name}{way.time_minutes ? ` · ${timeWords(way.time_minutes)}` : ''}</button
            >
          {/each}
        </div>
      {/if}

      {#if !network.offline}
        <!-- Cook now: the main button above the ingredients (spec "Cook mode (K4)"; Plan it
             comes beside it with the Plan redesign). Cook mode keeps the screen awake itself. -->
        <div class="actions">
          <a
            class="cook"
            href={resolve('/(app)/recipes/[id]/cook', { id: String(recipe.id) })}
            aria-busy={cookNow.busy}
            onclick={cookNowClicked}>Cook now</a
          >
          <button type="button" class="plan" aria-busy={planBusy} onclick={() => void planIt()}
            >Plan it</button
          >
        </div>
      {/if}

      {#if panes && recipe.photo}
        <!-- The photo beside the figures; narrower than the two together, they wrap. -->
        <div class="facts">
          <RecipePhoto photo={recipe.photo} name={recipe.name} beside />
          <div class="nutrition"><NutritionStrip nutrition={recipe.nutrition} /></div>
        </div>
      {:else}
        <NutritionStrip nutrition={recipe.nutrition} />
      {/if}

      {#if recipe.nutrition.possibly_out_of_date}
        <!-- R3 (mockup RecipeOptional08). "Update nutrition" opens the nutrition boxes in the
             editor: Mealwright doesn't work nutrition out from ingredients (not in v1), so the
             person looks at the figures there. The link's words are cabledrawer's (10 Nov). -->
        <p class="info" role="note">
          Nutrition possibly out of date: the ingredients changed since it was worked out.
          <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved; only the query is added -->
          <a href={`${resolve('/(app)/recipes/[id]/edit', { id: String(recipe.id) })}?nutrition=1`}
            >Update nutrition</a
          >
        </p>
      {/if}

      {#if empty}
        <p class="quiet">Nothing written down yet.</p>
      {/if}

      <div class="body">
        {#if recipe.lines.length}
          <section aria-labelledby="ingredients-title">
            <div class="head">
              <h2 id="ingredients-title">Ingredients</h2>
              {#if view.servesNow !== null}
                <ServingsStepper value={view.servesNow} onchange={(n) => view.setServes(n)} />
              {:else if makesStepper && view.timesNow !== null}
                <ServingsStepper
                  value={view.timesNow}
                  makes={makesNow}
                  onchange={(n) => view.setServes(n)}
                />
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
                        stockOf.get(line.id)
                          ? shopping.onList(stockOf.get(line.id)!.food.id)
                          : false
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
                    {#each group.steps as text, j (j)}
                      <li>
                        {#if group.optional[j]}<span class="opt">Optional step</span>{/if}<span
                          >{text}</span
                        >
                        {#if group.waits[j]}
                          <span class="wait-chip" data-step-wait
                            ><svg
                              aria-hidden="true"
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              stroke-width="2.4"
                              stroke-linecap="round"
                              ><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg
                            >{waitName(group.waits[j]!.kind)} · {waitLength(group.waits[j]!)}</span
                          >
                        {/if}
                      </li>
                    {/each}
                  </ol>
                {/if}
              {/each}
            </div>
          </section>
        {/if}
      </div>

      {#if recipe.tags.length}
        <ul class="tags" aria-label="Tags">
          {#each recipe.tags as tag (tag)}<li>{tag}</li>{/each}
        </ul>
      {/if}

      {#if recipe.source}
        <!-- Imported from a link: the site, and the author the page named. Opening the link is
             the person's own click; the server never visits it again. -->
        <p class="source">
          From:
          <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- the recipe's own site, opened by the person -->
          <a href={recipe.source.url} target="_blank" rel="noopener noreferrer"
            >{recipe.source.site}</a
          >{#if recipe.source.author}{` · by ${recipe.source.author}`}{/if}
        </p>
      {/if}

      {#if recipe.source_note}
        <p class="source">
          Source:
          {#if webAddress(recipe.source_note)}
            <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- a web address the person typed, opened by them -->
            <a href={recipe.source_note} target="_blank" rel="noopener noreferrer"
              >{recipe.source_note}</a
            >
          {:else}
            {recipe.source_note}
          {/if}
        </p>
      {/if}
      {#if printing.on}
        <!-- Only on paper (mockup Print-Recipe095-A4; proposed, for cabledrawer). -->
        <p class="foot">
          From Mealwright{view.servesNow !== null ? ` · amounts for ${view.servesNow}` : ''} · photo left
          off to save ink
        </p>
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
  {:else if peeked}
    <article class="recipe">
      {#if !panes}<RecipePhoto photo={peeked.photo} name={peeked.name} />{/if}
      <header>
        <h1>{peeked.name}</h1>
        {#if peekedMeta}<p class="meta">{peekedMeta}</p>{/if}
      </header>
      <p class="quiet loading" aria-busy="true">Loading…</p>
    </article>
  {:else}
    <p class="quiet loading" aria-busy="true">Loading…</p>
  {/if}
</div>

{#if planActions}
  {#await import('#lib/components/plan/PlanSheet.svelte') then { default: PlanSheet }}
    <PlanSheet actions={planActions} target={planning} onclose={() => (planning = null)} />
  {/await}
{/if}

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
    gap: var(--space-4);
    min-height: var(--touch-target);
  }

  .next-draft {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    align-self: flex-start;
    justify-content: center;
    min-height: var(--touch-target);
    padding: var(--space-3) var(--space-7);
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    text-decoration: none;
  }

  .next-title {
    font-weight: var(--weight-extrabold);
  }

  .next-name {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--text-md);
    opacity: 0.85;
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

  /* Edit sits at the far right of the top row (mockups Recipe and Desktop-Recipe). */
  .edit {
    display: flex;
    flex: none;
    align-items: center;
    min-height: var(--touch-target);
    margin-left: auto;
    padding: 0 var(--space-6);
    border: 1px solid transparent;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .actions {
    display: flex;
    gap: var(--space-5);
  }

  .cook {
    display: flex;
    flex: 1 1 0;
    align-items: center;
    justify-content: center;
    min-height: 54px;
    padding: 0 var(--space-8);
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .plan {
    display: flex;
    flex: 1 1 0;
    align-items: center;
    justify-content: center;
    min-height: 54px;
    padding: 0 var(--space-8);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .cook:hover {
    color: var(--color-inverse-text);
  }

  .edit:hover {
    color: var(--color-text);
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
    .edit {
      border-color: var(--color-border-strong);
      background: var(--color-surface);
    }
  }

  .recipe {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  /* The ingredients and the method: one under the other, as the page flows on a phone. */
  .body {
    display: contents;
  }

  /* In the desktop's reading pane: on the pane's own paper, not on cards; as wide as the
     pane, up to a comfortable reading width, and centred beyond that. */
  .page.panes {
    width: 100%;
    max-width: 68rem;
    margin-inline: auto;
    padding: var(--space-10) clamp(var(--space-8), 3vw, 3rem) var(--space-11);
    box-sizing: border-box;
    container-type: inline-size;
  }

  /* The heading focus lands on when a recipe opens is not something to press: no ring round it. */
  .page :global(:is(h1, h2)[tabindex='-1']:focus) {
    outline: none;
  }

  .panes .card {
    padding-inline: 0;
    background: transparent;
  }

  .panes .method {
    padding-bottom: 0;
  }

  /* Room for it: the ingredients beside the method, as the mockup draws them. */
  @container (min-width: 42.5rem) {
    h1 {
      font-size: 2.75rem;
      line-height: 1;
    }

    .body {
      display: grid;
      grid-template-columns: minmax(16rem, 1fr) minmax(0, 1.7fr);
      gap: var(--space-11);
      align-items: start;
    }

    .body > section:only-child {
      grid-column: 1 / -1;
    }
  }

  /* Photo and nutrition in one wrapping row (mockup Desktop-Recipe). */
  .facts {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: var(--space-7);
  }

  .nutrition {
    display: flex;
    flex: 2 1 360px;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-7);
    min-width: 0;
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

  .info {
    margin: 0;
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-info);
    color: var(--color-info-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .info a {
    color: inherit;
    font-weight: var(--weight-bold);
  }

  /* "Optional step" (R3), on its own line above the step's words. */
  .opt {
    display: block;
    width: fit-content;
    margin-bottom: var(--space-2);
    padding: 2px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-muted);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    white-space: normal;
  }

  .waits {
    color: var(--color-wait-text);
  }

  .method-switch {
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  .method-switch button {
    min-height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .method-switch button[aria-pressed='true'] {
    background: var(--color-segment-active);
    font-weight: var(--weight-extrabold);
  }

  /* A step that waits (M1): "Marinate · 4 h – overnight", under the step's words. */
  .wait-chip {
    display: flex;
    align-items: center;
    gap: 5px;
    width: fit-content;
    margin-top: var(--space-3);
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
    font: var(--weight-extrabold) var(--text-sm) var(--font-ui);
    white-space: normal;
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

  .source a {
    color: var(--color-accent);
    font-weight: var(--weight-semibold);
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

  /* On paper (mockup Print-Recipe095-A4; proposed, for cabledrawer): the title, the figures, the
     ingredients in two columns and the method, in dark ink on white, with no photo, buttons or
     links to other screens. The ingredients are as many as the servings now chosen. */
  .foot {
    display: none;
  }

  @media print {
    .top,
    .next-draft,
    .actions,
    .method-switch,
    .back,
    .crumbs {
      display: none !important;
    }
    .page,
    .page.panes {
      display: block;
      max-width: none;
      width: auto;
      margin: 0;
      padding: 0;
    }
    .recipe,
    .recipe :global(*) {
      color: #1a1f1c !important;
      background: transparent !important;
      border-color: #c9cfcb !important;
      box-shadow: none !important;
    }
    .recipe {
      display: block;
      font-size: 15px;
    }
    .recipe h1 {
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.02em;
      line-height: 1.2;
      break-after: avoid;
    }
    .recipe h2 {
      margin: 28px 0 8px;
      font-size: 18px;
      font-weight: 800;
      break-after: avoid;
    }
    .recipe h3 {
      break-after: avoid;
    }
    .meta {
      margin: 6px 0 0;
      font-size: 13px;
      color: #4a524d !important;
    }
    .card {
      padding: 0;
      border-radius: 0;
    }
    .lines {
      columns: 2;
      column-gap: 32px;
    }
    .lines li {
      break-inside: avoid;
      padding: 4px 0;
      border-bottom: 1px solid #dde2df !important;
    }
    .method ol {
      gap: 0;
      margin: 0;
      font-size: 15px;
    }
    .method li {
      margin: 0 0 10px;
      break-inside: avoid;
      text-wrap: pretty;
    }
    .tags {
      display: none;
    }
    .source {
      margin-top: 16px;
      font-size: 12px;
      color: #4a524d !important;
    }
    .foot {
      display: block;
      margin-top: 32px;
      padding-top: 10px;
      border-top: 1px solid #c9cfcb;
      font-size: 12px;
      color: #4a524d !important;
      break-inside: avoid;
    }
  }
</style>
