<script lang="ts">
  // Plan (mockups Plan, Desktop-Plan, Month-Desktop, Month-Phone and their dark twins).
  //   computer / iPad: the week grid or the month, a recipe tray under it; drag by mouse or finger
  //     (Alt copies), and a menu on click, Enter or a held finger that does all of it;
  //   phone and anything under 1100 px: the week as a list of days, the month as a dot grid; press
  //     and hold for the menu.
  // Online only, like the Pantry: offline the plan can be read but not changed. Cook once, eat for…
  // (PR 4) makes tubs, which can be placed, moved, given to someone and frozen.
  import Icon from '#lib/components/Icon.svelte';
  import { downLine } from '#lib/downWords.js';
  import { browser } from '$app/env';
  import { resolve } from '$app/paths';
  import { goto } from '$app/navigation';
  import { onDestroy, onMount, tick, untrack } from 'svelte';
  import type { PlanItem, PlanMeal, TubLeft } from '#lib/client/plan.js';
  import type { RecipeRow } from '#lib/client/recipes.js';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import type { LeftoverOptions } from '#lib/components/cooked/CookedReview.svelte';
  import PlanDays from '#lib/components/plan/PlanDays.svelte';
  import PlanMonth from '#lib/components/plan/PlanMonth.svelte';
  import PlanMonthPhone from '#lib/components/plan/PlanMonthPhone.svelte';
  import PlanShowSwitch from '#lib/components/plan/PlanShowSwitch.svelte';
  import PlanWeek from '#lib/components/plan/PlanWeek.svelte';
  import RecipeTray from '#lib/components/plan/RecipeTray.svelte';
  import { CookReview, answered } from '#lib/cookReview.svelte.js';
  import { cookTarget } from '#lib/cookTargets.js';
  import { eatLeftover, type Placed } from '#lib/eatLeftover.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import type { PlanActions, PlanTarget } from '#lib/planActions.js';
  import type { CookEntry } from '#lib/planCook.js';
  import { addDays, dayFull, dayWords, monthWords, weekWords } from '#lib/planDates.js';
  import { drag, type Carried } from '#lib/planDrag.svelte.js';
  import { afterCook, itemName, mealName, nextFreeMeals } from '#lib/planMeals.js';
  import { PlanModel } from '#lib/plan.svelte.js';
  import { keepShow, readShow, type PlanShow } from '#lib/planShow.js';
  import { RecipeList } from '#lib/recipes.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';

  const model = new PlanModel();
  const recipes = new RecipeList();

  // Two widths: the phone (under 768 px: bottom tabs), and "compact" (under 1100 px: the phone's
  // lists instead of the week grid and the month grid, whose seven columns are too narrow for the
  // words, with no tray to drag from). Between 768 and 1100 px the sidebar stays (spec: every Plan
  // screen works at 768–1100 px wide, with no words breaking in the middle).
  const PHONE = '(max-width: 767px)';
  const COMPACT = '(max-width: 1099px)';
  let phone = $state(browser && matchMedia(PHONE).matches);
  let compact = $state(browser && matchMedia(COMPACT).matches);
  $effect(() => {
    const [small, medium] = [matchMedia(PHONE), matchMedia(COMPACT)];
    const onSmall = () => (phone = small.matches);
    const onMedium = () => (compact = medium.matches);
    small.addEventListener('change', onSmall);
    medium.addEventListener('change', onMedium);
    return () => {
      small.removeEventListener('change', onSmall);
      medium.removeEventListener('change', onMedium);
    };
  });

  // Both · Eat · Cook: kept on this device; Eat opens first on the phone, Both on the computer.
  let show = $state<PlanShow>(untrack(() => readShow(phone)));
  function setShow(next: PlanShow) {
    show = next;
    keepShow(next);
  }

  /** Earlier days of the week are folded away on a list (the phone, Eat, Cook). */
  let earlier = $state(false);
  const listed = $derived(compact || show !== 'both');
  const past = $derived(
    model.view === 'week' && listed && model.days.includes(model.today)
      ? model.days.filter((d) => d < model.today)
      : []
  );
  const dayList = $derived(earlier ? model.days : model.days.filter((d) => !past.includes(d)));
  // Another week starts folded again.
  $effect(() => {
    void model.anchor;
    untrack(() => (earlier = false));
  });

  /** "You cook today →": the Cook view, at that day. */
  async function showCook(day: string) {
    show = 'cook';
    if (past.includes(day)) earlier = true;
    await tick();
    document.getElementById(`cook-${day}`)?.scrollIntoView({ block: 'start' });
  }

  let left = false;
  onDestroy(() => (left = true));

  /** Start cooking: Cook mode for this plan item, so "Cooked it" is there at the last step. */
  async function startCooking(entry: CookEntry) {
    if (entry.recipeId === null) return;
    const { cookNow } = await import('#lib/cookNow.svelte.js');
    if (left) return; // the Plan was left while the code was fetched: don't pull the person to Cook
    cookNow.open(entry.recipeId, entry.meal.id, entry.item.id);
    const to = resolve('/(app)/recipes/[id]/cook', { id: String(entry.recipeId) });
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
    await goto(`${to}?meal=${entry.meal.id}&day=${entry.meal.date}`);
  }

  const TRAY_KEY = 'mealwright.plan-tray';
  let trayOpen = $state(readTray());
  function readTray(): boolean {
    try {
      return localStorage.getItem(TRAY_KEY) !== 'closed';
    } catch {
      return true;
    }
  }
  function setTray(open: boolean) {
    trayOpen = open;
    try {
      if (open) localStorage.removeItem(TRAY_KEY);
      else localStorage.setItem(TRAY_KEY, 'closed');
    } catch {
      // Storage blocked: it still applies until the page is closed.
    }
  }

  let sheet = $state<PlanTarget | null>(null);
  let cooking = $state<{ meal: PlanMeal; item: PlanItem } | null>(null);
  let adding = $state<{ day: string; slotId: number | null } | null>(null);
  // Each part below is fetched the first time it is wanted, then stays mounted.
  let sheetAsked = $state(false);
  let cookingAsked = $state(false);
  let addingAsked = $state(false);
  let noPortionsAsked = $state(false);
  $effect(() => {
    if (sheet) sheetAsked = true;
    if (cooking) cookingAsked = true;
    if (adding) addingAsked = true;
    if (model.noPortions) noPortionsAsked = true;
  });
  /** The day shown under the phone's Month. */
  let picked = $state('');

  // Fetch the plan, and again after any change (ours, an Undo, a merge of ingredients…).
  $effect(() => {
    void kitchen.version;
    untrack(() => void model.load());
  });

  let wasOffline = false;
  $effect(() => {
    // `down`, not `offline`: the note shows from the first failure, so the page fetches again
    // when anything answers, even before the bar came (F67 review).
    if (network.down) wasOffline = true;
    else if (wasOffline) {
      wasOffline = false;
      void model.load();
      void recipes.load();
    }
  });

  onMount(() => void recipes.load());

  // The phone's Month starts on today, or the 1st when today is in another month.
  $effect(() => {
    const days = model.days;
    untrack(() => {
      if (!days.includes(picked)) {
        picked = days.includes(model.today) ? model.today : model.anchor.slice(0, 7) + '-01';
      }
    });
  });

  const readonly = $derived(network.offline);

  /** "Leftovers here" is offered only on meals after this one, and not in the past (F50). */
  const leftoversOk = (meal: PlanMeal) => (day: string, slot: number | null) =>
    afterCook(day, slot ?? meal.slot_id, meal, model.today, model.slotsOn);

  function carryMeal(meal: PlanMeal): Carried {
    return {
      label: mealName(meal, model.plan),
      zones: true,
      leftoversOk: leftoversOk(meal),
      drop: (day, slot, mode) => {
        const to = slot ?? meal.slot_id;
        if (day === meal.date && to === meal.slot_id) return; // dropped where it was
        void model.drop({ meal: meal.id }, day, to, mode);
      }
    };
  }

  // "Cooked it": the same review as on Today. The meal is then answered as cooked.
  const review = new CookReview();
  let cookedMeal = $state<PlanMeal | null>(null);
  let leftover = $state<LeftoverOptions | null>(null);

  /** The review's code is fetched when it is first asked for (size limit), then stays mounted. */
  let cookedAsked = $state(false);

  function openCooked(meal: PlanMeal) {
    cookedAsked = true;
    const target = cookTarget(
      model.plan,
      meal,
      `${dayFull(meal.date)} · ${model.slotName(meal.slot_id)}`
    );
    const first = meal.items.find((i) => i.kind === 'recipe');
    const useByFridge = model.tubFridgeDays ? addDays(meal.date, model.tubFridgeDays) : '';
    cookedMeal = meal;
    // A batch cooked once makes its own tubs, so there are no leftovers to ask about.
    leftover =
      first && target.parts.every((p) => p.batchId === null)
        ? {
            itemId: first.id,
            today: model.today,
            // A new fridge tub keeps tubFridgeDays from the cook day: not past that.
            ...(useByFridge ? { useByFridge } : {}),
            eatOn: nextFreeMeals(
              model.plan,
              model.slotsOn,
              meal,
              model.today,
              4,
              useByFridge || null
            ).map((f) => ({
              ...f,
              label: `${dayWords(f.day)} · ${model.slotName(f.slotId)}`
            }))
          }
        : null;
    void review.open(target);
  }

  function closeCooked() {
    review.close();
    cookedMeal = null;
  }

  const actions: PlanActions = {
    model,
    get readonly() {
      return readonly;
    },
    get desktop() {
      return !compact;
    },
    openMeal: (meal) => (sheet = { kind: 'meal', meal }),
    openItem: (meal, item) => (sheet = { kind: 'item', meal, item }),
    openCookOnce: (meal, item) => (cooking = { meal, item }),
    openCooked,
    add: (day, slotId) => (adding = { day, slotId }),
    openDay: (day) => (sheet = { kind: 'day', day }),
    carryMeal,
    // The cooking and its EAT card are one meal, so they move together, as one change with one
    // Undo. Tubs now before the cook day are flagged on the Week, not refused. It can't land on a
    // meal that is already planned: the meal would be folded into that one and lose its cooking.
    carryCook: (meal) => ({
      label: mealName(meal, model.plan),
      zones: false,
      drop: (day, slot) => {
        const to = slot ?? meal.slot_id;
        if (day === meal.date && to === meal.slot_id) return;
        if (model.mealAt(day, to)) {
          toasts.show('Cooking can only move to an empty meal.', { tone: 'problem' });
          return;
        }
        void model.drop({ meal: meal.id }, day, to, 'move');
      }
    }),
    carryItem: (meal, item) => ({
      label: itemName(item, model.plan),
      zones: true,
      leftoversOk: leftoversOk(meal),
      drop: (day, slot, mode) => {
        const to = slot ?? meal.slot_id;
        if (day === meal.date && to === meal.slot_id) return;
        void model.drop({ item: item.id }, day, to, mode);
      }
    })
  };

  function carryRecipe(recipe: RecipeRow): Carried {
    return {
      label: recipe.name,
      zones: false,
      drop: (day, slot) => {
        const to = slot ?? model.slotForDay(day);
        if (to !== null) void model.add({ recipe: { id: recipe.id, name: recipe.name } }, day, to);
      }
    };
  }

  function carryTub(tub: TubLeft): Carried {
    return {
      label: `${tub.recipe_name} tub ${tub.number}`,
      zones: false,
      drop: (day, slot) => {
        const to = slot ?? model.slotForDay(day);
        if (to !== null) void model.placeTub(tub.id, `${tub.recipe_name} tub`, day, to);
      }
    };
  }

  const range = $derived.by(() => {
    if (!model.anchor) return ''; // not loaded yet
    return model.view === 'week' && model.days[0]
      ? weekWords(model.days[0], model.today.slice(0, 4))
      : monthWords(model.anchor);
  });
  const empty = $derived(model.loaded && model.plan !== null && model.plan.meals.length === 0);
  const hasBatches = $derived((model.plan?.batch_cooks.length ?? 0) > 0);
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === 'Alt') drag.alt = true;
  }}
  onkeyup={(event) => {
    if (event.key === 'Alt') drag.alt = false;
  }}
/>

<div class="plan" class:fill={!compact}>
  <PageHeader title="Plan">
    {#snippet actions()}
      {#if model.view === 'week' && !compact}
        <PlanShowSwitch value={show} onchange={setShow} />
      {/if}
      <div class="view" role="group" aria-label="View">
        <button
          type="button"
          aria-pressed={model.view === 'week'}
          onclick={() => model.setView('week')}>Week</button
        >
        <button
          type="button"
          aria-pressed={model.view === 'month'}
          onclick={() => model.setView('month')}>Month</button
        >
      </div>
    {/snippet}
  </PageHeader>

  {#if model.view === 'week' && compact}
    <div class="showrow"><PlanShowSwitch value={show} onchange={setShow} /></div>
  {/if}

  <div class="toolbar">
    <!-- Only once the plan knows which week it is: while it can't load, no empty ‹ › (F67). -->
    {#if model.anchor}
      <div class="nav">
        <button
          type="button"
          aria-label={model.view === 'week' ? 'Previous week' : 'Previous month'}
          onclick={() => model.step(-1)}><Icon name="back" size={22} stroke={2.4} /></button
        >
        <span class="range" aria-live="polite">{range}</span>
        <button
          type="button"
          aria-label={model.view === 'week' ? 'Next week' : 'Next month'}
          onclick={() => model.step(1)}
          ><span class="flip"><Icon name="back" size={22} stroke={2.4} /></span></button
        >
      </div>
      <button
        type="button"
        class="today"
        disabled={!model.today || model.onToday}
        onclick={() => model.goToday()}>Today</button
      >
    {/if}
    {#if model.slots.length}
      <div class="meals" role="group" aria-label="Meals to show">
        <span class="meals-label">Meals</span>
        {#each model.slots as slot (slot.id)}
          <button
            type="button"
            aria-pressed={slot.enabled}
            disabled={readonly}
            onclick={() => void model.switchSlot(slot, !slot.enabled)}>{slot.name}</button
          >
        {/each}
      </div>
    {/if}
    {#if hasBatches}
      <span class="key">
        <span><i class="sw cook"></i>Cook day</span>
        <span><i class="sw tubs"></i>Its tubs</span>
        <span><i class="sw fresh"></i>Fresh</span>
      </span>
    {/if}
  </div>

  {#if readonly && model.loaded}
    <p class="note" role="status">
      {downLine(network.deviceOffline, (b) => `Plan changes ${b.when}.`)}
    </p>
  {/if}

  {#if !model.loaded && network.down}
    <OfflineNote screen="Plan" />
  {:else if model.problem && !model.loaded}
    <section class="problem" role="alert">
      <p>{model.problem}</p>
      <button type="button" onclick={() => void model.load()}>Try again</button>
    </section>
  {:else if !model.loaded}
    <p class="loading" role="status">Loading the plan…</p>
  {:else}
    {#if model.problem}
      <p class="note" role="alert">{model.problem}</p>
    {/if}
    {#if model.slotsOn.length === 0}
      <p class="note">All meals are switched off. Turn one on under Meals to plan it.</p>
    {:else}
      {#if empty && model.view === 'week'}
        <p class="empty">
          Nothing planned this week.
          {compact
            ? 'Tap + Add on a day to plan a meal.'
            : 'Drag a recipe up from the tray, or press + Add.'}
        </p>
      {/if}
      {#if model.view === 'week'}
        {#if past.length}
          <button
            type="button"
            class="earlier"
            aria-expanded={earlier}
            onclick={() => (earlier = !earlier)}
            >{earlier
              ? 'Hide earlier days'
              : `Earlier this week (${past.length} ${past.length === 1 ? 'day' : 'days'})`}</button
          >
        {/if}
        {#if show === 'cook'}
          <!-- Loaded when first asked for, so the Plan's first load stays small (size limit). -->
          {#await import('#lib/components/plan/PlanCook.svelte') then { default: Cook }}
            <Cook {actions} days={dayList} onstart={startCooking} />
          {/await}
        {:else if show === 'eat'}
          {#await import('#lib/components/plan/PlanEat.svelte') then { default: Eat }}
            <Eat {actions} days={dayList} oncook={showCook} />
          {/await}
        {:else if compact}
          <PlanDays {actions} days={dayList} />
        {:else}
          <PlanWeek {actions} />
        {/if}
      {:else if compact}
        <PlanMonthPhone {actions} selected={picked} onselect={(day) => (picked = day)} />
      {:else}
        <PlanMonth {actions} />
      {/if}
      {#if !compact && (model.view === 'month' || show === 'both')}
        <RecipeTray
          list={recipes}
          disabled={readonly}
          open={trayOpen}
          onopen={setTray}
          carry={carryRecipe}
          tubs={model.tubsLeft}
          today={model.today}
          {carryTub}
          onchooseTub={(tub) => (sheet = { kind: 'tubleft', tub })}
          onchoose={(recipe) =>
            (sheet = { kind: 'recipe', recipe: { id: recipe.id, name: recipe.name } })}
        />
      {/if}
    {/if}
  {/if}
</div>

<!-- The menu, Cook once, Plan a recipe and No portions are fetched when first asked for, so the
     Plan's first load stays under the size limit. -->
{#if sheetAsked}
  {#await import('#lib/components/plan/PlanSheet.svelte') then { default: PlanSheet }}
    <PlanSheet {actions} target={sheet} onclose={() => (sheet = null)} />
  {/await}
{/if}
{#if cookingAsked}
  {#await import('#lib/components/plan/CookOnce.svelte') then { default: CookOnce }}
    <CookOnce {actions} target={cooking} onclose={() => (cooking = null)} />
  {/await}
{/if}
{#if cookedAsked}
  {#await import('#lib/components/cooked/CookedReview.svelte') then { default: CookedReview }}
    <CookedReview
      {review}
      {leftover}
      {readonly}
      onclose={closeCooked}
      onconfirmed={async (leftovers, undoCooked, eatOn) => {
        const meal = cookedMeal;
        if (!meal) return true;
        const placed: Placed = { undo: null };
        const result = answered(
          await model.cooked(meal, leftovers, undoCooked, async () => placed.undo?.())
        );
        const name = meal.items.find((i) => i.id === leftovers?.item_id)?.recipe?.name;
        if (result === true && eatOn && leftovers && name)
          await eatLeftover(placed, name, meal.date, leftovers.count, eatOn);
        return result;
      }}
    />
  {/await}
{/if}
{#if addingAsked}
  {#await import('#lib/components/plan/PlanAdd.svelte') then { default: PlanAdd }}
    <PlanAdd {actions} target={adding} onclose={() => (adding = null)} />
  {/await}
{/if}
{#if model.noPortions || noPortionsAsked}
  {#await import('#lib/components/plan/NoPortions.svelte') then { default: NoPortions }}
    <NoPortions {actions} />
  {/await}
{/if}

{#if drag.carried}
  <div class="ghost" style:left="{drag.x}px" style:top="{drag.y}px" aria-hidden="true">
    {drag.carried.label}
  </div>
{/if}

<style>
  .plan {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }

  /* On a computer the grid fills the height under the header (UX: the week grid fills it). */
  .plan.fill {
    min-height: calc(100dvh - 2 * var(--space-10));
  }

  /* The title keeps its words whole: at a large text size the buttons wrap under it. */
  .plan :global(.page-header) {
    flex-wrap: wrap;
  }

  .toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-6);
  }

  .nav {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2);
    border-radius: var(--radius-full);
    background: var(--color-surface);
  }

  .nav button {
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    display: grid;
    place-items: center;
    padding: 0;
    cursor: pointer;
  }

  .flip {
    display: grid;
    transform: rotate(180deg);
  }

  .range {
    min-width: 7ch;
    padding: 0 var(--space-3);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: center;
  }

  .today {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .today:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .meals {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-surface);
  }

  .meals-label {
    margin-right: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .meals button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .meals button[aria-pressed='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .meals button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .key {
    display: flex;
    gap: var(--space-6);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .key span {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .sw {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }

  .sw.cook {
    background: var(--batch-1);
  }

  .sw.tubs {
    background: var(--batch-1-soft);
  }

  .sw.fresh {
    border: 1px solid var(--color-add-border);
  }

  .showrow {
    display: flex;
    flex-direction: column;
  }

  .showrow :global(.show) {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
  }

  .earlier {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .view {
    display: flex;
    padding: var(--space-2);
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
  }

  .view button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .view button[aria-pressed='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  .note,
  .empty,
  .loading {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .note {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
  }

  .problem {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    padding: var(--space-8);
    border-radius: var(--radius-3xl);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .problem button {
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: inherit;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .ghost {
    position: fixed;
    z-index: 100;
    max-width: 240px;
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: 0 12px 28px rgba(23, 32, 28, 0.2);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    pointer-events: none;
    transform: translate(12px, 12px) rotate(-2deg);
    overflow-wrap: anywhere;
  }
</style>
