<script lang="ts">
  // One line on the list (mockups ShopRows-*; cabledrawer 20 Oct).
  // Not ticked: only the square ticks. The name and the amount (a pill) both open the amount box.
  // On a phone, swiping the row left shows a red Remove; on a computer a bin shows when the
  // pointer is over the row. The red Remove after a swipe goes at once, with Undo (F77, cabledrawer
  // 28 Oct); the bin, the ⋯ menu and "Remove from list" in the amount box ask first.
  // In the trolley (F72, F173): one line, tick · name with what went in under it · the place as a
  // button ("→ Fridge ▾", tap to choose another); swipe left clears just this line. Notes for the
  // item sit underneath.
  import { tick as afterUpdate, untrack } from 'svelte';
  import { keepFocus } from '#lib/focusNear.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import type { Side } from '#lib/swipe.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { Note } from '#lib/shopping/types.js';
  import type { ViewItem } from '#lib/shopping/view.js';
  import Icon from '../Icon.svelte';
  import SwipeRow from '../SwipeRow.svelte';
  import AmountBox from './AmountBox.svelte';
  import MovePicker from './MovePicker.svelte';
  import NewPlace from '../NewPlace.svelte';
  import { addSuggestedSize } from '#lib/client/foods.js';
  import { serverUndo } from '#lib/client/changes.js';
  import type { FoodWrite, PackSuggestion } from '#lib/client/types.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { save } from '#lib/save.js';
  import { needLine, packLine, packParts, usualSize } from '#lib/shopping/packLine.js';
  import FoundSheet from './FoundSheet.svelte';
  import PackSheet from './PackSheet.svelte';
  import RemoveConfirm from './RemoveConfirm.svelte';
  import RowMenu from './RowMenu.svelte';

  let {
    model,
    view,
    trolley = false,
    notes = [],
    highlight = false,
    swiped = false,
    plan = false,
    clear = false
  }: {
    model: ShoppingModel;
    view: ViewItem;
    trolley?: boolean;
    notes?: Note[];
    highlight?: boolean;
    /** Start with the red Remove showing (the component gallery). */
    swiped?: boolean;
    /** Plan shopping (1100 px and wider): one line, tick · name · amount · why · ⋯. */
    plan?: boolean;
    /** In the trolley panel of Plan shopping: a ✕ that clears just this row. */
    clear?: boolean;
  } = $props();

  const item = $derived(view.item);
  const food = $derived(view.food);
  const tick = $derived(view.ticks[0]);
  /** "1 jar (500 g) · 120 g needed" under the name, when the Usual size is known (F120). */

  /** Plan shopping: the pack words are the amount ("1 jar (500 g)"); the need goes in the why. */
  const buy = $derived(plan && !trolley ? packParts(food, item.amount)?.buy : undefined);
  const why = $derived(plan && !trolley ? model.whyOf(item) : '');
  /** "Usual pack?": the common sizes, under a line with an amount and no size known. */
  const picks = $derived(
    !trolley && item.amount && !food.staple && !usualSize(food)
      ? (item.pack?.suggestions ?? [])
      : []
  );
  const packs = $derived(
    trolley
      ? null
      : (packLine(food, item.amount) ?? (picks.length ? needLine(food, item.amount) : null))
  );
  let whyOpen = $state(false);
  const offerStaple = $derived(!trolley && model.stapleOffered(item));

  function pick(choice: PackSuggestion) {
    let undoer: (() => Promise<string | void>) | null = null;
    void save<FoodWrite>({
      apply: () => {},
      rollback: () => {},
      send: (key) => addSuggestedSize(food.id, choice, key),
      saved: () => kitchen.changed({ elsewhere: true }),
      undo: {
        label: `${food.name}: added ${choice.display}`,
        labelFrom: (result) => result.change?.summary,
        skip: (result) => result.change === null,
        run: (result) => (result.change ? (undoer ??= serverUndo(result.change.id))() : false)
      }
    });
  }

  let editing = $state(false);
  let asking = $state(false);
  let packOpen = $state(false);
  let addingPlace = $state(false);
  $effect(() => {
    if (!placing) addingPlace = false;
  });
  let packButton = $state<HTMLElement>();
  let newPlaceButton = $state<HTMLElement>();
  let nameButton = $state<HTMLButtonElement>();
  let rowEl = $state<HTMLElement>();

  const place = $derived(model.placeName(tick?.place_id ?? item.put_away_place_id));
  const placing = $derived(model.placing === item.id);
  const planned = $derived(
    trolley && tick?.bought && tick.bought.display !== item.display && item.display
      ? `Planned ${item.display}`
      : null
  );
  const putAway = $derived(trolley ? model.putAwayFor(item) : null);
  /** The line under a name in the trolley: what went in ("2 × 200 g"), found at home, planned. */
  const trolleySub = $derived.by(() => {
    if (!trolley || !putAway) return '';
    const parts: string[] = [];
    if (putAway.kind === 'staple') parts.push('Restocked · staples aren’t counted');
    else if (putAway.kind === 'none') parts.push('Not in the pantry yet. No amount.');
    else parts.push(putAway.amount);
    if (tick?.found) parts.push('found at home');
    if (planned && !tick?.found) parts.push(planned);
    return parts.join(' · ');
  });

  // Just ticked with no amount: "How much?" opens on its row (F62). The row may be a new one in
  // the trolley by now, so the model remembers which item asked.
  $effect(() => {
    if (trolley && view.ticks.length && model.askingHowMuch === item.id) {
      untrack(() => {
        packOpen = true;
        autoOpened = true;
      });
    }
  });

  let autoOpened = $state(false);

  function closePack() {
    packOpen = false;
    autoOpened = false;
    if (model.askingHowMuch === item.id) model.askingHowMuch = null;
    // Opened by itself: there is no button to give the focus back to, so the row's own
    // "Add amount" (or, once it has an amount, its tick) takes it.
    const back =
      packButton ??
      rowEl?.querySelector<HTMLElement>(`button[aria-label="Add amount for ${food.name}"]`) ??
      rowEl?.querySelector<HTMLElement>('input[type="checkbox"]');
    back?.focus();
  }

  // The line was ticked elsewhere while its amount box was open: the box has no place now.
  $effect(() => {
    if (trolley) editing = false;
  });

  // --- Swipe (phone) -------------------------------------------------------------------------------
  let open = $state<Side>(untrack(() => (swiped ? 'left' : null)));
  const swipeable = $derived(model.device === 'phone' && !editing);
  /** "Already have it": how much is at home (a sheet), then it goes into the pantry as found. */
  let haveOpen = $state(false);

  /** In the trolley, swipe left clears just this line (F72, cabledrawer 6 Nov). */
  function clearNow() {
    const back = keepFocus(nameButton ?? rowEl ?? document.body);
    void model.clearTicked([item]);
    back();
  }

  function openBox() {
    open = null;
    editing = true;
  }

  async function closeBox() {
    editing = false;
    await afterUpdate();
    nameButton?.focus();
  }

  // Where the focus was when the question opened, so Keep it can give it back.
  let opener: Element | null = null;

  function ask(from?: Element) {
    opener = from ?? document.activeElement;
    open = null;
    asking = true;
  }

  // "Move to…": a sheet on a phone (swipe right, or the amount box), a small menu by the ⋯ button
  // on a computer. Never ticks the line.
  let moving = $state(false);
  let moveFrom = $state<HTMLElement | null>(null);

  function openMove(from?: HTMLElement) {
    moveFrom = from ?? (document.activeElement as HTMLElement | null);
    open = null;
    moving = true;
  }

  function moveTo(to: { shopId: number | null } | { listId: string }) {
    // The row leaves this spot: note its neighbour (or the shop's heading) to give focus to.
    const back = keepFocus(nameButton ?? moveFrom ?? document.body);
    editing = false;
    void model.move(item, {
      listId: 'listId' in to ? to.listId : item.list_id,
      shopId: 'shopId' in to ? to.shopId : item.shop_id
    });
    back();
  }

  async function keep() {
    asking = false;
    await afterUpdate();
    // The red Remove and the amount box go when the question closes: fall back to the name.
    const back = opener?.isConnected ? opener : nameButton;
    (back as HTMLElement | null | undefined)?.focus();
  }

  /** The red Remove after a swipe: the row goes at once, with "Removed X" and Undo. */
  function removeNow() {
    const back = keepFocus(nameButton ?? document.body);
    void model.remove(item);
    back();
  }

  function remove(event: MouseEvent) {
    // The row goes, and the focus with it: note the neighbour to move to first.
    const back = keepFocus(event.currentTarget as HTMLElement);
    asking = false;
    editing = false;
    void model.remove(item);
    back();
  }
</script>

{#snippet menu()}
  <RowMenu
    name={food.name}
    items={[
      { label: 'Change amount', run: () => openBox() },
      { label: 'Move to…', run: (from) => openMove(from) },
      { label: 'Remove from list…', danger: true, run: (from) => ask(from) }
    ]}
  />
{/snippet}

<li class="item" class:trolley class:highlight class:plan bind:this={rowEl}>
  {#if editing && !trolley}
    <AmountBox
      {model}
      {view}
      onclose={() => void closeBox()}
      onremove={() => ask()}
      onmove={() => openMove()}
      onhave={() => {
        editing = false;
        haveOpen = true;
      }}
    />
  {:else}
    <SwipeRow
      bleed={14}
      enabled={swipeable}
      bind:open
      left={trolley
        ? {
            label: 'Clear',
            describe: `${food.name} from the trolley`,
            icon: 'trash',
            tone: 'danger',
            run: () => clearNow()
          }
        : {
            label: 'Remove',
            describe: `${food.name} from the list`,
            icon: 'trash',
            tone: 'danger',
            run: () => removeNow()
          }}
      right={trolley
        ? undefined
        : {
            label: 'Already have it',
            describe: `${food.name}: it is at home`,
            icon: 'check',
            tone: 'used',
            run: () => (haveOpen = true)
          }}
      rightMore={trolley
        ? undefined
        : {
            label: 'Move…',
            describe: `${food.name} to another shop or list`,
            icon: 'arrow-right',
            tone: 'move',
            run: () => openMove()
          }}
    >
      <div class="line">
        <label class="tick">
          <input
            type="checkbox"
            checked={trolley}
            aria-label="{trolley ? 'Untick' : 'Tick'} {food.name}"
            onchange={(event) => {
              const back = keepFocus(event.currentTarget);
              void (trolley ? model.untick(item) : model.tick(item));
              back();
            }}
          />
          <span class="box" aria-hidden="true">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3.2"
              stroke-linecap="round"
              stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg
            >
          </span>
        </label>
        {#if trolley}
          <span class="what">
            <span class="name">{food.name}</span>
            {#if trolleySub}<span class="sub">{trolleySub}</span>{/if}
          </span>
          {#if putAway?.kind === 'amount'}
            <button
              type="button"
              class="place"
              aria-expanded={placing}
              aria-label="Change where {food.name} went"
              onclick={() => (model.placing = placing ? null : item.id)}
              >→ {putAway.place ?? 'Pantry'}<Icon
                name="chevron-down"
                size={12}
                stroke={2.8}
              /></button
            >
          {:else if putAway?.kind === 'none'}
            <button
              type="button"
              class="place"
              aria-label="Add amount for {food.name}"
              onclick={(event) => {
                autoOpened = false;
                packButton = event.currentTarget;
                packOpen = true;
              }}>Add amount</button
            >
          {/if}
          {#if clear}
            <button
              type="button"
              class="x"
              aria-label="Clear {food.name}"
              onclick={(event) => {
                const back = keepFocus(event.currentTarget);
                void model.clearTicked([item]);
                back();
              }}><Icon name="close" size={16} stroke={2.4} /></button
            >
          {/if}
        {:else}
          <button
            type="button"
            class="name"
            bind:this={nameButton}
            aria-expanded={editing}
            title={plan ? food.name : undefined}
            onclick={openBox}>{food.name}</button
          >
          <span class="end">
            <button
              type="button"
              class="amount"
              aria-expanded={editing}
              aria-label={item.display
                ? `Change amount: ${food.name}, ${item.display}`
                : `Add amount for ${food.name}`}
              onclick={openBox}
            >
              {buy ?? item.display ?? 'Add amount'}
              {#if item.display}<Icon name="chevron-down" size={14} stroke={2.4} />{/if}
            </button>
            {#if model.device === 'computer' && !plan}{@render menu()}{/if}
          </span>
          {#if plan}
            {#if why}
              <button
                type="button"
                class="why"
                title={why}
                aria-expanded={whyOpen}
                onclick={() => (whyOpen = !whyOpen)}>{why}</button
              >
            {:else}
              <span class="why"></span>
            {/if}
            <!-- After the why, so the keyboard meets them in the order they are seen. -->
            {#if model.device === 'computer'}{@render menu()}{/if}
          {:else if packs}
            <span class="packs">{packs}</span>
          {/if}
        {/if}
      </div>
    </SwipeRow>
  {/if}

  {#if picks.length}
    <div class="picks" role="group" aria-label="Usual pack for {food.name}?">
      <span class="lead">Usual pack for {food.name}?</span>
      {#each picks as choice (choice.amount)}
        <button type="button" class="chip" disabled={network.offline} onclick={() => pick(choice)}
          >{choice.amount_text}</button
        >
      {/each}
    </div>
  {/if}

  {#if offerStaple}
    <div class="picks">
      <button type="button" class="chip" onclick={() => void model.makeStaple(food)}
        >Make it a staple?</button
      >
    </div>
  {/if}

  {#if placing && trolley}
    <div class="places" role="radiogroup" aria-label="Where did {food.name} go?" use:radioKeys>
      {#each model.placeChoices as p (p.id)}
        <button
          type="button"
          role="radio"
          aria-checked={p.name === place}
          onclick={() => void model.putAway(item, p.id)}>{p.name}</button
        >
      {/each}
    </div>
    {#if addingPlace}
      <div class="new-place">
        <NewPlace
          onadded={(added) => {
            addingPlace = false;
            void model.putAway(item, added.id);
          }}
          oncancel={() => {
            // The "+ Place" that opened the box was gone while it was open: focus the new one.
            addingPlace = false;
            void afterUpdate().then(() => newPlaceButton?.focus());
          }}
        />
      </div>
    {:else}
      <button
        type="button"
        class="pack"
        bind:this={newPlaceButton}
        onclick={() => (addingPlace = true)}>+ Place</button
      >
    {/if}
    {#if !tick?.found}
      <button
        type="button"
        class="pack"
        bind:this={packButton}
        aria-expanded={packOpen}
        onclick={() => (packOpen = !packOpen)}>Different pack?</button
      >
    {/if}
  {/if}

  {#if packOpen && trolley && view.ticks.length}
    <PackSheet
      {model}
      {item}
      {food}
      ticks={view.ticks}
      focusOnOpen={autoOpened}
      onclose={closePack}
    />
  {/if}

  {#each notes as note (note.id)}
    <p class="note">
      <span>{note.text}</span>
      {#if note.undo}
        <button type="button" class="link" onclick={() => void model.undo(note.undo!)}>Undo</button>
      {/if}
      <button
        type="button"
        class="link"
        aria-label="Dismiss: {note.text}"
        onclick={() => void model.dismissNote(note.id)}>✕</button
      >
    </p>
  {/each}

  {#if moving || moveFrom}
    <MovePicker
      open={moving}
      name={food.name}
      {...model.movePlaces(item)}
      anchor={moveFrom}
      fallback={nameButton ?? null}
      onpick={moveTo}
      onclose={() => (moving = false)}
    />
  {/if}

  {#if haveOpen}
    <FoundSheet {model} {item} {food} onclose={() => (haveOpen = false)} />
  {/if}

  {#if asking}
    <RemoveConfirm name={food.name} onremove={remove} onkeep={() => void keep()} />
  {/if}
</li>

<style>
  .item {
    display: flex;
    flex-direction: column;
    border-bottom: 1px solid var(--color-divider);
  }

  .item:last-child {
    border-bottom: none;
  }

  /* The card's rounded corners, given to the swipe area inside the first and last row. */
  .item:first-child :global(.swipe) {
    border-top-left-radius: var(--radius-xl);
    border-top-right-radius: var(--radius-xl);
  }

  .item:last-child :global(.swipe) {
    border-bottom-left-radius: var(--radius-xl);
    border-bottom-right-radius: var(--radius-xl);
  }

  /* Plan shopping: one line, tick · name · amount · why · ⋯ (mockup Dark-ShopPlan08-Desktop). */
  .plan:not(.trolley) .line {
    display: grid;
    grid-template-columns: 24px minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1.2fr) 40px;
    align-items: center;
    gap: 0 var(--space-6);
    min-height: 48px;
    padding: 0;
  }

  .plan:not(.trolley) .line .tick {
    order: 1;
    margin: 0 -10px;
  }

  .plan:not(.trolley) .line .name {
    order: 2;
    flex: none;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .plan:not(.trolley) .end {
    display: contents;
  }

  .plan:not(.trolley) .amount {
    order: 3;
    justify-self: start;
    max-width: 100%;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text-soft, var(--color-text));
    font-size: var(--text-md);
    white-space: nowrap;
  }

  .plan:not(.trolley) .why {
    order: 4;
  }

  .plan:not(.trolley) .line > :global(.row-menu) {
    order: 5;
  }

  .why {
    min-width: 0;
    padding: 0;
    overflow: hidden;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-regular, 400) var(--text-md) var(--font-ui);
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* The whole text on hover, on focus and after a tap. */
  button.why {
    cursor: pointer;
  }

  .why:hover,
  .why:focus-visible,
  .why[aria-expanded='true'] {
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .picks {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    padding: 0 0 var(--space-4) 34px;
  }

  .plan .picks .chip {
    min-width: 0;
    min-height: 34px;
  }

  .picks .lead {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .picks .chip {
    /* 44 px to tap on a phone; Plan shopping's rows are denser (a computer, mockup 36 px). */
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 12px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .x {
    flex: none;
    width: 36px;
    height: 36px;
    margin-left: auto;
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .highlight :global(.slide) {
    background: var(--color-accent-soft);
  }

  .line {
    display: flex;
    flex-wrap: wrap; /* the amount drops under a name whose longest word doesn't fit beside it (F82) */
    align-items: center;
    gap: 0 var(--space-6);
    min-height: 60px;
    padding: var(--space-2) 0;
  }

  /* The amount and the menu stay together, and drop under the name as one. */
  .end {
    display: flex;
    flex: none;
    align-items: center;
    gap: 0 var(--space-6);
    margin-left: auto;
  }

  .trolley .line {
    flex-wrap: nowrap;
    align-items: center;
    min-height: 56px;
    padding: var(--space-2) 0;
  }

  /* The place the tick went to, as a button: "→ Fridge ▾" (F72, cabledrawer 28 Oct). */
  .place {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .place[aria-expanded='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  /* A 44 px tap area around the 28 px square, as in the mockup's row. */
  .tick {
    position: relative;
    display: grid;
    flex: none;
    place-items: center;
    width: var(--touch-target);
    height: var(--touch-target);
    margin: 0 calc(-1 * var(--space-2)) 0 calc(-1 * var(--space-4));
  }

  .tick input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .box {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border: 2px solid var(--color-field-border);
    border-radius: 8px;
    background: var(--color-field);
    color: transparent;
  }

  .tick input:checked + .box {
    border-color: #2e7d5b;
    background: #2e7d5b;
    color: #ffffff;
  }

  .tick input:focus-visible + .box {
    outline: 2px solid var(--color-focus);
    outline-offset: 2px;
  }

  .what {
    display: flex;
    flex: 1 1 8rem;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  /* Names wrap between words, never inside one: the name's starting width is its longest word
     (`flex-basis: min-content`, which `overflow-wrap: anywhere` would make tiny), and the amount
     moves under it when that doesn't fit. The cap at the row's width means only a word wider
     than the whole row still breaks, with no sideways scroll (F82, cabledrawer 30 Oct). */
  .name {
    flex: 1 1 min-content;
    min-width: 0;
    max-width: 100%;
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
    text-align: left;
    overflow-wrap: break-word;
  }

  /* Not ticked: the name is a button that opens the amount box. */
  button.name {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    cursor: pointer;
  }

  .trolley .name {
    flex: none;
    color: var(--color-text);
  }

  /* Under the name, on its own line, in line with it. */
  .packs {
    flex-basis: 100%;
    padding-left: calc(var(--touch-target) - var(--space-4) - var(--space-2) + var(--space-6));
    padding-bottom: var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  /* The amount looks tappable: a pill, with a chevron when there is an amount. */
  .amount {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--touch-target);
    padding: 0 var(--space-5) 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .amount :global(svg) {
    color: var(--color-text-muted);
  }

  .places {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0 0 var(--space-3) 34px;
  }

  .places button,
  .pack {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .pack {
    align-self: flex-start;
    margin: 0 0 var(--space-4) 34px;
  }

  .new-place {
    margin: 0 0 var(--space-4) 34px;
  }

  .places button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .note {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    margin: 0 0 var(--space-4) 34px;
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .note span {
    flex: 1;
  }

  .link {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }
</style>
