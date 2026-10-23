<script lang="ts">
  // One ingredient line on the review (mockups Import05-Phone and Import05-Desktop, spec
  // "The labels", "Learning", "New ingredient from an import" and "Treat as staple"): the line
  // as written, how Mealwright read it, and what it is in your kitchen.
  //
  //   Matched / Staple   nothing to do: the ingredient and where it lives.
  //   To confirm         "Same as Onions" · "New ingredient" (a close match it isn't sure of).
  //   Needs you          Pick an ingredient · New ingredient · Treat as staple.
  //
  // A choice shows what it will do, can be changed right here, and is only made when Save is
  // pressed (the new ingredient, the staple and the other name it learns).
  import FoodPicker from '$lib/components/FoodPicker.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import type { ReviewLine } from '$lib/client/imports';
  import type { CountedAs, Ref } from '$lib/client/types';
  import type { Choice, ImportFlow } from '$lib/import.svelte';
  import { placesAndShops } from '$lib/placesAndShops.svelte';

  import '$lib/styles/fields.css';
  let {
    flow,
    index,
    line,
    problem = null
  }: { flow: ImportFlow; index: number; line: ReviewLine; problem?: string | null } = $props();

  const uid = $props.id();
  let picking = $state(false);
  const choice = $derived(flow.choices[index] ?? null);
  const open = $derived(line.label === 'to_confirm' || line.label === 'needs_you');
  const COUNTED: { value: CountedAs; label: string }[] = [
    { value: 'weight', label: 'By weight' },
    { value: 'volume', label: 'By volume' },
    { value: 'count', label: 'One by one' }
  ];

  /** "200 g", "3", "1½ cups": the amount as it will be saved. */
  const quantity = $derived(
    line.amount_text
      ? [line.amount_text, line.unit ? unitWord(line.unit) : ''].join(' ').trim()
      : ''
  );

  function unitWord(unit: string): string {
    return unit === 'cup' ? (line.amount === 1 ? 'cup' : 'cups') : unit;
  }

  $effect(() => {
    if (!placesAndShops.places.length) void placesAndShops.load().catch(() => {});
  });

  function pick(food: Ref) {
    picking = false;
    flow.sameAs(index, food);
  }

  function edit(change: Partial<Extract<Choice, { kind: 'new' | 'staple' }>>) {
    if (choice && choice.kind !== 'food') flow.choose(index, { ...choice, ...change });
  }

  const alsoCalled = $derived(
    line.matched_by && line.food && line.matched_by.toLowerCase() !== line.food.name.toLowerCase()
      ? line.matched_by
      : null
  );
</script>

{#if line.kind === 'heading'}
  <li class="heading"><h3>{line.words}</h3></li>
{:else}
  <li
    class="line"
    class:confirm={line.label === 'to_confirm' && !choice}
    class:needs={line.label === 'needs_you' && !choice}
  >
    <p class="written"><span class="visually-hidden">As written: </span>{line.written}</p>

    {#if !open}
      <p class="read">
        <span class="what">
          {#if quantity}<b>{quantity}</b>{/if}
          {line.food?.name ?? line.words}
          {#if alsoCalled}<span class="muted">· also called {alsoCalled}</span>{/if}
          {#if line.note && !quantity}<span class="muted">· {line.note}</span>{/if}
          {#if !line.counts && line.label === 'matched'}<span class="muted">· not counted</span
            >{/if}
        </span>
        <span class="state" class:staple={line.label === 'staple'}>
          {#if line.label === 'staple'}Staple{:else}<Icon
              name="check"
              size={14}
              stroke={2.6}
            />{line.place ?? 'In your ingredients'}{/if}
        </span>
      </p>
    {:else if choice}
      <!-- A choice has been made: what it will do, and a way to change it. -->
      <p class="read">
        <span class="what">
          {#if quantity}<b>{quantity}</b>{/if}
          {#if choice.kind === 'food'}
            {choice.food.name}
            <span class="muted">· same as “{line.learn_name ?? line.words}”</span>
          {:else}
            {choice.name}
          {/if}
        </span>
        <span class="state">
          {choice.kind === 'food'
            ? 'Same as'
            : choice.kind === 'staple'
              ? 'New staple'
              : 'New ingredient'}
        </span>
      </p>
      {#if choice.kind === 'food' && line.learn_name}
        <p class="hint">
          Adds “{line.learn_name}” as another name for {choice.food.name} when you save.
        </p>
      {:else if choice.kind !== 'food'}
        <div class="fields">
          <label class="field" for="{uid}-name">
            <span>Name</span>
            <input
              id="{uid}-name"
              class="mw-input"
              type="text"
              maxlength="100"
              value={choice.name}
              oninput={(e) => edit({ name: e.currentTarget.value })}
            />
          </label>
          <label class="field" for="{uid}-how">
            <span>How it’s counted</span>
            <select
              id="{uid}-how"
              class="mw-input"
              value={choice.counted_as}
              onchange={(e) => edit({ counted_as: e.currentTarget.value as CountedAs })}
            >
              {#each COUNTED as option (option.value)}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </label>
          <label class="field" for="{uid}-place">
            <span>Usually kept in</span>
            <select
              id="{uid}-place"
              class="mw-input"
              value={choice.place_id ?? ''}
              onchange={(e) =>
                edit({ place_id: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
            >
              <option value="">Nowhere in particular</option>
              {#each placesAndShops.places as place (place.id)}
                <option value={place.id}>{place.name}</option>
              {/each}
            </select>
          </label>
        </div>
        <p class="hint">
          {choice.kind === 'staple'
            ? 'Made a staple when you save. It never counts towards stock.'
            : 'Made when you save. Nothing is added to the pantry.'}
        </p>
      {/if}
      <p class="buttons">
        <button type="button" class="chip" onclick={() => flow.choose(index, null)}>Change</button>
      </p>
    {:else}
      <p class="read">
        <span class="what">
          {#if quantity}<b>{quantity}</b>{/if}
          {#if line.label === 'to_confirm'}
            {line.words}
          {:else if line.readable}
            <span class="bad">Not in your ingredients</span>
          {:else}
            <span class="bad">Couldn’t read this line</span>
          {/if}
        </span>
      </p>
      {#if picking}
        <FoodPicker
          label="Pick an ingredient for {line.written}"
          onpick={pick}
          oncancel={() => (picking = false)}
        />
      {:else}
        <p class="buttons">
          {#if line.label === 'to_confirm' && line.food}
            <button type="button" class="chip main" onclick={() => flow.sameAs(index, line.food!)}
              >Same as “{line.food.name}”</button
            >
          {:else}
            <button type="button" class="chip main" onclick={() => (picking = true)}
              >Pick an ingredient</button
            >
          {/if}
          <button type="button" class="chip" onclick={() => flow.newIngredient(index)}
            >New ingredient</button
          >
          {#if line.label === 'needs_you'}
            <button type="button" class="chip" onclick={() => flow.newIngredient(index, true)}
              >Treat as staple</button
            >
          {:else}
            <button type="button" class="chip" onclick={() => (picking = true)}>Pick another</button
            >
          {/if}
        </p>
        {#if line.label === 'to_confirm' && line.food && line.learn_name}
          <p class="hint">
            “Same as” adds “{line.learn_name}” as another name for {line.food.name} when you save.
          </p>
        {/if}
      {/if}
    {/if}
    {#if problem}<p class="error" role="alert">{problem}</p>{/if}
  </li>
{/if}

<style>
  li {
    list-style: none;
  }

  .heading h3 {
    padding: var(--space-5) 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
    overflow-wrap: anywhere;
  }

  .line {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) 0;
    border-bottom: 1px solid var(--color-divider);
  }

  .line.confirm,
  .line.needs {
    margin: 0 calc(-1 * var(--space-6));
    padding-right: var(--space-6);
    padding-left: var(--space-6);
  }

  .line.confirm {
    background: var(--color-maybe-row);
  }

  .line.needs {
    background: var(--color-warning);
  }

  .written {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .read {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: var(--space-3) var(--space-5);
    font-size: var(--text-base);
  }

  .what {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .bad {
    color: var(--color-warning-text);
    font-weight: var(--weight-bold);
  }

  .state {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .state.staple {
    color: var(--color-text-soft);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chip.main {
    border-color: transparent;
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .fields {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: var(--space-4);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  /* Boxes are 16 px or more, so a phone doesn't zoom in on them. */
  .field :is(input, select) {
    font-size: 1rem;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }
</style>
