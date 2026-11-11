<script lang="ts">
  // "Cook once, eat for…" (mockups CookOnce-Desktop, CookOnce-Phone and their dark twins): how many
  // tubs, which meals to spread them over, who is eating, whether tubs with no meal go to the
  // freezer, and a preview of where the tubs land. The server works the preview out. A tub is
  // added to any meal with "+ Add a tub" (or "+ Add a tub too" when the meal has something planned), taken out
  // with ✕, and moved by dragging it or by tapping it and then tapping the meal (the keyboard and
  // finger way). Online only, like the rest of the plan.
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { untrack } from 'svelte';
  import type { PlanItem, PlanMeal } from '#lib/client/plan.js';
  import {
    CookOnceModel,
    type Ahead,
    MOST_TUBS,
    PATTERNS,
    perTubWords,
    timesWords,
    tubNumbers
  } from '#lib/cookOnce.svelte.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { colourOfBatch, itemName } from '#lib/planMeals.js';
  import Switch from '../Switch.svelte';

  let {
    actions,
    target,
    ahead = null,
    onclose
  }: {
    actions: Pick<PlanActions, 'model' | 'readonly'>;
    target: { meal: PlanMeal; item: PlanItem } | null;
    ahead?: Ahead | null;
    onclose: () => void;
  } = $props();

  /** What the sheet is for: a planned recipe, or one the session is about to plan. */
  const open = $derived(target !== null || ahead !== null);

  const model = $derived(actions.model);
  let dialog: HTMLDialogElement;
  let cook = $state<CookOnceModel | null>(null);
  /** The tub picked up to move (tap it, then tap the meal). */
  let moving = $state<number | null>(null);
  let dragged = $state<number | null>(null);

  // A new target starts again with a fresh model. Only the target is watched; what the model
  // reads while it asks the server is not (or every choice would start over).
  $effect(() => {
    const now = target;
    const sheet = ahead;
    untrack(() => {
      moving = null;
      if (now === null && sheet === null) {
        cook = null;
        return;
      }
      const made = now
        ? new CookOnceModel(now.item.id, now.meal.date, model.people)
        : new CookOnceModel(0, sheet!.day, model.people, sheet!.preview);
      cook = made;
      void made.refresh();
    });
  });

  $effect(() => {
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  });

  const name = $derived(target ? itemName(target.item, model.plan) : (ahead?.name ?? ''));
  const cookDay = $derived(target?.meal.date ?? ahead?.day ?? '');
  const colour = $derived(
    cook?.preview ? colourOfBatch({ id: 0, colour: cook.preview.colour }) : 1
  );
  /** The slot the cook meal is in, with the slots that come after it on that day. */
  const cookSlot = $derived(
    target?.meal.slot_id ?? cook?.preview?.cook_slot_id ?? ahead?.slotId ?? 0
  );
  const slotsOn = $derived(model.slotsOn);
  const slotAt = (slotId: number) => slotsOn.findIndex((s) => s.id === slotId);

  /** Past days and meals before the cooking are not offered (F50). The cook meal is shown as a
   * marker only; a day in the past shows nothing but that marker. */
  function slotsFor(day: string) {
    if (day < model.today)
      return day === cook?.cookDate ? slotsOn.filter((s) => s.id === cookSlot) : [];
    return day === cook?.cookDate
      ? slotsOn.filter((s) => slotAt(s.id) >= slotAt(cookSlot))
      : slotsOn;
  }

  function existing(day: string, slotId: number): string | null {
    const meal = cook?.plan?.meals.find((m) => m.date === day && m.slot_id === slotId);
    if (!meal || meal.items.length === 0) return null;
    return meal.items.map((i) => itemName(i, cook?.plan ?? null)).join(' · ');
  }

  function put(day: string, slotId: number) {
    if (!cook || actions.readonly) return;
    if (moving !== null) {
      cook.moveTub(moving, { date: day, slot_id: slotId });
      moving = null;
    } else {
      cook.addTub({ date: day, slot_id: slotId });
    }
  }

  function dropOn(event: DragEvent, day: string, slotId: number) {
    event.preventDefault();
    if (!cook || dragged === null || actions.readonly) return;
    cook.moveTub(dragged, { date: day, slot_id: slotId });
    dragged = null;
  }

  const unplaced = $derived(cook?.unplaced ?? []);
  const unplacedWords = $derived.by(() => {
    if (!cook?.preview || unplaced.length === 0) return '';
    const where = cook.extras
      ? 'Freezer · they’ll show in tubs left'
      : 'Fridge · they’ll show in tubs left';
    return `${tubNumbers(unplaced.map((t) => t.number))} → ${where}`;
  });

  const nutrition = $derived(cook?.preview ? perTubWords(cook.preview.per_tub) : null);
  const times = $derived(cook?.preview ? timesWords(cook.count, cook.preview.recipe_serves) : null);

  function save() {
    if (!cook || actions.readonly || !cook.preview) return;
    if (ahead) {
      ahead.save(cook.body());
      return;
    }
    if (!target) return;
    void model.cookOnce(target.item.id, name, cook.body());
    onclose();
  }

  const names = $derived(new Map(model.people.map((p) => [p.login_id, p.name])));
  const whose = (id: number | null) => (id === null ? null : (names.get(id) ?? null));
</script>

<dialog
  bind:this={dialog}
  aria-label={ahead ? `Cook once, eat for… ${ahead.position}` : 'Cook once, eat for…'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
  data-testid="cook-once"
>
  {#if open && cook}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        <p class="sub">
          {name} · cooking {dayFull(cookDay)} · {model.slotName(cookSlot)}
        </p>
        <h2>
          Cook once, eat for…{#if ahead}<span class="of"> {ahead.position}</span>{/if}
        </h2>
      </header>

      {#if actions.readonly}
        <p class="note" role="status">
          {downLine(network.deviceOffline, (b) => `Plan changes ${b.when}.`)}
        </p>
      {/if}
      {#if cook.problem}
        <p class="problem" role="alert">{cook.problem}</p>
      {/if}

      <div class="columns">
        <div class="controls">
          <div class="card row">
            <div class="what">
              <strong id="tubs-label">How many tubs?</strong>
              {#if cook.preview?.recipe_serves}
                <span class="hint"
                  >Recipe serves {cook.preview.recipe_serves}{times
                    ? ` · amounts ${times}`
                    : ''}</span
                >
              {/if}
            </div>
            <div class="stepper" role="group" aria-labelledby="tubs-label">
              <button
                type="button"
                aria-label="One tub fewer"
                disabled={cook.count <= 1 || actions.readonly}
                onclick={() => cook?.setCount(cook.count - 1)}>−</button
              >
              <output aria-live="polite" data-testid="tub-count">{cook.count}</output>
              <button
                type="button"
                aria-label="One tub more"
                disabled={cook.count >= MOST_TUBS || actions.readonly}
                onclick={() => cook?.setCount(cook.count + 1)}>+</button
              >
            </div>
          </div>

          <div class="group" role="group" aria-labelledby="spread-label">
            <strong id="spread-label">Spread them over</strong>
            <div class="chips">
              {#each PATTERNS as p (p.value)}
                <button
                  type="button"
                  aria-pressed={cook.pattern === p.value}
                  disabled={actions.readonly}
                  onclick={() => cook?.setPattern(p.value)}>{p.label}</button
                >
              {/each}
            </div>
          </div>

          {#if model.people.length > 1}
            <div class="group" role="group" aria-labelledby="who-label">
              <strong id="who-label">Who’s eating?</strong>
              <div class="chips">
                <button
                  type="button"
                  aria-pressed={cook.who === 'all'}
                  disabled={actions.readonly}
                  onclick={() => cook?.setWho('all')}>Everyone</button
                >
                {#each model.people as person (person.login_id)}
                  <button
                    type="button"
                    aria-pressed={cook.who === person.login_id}
                    disabled={actions.readonly}
                    onclick={() => cook?.setWho(person.login_id)}>{person.name}</button
                  >
                {/each}
              </div>
            </div>
          {/if}

          <div class="card row">
            <strong id="freezer-label">Extra tubs go to the freezer</strong>
            <Switch
              labelledby="freezer-label"
              checked={cook.extras}
              disabled={actions.readonly}
              onchange={(on) => cook?.setExtras(on)}
            />
          </div>

          <div class="card">
            <label for="prep-note"><strong>Prep note</strong></label>
            <input
              id="prep-note"
              type="text"
              maxlength="500"
              placeholder="Soak chickpeas Tue night"
              bind:value={cook.prepNote}
              disabled={actions.readonly}
            />
          </div>

          <div class="card per">
            <strong>Per tub</strong>
            <span>{nutrition ?? 'Nutrition not known for this recipe'}</span>
          </div>
        </div>

        <section class="land" aria-labelledby="land-label">
          <div class="land-head">
            <h3 id="land-label">Where the tubs land</h3>
            <p class="hint">
              {moving !== null
                ? `Tap a meal to move tub ${moving} there`
                : 'Tap a meal to add a tub, ✕ to take one out, drag to move'}
            </p>
          </div>
          <ul class="days">
            {#each cook.days.filter((d) => slotsFor(d).length > 0) as day (day)}
              <li class="day">
                <h4>{dayShort(day)} {dayOfMonth(day)}</h4>
                {#each slotsFor(day) as slot (slot.id)}
                  {@const here = cook.tubsAt(day, slot.id)}
                  {@const planned = existing(day, slot.id)}
                  {@const isCook = day === cook.cookDate && slot.id === cookSlot}
                  <div
                    class="cell"
                    class:cooking={isCook}
                    role="group"
                    aria-label="{slot.name} on {dayFull(day)}"
                    data-testid="cook-cell-{day}-{slot.id}"
                    ondragover={(event) => event.preventDefault()}
                    ondrop={(event) => dropOn(event, day, slot.id)}
                  >
                    <span class="slot">{slot.name}</span>
                    {#if isCook}
                      <span class="cook" style:--c="var(--batch-{colour})">Cook · {name}</span>
                    {:else}
                      {#if planned && here.length === 0}
                        <span class="has">{planned} · already planned</span>
                      {/if}
                      {#each here as tub (tub.number)}
                        <span
                          class="tub"
                          style:--soft="var(--batch-{colour}-soft)"
                          style:--soft-text="var(--batch-{colour}-soft-text)"
                        >
                          <button
                            type="button"
                            class="pick"
                            aria-pressed={moving === tub.number}
                            draggable={!actions.readonly}
                            disabled={actions.readonly}
                            ondragstart={() => (dragged = tub.number)}
                            onclick={() => (moving = moving === tub.number ? null : tub.number)}
                            aria-label="Tub {tub.number}{whose(tub.member_login_id)
                              ? `, ${whose(tub.member_login_id)}`
                              : ''}. Move it"
                            >Tub {tub.number}{whose(tub.member_login_id)
                              ? ` · ${whose(tub.member_login_id)}`
                              : ''}</button
                          >
                          <button
                            type="button"
                            class="x"
                            disabled={actions.readonly}
                            aria-label="Take tub {tub.number} out of {slot.name} on {dayFull(day)}"
                            onclick={() => cook?.removeTub(tub.number)}>✕</button
                          >
                        </span>
                      {/each}
                      <button
                        type="button"
                        class="add"
                        disabled={actions.readonly || (moving === null && cook.nextFree === null)}
                        aria-label="{moving !== null
                          ? `Put tub ${moving} in`
                          : planned || here.length
                            ? 'Add a tub too to'
                            : 'Add a tub to'} {slot.name} on {dayFull(day)}"
                        onclick={() => put(day, slot.id)}
                        >{moving !== null
                          ? 'Move it here'
                          : planned || here.length
                            ? '+ Add a tub too'
                            : '+ Add a tub'}</button
                      >
                    {/if}
                  </div>
                {/each}
              </li>
            {/each}
          </ul>
          {#if cook.canShowMore}
            <button type="button" class="later" onclick={() => cook?.showMore()}>Later days</button>
          {/if}
          {#if cook.preview}
            <p class="foot" data-testid="cook-summary">
              {#if unplacedWords}{unplacedWords}.
              {/if}The pattern skips meals that already have something planned; you can still add a
              tub to one yourself.
              <strong>{cook.preview.placed} of {cook.count} placed.</strong>
            </p>
          {/if}
        </section>
      </div>

      <div class="buttons">
        <button type="button" class="back" onclick={onclose}>Cancel</button>
        <button type="button" class="go" disabled={actions.readonly || !cook.preview} onclick={save}
          >{#if ahead}{ahead.last ? 'Plan this batch' : 'Next recipe'}{:else}Add {cook.count}
            {cook.count === 1 ? 'tub' : 'tubs'} to the plan{/if}</button
        >
      </div>
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

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .sub,
  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    overflow-wrap: break-word;
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  .of {
    color: var(--color-text-muted);
    font-weight: var(--weight-bold);
  }

  h3 {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  h4 {
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    color: var(--color-text-muted);
  }

  .note,
  .problem {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
  }

  .problem {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .columns {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-7);
    align-items: flex-start;
  }

  .controls {
    flex: 1 1 300px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .land {
    flex: 2 1 460px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6);
    border-radius: var(--radius-panel);
    background: var(--color-surface);
  }

  .land-head {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }

  .card.row {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .what {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .per span {
    font-size: var(--text-md);
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chips button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .chips button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2);
    border-radius: var(--radius-full);
    background: var(--color-ground);
  }

  .stepper button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-3xl);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .stepper output {
    min-width: 2ch;
    text-align: center;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  input[type='text'] {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
  }

  .days {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: var(--space-4);
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .day {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .cell {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
  }

  .slot {
    color: var(--color-text-muted);
    font-weight: var(--weight-bold);
  }

  .cook {
    padding: var(--space-4);
    border-radius: var(--radius-sm);
    background: var(--c);
    color: #fff;
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  .has {
    color: var(--color-text-muted);
    overflow-wrap: break-word;
  }

  .tub {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-1);
    border-radius: var(--radius-sm);
    background: var(--soft);
    color: var(--soft-text);
    font-weight: var(--weight-bold);
  }

  .tub button {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
  }

  .tub .pick {
    flex: 1;
    min-width: 0;
    padding: 0 var(--space-4);
    text-align: left;
    overflow-wrap: break-word;
  }

  .tub .pick[aria-pressed='true'] {
    outline: 2px solid currentColor;
    border-radius: var(--radius-sm);
  }

  .tub .x {
    width: var(--touch-target);
    font-weight: var(--weight-extrabold);
  }

  .add {
    min-height: var(--touch-target);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .later {
    align-self: flex-start;
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

  .foot {
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
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

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: calc(100dvh - 48px);
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
    .days {
      grid-template-columns: 1fr;
    }
    .land {
      padding: var(--space-5);
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(1040px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 28px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }
</style>
