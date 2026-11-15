<script lang="ts">
  // Today (mockups Main, Desktop-Today and their dark twins): what we are eating, the tubs
  // left, what to use soon, what to buy, the next cook, and "Did you cook Sambar?" for a planned
  // meal whose day has come (Cooked it · Didn't · Move it). A household with nothing yet sees
  // "Your kitchen is ready". Online only, like the Plan: offline it shows the copy saved last
  // time, with the answer buttons switched off. "Did you buy 2?" shows here as well as on
  // Shopping (spec, "Offline shopping-list sync"). Docs: docs/dev/api-0.2.md section 6.3c.
  import Icon from '#lib/components/Icon.svelte';
  import { downLine } from '#lib/downWords.js';
  import { resolve } from '$app/paths';
  import { untrack } from 'svelte';
  import CookedReview, { type LeftoverOptions } from '#lib/components/cooked/CookedReview.svelte';
  import FirstDay from '#lib/components/today/FirstDay.svelte';
  import MoveSheet from '#lib/components/today/MoveSheet.svelte';
  import WaitingCard from '#lib/components/today/WaitingCard.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import DoubleTickCard from '#lib/components/shopping/DoubleTickCard.svelte';
  import { CookReview, answered } from '#lib/cookReview.svelte.js';
  import MealRecipes from '#lib/components/today/MealRecipes.svelte';
  import { cookTarget, isCookable } from '#lib/cookTargets.js';
  import { dateWords, whenWords as packetWhen } from '#lib/dates.js';
  import { startsByNow } from '#lib/startWords.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { dayFull, dayShort, dayOfMonth } from '#lib/planDates.js';
  import {
    colourOfBatch,
    eatenItems,
    itemName,
    nextFreeMeals,
    tubOf,
    whoseTub
  } from '#lib/planMeals.js';
  import { eatLeftover, type Placed } from '#lib/eatLeftover.js';
  import { getHousehold } from '#lib/client/household.js';
  import { cookedUseBy, eatOnUntil, type TubLife } from '#lib/tubUseBy.js';
  import { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import { TodayModel } from '#lib/today.svelte.js';
  import { dayWords, partsCooked, weekRows, whenWords } from '#lib/todayWords.js';
  import type { PlanItem, PlanMeal } from '#lib/client/plan.js';
  import type { WaitingMeal } from '#lib/client/today.js';

  const model = new TodayModel();
  // The shopping list's own copy: "to buy", and the "Did you buy 2?" cards.
  const shop = new ShoppingModel();

  // The household's today, from the server; the plan covers a week before and a week after.
  $effect(() => {
    void kitchen.version;
    untrack(() => void model.load());
  });
  $effect(() => {
    void kitchen.version;
    untrack(() => void shop.open());
  });
  $effect(() => {
    const heard = live.shopping;
    untrack(() => {
      if (shop.loaded && heard > shop.copy.cursor) void shop.load();
    });
  });

  let wasOffline = false;
  $effect(() => {
    // `down`, not `offline`: the note shows from the first failure, so the page fetches again
    // when anything answers, even before the bar came (F67 review).
    if (network.down) wasOffline = true;
    else if (wasOffline) {
      wasOffline = false;
      void model.load();
    }
  });

  function onVisible() {
    if (document.visibilityState === 'visible') {
      void model.load();
      void shop.open();
    }
  }

  // "Cooked it": the one review for a meal waiting on Today and for a meal eaten today.
  const review = new CookReview();
  let answering = $state<WaitingMeal | null>(null);
  let leftover = $state<LeftoverOptions | null>(null);

  /** F65: the next free meals in the week on Today, for "Eat it on…". */
  function eatOnOptions(meal: PlanMeal, until: string | null) {
    const data = model.data;
    if (!data) return [];
    const slots = data.slots
      .filter((s) => s.enabled)
      .sort((a, b) => a.position - b.position || a.id - b.id);
    return nextFreeMeals(data.plan, slots, meal, data.today, 4, until).map((f) => ({
      ...f,
      label: `${dayWords(f.day, data.today)} · ${model.slotName(f.slotId)}`
    }));
  }

  function openCooked(w: WaitingMeal, only: PlanItem | null = null) {
    const meal = model.mealOf(w);
    if (!meal || !model.data) return;
    answering = w;
    // F128: "Eat it on…" only up to the tub's use-by, the fridge's or the freezer's as the
    // review's place says; with none known, no meal is offered.
    const useBy = {
      ...(w.use_by_fridge ? { useByFridge: w.use_by_fridge } : {}),
      ...(w.use_by_freezer ? { useByFreezer: w.use_by_freezer } : {})
    };
    const until = eatOnUntil(useBy);
    leftover =
      w.leftover_item_id !== null
        ? {
            itemId: w.leftover_item_id,
            today: model.data.today,
            eatOn: until ? eatOnOptions(meal, until) : [],
            ...useBy
          }
        : null;
    const when = `${whenWords(w.date, model.data.today)} · ${model.slotName(w.slot_id).toLowerCase()}`;
    void review.open(cookTarget(model.data.plan, meal, when, only));
  }

  /**
   * A meal eaten today that is still planned: the same review. Its tub's use-by is counted from
   * the household's tub life, as the server counts it (F128).
   */
  async function cookEating(meal: PlanMeal, only: PlanItem | null = null) {
    // The recipe pressed, else the first not cooked yet, never one cooked before (F157 review).
    const first = only ?? meal.items.find((i) => isCookable(i) && !i.cooked);
    let life: TubLife | null = null;
    try {
      const household = await getHousehold();
      life = { fridgeDays: household.tub_fridge_days, freezerMonths: household.tub_freezer_months };
    } catch {
      // Not reached: the review still opens, with no "Eat it on…" meals and the usual use-by.
    }
    const useBy = cookedUseBy(meal.date, model.data?.today ?? meal.date, life);
    openCooked(
      {
        meal_id: meal.id,
        date: meal.date,
        slot_id: meal.slot_id,
        leftover_item_id: first?.id ?? null,
        use_by_fridge: useBy.useByFridge ?? '',
        use_by_freezer: useBy.useByFreezer ?? ''
      },
      only
    );
  }

  function closeCooked() {
    review.close();
    answering = null;
  }
  let moving = $state<WaitingMeal | null>(null);

  const data = $derived(model.data);
  const today = $derived(data?.today ?? '');
  const usedSoon = $derived((data?.use_soon_lots.length ?? 0) + (data?.use_soon_tubs.length ?? 0));
  const toBuy = $derived(shop.loaded ? String(shop.counts.toBuy) : '–');
  const tubsLeft = $derived(
    data ? `${data.tubs_left.length}${data.tubs_left_more ? '+' : ''}` : '0'
  );

  /** M3: recipes whose long wait is to be started today (or should have been), not begun yet. */
  const starts = $derived(data ? startsByNow(data.plan, today) : []);

  /** F150: the seven days from today, one row each. */
  const week = $derived(data ? weekRows(data.plan, data.slots, today) : []);

  /** "+ Plan": the Plan, on the week of that day. */
  function planOn(day: string): string {
    return `${resolve('/(app)/plan')}?day=${day}`;
  }

  /** F160: a meal with several recipes shows one line for each. */
  const parts = (meal: PlanMeal) => meal.items.filter((i) => i.kind === 'recipe').length > 1;
  const partsWords = (meal: PlanMeal) => {
    const recipes = meal.items.filter(isCookable);
    const done = recipes.filter((i) => i.cooked).length;
    return partsCooked(done, recipes.length);
  };

  const nothingToday = $derived(!!data && model.eating.length === 0);
</script>

<svelte:document onvisibilitychange={onVisible} />

<PageHeader title="Today" overline={today ? dayFull(today) : undefined}>
  {#snippet actions()}
    <a class="import" href={resolve('/(app)/recipes/import')}>+ Import a recipe</a>
  {/snippet}
</PageHeader>

{#if !data && network.down}
  <!-- Offline (or the server down) with no saved copy: the same note as every page (F67). -->
  <OfflineNote screen="Today" />
{:else if model.problem && !data}
  <p class="problem" role="alert">{model.problem}</p>
{:else if !data}
  <p class="loading">Loading…</p>
{:else if data.first_day}
  <FirstDay />
{:else}
  {#if model.readonly}
    <p class="offline" role="status">
      {downLine(
        network.deviceOffline,
        (b) => `Today changes ${b.when}. This is what was saved last time.`
      )}
    </p>
  {/if}

  <div class="today">
    <div class="stats" data-testid="today-stats">
      <div class="stat tubs" class:none={tubsLeft === '0'}>
        <b>{tubsLeft}</b><span>tubs left</span>
      </div>
      <div class="stat soon">
        <b>{usedSoon}</b><span>use soon</span>
      </div>
      <div class="stat buy">
        <b>{toBuy}</b><span>to buy</span>
      </div>
    </div>

    {#if model.asking}
      <WaitingCard
        {model}
        waiting={model.asking}
        oncooked={() => model.asking && openCooked(model.asking)}
        onmove={() => (moving = model.asking)}
      />
    {/if}

    <!-- Import from Mealie finished (0.9.5): a note for a day; loaded when there is one. -->
    {#if data.mealie}
      {#await import('#lib/components/today/MealieNote.svelte') then { default: MealieNote }}
        {#if data.mealie}<MealieNote note={data.mealie} />{/if}
      {/await}
    {/if}

    <!-- Start tonight (M3): a recipe with a long wait whose start is today; loaded when there is one. -->
    {#each starts as entry (entry.key)}
      {#await import('#lib/components/today/StartTonight.svelte') then { default: StartTonight }}
        <StartTonight
          {entry}
          plan={data.plan}
          {today}
          slotName={model.slotName(entry.meal.slot_id)}
          disabled={model.readonly}
          onchanged={() => void model.load()}
        />
      {/await}
    {/each}

    {#each shop.cards as question (question.id)}
      <DoubleTickCard model={shop} {question} />
    {/each}

    <section class="eating" aria-labelledby="eating-h" data-testid="today-eating">
      <h2 id="eating-h">Eating today</h2>
      {#if nothingToday}
        <div class="card empty">
          <p class="title">Nothing planned for today</p>
          <p class="muted">Plan a meal and it shows here.</p>
          <a class="pill" href={resolve('/(app)/plan')}>Plan a meal</a>
        </div>
      {/if}
      {#each model.eating as meal (meal.id)}
        {@const slot = model.slotName(meal.slot_id)}
        <div class="card meal">
          <div class="head">
            <div class="who">
              <span class="overline">{slot}</span>
              <span class="name"
                >{eatenItems(meal, data.plan)
                  .map((i) => itemName(i, data.plan))
                  .join(' & ') || 'Empty meal'}</span
              >
            </div>
            {#if parts(meal)}
              {#if partsWords(meal)}<span class="muted nowrap">{partsWords(meal)}</span>{/if}
            {:else if meal.status === 'cooked'}<span class="muted">Cooked</span>{/if}
          </div>
          {#if parts(meal)}
            <MealRecipes
              {meal}
              plan={data.plan}
              disabled={model.readonly}
              oncook={(item) => void cookEating(meal, item)}
            />
          {/if}
          {#if meal.items.some((i) => i.kind === 'tub')}
            <div class="chips">
              {#each meal.items.filter((i) => i.kind === 'tub') as item (item.id)}
                {@const found = tubOf(data.plan, item)}
                {#if found}
                  {@const n = colourOfBatch(found.batch)}
                  <span
                    class="chip"
                    style:--soft="var(--batch-{n}-soft)"
                    style:--soft-text="var(--batch-{n}-soft-text)"
                    >{whoseTub(found.tub, data.people, data.plan.removed_people) ?? 'Everyone'} · tub
                    {found.tub.number} of {found.batch.tub_count}</span
                  >
                {/if}
              {/each}
            </div>
          {/if}
          {#if meal.kcal !== null}<p class="muted">{meal.kcal} kcal each</p>{/if}
          {#if !parts(meal) && meal.status === 'planned' && meal.items.some((i) => isCookable(i) && !i.cooked)}
            <button
              type="button"
              class="cooked-it"
              disabled={model.readonly}
              onclick={() => void cookEating(meal)}>Cooked it</button
            >
          {/if}
        </div>
      {/each}
    </section>

    <section class="soon" aria-labelledby="soon-h" data-testid="today-use-soon">
      <div class="row">
        <h2 id="soon-h">Use soon</h2>
        <a href={resolve('/(app)/recipes')}>Find a recipe</a>
      </div>
      {#if usedSoon === 0}
        <div class="card empty">
          <p class="muted">Nothing needs using up soon.</p>
        </div>
      {:else}
        <ul class="card list">
          {#each data.use_soon_tubs as tub (`tub-${tub.batch_id}-${tub.place.id}`)}
            <li>
              <span class="what"
                ><span class="n">{tub.recipe_name}</span><span class="muted"
                  >{tub.place.name} · {tub.words}</span
                ></span
              >
              <span class="when">{dateWords(tub.use_by, tub.days_left)}</span>
            </li>
          {/each}
          {#each data.use_soon_lots as lot (`lot-${lot.id}`)}
            {@const when = packetWhen(lot.date_kind, lot.use_by, lot.days_left, { capital: true })}
            <li>
              <span class="what"
                ><span class="n">{lot.food.name}</span><span class="muted"
                  >{lot.place.name} · {lot.stock.short ?? lot.stock.display}</span
                ></span
              >
              <span class="when" class:bb={when.tone === 'bb'}
                >{when.text}{when.ago ? ` · ${when.ago}` : ''}</span
              >
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {#if data.next_cook}
      <section class="next" aria-label="Next cook" data-testid="today-next-cook">
        <div class="what">
          <span class="overline">Next cook · {dayWords(data.next_cook.date, today)}</span>
          <span class="name"
            >{data.next_cook.recipe_name} · {data.next_cook.tub_count}
            {data.next_cook.tub_count === 1 ? 'tub' : 'tubs'}</span
          >
        </div>
        <a href={resolve('/(app)/shopping')}>Shop list</a>
      </section>
    {/if}

    <section class="week" aria-labelledby="week-h">
      <div class="row">
        <h2 id="week-h">This week</h2>
        <a href={resolve('/(app)/plan')}>Open plan</a>
      </div>
      <ul class="days">
        {#each week as d (d.day)}
          <li class:now={d.isToday} data-testid="week-{d.day}">
            <span class="dow">
              {d.isToday ? 'Today' : dayShort(d.day)}
              <span
                >{d.isToday ? `${dayShort(d.day)} ${dayOfMonth(d.day)}` : dayOfMonth(d.day)}</span
              >
            </span>
            {#if d.name !== null}
              <span class="what">
                <span class="name">{d.name}</span>
                <span class="more">{d.count}</span>
              </span>
              {#if d.cooks}
                <span class="cooks" title="You cook"
                  ><Icon name="pan" size={14} stroke={2.4} />Cook</span
                >
              {/if}
            {:else}
              <span class="what"><span class="name none">Nothing planned</span></span>
              <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved in planOn; only the query is added -->
              <a class="plan" href={planOn(d.day)}>+ Plan</a>
            {/if}
          </li>
        {/each}
      </ul>
      <span class="note">The name is each day’s dinner (or its last meal).</span>
    </section>
  </div>
{/if}

<CookedReview
  {review}
  {leftover}
  readonly={model.readonly}
  onclose={closeCooked}
  onconfirmed={async (leftovers, undoCooked, eatOn) => {
    const waiting = answering;
    if (!waiting) return true;
    const placed: Placed = { undo: null };
    const title = review.target?.title; // F161: only what this press cooked
    const result = answered(
      await model.cooked(waiting, leftovers, undoCooked, async () => placed.undo?.(), title)
    );
    const meal = model.mealOf(waiting);
    const name = meal?.items.find((i) => i.id === leftovers?.item_id)?.recipe?.name;
    if (result === true && meal && eatOn && leftovers && name)
      await eatLeftover(placed, name, meal.date, leftovers.count, eatOn);
    return result;
  }}
/>
<MoveSheet {model} waiting={moving} onclose={() => (moving = null)} />

<style>
  .today {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    max-width: 1100px;
  }

  .loading,
  .problem {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .offline {
    max-width: 1100px;
    margin-bottom: var(--space-6);
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
  }

  .import {
    display: none;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 18px;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .stats {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 14px 14px 12px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .stat b {
    font-size: 1.875rem;
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
  }

  .stat span {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .soon .row a,
  .week .row a {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .stat.tubs b {
    color: var(--color-tubs);
  }

  /* "0 tubs left" is not a warm number: nothing to look at (0.7 paper cuts). */
  .stat.tubs.none b {
    color: var(--color-text-muted);
  }

  .stat.soon b {
    color: var(--color-use-soon);
  }

  .stat.buy b {
    color: var(--color-accent);
  }

  h2 {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  section.eating,
  section.soon,
  section.week {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .row a {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    color: var(--color-accent-on-soft);
  }

  .card {
    padding: var(--space-8);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .card.meal {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .card.empty {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .who {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .name,
  .title {
    font-size: 1.125rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .nowrap {
    white-space: nowrap;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    padding: 6px 12px;
    border-radius: var(--radius-full);
    background: var(--soft, var(--color-tub-chip));
    color: var(--soft-text, var(--color-tub-chip-text));
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .cooked-it {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 18px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .cooked-it:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 18px;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .list {
    padding-block: var(--space-1);
  }

  .list li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: 52px;
    border-bottom: 1px solid var(--color-divider);
  }

  .list li:last-child {
    border-bottom: none;
  }

  .what {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .n {
    font-size: 0.9375rem;
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .when {
    flex: none;
    padding: 4px 10px;
    border-radius: var(--radius-full);
    background: var(--color-use-soon-chip);
    color: var(--color-use-soon-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    max-width: 55%;
    text-align: right;
  }

  /* A passed Best before is quiet: grey, "probably fine" (0.8). */
  .when.bb {
    background: var(--color-fill);
    color: var(--color-text-muted);
  }

  .next {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    padding: var(--space-8);
    border-radius: var(--radius-2xl);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .next .overline {
    color: inherit;
    opacity: 0.8;
  }

  .next .name {
    font-size: 1rem;
  }

  .next a {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
    white-space: nowrap;
  }

  /* F150 (mockup Dark-Today08-Phone): a row for each day inside one card, rows at least 44 px;
     a long name ends with an ellipsis. The same rows on a computer. */
  .days {
    padding: 0 var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .days li {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: var(--space-3) 0;
    border-top: 1px solid var(--color-border);
  }

  .days li:first-child {
    border-top: none;
  }

  .days li.now .dow {
    color: var(--color-accent-on-soft);
  }

  .dow {
    display: flex;
    flex: none;
    flex-direction: column;
    width: 3.6rem;
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
  }

  .dow span {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
  }

  .what {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    overflow: hidden;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .name.none {
    color: var(--color-text-muted);
    font-weight: var(--weight-semibold);
  }

  .more {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
  }

  .cooks {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-cook-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  a.plan {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .week .note {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
  }

  @media (min-width: 768px) {
    .import {
      display: inline-flex;
    }
  }
</style>
