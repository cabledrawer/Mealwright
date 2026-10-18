<script lang="ts">
  // One line on the list. Unticked: a checkbox, the name (opens the ingredient), and the
  // amount (tap to change it or take the item off the list). In the trolley: struck through,
  // where it went, and "Different pack?" (mockup Shop). Notes for the item sit underneath.
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import { toBaseAmount } from '$lib/shopping/amountEdit';
  import type { ShoppingModel } from '$lib/shopping/store.svelte';
  import type { Note } from '$lib/shopping/types';
  import type { ViewItem } from '$lib/shopping/view';
  import PackSheet from './PackSheet.svelte';
  import { radioKeys } from '$lib/radioKeys';

  let {
    model,
    view,
    trolley = false,
    notes = [],
    highlight = false
  }: {
    model: ShoppingModel;
    view: ViewItem;
    trolley?: boolean;
    notes?: Note[];
    highlight?: boolean;
  } = $props();

  const uid = $props.id();
  const item = $derived(view.item);
  const food = $derived(view.food);
  const tick = $derived(view.ticks[0]);

  let editing = $state(false);
  let text = $state('');
  let problem = $state<string | null>(null);
  let packOpen = $state(false);

  const place = $derived(model.placeName(tick?.place_id ?? item.put_away_place_id));
  const placing = $derived(model.placing === item.id);
  const planned = $derived(
    trolley && tick?.bought && tick.bought.display !== item.display && item.display
      ? `Planned ${item.display}`
      : null
  );

  async function startEdit() {
    text = '';
    problem = null;
    editing = true;
    await model.sizesOf(food.id).catch(() => []);
  }

  function saveAmount(event: SubmitEvent) {
    event.preventDefault();
    const parsed = toBaseAmount(text, {
      counted_as: food.counted_as,
      sizes: food.sizes ?? [],
      count_word: food.count_word ?? null,
      count_word_plural: food.count_word_plural ?? null
    });
    if ('problem' in parsed) {
      problem = parsed.problem;
      return;
    }
    editing = false;
    void model.setAmount(item, parsed.amount, parsed.sizeId);
  }

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

<li class="item" class:trolley class:highlight>
  <div class="line">
    <label class="tick">
      <input
        type="checkbox"
        checked={trolley}
        aria-label="{trolley ? 'Untick' : 'Tick'} {food.name}"
        onchange={() => void (trolley ? model.untick(item) : model.tick(item))}
      />
      <span class="box" aria-hidden="true">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="3.2"
          stroke-linecap="round"
          stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg
        >
      </span>
    </label>
    <span class="what">
      <button type="button" class="name" onclick={() => ingredientEditor.open(food.id)}
        >{food.name}</button
      >
      {#if planned}<span class="sub">{planned}</span>{/if}
    </span>
    {#if trolley}
      <button
        type="button"
        class="pill"
        aria-expanded={placing}
        onclick={() => (model.placing = placing ? null : item.id)}
        >{place ? `→ ${place}` : 'Put away'}</button
      >
      <button
        type="button"
        class="pill"
        aria-expanded={packOpen}
        onclick={() => (packOpen = !packOpen)}
        >{item.amount ? 'Different pack?' : 'How much?'}</button
      >
    {:else}
      <button
        type="button"
        class="amount"
        aria-expanded={editing}
        aria-label={item.display
          ? `${food.name}: ${item.display}. Change`
          : `Set how much ${food.name}`}
        onclick={() => (editing ? (editing = false) : void startEdit())}
        >{item.display ?? '+'}</button
      >
    {/if}
  </div>

  {#if placing && trolley}
    <div class="places" role="radiogroup" aria-label="Where did {food.name} go?" use:radioKeys>
      {#each model.copy.places as p (p.id)}
        <button
          type="button"
          role="radio"
          aria-checked={p.name === place}
          onclick={() => void model.putAway(item, p.id)}>{p.name}</button
        >
      {/each}
    </div>
  {/if}

  {#if editing && !trolley}
    <form class="edit" onsubmit={saveAmount}>
      <label>
        How much {food.name}?
        <input
          bind:value={text}
          inputmode="decimal"
          placeholder={item.display ?? 'e.g. 500 g'}
          aria-describedby={problem ? `${uid}-p` : undefined}
          use:focusOnShow
        />
      </label>
      <button type="submit" class="pill strong">Save</button>
      <button
        type="button"
        class="pill"
        onclick={() => {
          editing = false;
          void model.remove(item);
        }}>Remove from list</button
      >
      {#if problem}<p id="{uid}-p" class="problem" role="alert">{problem}</p>{/if}
    </form>
  {/if}

  {#if packOpen && trolley && tick}
    <PackSheet {model} {item} {food} {tick} onclose={() => (packOpen = false)} />
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

  .highlight {
    background: var(--color-accent-soft);
  }

  .line {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 52px;
  }

  /* A 44 px tap area around a 22 px box, as in the mockup's row. */
  .tick {
    position: relative;
    display: grid;
    flex: none;
    place-items: center;
    width: var(--touch-target);
    height: var(--touch-target);
    margin-left: calc(-1 * var(--space-4));
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
    width: 22px;
    height: 22px;
    border: 2px solid var(--color-field-border);
    border-radius: 7px;
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
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-lg) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .trolley .name {
    color: var(--color-text-muted);
    text-decoration: line-through;
  }

  .sub {
    margin-top: calc(-1 * var(--space-3));
    padding-bottom: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .amount {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-2);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-regular) var(--text-base) var(--font-ui);
    text-align: right;
    cursor: pointer;
  }

  .pill {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .pill.strong {
    border-color: transparent;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .places,
  .edit {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-3);
    margin: 0 0 var(--space-4) 34px;
  }

  .edit label {
    display: flex;
    flex: 1 1 10rem;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .edit input {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .places button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .places button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .problem {
    flex-basis: 100%;
    color: var(--color-warning-text);
    font-size: var(--text-md);
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
