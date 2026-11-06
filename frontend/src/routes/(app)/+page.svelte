<script lang="ts">
  // Today (mockups Main, Desktop-Today and their dark twins): what we are eating, the tubs
  // left, what to use soon, what to buy, the next cook, and "Did you cook Sambar?" for a planned
  // meal whose day has come (Cooked it · Didn't · Move it). A household with nothing yet sees
  // "Your kitchen is ready". Online only, like the Plan: offline it shows the copy saved last
  // time, with the answer buttons switched off. "Did you buy 2?" shows here as well as on
  // Shopping (spec, "Offline shopping-list sync"). Docs: docs/dev/api-0.2.md section 6.3c.
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
  import CookedParts from '#lib/components/CookedParts.svelte';
  import { cookTarget } from '#lib/cookTargets.js';
  import { dateWords } from '#lib/dates.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { addDays, dayFull, dayShort, dayOfMonth } from '#lib/planDates.js';
  import { colourOfBatch, itemName, nextFreeMeals, tubOf, whoseTub } from '#lib/planMeals.js';
  import { eatLeftover, type Placed } from '#lib/eatLeftover.js';
  import { getHousehold } from '#lib/client/household.js';
  import { eatOnUntil, leftoverUseBy, type TubLife } from '#lib/tubUseBy.js';
  import { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import { TodayModel } from '#lib/today.svelte.js';
  import { dayWords, mealsWords, whenWords } from '#lib/todayWords.js';
  import type { PlanMeal } from '#lib/client/plan.js';
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

  function openCooked(w: WaitingMeal) {
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
    void review.open(cookTarget(model.data.plan, meal, when));
  }

  /**
   * A meal eaten today that is still planned: the same review. Its tub's use-by is counted from
   * the household's tub life, as the server counts it (F128).
   */
  async function cookEating(meal: PlanMeal) {
    // The first recipe not cooked yet, never one cooked before (F157 review).
    const first = meal.items.find((i) => i.kind === 'recipe' && !i.cooked);
    let life: TubLife | null = null;
    try {
      const household = await getHousehold();
      life = { fridgeDays: household.tub_fridge_days, freezerMonths: household.tub_freezer_months };
    } catch {
      // Not reached: the review still opens, with no "Eat it on…" meals and the usual use-by.
    }
    const useBy = leftoverUseBy(meal.date, life);
    openCooked({
      meal_id: meal.id,
      date: meal.date,
      slot_id: meal.slot_id,
      leftover_item_id: first?.id ?? null,
      use_by_fridge: useBy.useByFridge ?? '',
      use_by_freezer: useBy.useByFreezer ?? ''
    });
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

  const daysLeft = (iso: string) => Math.round((Date.parse(iso) - Date.parse(today)) / 86_400_000);

  /** The seven days from today, with how many meals are on each (This week, on a computer). */
  const week = $derived(
    data
      ? Array.from({ length: 7 }, (_, i) => {
          const day = addDays(today, i);
          const count = data.plan.meals.filter(
            (m) => m.date === day && (m.status === 'planned' || m.status === 'cooked')
          ).length;
          return { day, count };
        })
      : []
  );

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
                >{meal.items.map((i) => itemName(i, data.plan)).join(' & ') || 'Empty meal'}</span
              >
            </div>
            {#if meal.status === 'cooked'}<span class="muted">Cooked</span>{/if}
          </div>
          <CookedParts {meal} plan={data.plan} />
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
                    >{whoseTub(found.tub, data.people) ?? 'Everyone'} · tub {found.tub.number} of {found
                      .batch.tub_count}</span
                  >
                {/if}
              {/each}
            </div>
          {/if}
          {#if meal.kcal !== null}<p class="muted">{meal.kcal} kcal each</p>{/if}
          {#if meal.status === 'planned' && meal.items.some((i) => i.kind === 'recipe' && !i.cooked)}
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
          {#each data.use_soon_tubs as tub (`tub-${tub.id}`)}
            <li>
              <span class="what"
                ><span class="n">{tub.recipe_name} · tub {tub.number} of {tub.tub_count}</span><span
                  class="muted">{tub.place_kind === 'freezer' ? 'Freezer' : 'Fridge'} · tub</span
                ></span
              >
              <span class="when">{dateWords(tub.use_by, daysLeft(tub.use_by))}</span>
            </li>
          {/each}
          {#each data.use_soon_lots as lot (`lot-${lot.id}`)}
            <li>
              <span class="what"
                ><span class="n">{lot.food.name}</span><span class="muted"
                  >{lot.place.name} · {lot.stock.short ?? lot.stock.display}</span
                ></span
              >
              <span class="when">{dateWords(lot.use_by, lot.days_left)}</span>
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
          <li class:today={d.day === today}>
            <span>{dayShort(d.day)}</span><b>{dayOfMonth(d.day)}</b><span class="muted"
              >{mealsWords(d.count)}</span
            >
          </li>
        {/each}
      </ul>
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
    const result = answered(
      await model.cooked(waiting, leftovers, undoCooked, async () => placed.undo?.())
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

  .week {
    display: none;
  }

  .days {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .days li {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: var(--space-4) var(--space-2);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    font-size: var(--text-base);
    text-align: center;
  }

  .days li.today {
    outline: 2px solid var(--color-accent);
  }

  .days b {
    font-size: var(--text-xl);
  }

  @media (min-width: 768px) {
    .import {
      display: inline-flex;
    }

    .week {
      display: flex;
    }
  }
</style>
