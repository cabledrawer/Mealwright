<script lang="ts">
  // "+ Add to pantry" (spec "Decided for 0.2"; no mockup yet): pick or type a food; how
  // much, as sold (1 packet, 2 packets…) or typed; where (filled in from the food's
  // usual place); and an optional use-by (none · today · +3 days · +1 week · pick a date,
  // which opens the device's own date picker and then shows the date it chose).
  // A sheet from the bottom on phones, a dialog on desktop.
  import { cantReach } from '#lib/api.js';
  import { cantReachText, needsServer } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import { addToPantry } from '#lib/addToPantry.svelte.js';
  import { getFood } from '#lib/client/foods.js';
  import type { Food, Place, Ref } from '#lib/client/types.js';
  import { BAD_DATE, addDays, isSaneDay, pickedDateWords } from '#lib/dates.js';
  import type { PantryModel } from '#lib/pantry.svelte.js';
  import { amountExample } from '#lib/amountExample.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import FoodPicker from './FoodPicker.svelte';
  import NewPlace, { NEW_PLACE } from './NewPlace.svelte';
  import Icon from './Icon.svelte';
  import { couldntLoad } from '#lib/errorWords.js';

  let { model, places, today }: { model: PantryModel; places: Place[]; today: string } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let food = $state<Food | null>(null);
  let loading = $state(false);
  /** "size:12:2" = 2 of size 12; "typed" = the amount box. */
  let howMuch = $state('typed');
  let typedAmount = $state('');
  let typedUnit = $state('g');
  let placeId = $state<number | null>(null);
  let when = $state<'none' | 'today' | '3' | '7' | 'pick'>('none');
  let picked = $state('');
  let dateInput = $state<HTMLInputElement>();
  let problem = $state<string | null>(null);
  let addingPlace = $state(false);
  /** The pantry's places, and any made here with "+ Place" before the pantry has reloaded. */
  const allPlaces = $derived([
    ...places,
    ...placesAndShops.places.filter((p) => !places.some((q) => q.id === p.id))
  ]);

  $effect(() => {
    if (addToPantry.open && !dialog.open) {
      reset();
      dialog.showModal();
      if (addToPantry.foodId !== null) void choose({ id: addToPantry.foodId, name: '' });
      // Start in the "What" box, not on Cancel.
      else dialog.querySelector<HTMLInputElement>('input[type="search"]')?.focus();
    } else if (!addToPantry.open && dialog.open) {
      dialog.close();
    }
  });

  function reset() {
    food = null;
    howMuch = 'typed';
    typedAmount = '';
    when = 'none';
    picked = '';
    problem = null;
    addingPlace = false;
  }

  const usual = $derived(food?.sizes.find((s) => s.usual) ?? food?.sizes[0]);
  const units = $derived(
    !food
      ? []
      : [
          ...(food.counted_as === 'count' ? [] : food.sizes.map((s) => s.name)),
          ...(food.counted_as === 'weight'
            ? ['g', 'kg']
            : food.counted_as === 'volume'
              ? ['ml', 'l']
              : [food.count_word_plural ?? 'items'])
        ]
  );

  async function choose(ref: Ref) {
    loading = true;
    problem = null;
    try {
      const loaded = await getFood(ref.id);
      food = loaded;
      const size = loaded.sizes.find((s) => s.usual) ?? loaded.sizes[0];
      howMuch = size ? `size:${size.id}:1` : 'typed';
      typedUnit =
        loaded.counted_as === 'weight'
          ? 'g'
          : loaded.counted_as === 'volume'
            ? 'ml'
            : (loaded.count_word_plural ?? 'items');
      placeId =
        loaded.place?.id ?? places.find((p) => p.kind === 'cupboard')?.id ?? places[0]?.id ?? null;
    } catch (error) {
      // The words follow the cause, like the pages (cabledrawer 30 Oct).
      problem = cantReach(error)
        ? needsServer(network.deviceOffline, cantReachText(true))
        : couldntLoad('that ingredient');
    } finally {
      loading = false;
    }
  }

  /**
   * "+ New ingredient": asks "Pantry keeps it by" first, as Shopping and the recipe editor
   * do; that sheet makes it (or finds the one already called that), then it’s picked here.
   * The question opens on top of this sheet; Cancel there comes back here with nothing made.
   */
  async function create(name: string) {
    const made = await newIngredient.ask(name);
    if (made) await choose(made);
  }

  function amountChoices(f: Food) {
    if (!usual || f.counted_as === 'count') return [];
    return [1, 2, 3].map((n) => ({
      value: `size:${usual.id}:${n}`,
      label: `${n}\u00a0${n === 1 ? usual.name : usual.plural}`
    }));
  }

  /**
   * "Pick a date": open the device's own picker. On a touch screen the date input lies
   * over the chip and the tap lands on it directly (see the style), which is what makes
   * iOS Safari open its date wheel at once. With a mouse or keyboard the chip asks the
   * input to show its picker, falling back to a click where showPicker isn't there.
   * Nothing changes until a date comes back, so cancelling leaves things as they were.
   */
  function openPicker() {
    if (!dateInput) return;
    try {
      dateInput.showPicker();
    } catch {
      dateInput.focus();
      dateInput.click();
    }
  }

  /** A date came back from the picker (or it was cleared there). */
  function picker() {
    if (!dateInput) return;
    const value = dateInput.value;
    if (value && !isSaneDay(value)) {
      problem = BAD_DATE;
      dateInput.value = picked;
    } else if (value && value >= today) {
      problem = null;
      picked = value;
      when = 'pick';
    } else {
      // Cleared in the picker, or earlier than today: a cleared date goes back to "No
      // date", an earlier one leaves things as they were.
      if (!value && when === 'pick') {
        when = 'none';
        picked = '';
      }
      dateInput.value = picked;
    }
  }

  /** Choosing any other chip puts the picked date away. */
  function setWhen(option: 'none' | 'today' | '3' | '7') {
    when = option;
    picked = '';
  }

  function useBy(): string | null {
    if (when === 'today') return today;
    if (when === '3') return addDays(today, 3);
    if (when === '7') return addDays(today, 7);
    if (when === 'pick') return picked || null;
    return null;
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!food) return;
    let amount: { amount: number; unit?: string; size_id?: number };
    let words: string;
    if (howMuch.startsWith('size:')) {
      const [, sizeId, n] = howMuch.split(':').map(Number) as [number, number, number];
      const size = food.sizes.find((s) => s.id === sizeId);
      amount = { amount: n, size_id: sizeId };
      words = `${n}\u00a0${n === 1 ? size?.name : size?.plural}`;
    } else {
      const n = Number(typedAmount.replace(',', '.'));
      if (!(n > 0)) {
        problem = 'How much? Type an amount, like 200.';
        return;
      }
      const unit =
        food.counted_as === 'count' && !food.sizes.some((s) => s.name === typedUnit)
          ? 'count'
          : typedUnit;
      amount = { amount: n, unit };
      words = unit === 'count' ? String(n) : `${n}\u00a0${typedUnit}`;
    }
    const place = allPlaces.find((p) => p.id === placeId);
    const stock = {
      food_id: food.id,
      amount,
      ...(placeId ? { place_id: placeId } : {}),
      ...(useBy() ? { use_by: useBy() } : {})
    };
    const label = `Added ${words} ${food.name}${place ? ` → ${place.name}` : ''}`;
    addToPantry.close();
    // Optimistic: the sheet closes and the toast (with Undo) shows at once; the pantry
    // fills in when the server answers.
    void model.add(stock, label);
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) addToPantry.close();
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  oncancel={() => addToPantry.close()}
  onclick={closeOnBackdrop}
>
  {#if addToPantry.open}
    <form class="body" onsubmit={submit}>
      <span class="handle" aria-hidden="true"></span>
      <header>
        <h2 id="{uid}-title">Add to pantry</h2>
        <button type="button" class="quiet" onclick={() => addToPantry.close()}>Cancel</button>
      </header>

      <section aria-labelledby="{uid}-what">
        <h3 id="{uid}-what">What</h3>
        {#if food}
          <div class="chosen">
            <b>{food.name}</b>
            {#if addToPantry.foodId === null}
              <button type="button" class="link" onclick={() => (food = null)}>Change</button>
            {/if}
          </div>
        {:else if loading}
          <p class="hint">Loading…</p>
        {:else}
          <FoodPicker
            label="Find an ingredient"
            placeholder="e.g. toor dal"
            onpick={(f) => void choose(f)}
            oncreate={(name) => void create(name)}
          />
        {/if}
      </section>

      {#if food}
        {#if food.staple}
          <p class="note" role="status">
            {food.name} is a staple, so it isn’t counted. Turn off Staple in the ingredient to count it.
          </p>
        {:else}
          <section aria-labelledby="{uid}-much">
            <h3 id="{uid}-much">How much</h3>
            <div class="chips" role="radiogroup" aria-labelledby="{uid}-much" use:radioKeys>
              {#each amountChoices(food) as choice (choice.value)}
                <button
                  type="button"
                  role="radio"
                  aria-checked={howMuch === choice.value}
                  onclick={() => (howMuch = choice.value)}>{choice.label}</button
                >
              {/each}
              {#if amountChoices(food).length}
                <button
                  type="button"
                  role="radio"
                  aria-checked={howMuch === 'typed'}
                  onclick={() => (howMuch = 'typed')}>Other amount</button
                >
              {/if}
            </div>
            {#if howMuch === 'typed'}
              <div class="typed">
                <label>
                  Amount
                  <input
                    inputmode="decimal"
                    maxlength="20"
                    bind:value={typedAmount}
                    placeholder={amountExample(
                      typedUnit,
                      food.sizes.some((size) => size.name === typedUnit)
                    )}
                  />
                </label>
                <label>
                  Unit
                  <select bind:value={typedUnit}>
                    {#each units as unit (unit)}<option>{unit}</option>{/each}
                  </select>
                </label>
              </div>
            {/if}
          </section>

          <section>
            <h3 id="{uid}-where">Where</h3>
            <select
              class="where"
              aria-labelledby="{uid}-where"
              value={placeId}
              onchange={(event) => {
                if (event.currentTarget.value === NEW_PLACE) {
                  addingPlace = true;
                  event.currentTarget.value = String(placeId ?? '');
                } else placeId = Number(event.currentTarget.value);
              }}
            >
              {#each allPlaces as place (place.id)}<option value={place.id}>{place.name}</option
                >{/each}
              <option value={NEW_PLACE}>+ Place</option>
            </select>
            {#if addingPlace}
              <NewPlace
                onadded={(place) => {
                  placeId = place.id;
                  addingPlace = false;
                }}
                oncancel={() => (addingPlace = false)}
              />
            {/if}
          </section>

          <section aria-labelledby="{uid}-when">
            <h3 id="{uid}-when">Use by</h3>
            <!-- Arrows choose as they move, like the other chip groups. The one exception is
                 "Pick a date" (data-no-arrow-select): arrowing onto it only moves focus, so
                 the picker opens on Space, Enter or a tap, never just because focus arrived. -->
            <div class="chips" role="radiogroup" aria-labelledby="{uid}-when" use:radioKeys>
              {#each [{ v: 'none', l: 'No date' }, { v: 'today', l: 'Today' }, { v: '3', l: '+3 days' }, { v: '7', l: '+1 week' }] as const as option (option.v)}
                <button
                  type="button"
                  role="radio"
                  aria-checked={when === option.v}
                  onclick={() => setWhen(option.v)}>{option.l}</button
                >
              {/each}
              <span class="pick">
                <button
                  type="button"
                  role="radio"
                  aria-checked={when === 'pick'}
                  data-no-arrow-select
                  onclick={openPicker}
                >
                  {#if when === 'pick'}
                    <Icon name="calendar" size={16} stroke={2.2} />{pickedDateWords(picked)}
                  {:else}
                    Pick a date
                  {/if}
                </button>
                <!-- The device's own date picker, laid over the chip and see-through. -->
                <input
                  bind:this={dateInput}
                  class="native"
                  type="date"
                  min={today}
                  value={picked}
                  tabindex="-1"
                  aria-hidden="true"
                  data-use-by-input
                  onchange={picker}
                />
              </span>
            </div>
          </section>
        {/if}
      {/if}

      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}

      <button type="submit" class="add" disabled={!food || food.staple || network.offline}
        >Add to pantry</button
      >
    </form>
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
    gap: var(--space-7);
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
    justify-content: space-between;
    align-items: center;
  }

  h2 {
    font-size: 1.375rem;
    font-weight: var(--weight-extrabold);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .chosen {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    font-size: var(--text-lg);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chips button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chips button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .typed {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
  }

  label {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  label input,
  label select,
  select.where {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  /*
   * "Pick a date" is a chip with a see-through date input laid exactly over it.
   *  - Touch screens: the input takes the tap itself. That is the one thing iOS Safari
   *    (WebKit) reliably answers with its date wheel; a script calling showPicker() on
   *    another element's tap is not as dependable there.
   *  - Mouse: the input ignores the pointer, so the chip is clicked as usual and asks
   *    the input to open its picker, which then sits right at the chip.
   * appearance: none (with the -webkit- spelling), min-width: 0 and a 16 px font keep
   * WebKit from giving the input a width of its own, or zooming the page on focus.
   */
  .pick {
    position: relative;
    display: inline-flex;
  }

  .chips .pick button {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
  }

  .native {
    -webkit-appearance: none;
    appearance: none;
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    min-width: 0;
    max-width: 100%;
    margin: 0;
    padding: 0;
    border: none;
    opacity: 0;
    font-size: 16px;
    pointer-events: none;
  }

  @media (pointer: coarse) {
    .native {
      pointer-events: auto;
    }
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .note {
    padding: var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .quiet {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .link {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .add {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .add:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: calc(100dvh - 60px);
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(480px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-10));
      padding: var(--space-9);
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }
</style>
