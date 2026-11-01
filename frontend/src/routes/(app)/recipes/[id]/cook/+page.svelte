<script lang="ts">
  // Cook mode for one recipe (spec section 6, "Cook mode"). Full screen, over the app's own
  // menus. Leaving with a timer running asks "Stop the timer and leave?" (Stay · Leave), also for
  // the browser's Back and for a link; closing the tab asks the browser's own question.
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { onDestroy, onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { getRecipe, type Recipe } from '#lib/client/recipes.js';
  import CookMode from '#lib/components/cook/CookMode.svelte';
  import CookedReview, { type LeftoverOptions } from '#lib/components/cooked/CookedReview.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import { cookNow } from '#lib/cookNow.svelte.js';
  import { cookPrefs } from '#lib/cookPrefs.svelte.js';
  import { CookReview, answered } from '#lib/cookReview.svelte.js';
  import { cookTarget } from '#lib/cookTargets.js';
  import { CookTimers } from '#lib/cookTimers.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { PlanModel } from '#lib/plan.svelte.js';
  import { dayFull } from '#lib/planDates.js';
  import { ScreenAwake } from '#lib/screenAwake.svelte.js';

  const id = $derived(Number(page.params.id));
  const here = $derived(resolve('/(app)/recipes/[id]', { id: String(id) }));

  const timers = new CookTimers();
  const awake = new ScreenAwake();
  let cook = $state<ReturnType<typeof CookMode>>();
  let recipe = $state<Recipe | null>(null);
  let gone = $state(false);
  let problem = $state<string | null>(null);
  /** Set when the person has chosen to leave: the next navigation goes through. */
  let leaving = false;

  // "Cooked it" at the last step: only when this recipe is planned in a meal (Cook now plans it
  // first, or finds it planned today). The meal comes in the address (?meal=). The plan is read
  // here so a meal that was taken out again (Undo) or cooked already has no "Cooked it".
  const mealId = $derived(Number(page.url.searchParams.get('meal')) || null);
  const model = new PlanModel();
  const meal = $derived(
    mealId && !(cookNow.undone && cookNow.mealId === mealId)
      ? (model.plan?.meals.find(
          (m) =>
            m.id === mealId &&
            m.status === 'planned' &&
            m.items.some((i) => i.kind === 'recipe' && i.recipe?.id === id)
        ) ?? null)
      : null
  );
  const shown = $derived(cookNow.noticeFor(id, mealId));
  const notice = $derived(
    shown
      ? { text: shown.text, ...(shown.canUndo ? { undo: () => void cookNow.undo() } : {}) }
      : null
  );

  const review = new CookReview();
  let leftover = $state<LeftoverOptions | null>(null);
  let confirmed = false;

  function openCooked() {
    if (!meal) return;
    // Cook now added this recipe to the meal: Cooked it reviews only it, not the others there.
    const only = cookNow.onlyItem(id, meal);
    const target = cookTarget(
      model.plan,
      meal,
      `${dayFull(meal.date)} · ${model.slotName(meal.slot_id)}`,
      only
    );
    const first = only ?? meal.items.find((i) => i.kind === 'recipe');
    // A batch cooked once makes its own tubs, so there are no leftovers to ask about.
    leftover =
      first && target.parts.every((p) => p.batchId === null)
        ? { itemId: first.id, today: model.today }
        : null;
    void review.open(target);
  }

  function closeCooked() {
    review.close();
    if (confirmed) exit();
  }

  async function load() {
    try {
      recipe = await getRecipe(id);
      gone = false;
      problem = null;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) gone = true;
      else problem = cantReach(error) ? cantReachWords() : 'Couldn’t load this recipe. Try again.';
    }
  }
  onMount(() => {
    void load();
    void cookPrefs.load(); // the household's per-step switch
    // Start cooking from the Plan names the meal's day (?day=): the plan is read for that week.
    const day = page.url.searchParams.get('day');
    if (day && /^\d{4}-\d{2}-\d{2}$/.test(day)) model.anchor = day;
    if (mealId) void model.load();
  });

  function exit() {
    leaving = true;
    void goto(here);
  }

  beforeNavigate((navigation) => {
    if (leaving || !timers.running) return;
    navigation.cancel();
    // A closed tab or a typed address can't be asked about here: the browser asks (cancel()
    // does that); any other way out is asked with our own question.
    const to = navigation.to?.url;
    if (navigation.willUnload || !to) return;
    cook?.leaveOr(() => {
      leaving = true;
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- the page the person was going to
      void goto(to);
    });
  });

  onDestroy(() => {
    cookNow.leave(); // the notice must not come back on a later visit
    cookPrefs.leave(); // nor a failed switch's line
    timers.stopAll();
    void awake.leave();
  });
</script>

{#if recipe}
  <CookMode
    bind:this={cook}
    {recipe}
    {timers}
    {awake}
    perStep={cookPrefs.perStep}
    {notice}
    oncooked={meal ? openCooked : null}
    problem={cookPrefs.problem}
    onperstep={(on) => void cookPrefs.setPerStep(on)}
    onexit={exit}
  />
{:else if gone}
  <EmptyState title="Recipe not found">
    This recipe isn’t here any more. It may have been deleted.
  </EmptyState>
{:else if problem}
  <div class="failed" role="alert">
    <p>{problem}</p>
    <button type="button" onclick={() => void load()}>Try again</button>
  </div>
{:else}
  <p class="loading" aria-busy="true">Loading…</p>
{/if}

<CookedReview
  {review}
  {leftover}
  readonly={network.offline}
  onclose={closeCooked}
  onconfirmed={async (leftovers, undoCooked) => {
    const planned = meal;
    if (!planned) return true;
    const result = answered(await model.cooked(planned, leftovers, undoCooked));
    if (result === true) confirmed = true;
    return result;
  }}
/>

<style>
  .loading,
  .failed {
    color: var(--color-text-muted);
  }

  .failed button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
