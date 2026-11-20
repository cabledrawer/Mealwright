<script lang="ts">
  import LoadFailed from '#lib/components/LoadFailed.svelte';
  // The menu for something on the Plan (spec "Meal planner interactions": phone long-press
  // sheet; and the keyboard way to do everything a drag does):
  //   a meal or one thing in it: Move to… · Copy to… · Leftovers on… · Remove, then a day
  //   and a meal to pick; a recipe from the tray: the day and meal to plan it on;
  //   a day (Month): its meals.
  //   a tub (Cook once, PR 4): Whose tub? · Move to… · To freezer · Remove (back to tubs left); a
  //   tub is never copied, so it has no Copy to… or Leftovers on…;
  //   a planned recipe: also Cook once, eat for… (opens the sheet that makes the tubs).
  import Icon from '#lib/components/Icon.svelte';
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { TOO_LATE_TO_FREEZE, tubTooLateToFreeze } from '#lib/tooLateToFreeze.js';
  import { startOptionWords } from '#lib/startWords.js';
  import type { DropMode } from '#lib/client/plan.js';
  import type { PlanActions, PlanTarget as Target } from '#lib/planActions.js';
  import {
    addDays,
    dayFull,
    dayOfMonth,
    dayShort,
    weekDays,
    weekStart,
    weekWords
  } from '#lib/planDates.js';
  import {
    afterCook,
    cookBatchOfItem,
    dayAfterCook,
    itemName,
    mealName,
    tubOf,
    useByWords
  } from '#lib/planMeals.js';
  import { BAD_DATE, isSaneDay } from '#lib/dates.js';
  import type { PlanItem, PlanMeal } from '#lib/client/plan.js';
  import { cookedStaysNote } from '#lib/cookTargets.js';
  import LeftoversOn from './LeftoversOn.svelte';
  import MealWho from './MealWho.svelte';
  import PlanDays from './PlanDays.svelte';
  import ServesStepper from './ServesStepper.svelte';

  let {
    actions,
    target,
    onclose
  }: { actions: PlanActions; target: Target | null; onclose: () => void } = $props();

  const model = $derived(actions.model);
  let dialog: HTMLDialogElement;

  // Which step, and what has been picked so far.
  let mode = $state<DropMode | 'plan' | 'whose' | 'useby' | null>(null);
  /** The use-by date being typed for a tub (F48). */
  let useBy = $state('');
  let weekOf = $state('');
  let day = $state<string | null>(null);
  let slotId = $state<number | null>(null);

  // A new target starts again at the first step. A recipe has only the one: where.
  $effect(() => {
    if (target === null) return;
    mode = target.kind === 'recipe' || target.kind === 'tubleft' ? 'plan' : null;
    day = null;
    slotId = null;
    const from =
      target.kind === 'meal' || target.kind === 'item'
        ? target.meal.date
        : target.kind === 'day'
          ? target.day
          : model.anchor || model.today;
    weekOf = weekStart(from, model.startsOn);
  });

  $effect(() => {
    if (target !== null && !dialog.open) dialog.showModal();
    else if (target === null && dialog.open) dialog.close();
  });

  const heading = $derived.by(() => {
    if (!target) return '';
    if (target.kind === 'day') return dayFull(target.day);
    if (target.kind === 'recipe') return target.recipe.name;
    if (target.kind === 'tubleft') return `${target.tub.recipe_name} · tub ${target.tub.number}`;
    if (target.kind === 'item') return itemName(target.item, model.plan);
    return mealName(target.meal, model.plan);
  });

  const subheading = $derived.by(() => {
    if (!target || target.kind === 'recipe' || target.kind === 'tubleft' || target.kind === 'day')
      return '';
    return `${dayFull(target.meal.date)} · ${model.slotName(target.meal.slot_id)}`;
  });

  /** The tub this menu is about: the item itself, or a meal that holds just the one tub. */
  const tubItem = $derived.by((): PlanItem | null => {
    if (!target) return null;
    if (target.kind === 'item') return target.item.kind === 'tub' ? target.item : null;
    if (target.kind === 'meal') {
      const only = target.meal.items.length === 1 ? target.meal.items[0] : null;
      return only?.kind === 'tub' ? only : null;
    }
    return null;
  });
  const tub = $derived(tubItem ? tubOf(model.plan, tubItem) : null);

  /** The meal this menu is about (a meal, or the meal of one thing in it). */
  const aboutMeal = $derived(
    target && (target.kind === 'meal' || target.kind === 'item') ? target.meal : null
  );

  /** The recipes whose Serves can be changed here: those of a planned meal (0.7 P1, F57). */
  const servesItems = $derived.by((): PlanItem[] => {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return [];
    if (target.meal.status !== 'planned') return [];
    const items = target.kind === 'item' ? [target.item] : target.meal.items;
    return items.filter((i) => i.kind === 'recipe' && !i.cooked);
  });

  /**
   * The recipes here with Optional ingredients, that can still change which ones the meal uses
   * (R3): a recipe not cooked yet, in a planned meal.
   */
  const optionalItems = $derived(servesItems.filter((i) => (i.recipe?.optional_count ?? 0) > 0));

  /** The recipes here with two ways of cooking them, that can still change it (M2). */
  const methodItems = $derived(servesItems.filter((i) => (i.recipe?.methods?.length ?? 0) > 1));

  /**
   * The recipes here with a long wait to start ahead, that can still be started (M3). A meal on
   * a day that has gone by has nothing to pick (no time can be started ahead of it), so its menu
   * doesn't offer the change (FX5, review m3).
   */
  const startItems = $derived(
    servesItems.filter(
      (i) =>
        !!i.ahead &&
        (target?.kind === 'meal' || target?.kind === 'item') &&
        target.meal.date >= model.today
    )
  );

  /** "Starts Fri 21:00…", or "Set when to start…" when it has no time (names it when several). */
  function startLabel(item: PlanItem, named: boolean): string {
    const ahead = item.ahead;
    const base =
      ahead?.start_day && ahead.start_time
        ? `Starts ${startOptionWords(ahead.start_day, ahead.start_time)}`
        : 'Set when to start';
    return `${base}${named ? `: ${itemName(item, model.plan)}` : ''}…`;
  }

  function changeStart(item: PlanItem) {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return;
    const day = target.meal.date;
    onclose();
    void model.changeStart(item, day);
  }

  function changeMethod(item: PlanItem) {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return;
    const day = target.meal.date;
    onclose();
    void model.changeMethod(item, day);
  }

  function changeOptional(item: PlanItem) {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return;
    const day = target.meal.date;
    onclose();
    void model.changeOptional(item, day);
  }

  /**
   * Something in this menu was cooked (F157): the meal is still planned, but a cooked recipe
   * can't be moved or taken off while its record stands. Cooked it's Undo frees it.
   */
  const holdsCooked = $derived(
    !!target &&
      (target.kind === 'item' || target.kind === 'meal') &&
      target.meal.status === 'planned' &&
      (target.kind === 'item' ? !!target.item.cooked : target.meal.items.some((i) => i.cooked))
  );

  /** The recipes of a meal cooked in parts, for the list in its menu (F163). */
  const partRecipes = $derived.by((): PlanItem[] => {
    if (!target || target.kind !== 'meal' || !holdsCooked) return [];
    const recipes = target.meal.items.filter((i) => i.kind === 'recipe');
    return recipes.length > 1 ? recipes : [];
  });

  /** A meal cooked in parts (F166): its Serves says which recipe it changes, "Serves · Lentil soup". */
  const servesNamed = $derived(
    !!target &&
      (target.kind === 'item' || target.kind === 'meal') &&
      target.meal.status === 'planned' &&
      target.meal.items.some((i) => i.cooked) &&
      target.meal.items.filter((i) => i.kind === 'recipe').length > 1
  );

  /** The cooked recipes the note names: the one pressed, or those of the meal. */
  const cookedNames = $derived.by((): string[] => {
    if (!target || !holdsCooked) return [];
    const items =
      target.kind === 'item' ? [target.item] : target.kind === 'meal' ? target.meal.items : [];
    return items.filter((i) => i.cooked).map((i) => itemName(i, model.plan));
  });

  /** A note has no leftovers (it is "Eating out"), and no Serves. */
  const noteOnly = $derived(
    !!target &&
      (target.kind === 'item'
        ? target.item.kind === 'note'
        : target.kind === 'meal' && target.meal.items.every((i) => i.kind === 'note'))
  );

  /**
   * The one recipe "Leftovers on…" works from when it can tick several meals at once: the thing
   * itself, or the only thing in a meal that is not a tub or a note. A meal of several things
   * keeps the single-day picker (it copies the whole meal).
   */
  const leftoverItem = $derived.by((): PlanItem | null => {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return null;
    if (target.meal.status !== 'planned') return null;
    if (target.kind === 'item') return target.item.kind === 'recipe' ? target.item : null;
    const things = target.meal.items.filter((i) => i.kind !== 'tub' && i.kind !== 'note');
    return things.length === 1 && things[0]!.kind === 'recipe' ? things[0]! : null;
  });

  /** The planned recipe Cook once can be made from, when the menu is about one. */
  const cookable = $derived.by((): PlanItem | null => {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return null;
    if (target.meal.status !== 'planned') return null;
    const items =
      target.kind === 'item' ? [target.item] : target.meal.items.filter((i) => i.kind === 'recipe');
    const only = items.length === 1 ? items[0] : null;
    if (!only || only.kind !== 'recipe' || only.cooked || !only.recipe || only.recipe.removed)
      return null;
    return cookBatchOfItem(model.plan, target.meal, only) ? null : only;
  });

  /** The meal this menu can answer as cooked: planned, from its day on, with a recipe in it. */
  const cookedMeal = $derived.by((): PlanMeal | null => {
    if (!target || (target.kind !== 'meal' && target.kind !== 'item')) return null;
    const meal = target.meal;
    if (meal.status !== 'planned' || meal.date > model.today) return null;
    // Something in it still to cook (F157): a recipe cooked already is not asked about again.
    const items = target.kind === 'item' ? [target.item] : meal.items;
    return items.some((i) => i.kind === 'recipe' && i.recipe && !i.recipe.removed && !i.cooked)
      ? meal
      : null;
  });

  function cooked() {
    const meal = cookedMeal;
    if (!meal) return;
    onclose();
    actions.openCooked(meal);
  }

  function cookOnce() {
    if (!target || !cookable || (target.kind !== 'meal' && target.kind !== 'item')) return;
    // Read both before closing: closing empties the target, and with it what is cookable.
    const [meal, item] = [target.meal, cookable];
    onclose();
    actions.openCookOnce(meal, item);
  }

  function whose(memberId: number | null) {
    if (!tubItem || !tub) return;
    void model.setWhose(tub.tub.id, itemName(tubItem, model.plan), memberId);
    onclose();
  }

  function openUseBy() {
    if (!tub) return;
    useBy = tub.tub.use_by;
    mode = 'useby';
  }

  /** Not before the cook day (cabledrawer 29 Oct); dates compare as yyyy-mm-dd text. */
  const badDay = $derived(!!useBy && useBy !== tub?.tub.use_by && !isSaneDay(useBy));
  const tooEarly = $derived(!!tub && !!useBy && useBy < tub.batch.cooked_on);

  function saveUseBy() {
    if (!tubItem || !tub || !useBy || badDay || tooEarly || actions.readonly) return;
    if (useBy !== tub.tub.use_by)
      void model.setUseBy(tub.tub.id, itemName(tubItem, model.plan), useBy);
    onclose();
  }

  /** Too late to freeze (cabledrawer 8 Nov): a tub past its use-by date, as a packet. */
  const tubTooLate = $derived(!!tub && tubTooLateToFreeze(tub.tub.use_by, model.today));
  const uid = $props.id();

  function toFreezer() {
    if (!tubItem || !tub || tubTooLate) return;
    void model.toFreezer(tub.tub.id, itemName(tubItem, model.plan));
    onclose();
  }

  const question = $derived(
    mode === 'move'
      ? 'Move to…'
      : mode === 'copy'
        ? 'Copy to…'
        : mode === 'leftovers'
          ? 'Leftovers on…'
          : 'Plan it on…'
  );
  const confirmWords = $derived(
    mode === 'move'
      ? 'Move here'
      : mode === 'copy'
        ? 'Copy here'
        : mode === 'leftovers'
          ? 'Plan leftovers here'
          : 'Plan it here'
  );

  // Leftovers go only to meals after the cooking, and never to a past day (F50): the days and
  // meals before are not shown.
  const onlyAfter = $derived(
    mode === 'leftovers' && target && (target.kind === 'meal' || target.kind === 'item')
      ? target.meal
      : null
  );
  const dayShown = (d: string) =>
    !onlyAfter || dayAfterCook(d, onlyAfter, model.today, model.slotsOn);
  const slotShown = (id: number) =>
    !onlyAfter || day === null || afterCook(day, id, onlyAfter, model.today, model.slotsOn);
  /** The earliest day that can be picked, so the week bar doesn't walk back into the past. */
  const earliest = $derived(
    onlyAfter ? (onlyAfter.date > model.today ? onlyAfter.date : model.today) : null
  );
  const atEarliestWeek = $derived(
    earliest !== null && weekOf >= weekStart(earliest, model.startsOn)
  );

  $effect(() => {
    // Leftovers open on the week of the first day that can be picked.
    if (earliest !== null) weekOf = weekStart(earliest, model.startsOn);
  });

  $effect(() => {
    // A day change can leave the picked meal behind the cooking: forget it.
    if (slotId !== null && !slotShown(slotId)) slotId = null;
  });

  /** Moving or copying onto the very place it is in does nothing. */
  const samePlace = $derived(
    !!target &&
      (target.kind === 'meal' || target.kind === 'item') &&
      day === target.meal.date &&
      slotId === target.meal.slot_id
  );
  const ready = $derived(day !== null && slotId !== null && !samePlace && !actions.readonly);

  function choose() {
    if (!target || !ready || day === null || slotId === null) return;
    if (target.kind === 'tubleft') {
      void model.placeTub(target.tub.id, `${target.tub.recipe_name} tub`, day, slotId);
    } else if (target.kind === 'recipe') {
      void model.add({ recipe: target.recipe }, day, slotId);
    } else if (target.kind === 'meal') {
      void model.drop({ meal: target.meal.id }, day, slotId, mode as DropMode);
      focusCard(day, slotId, mode === 'move' ? target.meal.items.map((i) => i.id) : []);
    } else if (target.kind === 'item') {
      void model.drop({ item: target.item.id }, day, slotId, mode as DropMode);
      focusCard(day, slotId, mode === 'move' ? [target.item.id] : []);
    }
    onclose();
  }

  // --- The keyboard way to move a card (spec "Moving plan cards with the keyboard") ---------------
  // Enter on a card opens this menu; Move to… / Copy to… then take the arrow keys: Left and Right
  // (or Up and Down) pick the day, Shift with them picks the meal, Enter confirms, Escape cancels.
  // The picker holds the focus (the button that opened it is gone), so the keys reach it.
  let picker = $state<HTMLElement | null>(null);
  $effect(() => {
    if (picker && document.activeElement !== picker) picker.focus();
  });

  /** Where the arrow keys start from: the card's own place, else the first meal of the week. */
  const origin = $derived.by(() => {
    if (target && (target.kind === 'meal' || target.kind === 'item'))
      return { day: target.meal.date, slot: target.meal.slot_id };
    return { day: model.anchor || model.today, slot: model.slotsOn[0]?.id ?? null };
  });

  function stepDay(by: 1 | -1) {
    let next = day ?? origin.day;
    for (let i = 0; i < 400; i++) {
      next = addDays(next, by);
      if (dayShown(next)) break;
    }
    if (!dayShown(next)) return;
    day = next;
    weekOf = weekStart(next, model.startsOn);
    if (slotId === null || !slotShown(slotId)) {
      const start = model.slotsOn.find((s) => s.id === origin.slot && slotShown(s.id));
      slotId = (start ?? model.slotsOn.find((s) => slotShown(s.id)))?.id ?? null;
    }
  }

  function stepSlot(by: 1 | -1) {
    day ??= origin.day;
    const shown = model.slotsOn.filter((s) => slotShown(s.id));
    const at = shown.findIndex((s) => s.id === (slotId ?? origin.slot));
    const next = shown[Math.min(Math.max(at + by, 0), shown.length - 1)];
    if (next) slotId = next.id;
  }

  const ARROWS: Record<string, 1 | -1> = {
    ArrowLeft: -1,
    ArrowUp: -1,
    ArrowRight: 1,
    ArrowDown: 1
  };

  function pickKey(event: KeyboardEvent) {
    if (event.target !== picker) return; // a button inside keeps its own Enter
    if (event.key === 'Enter') {
      if (!ready) return;
      event.preventDefault();
      choose();
      return;
    }
    const by = ARROWS[event.key];
    if (!by || event.altKey || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    if (event.shiftKey) stepSlot(by);
    else stepDay(by);
  }

  /** What was picked, said out loud and shown ("Move to Tue 20 October · Dinner"). */
  const picked = $derived(
    day !== null && slotId !== null
      ? `${question.replace('…', '')} ${dayFull(day)} · ${model.slotName(slotId)}`
      : ''
  );

  /** After the keyboard moved a card, the focus goes to the card where it landed. */
  function focusCard(toDay: string, toSlot: number, ids: number[]) {
    let frames = 0;
    const look = () => {
      const place = document.querySelector(`[data-testid="cell-${toDay}-${toSlot}"]`);
      if (!place) return; // the phone and the Month have no such card
      const card =
        (ids.length &&
          place.querySelector<HTMLElement>(ids.map((i) => `[data-item="${i}"]`).join(','))) ||
        place.querySelector<HTMLElement>('.card');
      if (card && frames > 2) card.focus();
      else if (frames++ < 60) requestAnimationFrame(look);
    };
    requestAnimationFrame(look);
  }

  function remove() {
    if (!target) return;
    // A tub on its own is taken out of its meal (it goes back to tubs left), not thrown away.
    if (tubItem) void model.removeItem(tubItem.id);
    else if (target.kind === 'meal') void model.removeMeal(target.meal.id);
    if (target.kind === 'item') void model.removeItem(target.item.id);
    onclose();
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={heading || 'Plan'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="plan-sheet"
>
  {#if target}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        {#if subheading}<p class="sub">{subheading}</p>{/if}
        <h2>{heading}</h2>
      </header>

      {#if actions.readonly}
        <p class="note" role="status">
          {downLine(network.deviceOffline, (b) => `Plan changes ${b.when}.`)}
        </p>
      {/if}

      {#if target.kind === 'day'}
        <PlanDays {actions} days={[target.day]} />
      {:else if mode === null}
        {#if servesItems.length || (aboutMeal && aboutMeal.status === 'planned' && model.people.length > 1)}
          <div class="extras">
            {#each servesItems as serving (serving.id)}
              <ServesStepper
                {model}
                item={serving}
                named={servesItems.length > 1}
                after={servesNamed}
                disabled={actions.readonly}
              />
            {/each}
            {#if aboutMeal && aboutMeal.status === 'planned' && !tub}
              <MealWho {model} meal={aboutMeal} disabled={actions.readonly} />
            {/if}
          </div>
        {/if}
        {#if partRecipes.length}
          <ul class="parts" data-testid="plan-sheet-parts">
            {#each partRecipes as recipe (recipe.id)}
              <li>
                <span>{itemName(recipe, model.plan)}</span>
                {#if recipe.cooked}<span class="tag">Cooked</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
        <div class="list">
          {#if tub}
            <p class="sub">
              {tub.tub.place_kind === 'freezer' ? 'In the freezer' : 'In the fridge'} · {useByWords(
                tub.tub.use_by,
                model.today,
                tub.batch.cooked_on
              )}
            </p>
            <button type="button" disabled={actions.readonly} onclick={() => (mode = 'whose')}
              >Whose tub?</button
            >
            <button type="button" disabled={actions.readonly} onclick={openUseBy}
              >Change use-by date</button
            >
          {/if}
          {#if cookedMeal}
            <button type="button" disabled={actions.readonly} onclick={cooked}>Cooked it</button>
          {/if}
          {#if cookable}
            <button type="button" disabled={actions.readonly} onclick={cookOnce}
              >Cook once, eat for…</button
            >
          {/if}
          {#each methodItems as way (way.id)}
            <button
              type="button"
              disabled={actions.readonly}
              data-testid="plan-sheet-method"
              onclick={() => changeMethod(way)}
              >{methodItems.length > 1
                ? `How it’s cooked: ${itemName(way, model.plan)}…`
                : 'How it’s cooked…'}</button
            >
          {/each}
          {#each startItems as waiting (waiting.id)}
            <button
              type="button"
              disabled={actions.readonly}
              data-testid="plan-sheet-start"
              onclick={() => changeStart(waiting)}
              >{startLabel(waiting, startItems.length > 1)}</button
            >
          {/each}
          {#each optionalItems as optional (optional.id)}
            <button
              type="button"
              disabled={actions.readonly}
              data-testid="plan-sheet-optional"
              onclick={() => changeOptional(optional)}
              >{optionalItems.length > 1
                ? `Optional ingredients: ${itemName(optional, model.plan)}…`
                : 'Optional ingredients…'}</button
            >
          {/each}
          {#if !holdsCooked}
            <button type="button" disabled={actions.readonly} onclick={() => (mode = 'move')}
              >Move to…</button
            >
          {/if}
          {#if !tub}
            <button type="button" disabled={actions.readonly} onclick={() => (mode = 'copy')}
              >Copy to…</button
            >
            {#if !noteOnly}
              <button type="button" disabled={actions.readonly} onclick={() => (mode = 'leftovers')}
                >Leftovers on…</button
              >
            {/if}
          {/if}
          {#if tub && tub.tub.place_kind !== 'freezer'}
            <button
              type="button"
              disabled={actions.readonly || tubTooLate}
              aria-describedby={tubTooLate ? `${uid}-late` : undefined}
              onclick={toFreezer}>To freezer</button
            >
            {#if tubTooLate}
              <p class="hint" id="{uid}-late" data-testid="tub-too-late">{TOO_LATE_TO_FREEZE}</p>
            {/if}
          {/if}
          <!-- F49: taking a tub off a meal keeps the tub, so it isn't red and it says so. -->
          {#if holdsCooked}
            <!-- Proposed, for cabledrawer. -->
            <p class="hint" data-testid="cooked-stays">
              {cookedStaysNote(cookedNames)}
            </p>
            {#each partRecipes.filter((r) => !r.cooked) as left (left.id)}
              <!-- A recipe not cooked yet can go on its own; only cooked ones are locked. -->
              <button
                type="button"
                class="remove"
                disabled={actions.readonly}
                onclick={() => {
                  void model.removeItem(left.id);
                  onclose();
                }}>Remove {itemName(left, model.plan)}</button
              >
            {/each}
          {:else}
            <button
              type="button"
              class:remove={!tub}
              disabled={actions.readonly}
              onclick={remove}
              aria-describedby={tub ? 'take-off-hint' : undefined}
              >{tub ? 'Take off this meal (keep the tub)' : 'Remove'}</button
            >
          {/if}
          {#if tub}
            <p id="take-off-hint" class="hint">
              The tub stays in the {tub.tub.place_kind === 'freezer' ? 'freezer' : 'fridge'}, in
              Tubs left.
            </p>
          {/if}
        </div>
      {:else if mode === 'whose'}
        <h3>Whose tub?</h3>
        <div class="list">
          {#each model.people as person (person.member_id)}
            <button
              type="button"
              disabled={actions.readonly}
              aria-pressed={tub?.tub.member_id === person.member_id}
              onclick={() => whose(person.member_id)}>{person.name}</button
            >
          {/each}
          <button type="button" disabled={actions.readonly} onclick={() => whose(null)}
            >Nobody in particular</button
          >
          <button type="button" class="back" onclick={() => (mode = null)}>Back</button>
        </div>
      {:else if mode === 'useby'}
        <h3>Use by</h3>
        <input
          type="date"
          bind:value={useBy}
          min={tub?.batch.cooked_on}
          aria-label="Use by"
          aria-describedby={tooEarly ? 'tub-use-by-early' : undefined}
          data-testid="tub-use-by"
        />
        {#if badDay}
          <p class="early" role="alert">{BAD_DATE}</p>
        {:else if tooEarly}
          <p id="tub-use-by-early" class="early">Pick the cook day or later.</p>
        {/if}
        <div class="buttons">
          <button type="button" class="back" onclick={() => (mode = null)}>Back</button>
          <button
            type="button"
            class="go"
            disabled={!useBy || badDay || tooEarly || actions.readonly}
            onclick={saveUseBy}>Save</button
          >
        </div>
      {:else if mode === 'leftovers' && leftoverItem && aboutMeal}
        <LeftoversOn
          {actions}
          meal={aboutMeal}
          item={leftoverItem}
          onback={() => (mode = null)}
          {onclose}
        />
      {:else}
        <h3>{question}</h3>
        {#if target?.kind === 'recipe' && target.ahead}
          <!-- The next 14 days, from the recipe page only; fetched when first asked for (size limit). -->
          {#await import('./PlanItPicker.svelte') then { default: Loaded }}
            <Loaded {model} bind:day bind:slotId />
          {:catch}
            <LoadFailed />
          {/await}
        {:else}
          <!-- The arrow keys pick the day (Shift: the meal), Enter confirms; the focus is on this box. -->
          <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
          <div
            class="picker"
            role="group"
            aria-label="Pick the day and the meal with the arrow keys"
            tabindex="-1"
            bind:this={picker}
            onkeydown={pickKey}
          >
            <div class="weekbar">
              <button
                type="button"
                aria-label="Earlier week"
                disabled={atEarliestWeek}
                onclick={() => (weekOf = addDays(weekOf, -7))}
                ><Icon name="back" size={22} stroke={2.4} /></button
              >
              <span>{weekWords(weekOf, model.today.slice(0, 4))}</span>
              <button
                type="button"
                aria-label="Later week"
                onclick={() => (weekOf = addDays(weekOf, 7))}
                ><span class="flip"><Icon name="back" size={22} stroke={2.4} /></span></button
              >
            </div>
            <div class="days" role="group" aria-label="Day">
              {#each weekDays(weekOf) as d (d)}
                {#if dayShown(d)}
                  <button
                    type="button"
                    aria-pressed={day === d}
                    aria-label={dayFull(d)}
                    onclick={() => (day = d)}
                    ><span>{dayShort(d)}</span><b>{dayOfMonth(d)}</b></button
                  >
                {:else}
                  <span aria-hidden="true"></span>
                {/if}
              {/each}
            </div>
            <div class="slots" role="group" aria-label="Meal">
              {#each model.slotsOn as slot (slot.id)}
                {#if slotShown(slot.id)}
                  <button
                    type="button"
                    aria-pressed={slotId === slot.id}
                    onclick={() => (slotId = slot.id)}>{slot.name}</button
                  >
                {/if}
              {/each}
            </div>
          </div>
          <p class="picked" role="status">{samePlace ? '' : picked}</p>
          <p class="keys">
            Arrow keys pick the day, Shift and arrow keys pick the meal, Enter confirms, Esc
            cancels.
          </p>
        {/if}
        {#if samePlace}<p class="note" role="status">
            It’s already there. Pick another day or meal.
          </p>{/if}
        <div class="buttons">
          <button
            type="button"
            class="back"
            onclick={() =>
              target?.kind === 'recipe' || target?.kind === 'tubleft' ? onclose() : (mode = null)}
            >Back</button
          >
          <button type="button" class="go" disabled={!ready} onclick={choose}>{confirmWords}</button
          >
        </div>
      {/if}
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
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
    text-align: center;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: break-word;
  }

  h3 {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  /* The use-by box (F48), styled as the date boxes elsewhere (LotMenu). */
  .early {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  input[type='date'] {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .note {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
  }

  .list,
  .extras {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .extras {
    gap: var(--space-5);
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .list button {
    min-height: 54px;
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    text-align: left;
  }

  .parts {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .parts li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: 44px;
    border-bottom: 1px solid var(--color-divider);
    font-weight: var(--weight-bold);
  }

  .tag {
    padding: 4px 10px;
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .list .remove {
    color: var(--color-warning-text);
    background: var(--color-warning);
  }

  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .picker:focus-visible {
    outline: var(--focus-width) solid var(--color-focus);
    outline-offset: 4px;
    border-radius: var(--radius-md);
  }

  .picked {
    margin: 0;
    font-weight: var(--weight-bold);
    min-height: 1lh;
  }

  /* The key hints are for a mouse and keyboard; a finger has no arrow keys. */
  .keys {
    margin: 0;
    display: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  @media (pointer: fine) {
    .keys {
      display: block;
    }
  }

  .weekbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: var(--weight-bold);
  }

  .weekbar button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    display: grid;
    place-items: center;
    padding: 0;
  }

  .flip {
    display: grid;
    transform: rotate(180deg);
  }

  .days {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .days button {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 54px;
    padding: var(--space-3) 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .days b {
    font-size: var(--text-lg);
  }

  .slots {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .slots button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .days button[aria-pressed='true'],
  .slots button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
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
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
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
      max-height: min(680px, calc(100dvh - 120px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }
</style>
