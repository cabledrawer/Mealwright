<script lang="ts">
  import Button from '#lib/components/Button.svelte';
  import Lazy from '#lib/components/Lazy.svelte';
  // Batch cook (Experimental; mockups Dark-BatchPick08-Phone and -Desktop): recipes picked from
  // your own to cook together in one session. The computer has its own sidebar entry; on the phone
  // this is the Plan's third tab (Week | Month | Batch cook). "Plan this batch" sends each recipe
  // through Cook once, one sheet after another, and plans it all in one change with one Undo.
  // Online only, like the rest of the plan.
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { downLine } from '#lib/downWords.js';
  import { batchCook, markNoteSeen, noteSeen } from '#lib/batchCook.svelte.js';
  import { askPicks, reopenLast, type Flow, type Picked } from '#lib/batchFlow.js';
  import { BatchPickModel, COUNTS } from '#lib/batchPick.svelte.js';
  import { optionalAsk } from '#lib/optionalAsk.svelte.js';
  import type { BatchBody, PreviewTub } from '#lib/client/plan.js';
  import { previewSession, type SessionBody } from '#lib/client/batch.js';
  import { getKitchen, type Kitchen } from '#lib/client/household.js';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import YourKitchen from '#lib/components/YourKitchen.svelte';
  import type { Ahead, Earlier } from '#lib/cookOnce.svelte.js';
  import { askBatchMethod } from '#lib/lazyActions.js';
  import { network } from '#lib/network.svelte.js';
  import { dayShort, dayOfMonth, monthShort } from '#lib/planDates.js';
  import { PlanModel } from '#lib/plan.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { timeWords } from '#lib/timeWords.js';
  import { PHONE_QUERY } from '#lib/layout.js';

  const model = new BatchPickModel();
  const plan = new PlanModel();
  const readonly = $derived(network.offline);

  // Two widths, as the Plan: under 768 px the bottom tabs, and this is the Plan's tab.
  let phone = $state(typeof matchMedia === 'function' && matchMedia(PHONE_QUERY).matches);
  $effect(() => {
    const query = matchMedia(PHONE_QUERY);
    const on = () => (phone = query.matches);
    query.addEventListener('change', on);
    return () => query.removeEventListener('change', on);
  });

  /** "2 h 55 min one by one", and on a computer " · hob 4 · pressure cooker 1 · oven yes " (the space is for the Change button after it). One string, so
   * the space before each dot is never lost where an {#if} begins (RF5). */
  function oneByOneWords(result: {
    one_by_one_minutes: number;
    kitchen: { hob_rings: number; pressure_cookers: number; oven: boolean };
  }): string {
    const k = result.kitchen;
    return (
      `${timeWords(result.one_by_one_minutes)} one by one` +
      (phone
        ? ''
        : ` · hob ${k.hob_rings} · pressure cooker ${k.pressure_cookers} · oven ${k.oven ? 'yes' : 'no'} `)
    );
  }

  // Changing a session: /batch-cook?change=<session id>, from the Plan's card.
  const changing = $derived(Number(page.url.searchParams.get('change')) || null);
  let changingDay = $state<string | null>(null);

  // --- The first-time note and Your kitchen ---------------------------------------------------
  let noteShown = $state(false);
  let kitchenNow = $state<Kitchen | null>(null);
  let kitchenOpen = $state(false);
  let kitchenOpener = $state<HTMLElement | null>(null);
  let askedKitchen = false;

  onMount(async () => {
    noteShown = !noteSeen(session.me?.id);
    void batchCook.load();
    void plan.load();
    if (changing !== null) {
      const { getSession } = await import('#lib/client/batch.js');
      try {
        const found = await getSession(changing);
        changingDay = found.cook_day;
        await model.startFrom(
          found.cook_day,
          found.recipes.flatMap((r) => (r.recipe_id === null ? [] : [r.recipe_id]))
        );
      } catch {
        await model.load();
      }
    } else {
      await model.load();
    }
  });

  // On first use, if the kitchen has not been asked, Your kitchen opens first.
  $effect(() => {
    const result = model.result;
    if (!result || askedKitchen) return;
    askedKitchen = true;
    kitchenNow = result.kitchen;
    if (!result.kitchen.asked && !readonly) kitchenOpen = true;
  });

  function gotIt() {
    markNoteSeen(session.me?.id);
    noteShown = false;
  }

  async function openKitchen(event: Event) {
    kitchenOpener = event.currentTarget as HTMLElement;
    kitchenNow ??= await getKitchen().catch(() => null);
    if (kitchenNow) kitchenOpen = true;
  }

  // --- Reading ---------------------------------------------------------------------------------
  const dayChip = (iso: string, first: boolean) =>
    first
      ? `${dayShort(iso)} ${dayOfMonth(iso)} ${monthShort(iso)}`
      : `${dayShort(iso)} ${dayOfMonth(iso)}`;

  const soonWords = (days: number) => (days <= 0 ? 'today' : days === 1 ? '1 day' : `${days} days`);

  let other = $state(false);
  const enough = $derived(model.picks.length >= 2);

  // --- Plan this batch: one Cook once sheet after another ------------------------------------
  let flow = $state<Flow | null>(null);
  let flowAsked = $state(false);
  /** What each recipe's sheet placed so far: the later sheets show those meals as taken (F229). */
  let earlier = $state<Earlier[]>([]);
  // The questions of a recipe are on show (the Cook once sheet comes after them).
  let asking = $state(false);

  /** Ask what adding the recipe to the plan asks (the way of cooking it, then the optional
   * ingredients), then show its Cook once sheet. Cancelling any question plans nothing. */
  async function open(at: number, bodies: BatchBody[], picked: Picked[]) {
    const pick = model.picks[at];
    if (!pick || !model.cookDay) return;
    asking = true;
    let answer: Picked | null;
    try {
      answer = await askPicks(
        pick.recipe_id,
        `${dayShort(model.cookDay)} ${dayOfMonth(model.cookDay)}`,
        {
          method: askBatchMethod,
          optional: (id, where, method) =>
            optionalAsk.ask({ id }, where, { method, button: 'Next' })
        }
      );
    } finally {
      asking = false;
    }
    flow = answer === null ? null : { at, bodies, picked: [...picked, answer] };
  }

  function plan_() {
    if (!enough || readonly || !model.cookDay || asking) return;
    flowAsked = true;
    earlier = [];
    void open(0, [], []);
  }

  function sessionBody(
    bodies: BatchBody[],
    picked: Picked[],
    forPreview = false
  ): SessionBody | null {
    if (!model.cookDay) return null;
    // No meal is sent: the server picks the last one with no recipe that day, and a change keeps
    // the session's own.
    return {
      date: model.cookDay,
      ...(forPreview && changing !== null ? { session_id: changing } : {}),
      recipes: bodies.map((b, i) => ({
        ...b,
        ...picked[i],
        recipe_id: model.picks[i]!.recipe_id
      }))
    };
  }

  const ahead = $derived.by<Ahead | null>(() => {
    if (!flow || !model.cookDay) return null;
    const at = flow.at;
    const pick = model.picks[at];
    if (!pick) return null;
    const day = model.cookDay;
    const before = flow.bodies.slice(0, at);
    const picked = flow.picked;
    return {
      name: pick.name,
      day,
      slotId: null,
      position: `${at + 1} of ${model.picks.length}`,
      last: at === model.picks.length - 1,
      before: earlier.slice(0, at),
      preview: (body) => {
        const so_far = sessionBody([...before, body], picked, true);
        if (!so_far) return Promise.reject(new Error('No meal'));
        return previewSession({ ...so_far, recipes: so_far.recipes.slice(0, at + 1) });
      },
      save: (body, tubs) => void next(body, tubs)
    };
  });

  async function next(body: BatchBody, tubs: PreviewTub[]) {
    if (!flow) return;
    const bodies = [...flow.bodies, body];
    earlier = [
      ...earlier.slice(0, bodies.length - 1),
      { name: model.picks[bodies.length - 1]?.name ?? '', tubs }
    ];
    const picked = flow.picked;
    if (bodies.length < model.picks.length) {
      flow = null; // the next recipe's questions, then its sheet
      void open(bodies.length, bodies, picked);
      return;
    }
    const made = sessionBody(bodies, picked);
    flow = null;
    if (!made) return;
    const result =
      changing !== null
        ? await plan.changeBatch(changing, made, bodies.length)
        : await plan.planBatch(made, bodies.length);
    if (result.ok) {
      const to = resolve('/(app)/plan');
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
      await goto(`${to}?day=${made.date}`);
    } else if (!result.cancelled) {
      // Refused: the last sheet is offered again, with every answer so far kept (H10).
      flow = reopenLast(bodies, picked);
    }
  }

  const cancelFlow = () => (flow = null);
  const slotMissing = $derived(plan.loaded && plan.slotsOn.length === 0);
</script>

<div class="batch">
  {#if phone}
    <PageHeader title="Plan">
      {#snippet actions()}
        <span class="exp"><Icon name="flask" size={13} stroke={2.4} />Experimental</span>
      {/snippet}
    </PageHeader>
    <div class="view" role="group" aria-label="Plan views">
      <a href={resolve('/(app)/plan')}>Week</a>
      <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved; only the query is added -->
      <a href="{resolve('/(app)/plan')}?view=month">Month</a>
      <span class="on" aria-current="page"
        >Batch cook<Icon name="flask" size={14} stroke={2.4} /><span class="visually-hidden"
          >Experimental</span
        ></span
      >
    </div>
  {:else}
    <PageHeader title="Batch cook">
      {#snippet actions()}
        <span class="exp"><Icon name="flask" size={13} stroke={2.4} />Experimental</span>
      {/snippet}
    </PageHeader>
    <p class="muted">Picks come only from your own recipes.</p>
  {/if}

  {#if !batchCook.shown}
    <EmptyState title="Batch cook is switched off">
      An admin can switch it on in Settings.
    </EmptyState>
  {:else if !model.result && network.down}
    <OfflineNote screen="Plan" />
  {:else if model.problem && !model.result}
    <section class="problem" role="alert">
      <p>{model.problem}</p>
      <button type="button" onclick={() => void model.load()}>Try again</button>
    </section>
  {:else if !model.result}
    <p class="muted" role="status">Finding recipes…</p>
  {:else}
    {#if noteShown}
      <p class="note">
        The picks and timings are guesses. Swap a recipe if it’s wrong, and fix a step’s timing when
        you edit the recipe.
        <button type="button" class="link" onclick={gotIt}>Got it</button>
      </p>
    {/if}
    {#if readonly}
      <p class="note" role="status">
        {downLine(network.deviceOffline, (b) => `Batch cook changes ${b.when}.`)}
      </p>
    {/if}
    {#if model.problem}<p class="note" role="alert">{model.problem}</p>{/if}
    {#if changingDay}<p class="muted">
        Changing the batch cook on {dayShort(changingDay)}
        {dayOfMonth(changingDay)}.
      </p>{/if}

    {#if model.result.pool === 0}
      <EmptyState title="No recipes to batch yet">
        Batch cook picks from your own recipes that have steps. Add a recipe, or add steps to one.
      </EmptyState>
      <a class="add" href={resolve('/(app)/recipes')}>Go to recipes</a>
    {:else}
      <div class="controls">
        <div class="group">
          <span class="h2" id="cookday">Cook day</span>
          <div class="chips" role="group" aria-labelledby="cookday">
            {#each model.chips as iso, i (iso)}
              <button
                type="button"
                class="chip"
                aria-pressed={iso === model.cookDay}
                onclick={() => {
                  model.setDay(iso);
                  other = false;
                }}>{dayChip(iso, i === 0)}</button
              >
            {/each}
            <button type="button" class="chip" aria-pressed={other} onclick={() => (other = !other)}
              >Other…</button
            >
          </div>
          {#if other}
            <label class="date"
              >Cook day
              <input
                type="date"
                value={model.cookDay ?? ''}
                min={plan.today || undefined}
                onchange={(event) => {
                  if (event.currentTarget.value) model.setDay(event.currentTarget.value);
                }}
              /></label
            >
          {/if}
        </div>
        <div class="group count">
          <span class="h2" id="howmany">How many recipes</span>
          <div class="seg" role="radiogroup" aria-labelledby="howmany">
            {#each COUNTS as n (n)}
              <button
                type="button"
                role="radio"
                aria-checked={model.count === n}
                disabled={model.loading}
                onclick={() => void model.setCount(n)}>{n}</button
              >
            {/each}
          </div>
        </div>
        <div class="times">
          <strong>About {timeWords(model.result.together_minutes)} together</strong>
          <span class="muted"
            >{oneByOneWords(model.result)}{#if !phone}
              <button type="button" class="link" onclick={openKitchen}>Change</button>{/if}</span
          >
        </div>
      </div>

      {#if model.picks.length < model.count}
        <p class="note">
          {model.picks.length === 1
            ? 'Only 1 recipe has steps, so there is nothing to batch with. Add steps to another recipe.'
            : `Only ${model.picks.length} of your recipes have steps, so this batch has ${model.picks.length}.`}
        </p>
      {/if}

      <ul class="picks" aria-busy={model.loading}>
        {#each model.picks as pick (pick.recipe_id)}
          <li class="pick">
            <div class="row">
              <span class="nm">{pick.name}</span>
              <span class="am">{timeWords(pick.minutes)}</span>
            </div>
            <span class="why">{pick.why}</span>
            {#if pick.use_soon}
              <span class="tag"
                >Use soon · {pick.use_soon.foods.join(', ').toLowerCase()}, {soonWords(
                  pick.use_soon.days_left
                )}</span
              >
            {/if}
            <div class="row left">
              <Button
                small
                quiet
                disabled={readonly || model.loading || model.result.pool <= model.picks.length}
                aria-label="Swap {pick.name}"
                onclick={() => void model.swap(pick.recipe_id)}>Swap</Button
              >
              <a
                class="open"
                href={resolve('/(app)/recipes/[id]', { id: String(pick.recipe_id) })}
                aria-label="Open recipe {pick.name}">Open recipe</a
              >
            </div>
          </li>
        {/each}
      </ul>

      <div class="foot">
        <Button
          small
          quiet
          disabled={readonly || model.loading || model.result.pool <= model.picks.length}
          onclick={() => void model.others()}>Show me others</Button
        >
        <Button small disabled={readonly || model.loading || !enough || slotMissing} onclick={plan_}
          >Plan this batch</Button
        >
      </div>
    {/if}
  {/if}
</div>

{#if kitchenNow}
  <YourKitchen
    open={kitchenOpen}
    kitchen={kitchenNow}
    onsaved={(saved) => {
      kitchenNow = saved;
      kitchenOpen = false;
      void model.load();
    }}
    onclose={() => {
      kitchenOpen = false;
      kitchenOpener?.focus();
    }}
  />
{/if}

<!-- The Cook once sheets are fetched when "Plan this batch" is first pressed (size limit). -->
{#if flowAsked}
  <Lazy
    load={() => import('#lib/components/plan/CookOnce.svelte')}
    actions={{ model: plan, readonly }}
    target={null}
    {ahead}
    onclose={cancelFlow}
  />
{/if}

<style>
  .batch {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .exp {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: var(--radius-full);
    background: var(--color-experimental-bg);
    color: var(--color-experimental-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .view {
    display: grid;
    grid-template-columns: 1fr 1fr 1.5fr;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  .view a,
  .view .on {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-height: var(--touch-target);
    border-radius: var(--radius-full);
    color: var(--color-text-muted);
    font-weight: var(--weight-semibold);
    text-decoration: none;
  }

  .view .on {
    background: var(--color-surface-raised, var(--color-surface));
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
  }

  .view .on :global(svg) {
    color: var(--color-experimental);
  }

  .note {
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-info);
    color: var(--color-info-text);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .link {
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent-on-soft, var(--color-accent));
    font: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    min-height: var(--touch-target);
    cursor: pointer;
  }

  .problem {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    padding: var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .problem button,
  .add {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-weight: var(--weight-bold);
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    align-self: flex-start;
  }

  .controls {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .h2 {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-weight: var(--weight-semibold);
    white-space: nowrap;
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: transparent;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .date {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font-size: var(--text-sm);
  }

  .date input {
    min-height: var(--touch-target);
    max-width: 14rem;
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
  }

  .count {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .seg {
    display: grid;
    grid-template-columns: repeat(3, 48px);
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  .seg button {
    min-height: 44px;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .seg button[aria-checked='true'] {
    background: var(--color-surface);
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
  }

  .times {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .picks {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: var(--space-5);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .pick {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .row.left {
    justify-content: flex-start;
    margin-top: auto;
  }

  .nm {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .am {
    white-space: nowrap;
  }

  .why {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .tag {
    align-self: flex-start;
    padding: 3px 9px;
    border-radius: var(--radius-full);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
  }

  .open {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    font-weight: var(--weight-bold);
  }

  .foot {
    display: flex;
    gap: var(--space-5);
    justify-content: flex-end;
    flex-wrap: wrap;
  }

  /* On the phone the two buttons stay in reach above the bottom tabs. */
  @media (max-width: 767px) {
    .foot {
      position: sticky;
      bottom: var(--tabbar-height);
      padding: var(--space-5) 0;
      background: var(--color-ground);
      justify-content: stretch;
    }

    .foot > * {
      flex: 1;
      padding: 0 var(--space-5);
    }
  }
</style>
