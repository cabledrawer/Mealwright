<script lang="ts">
  import Stepper from '#lib/components/Stepper.svelte';
  // The "Cooked it" review (mockups Cooked-Desktop/Phone and CookedMeal-Desktop/Phone; spec
  // section 2, "Cooking — how deduction works"; cabledrawer 31 Oct): every ingredient the recipe
  // would take from the pantry, each with its Use switch and an amount you can change, then one
  // Confirm and one Undo. A meal with several recipes has one tab for each. Today's "Did you
  // cook…?" and the Plan's Cooked it open this same screen. The words are proposed, for cabledrawer.
  import type { Leftovers } from '#lib/client/today.js';
  import { TOO_MANY_ANSWERS, changeCount } from '#lib/cookRows.js';
  import { undoAll, type CookReview } from '#lib/cookReview.svelte.js';
  import { BAD_DATE, isSaneDay, pickedDateWords } from '#lib/dates.js';
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { useByWords } from '#lib/planMeals.js';
  import { eatOnUpTo } from '#lib/tubUseBy.js';
  import { tubsWords } from '#lib/todayWords.js';
  import CookRowView from './CookRowView.svelte';
  import { plural } from '#lib/words.js';

  /** "Any left over?": only for a meal answered from Today or the Plan. */
  export interface LeftoverOptions {
    itemId: number;
    today: string;
    useByFridge?: string;
    useByFreezer?: string;
    /** The next free meals a tub can be eaten at ("Eat it on…", F65), when the Plan knows them. */
    eatOn?: { day: string; slotId: number; label: string }[];
  }

  let {
    review,
    leftover = null,
    readonly = false,
    onclose,
    onconfirmed
  }: {
    review: CookReview;
    leftover?: LeftoverOptions | null;
    readonly?: boolean;
    onclose: () => void;
    /** After the pantry is changed: Today's answer for the meal itself (and its tubs). */
    onconfirmed?: (
      leftovers: Leftovers | null,
      undoCooked: () => Promise<string | void>,
      eatOn: { day: string; slotId: number } | null
    ) => void | boolean | 'unsure' | Promise<void | boolean | 'unsure'>;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  let count = $state(0);
  let place = $state<'fridge' | 'freezer'>('fridge');
  let chosen = $state<string | null>(null);
  let changing = $state(false);
  let dateProblem = $state('');
  /** "Eat it on…": a day and a meal as "2026-10-19|2", or nothing yet. */
  let eatAt = $state('');

  const target = $derived(review.target);
  const tab = $derived(review.tab);
  const rows = $derived(tab?.rows.filter((r) => r.status !== 'staple') ?? []);
  const staples = $derived(tab?.rows.filter((r) => r.status === 'staple') ?? []);

  $effect(() => {
    if (target) {
      count = 0;
      place = 'fridge';
      chosen = null;
      changing = false;
      dateProblem = '';
      eatAt = '';
    }
  });

  $effect(() => {
    if (target !== null && !dialog.open) dialog.showModal();
    else if (target === null && dialog.open) dialog.close();
  });

  const useBy = $derived(
    chosen ?? (place === 'fridge' ? leftover?.useByFridge : leftover?.useByFreezer) ?? ''
  );

  /** "Eat it on…": not past the tub's use-by, the fridge's or the freezer's as the place says (a
   * chosen date wins). With no use-by known, none: never a meal the server will refuse (F128). */
  const eatChoices = $derived(eatOnUpTo(leftover?.eatOn ?? [], useBy));
  $effect(() => {
    if (eatAt && !eatChoices.some((o) => `${o.day}|${o.slotId}` === eatAt)) eatAt = '';
  });

  const changes = $derived(review.tabs.reduce((n, t) => n + changeCount(t.rows, t.states), 0));
  const summary = $derived(
    [
      changes === 0
        ? 'Nothing will be taken from the pantry'
        : `${changes} ${plural(changes, 'ingredient', 'ingredients')} will change`,
      count > 0 ? `${tubsWords(count)} → ${place === 'fridge' ? 'Fridge' : 'Freezer'}` : ''
    ]
      .filter(Boolean)
      .join(' · ')
  );

  async function confirm() {
    if (!target) return;
    const leftovers: Leftovers | null =
      count > 0 && leftover
        ? {
            count,
            place_kind: place,
            item_id: leftover.itemId,
            ...(chosen ? { use_by: chosen } : {})
          }
        : null;
    // The meal's answer follows the pantry; if either fails the pantry is put back and the
    // screen stays open, so Confirm can be pressed again.
    const { ok } = await review.confirm({
      after: onconfirmed
        ? async (outcomes) => {
            const [day, slot] = eatAt.split('|');
            const eatOn = leftovers && day && slot ? { day, slotId: Number(slot) } : null;
            const answered = await onconfirmed(leftovers, undoAll(outcomes), eatOn);
            return answered === undefined ? true : answered;
          }
        : undefined
    });
    if (ok) onclose(); // the answer was given first: closing lets go of what it was about
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }

  function tabKeys(event: KeyboardEvent) {
    const last = review.tabs.length - 1;
    const to =
      event.key === 'ArrowRight'
        ? Math.min(review.active + 1, last)
        : event.key === 'ArrowLeft'
          ? Math.max(review.active - 1, 0)
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? last
              : null;
    if (to === null) return;
    event.preventDefault();
    review.active = to;
    document.getElementById(`${uid}-tab-${to}`)?.focus();
  }

  const portionsNote = $derived.by(() => {
    const proposal = tab?.proposal;
    if (!proposal) return '';
    if (tab && tab.chosen !== null && tab.chosen !== proposal.portions) return '';
    if (proposal.servings && proposal.portions !== proposal.servings)
      return `recipe × ${Math.round((proposal.portions / proposal.servings) * 100) / 100}`;
    return 'as planned';
  });
</script>

<dialog
  bind:this={dialog}
  aria-label={target?.title ?? 'Cooked it'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="cooked-review"
>
  {#if target}
    <div class="shell">
      <span class="handle" aria-hidden="true"></span>
      <header>
        <button type="button" class="cancel" onclick={onclose}>Cancel</button>
        <div class="titles">
          <p class="sub">{target.subtitle}</p>
          <h2>{target.title}</h2>
          <p class="sub">Check what comes out of the pantry</p>
        </div>
      </header>

      <div class="scroll">
        {#if readonly}
          <p class="note" role="status">
            {downLine(network.deviceOffline, (b) => `Cooked it changes ${b.when}.`)}
          </p>
        {/if}

        {#if review.tooMany}
          <p class="problem" role="alert">{TOO_MANY_ANSWERS}</p>
        {/if}

        {#if review.nothingToTake}
          <p class="note">Nothing in this meal comes from the pantry.</p>
        {:else}
          {#if review.tabs.length > 1}
            <div class="tabs" role="tablist" aria-label="Recipes in this meal">
              {#each review.tabs as each, i (i)}
                <button
                  type="button"
                  role="tab"
                  id="{uid}-tab-{i}"
                  aria-selected={review.active === i}
                  aria-controls="{uid}-panel"
                  tabindex={review.active === i ? 0 : -1}
                  onkeydown={tabKeys}
                  onclick={() => (review.active = i)}>{each.part.name}</button
                >
              {/each}
            </div>
          {/if}

          <div
            id="{uid}-panel"
            role={review.tabs.length > 1 ? 'tabpanel' : undefined}
            aria-labelledby={review.tabs.length > 1 ? `${uid}-tab-${review.active}` : undefined}
            class="panel"
          >
            {#if tab?.proposal && !tab.proposal.servings}
              <!-- F170: with no Serves there is nothing to scale by, so no Portions cooked. -->
              <p class="note" data-testid="no-serves">Add Serves to the recipe to scale it.</p>
            {:else if tab}
              <div class="portions">
                <span class="words">
                  <b>Portions cooked</b>
                  {#if portionsNote}<span class="sub">{portionsNote}</span>{/if}
                </span>
                <Stepper
                  what="portions"
                  label="Portions cooked"
                  onless={() => void review.setPortions(tab, tab.portions - 1)}
                  onmore={() => void review.setPortions(tab, tab.portions + 1)}
                  lessOff={readonly || tab.portions <= 1 || review.saving}
                  moreOff={readonly || tab.portions >= 999 || review.saving}>{tab.portions}</Stepper
                >
              </div>
            {/if}

            {#if review.problem}
              <p class="problem" role="alert">{review.problem}</p>
            {:else if !tab?.proposal}
              <p class="note" role="status">Working out what to take…</p>
            {:else}
              <div class="table" class:busy={review.loading} aria-busy={review.loading}>
                <div class="head" aria-hidden="true">
                  <span>Ingredient</span><span>From</span><span>Before → after</span>
                  <span class="r">Take</span><span class="r">Use</span>
                </div>
                <ul class="rows" aria-label="Taken from the pantry">
                  {#each rows as row (row.key)}
                    <CookRowView {review} {tab} {row} disabled={readonly || review.saving} />
                  {/each}
                </ul>
                {#if rows.length === 0}
                  <p class="note">Nothing in this recipe comes from the pantry.</p>
                {/if}
              </div>
              {#if staples.length}
                <div class="staples">
                  <span class="overline">Staples · not counted</span>
                  <ul>
                    {#each staples as row (row.key)}
                      <li>{row.food?.name ?? row.lines.map((l) => l.words).join(' + ')}</li>
                    {/each}
                  </ul>
                </div>
              {/if}
            {/if}
          </div>
        {/if}

        {#if leftover}
          <section class="left" aria-labelledby="{uid}-left">
            <div class="row">
              <span class="words"
                ><span class="label" id="{uid}-left">Any left over?</span><span class="hint"
                  >Optional · makes tubs for later</span
                ></span
              >
              <Stepper
                what="tubs"
                label="Leftover tubs"
                onless={() => (count = Math.max(0, count - 1))}
                onmore={() => (count = Math.min(12, count + 1))}
                lessOff={count <= 0}
                moreOff={count >= 12}>{tubsWords(count)}</Stepper
              >
            </div>
            {#if count > 0}
              <div class="places" role="group" aria-label="Where the tub goes">
                <button
                  type="button"
                  aria-pressed={place === 'fridge'}
                  onclick={() => (place = 'fridge')}>Fridge</button
                >
                <button
                  type="button"
                  aria-pressed={place === 'freezer'}
                  onclick={() => (place = 'freezer')}>Freezer</button
                >
              </div>
              <div class="useby">
                {#if useBy}
                  <span
                    >Use by <b>{pickedDateWords(useBy)}</b> · {useByWords(
                      useBy,
                      leftover.today
                    )}</span
                  >
                {:else}
                  <span>Use by the usual number of days</span>
                {/if}
                <button type="button" class="link" onclick={() => (changing = !changing)}
                  >Change</button
                >
              </div>
              {#if eatChoices.length}
                <label class="eaton">
                  <span>Eat it on…</span>
                  <select bind:value={eatAt}>
                    <option value="">Not planned yet</option>
                    {#each eatChoices as option (`${option.day}|${option.slotId}`)}
                      <option value="{option.day}|{option.slotId}">{option.label}</option>
                    {/each}
                  </select>
                </label>
              {/if}
              {#if changing}
                <label class="date">
                  <span class="visually-hidden">Use-by date</span>
                  <input
                    type="date"
                    value={useBy}
                    onchange={(event) => {
                      const value = event.currentTarget.value;
                      if (value && !isSaneDay(value)) {
                        dateProblem = BAD_DATE;
                        event.currentTarget.value = useBy;
                        return;
                      }
                      dateProblem = '';
                      chosen = value || null;
                    }}
                  />
                </label>
                {#if dateProblem}<p class="problem" role="alert">{dateProblem}</p>{/if}
              {/if}
            {/if}
          </section>
        {/if}
        <p class="sub">
          Nothing changes until you confirm. You can undo it from the message that follows, or from
          Pantry → Recent changes.
        </p>
      </div>

      <footer>
        <p class="summary" role="status">{summary}</p>
        <div class="buttons">
          <button type="button" class="back" onclick={onclose}>Cancel</button>
          <button
            type="button"
            class="go"
            disabled={readonly ||
              review.saving ||
              review.loading ||
              (!review.nothingToTake && !!review.problem)}
            onclick={confirm}>{review.saving ? 'Saving…' : 'Confirm · update pantry'}</button
          >
        </div>
      </footer>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-ground);
    color: var(--color-text);
    overscroll-behavior: contain;
    scrollbar-width: none;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .shell {
    display: flex;
    flex-direction: column;
    max-height: inherit;
    height: 100%;
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    margin: var(--space-3) 0;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-4);
    padding: var(--space-5) var(--space-8);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
  }

  .titles {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    text-align: center;
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
  }

  .cancel {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent-on-soft);
    font: inherit;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .scroll {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-5);
    min-height: 0;
    padding: var(--space-5) var(--space-8);
    overflow-y: auto;
    scrollbar-width: none;
  }

  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .tabs {
    display: flex;
    gap: var(--space-2);
    overflow-x: auto;
    scrollbar-width: none;
  }

  .tabs button {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: inherit;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .tabs button[aria-selected='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .portions,
  .table,
  .left,
  .staples {
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .portions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .table.busy {
    opacity: 0.6;
  }

  .head {
    display: none;
  }

  .rows {
    margin: 0;
    padding: 0;
  }

  .rows :global(li:first-child) {
    border-top: none;
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .staples {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    background: var(--color-staples-panel);
  }

  .staples ul {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .staples li {
    padding: 5px 11px;
    border-radius: var(--radius-full);
    background: var(--color-staple-chip);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .note,
  .problem {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .problem {
    padding: var(--space-5);
    border-radius: var(--radius-xl);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-weight: var(--weight-bold);
  }

  .left {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .label {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .hint {
    font-size: var(--text-base);
  }

  .places {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .places button {
    min-height: var(--touch-target);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .places button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .useby {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    font-size: var(--text-base);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent-on-soft);
    font: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .eaton {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    font-weight: var(--weight-bold);
  }

  .eaton select,
  .date input {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
  }

  footer {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) var(--space-8) max(var(--space-7), env(safe-area-inset-bottom));
    background: var(--color-surface);
    border-top: 1px solid var(--color-border);
  }

  .summary {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  .back,
  .go {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    font: inherit;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .back {
    padding: 0 var(--space-8);
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .go {
    flex: 1;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .go:disabled {
    opacity: 0.5;
    cursor: default;
  }

  @media (max-width: 767px) {
    .back {
      display: none;
    }
    dialog {
      overflow: hidden;
      inset: 0;
      width: 100%;
      height: 100dvh;
      margin: 0;
    }
    .handle {
      display: none;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(1040px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      border-radius: var(--radius-panel);
      overflow: hidden;
    }
    .shell {
      max-height: calc(100dvh - 2 * var(--space-7));
    }
    .handle {
      display: none;
    }
    .head {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.9fr) minmax(0, 1fr) minmax(0, 1.3fr) 60px;
      column-gap: var(--space-4);
      padding-bottom: var(--space-3);
      color: var(--color-text-muted);
      font-size: var(--text-sm);
      font-weight: var(--weight-extrabold);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .head .r {
      text-align: right;
    }
  }
</style>
