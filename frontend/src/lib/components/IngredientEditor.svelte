<script lang="ts">
  // The ingredient editor's contents (mockups Ingredients-Phone, Ingredients-Desktop).
  // The same component everywhere: inside the phone sheet / desktop panel
  // (IngredientSheet.svelte), and beside the list on the Ingredients page.
  //
  // SKELETON: edits change the placeholder kitchen only. Saving through the API (with
  // Undo) arrives with the 0.2 API. "Used in N recipes" waits for recipes (0.4).
  import { describeSaleUnit, type Food } from '$lib/foods';
  import { kitchen } from '$lib/foods.sample.svelte';
  import { undoHistory } from '$lib/undo.svelte';
  import Switch from './Switch.svelte';

  let {
    food,
    variant,
    onclose
  }: {
    food: Food;
    /** "sheet" on phones (with Done), "panel" beside the list on desktop. */
    variant: 'sheet' | 'panel';
    onclose?: () => void;
  } = $props();

  const uid = $props.id();

  let addingName = $state(false);
  let newName = $state('');
  let addingStandIn = $state(false);

  const standIns = $derived(
    food.standInIds
      .map((id) => kitchen.foods.find((other) => other.id === id))
      .filter((other): other is Food => !!other)
  );
  const standInChoices = $derived(
    kitchen.foods.filter((other) => other.id !== food.id && !food.standInIds.includes(other.id))
  );

  function addName() {
    const name = newName.trim();
    if (name && !food.otherNames.some((n) => n.toLocaleLowerCase() === name.toLocaleLowerCase())) {
      food.otherNames.push(name);
    }
    newName = '';
    addingName = false;
  }

  function removeName(name: string) {
    food.otherNames = food.otherNames.filter((n) => n !== name);
  }

  function addStandIn(event: Event) {
    const id = Number((event.currentTarget as HTMLSelectElement).value);
    if (id) food.standInIds.push(id);
    addingStandIn = false;
  }

  function removeStandIn(id: number) {
    food.standInIds = food.standInIds.filter((other) => other !== id);
  }

  /** Focus a field as soon as it appears (the "+ Add" boxes). */
  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

<div class="editor {variant}">
  <header>
    <h2 id="{uid}-title">{food.name}</h2>
    {#if variant === 'sheet'}
      <button type="button" class="done" onclick={() => onclose?.()}>Done</button>
    {:else}
      <span class="saves">Saves as you go</span>
    {/if}
  </header>

  <section aria-labelledby="{uid}-names">
    <h3 id="{uid}-names">Other names</h3>
    <ul class="chips">
      {#each food.otherNames as name (name)}
        <li class="chip">
          {name}<button
            type="button"
            class="remove"
            aria-label="Remove {name}"
            onclick={() => removeName(name)}>✕</button
          >
        </li>
      {/each}
      <li>
        {#if addingName}
          <input
            class="chip-input"
            aria-label="Another name for {food.name}"
            bind:value={newName}
            use:focusOnShow
            onkeydown={(event) => {
              if (event.key === 'Enter') addName();
              if (event.key === 'Escape') {
                // Close just this box, not the whole sheet.
                event.preventDefault();
                event.stopPropagation();
                addingName = false;
              }
            }}
            onblur={addName}
          />
        {:else}
          <button type="button" class="add" onclick={() => (addingName = true)}>+ Add</button>
        {/if}
      </li>
    </ul>
    <p class="hint">Recipe imports match any of these names.</p>
  </section>

  <section aria-labelledby="{uid}-sold">
    <h3 id="{uid}-sold">How it's sold</h3>
    <ul class="sold">
      {#each food.saleUnits as unit (unit.name)}
        <li class:usual={unit.usual}>
          <span>{describeSaleUnit(unit, food)}</span>
          {#if unit.usual}<span class="tag">Usual</span>
          {:else if unit.note}<span class="note">{unit.note}</span>{/if}
        </li>
      {/each}
      <li class="add-row">
        <button type="button" class="add" disabled title="Coming with the 0.2 API">
          + Add a size
        </button>
      </li>
    </ul>
  </section>

  <div class="fields">
    <label>
      Weight of 1 cup
      <input type="text" bind:value={food.cupWeight} placeholder="e.g. 200 g" />
    </label>
    <label>
      Running low at
      <input type="text" bind:value={food.runningLow} placeholder="e.g. ½ packet" />
    </label>
    <label>
      Lives in
      <select bind:value={food.placeId}>
        {#each kitchen.places as place (place.id)}
          <option value={place.id}>{place.name}</option>
        {/each}
      </select>
    </label>
    <label>
      Usual shop
      <select bind:value={food.shopId}>
        <option value={null}>Any shop</option>
        {#each kitchen.shops as shop (shop.id)}
          <option value={shop.id}>{shop.name}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="switch-row">
    <span class="switch-text">
      <span id="{uid}-staple" class="switch-label">Staple</span>
      <span id="{uid}-staple-hint" class="hint">Assume it's in stock; don't count it</span>
    </span>
    <Switch bind:checked={food.staple} labelledby="{uid}-staple" describedby="{uid}-staple-hint" />
  </div>

  <section aria-labelledby="{uid}-instead">
    <h3 id="{uid}-instead">Can use instead</h3>
    <ul class="chips">
      {#each standIns as other (other.id)}
        <li class="chip">
          {other.name}<button
            type="button"
            class="remove"
            aria-label="Remove {other.name.toLocaleLowerCase()}"
            onclick={() => removeStandIn(other.id)}>✕</button
          >
        </li>
      {/each}
      <li>
        {#if addingStandIn}
          <select
            class="chip-input"
            aria-label="Can use instead of {food.name}"
            use:focusOnShow
            onchange={addStandIn}
            onblur={() => (addingStandIn = false)}
          >
            <option value="">Pick one…</option>
            {#each standInChoices as other (other.id)}
              <option value={other.id}>{other.name}</option>
            {/each}
          </select>
        {:else}
          <button type="button" class="add" onclick={() => (addingStandIn = true)}>+ Add</button>
        {/if}
      </li>
    </ul>
  </section>

  <footer>
    <button type="button" class="merge" disabled title="Coming with the 0.2 API">
      Merge with another…
    </button>
    {#if variant === 'panel'}
      <button
        type="button"
        class="undo"
        disabled={undoHistory.size === 0}
        onclick={() => void undoHistory.undoLast()}>Undo last change</button
      >
    {:else}
      <span class="hint">Saves as you go · Undo</span>
    {/if}
  </footer>
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .panel {
    gap: var(--space-7);
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
  }

  h2 {
    font-size: 1.375rem;
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .done {
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

  .saves {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .chip {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: 32px;
    padding: 0 var(--space-1) 0 var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  /* The ✕: small to look at, 44 px to tap. */
  .remove {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    margin-right: var(--space-1);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-chip-remove);
    color: var(--color-text-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .remove::before {
    content: '';
    position: absolute;
    inset: -10px;
  }

  .add {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .add:disabled,
  .merge:disabled,
  .undo:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .chip-input {
    min-height: var(--touch-target);
    max-width: 14rem;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  /* How it's sold: rows in the desktop panel, chips in the phone sheet. */
  .sold {
    padding: var(--space-1) var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: 14px;
  }

  .sold li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-height: 42px;
    border-bottom: 1px solid var(--color-divider);
    font-size: var(--text-base);
  }

  .sold li.add-row {
    border-bottom: none;
  }

  .sold .add-row .add {
    padding: 0;
    border: none;
  }

  .tag {
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .sheet .sold {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    padding: 0;
    border: none;
  }

  .sheet .sold li {
    min-height: 32px;
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .sheet .sold li.usual {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .sheet .sold li.usual .tag::before {
    content: '· ';
  }

  .sheet .sold li .note {
    display: none;
  }

  .sheet .sold li.add-row {
    padding: 0;
    background: transparent;
  }

  .sheet .sold .add-row .add {
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
  }

  .fields {
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
  label select {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    /* 16 px on phones stops them zooming in. */
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .switch-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
  }

  .switch-text {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .switch-label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    padding-top: 14px;
    border-top: 1px solid var(--color-divider);
  }

  .merge {
    min-height: var(--touch-target);
    padding: 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .undo {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  @media (min-width: 768px) {
    label input,
    label select {
      font-size: var(--text-base);
    }
  }
</style>
