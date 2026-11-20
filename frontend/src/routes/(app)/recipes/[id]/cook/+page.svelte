<script lang="ts">
  // Cook mode for one recipe (spec section 6, "Cook mode"). Full screen, over the app's own
  // menus. Leaving with a timer running asks "Stop the timer and leave?" (Stay · Leave), also for
  // the browser's Back and for a link; closing the tab asks the browser's own question.
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { onDestroy, onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords, wordsFor } from '#lib/api.js';
  import { getRecipe, type Recipe } from '#lib/client/recipes.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { withMethod } from '#lib/recipeMethods.js';
  import CookMode from '#lib/components/cook/CookMode.svelte';
  import type { LeftoverOptions } from '#lib/components/cooked/CookedReview.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import type { AheadView } from '#lib/cookAhead.js';
  import { cookNow } from '#lib/cookNow.svelte.js';
  import { cookPrefs } from '#lib/cookPrefs.svelte.js';
  import { CookReview, answered } from '#lib/cookReview.svelte.js';
  import { cookSteps } from '#lib/cookSteps.js';
  import { cookTarget } from '#lib/cookTargets.js';
  import { CookTimers } from '#lib/cookTimers.svelte.js';
  import { markWaitBegun } from '#lib/lazyActions.js';
  import { network } from '#lib/network.svelte.js';
  import { PlanModel } from '#lib/plan.svelte.js';
  import { dayFull } from '#lib/planDates.js';
  import { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import { couldntLoad } from '#lib/errorWords.js';

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
  /** The plan is still loading: the last step's buttons wait, so they don't change under a thumb. */
  let settling = $state(page.url.searchParams.get('meal') !== null);

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
            m.items.some((i) => i.kind === 'recipe' && !i.cooked && i.recipe?.id === id)
        ) ?? null)
      : null
  );
  const shown = $derived(cookNow.noticeFor(id, mealId));
  const notice = $derived(
    shown
      ? { text: shown.text, ...(shown.canUndo ? { undo: () => void cookNow.undo() } : {}) }
      : null
  );

  // Two ways of cooking it (M2, mockup CookMethod08): Cook mode asks "How are you cooking it
  // today?" once the recipe and the plan are known, and follows the pick; the meal is set to it so
  // Cooked it follows too. The way can be switched again on the first step.
  let pick = $state<number | null>(null);
  let asking = $state(false);
  let asked = false;
  const twoWays = $derived((recipe?.methods?.length ?? 0) > 1);
  const shownRecipe = $derived(recipe ? withMethod(recipe, pick) : null);
  /** This recipe's item in the meal (the one Cooked it would review). */
  const mealItem = () =>
    meal?.items.find((i) => i.kind === 'recipe' && !i.cooked && i.recipe?.id === id) ?? null;

  // The recipe's long wait in this meal (M3): when it was begun, Cook mode opens after its step,
  // with the steps up to it folded. Worked out when there is one (it loads on first use).
  const waiting = $derived(mealItem()?.ahead ?? null);
  const sameWay = $derived(!twoWays || pick === null || mealItem()?.method_id === pick);
  let ahead = $state<AheadView | null>(null);
  let aheadAsked = 0;
  $effect(() => {
    const found = waiting;
    const shown = shownRecipe;
    const today = model.today;
    const mine = ++aheadAsked;
    if (!found || !shown || !sameWay || !today) {
      ahead = null;
      return;
    }
    void import('#lib/cookAhead.js').then(({ aheadView }) => {
      if (mine === aheadAsked) ahead = aheadView(found, cookSteps(shown.steps), today);
    });
  });

  /** Past the step that waits for the first time: the wait is begun, and tomorrow Cook mode opens
   *  after it. No Undo is offered (the person only moved to the next step). */
  const begun = () => markWaitBegun(mealItem(), network.offline, () => model.load());

  $effect(() => {
    if (twoWays && !settling && !asked) {
      asked = true;
      asking = true;
    }
  });

  /** The way is picked (here, or by the question on its own when it was closed). */
  function start(chosen: number) {
    pick = chosen;
    asking = false;
  }

  const review = new CookReview();
  let leftover = $state<LeftoverOptions | null>(null);
  let confirmed = false;

  async function openCooked() {
    if (!meal) return;
    // The way cooked today is the meal's own way: set again here when the pick was not saved
    // (offline, or it failed), so Cooked it never records the other way (M2).
    const item = mealItem();
    if (pick !== null && item && item.method_id !== pick) {
      const { setMealWay } = await import('#lib/cookWays.js');
      if (!(await setMealWay(item, pick))) {
        // proposed, for cabledrawer
        toasts.show(
          'Couldn’t tell the Plan which way you cooked it. Check the connection and try again.',
          {
            tone: 'problem'
          }
        );
        return;
      }
      await model.load();
      if (!meal) return;
    }
    // Cook now added this recipe to the meal: Cooked it reviews only it, not the others there.
    // Reloaded, or opened from the address: this recipe's first item not cooked yet in that
    // meal (cabledrawer 1 Nov; 6 Nov), never the whole meal.
    const only =
      cookNow.onlyItem(id, meal) ??
      meal.items.find((i) => i.kind === 'recipe' && i.recipe?.id === id && !i.cooked) ??
      null;
    const target = cookTarget(
      model.plan,
      meal,
      `${dayFull(meal.date)} · ${model.slotName(meal.slot_id)}`,
      only
    );
    const first = target.parts.find((p) => p.itemId !== null);
    // A batch cooked once makes its own tubs, so there are no leftovers to ask about.
    leftover =
      first && target.parts.every((p) => p.batchId === null)
        ? { itemId: first.itemId as number, today: model.today }
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
      else problem = wordsFor(error, couldntLoad('this recipe'));
    }
  }
  onMount(() => {
    void load();
    void cookPrefs.load(); // the household's per-step switch
    // Start cooking from the Plan names the meal's day (?day=): the plan is read for that week.
    const day = page.url.searchParams.get('day');
    if (day && /^\d{4}-\d{2}-\d{2}$/.test(day)) model.anchor = day;
    if (mealId) void model.load().finally(() => (settling = false));
    else settling = false;
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

{#if recipe && shownRecipe}
  <CookMode
    bind:this={cook}
    recipe={shownRecipe}
    way={twoWays && pick !== null
      ? {
          name: recipe.methods?.find((m) => m.id === pick)?.name ?? '',
          onswitch: () => (asking = true)
        }
      : null}
    {timers}
    {awake}
    perStep={cookPrefs.perStep}
    {notice}
    oncooked={meal ? () => void openCooked() : null}
    {settling}
    {ahead}
    onbegun={waiting && ahead ? () => void begun() : null}
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

{#if asking && twoWays && recipe}
  {#await import('#lib/components/cook/CookMethodAsk.svelte') then { default: CookMethodAsk }}
    <CookMethodAsk
      {recipe}
      item={mealItem()}
      current={pick}
      onstart={start}
      onchanged={() => void model.load()}
    />
  {/await}
{/if}

<!-- Cooked it is only needed at the last step: it loads when it is first opened (size limit). -->
{#if review.target}
  {#await import('#lib/components/cooked/CookedReview.svelte') then { default: CookedReview }}
    <CookedReview
      {review}
      {leftover}
      readonly={network.offline}
      onclose={closeCooked}
      onconfirmed={async (leftovers, undoCooked) => {
        const planned = meal;
        if (!planned) return true;
        const result = answered(
          await model.cooked(planned, leftovers, undoCooked, undefined, review.target?.title)
        );
        if (result === true) confirmed = true;
        return result;
      }}
    />
  {/await}
{/if}

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
