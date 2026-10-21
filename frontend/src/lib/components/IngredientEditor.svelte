<script lang="ts">
  // The ingredient editor (mockups Ingredients-Phone, Ingredients-Desktop). The same
  // component everywhere: in the phone sheet / desktop panel (IngredientSheet.svelte)
  // and beside the list on the Ingredients page. Saves as you go: each field is saved
  // when it's left or switched, with Undo (foodEditor.svelte.ts).
  //
  // 0.4: "Used in N recipes" lists the recipes that use the ingredient, each a link to its
  // page, and "Remove from Ingredients" says so before it is pressed (spec "Removing an
  // ingredient", cabledrawer 19 Oct: the recipes don't block it; their lines keep their words
  // and show "not linked").
  import { parseAmount } from '$lib/amountText';
  import type { CountedAs, Food, Ref } from '$lib/client/types';
  import { canRemove } from '$lib/canRemove';
  import { FoodModel } from '$lib/foodEditor.svelte';
  import { kitchen } from '$lib/freshness.svelte';
  import { placesAndShops } from '$lib/placesAndShops.svelte';
  import { toasts } from '$lib/toast.svelte';
  import FoodPicker from './FoodPicker.svelte';
  import Icon from './Icon.svelte';
  import RemoveIngredient from './RemoveIngredient.svelte';
  import Switch from './Switch.svelte';
  import UsedInRecipes from './UsedInRecipes.svelte';

  let {
    foodId,
    variant,
    onname,
    onclose,
    onopen
  }: {
    foodId: number;
    /** Tells the dialog or panel around the editor the food's name ("Edit toor dal"). */
    onname?: (name: string) => void;
    /** "sheet" on phones (with Done), "panel" beside the list on desktop. */
    variant: 'sheet' | 'panel';
    onclose?: () => void;
    /** Show another food instead ("name taken → open it"). */
    onopen?: (id: number) => void;
  } = $props();

  const uid = $props.id();
  const model = $derived(new FoodModel(foodId));

  $effect(() => {
    model.onGone = () => onclose?.();
    model.onOpenOther = (id) => onopen?.(id);
    void model.load();
    placesAndShops.load().catch(() => {});
  });

  const food = $derived(model.food);

  // Changed elsewhere (an Undo, a merge from the list): show the server's version.
  let seen = kitchen.elsewhere;
  $effect(() => {
    if (kitchen.elsewhere !== seen) {
      seen = kitchen.elsewhere;
      void model.load();
    }
  });

  $effect(() => {
    onname?.(food?.name ?? '');
  });

  let renaming = $state(false);
  let splitting = $state<Ref | null>(null);
  let addingName = $state(false);
  let addingSize = $state(false);
  let addingShop = $state(false);
  let picking = $state<'stand-in' | 'merge' | null>(null);
  let lowProblem = $state<string | null>(null);
  let sizeProblem = $state<string | null>(null);

  const COUNTED: { value: CountedAs; label: string }[] = [
    { value: 'weight', label: 'By weight' },
    { value: 'volume', label: 'By volume' },
    { value: 'count', label: 'One by one' }
  ];

  const sizeUnits = $derived(
    food?.counted_as === 'weight'
      ? ['g', 'kg']
      : food?.counted_as === 'volume'
        ? ['ml', 'l']
        : [food?.count_word_plural ?? 'items']
  );

  /** For comparing names only; on screen names stay as typed. */
  const lower = (text: string) => text.toLocaleLowerCase();
  const valueOf = (event: Event) => (event.currentTarget as HTMLInputElement).value;

  function rename(event: Event) {
    renaming = false;
    const name = valueOf(event).trim();
    if (!food || !name || name === food.name) return;
    void model.setField({ name }, (f) => (f.name = name), `Renamed to ${name}`);
  }

  function addName(event: Event) {
    const name = valueOf(event).trim();
    addingName = false;
    if (!food || !name) return;
    const taken =
      lower(food.name) === lower(name) ||
      food.other_names.some((n) => lower(n.name) === lower(name));
    if (!taken) void model.addName(name);
  }

  /** "200 g" or "200" → 200 (grams). Empty → null (forget it). Nonsense → undefined. */
  function grams(text: string): number | null | undefined {
    const t = text.trim().toLowerCase().replace(/\s*g$/, '').replace(',', '.');
    if (!t) return null;
    const n = Number(t);
    return n > 0 ? n : undefined;
  }

  function setCupWeight(event: Event) {
    const value = grams(valueOf(event));
    if (value === undefined || !food) return;
    void model.setField(
      { cup_weight: value },
      (f) =>
        (f.cup_weight =
          value === null
            ? null
            : { grams: value, from: 'you', cup_ml: f.cup_weight?.cup_ml ?? 250 }),
      value === null ? 'Forgot the weight of 1 cup' : `Weight of 1 cup: ${value} g`
    );
  }

  function setItemWeight(event: Event) {
    const value = grams(valueOf(event));
    if (value === undefined || !food) return;
    void model.setField(
      { item_weight: value },
      (f) => (f.item_weight = value === null ? null : { grams: value, from: 'you' }),
      value === null ? 'Forgot the weight of one' : `Weight of one: ${value} g`
    );
  }

  function setRunningLow(event: Event) {
    if (!food) return;
    const text = valueOf(event).trim();
    if (!text) {
      lowProblem = null;
      void model.setField(
        { running_low_at: null },
        (f) => (f.running_low_at = null),
        'No running-low level'
      );
      return;
    }
    const amount = parseAmount(text, food);
    if (!amount) {
      lowProblem = 'Try something like ½ packet or 250 g.';
      return;
    }
    lowProblem = null;
    void model.setField(
      { running_low_at: amount },
      (f) => (f.running_low_at = { amount: amount.amount, display: text, short: text }),
      `Running low at ${text}`
    );
  }

  function setCountedAs(event: Event) {
    const value = valueOf(event) as CountedAs;
    void model.setField(
      { counted_as: value },
      (f) => (f.counted_as = value),
      'Changed how it’s counted'
    );
  }

  function setCountWord(event: Event) {
    const word = valueOf(event).trim() || null;
    if (!food || word === food.count_word) return;
    void model.setField(
      { count_word: word },
      (f) => (f.count_word = word),
      word ? `Counted in ${word}s` : 'Counted one by one'
    );
  }

  function setPlace(event: Event) {
    const id = Number(valueOf(event)) || null;
    const place = placesAndShops.places.find((p) => p.id === id) ?? null;
    void model.setField(
      { place_id: id },
      (f) => (f.place = place && { id: place.id, name: place.name }),
      place ? `Lives in ${place.name}` : 'No usual place'
    );
  }

  function setShop(shop: Ref | null) {
    void model.setField(
      { shop_id: shop?.id ?? null },
      (f) => (f.shop = shop),
      shop ? `Usual shop: ${shop.name}` : 'No usual shop'
    );
  }

  async function addShop(event: Event) {
    const name = valueOf(event).trim();
    addingShop = false;
    if (!name) return;
    try {
      setShop(await placesAndShops.addShop(name));
    } catch {
      toasts.show('Couldn’t add that shop. Try again.', { tone: 'problem' });
    }
  }

  function addSize(event: SubmitEvent) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const name = String(form.get('name') ?? '')
      .trim()
      .toLowerCase();
    const amount = Number(String(form.get('amount') ?? '').replace(',', '.'));
    const unit = food?.counted_as === 'count' ? 'count' : String(form.get('unit') ?? '');
    if (!name || !(amount > 0)) {
      sizeProblem = 'Give the size a name and an amount, like packet = 500 g.';
      return;
    }
    if (!/\p{L}/u.test(name)) {
      sizeProblem = 'Give the size a name, like tub or packet.';
      return;
    }
    sizeProblem = null;
    addingSize = false;
    void model.addSize(name, amount, unit);
  }

  function pickStandIn(other: Ref) {
    picking = null;
    void model.addStandIn(other);
  }

  function pickMerge(other: Ref) {
    picking = null;
    void model.mergeInto(other);
  }

  /** Enter saves a box; Escape closes it without saving. */
  function boxKeys(close: () => void) {
    return (event: KeyboardEvent) => {
      const box = event.currentTarget as HTMLInputElement;
      if (event.key === 'Enter') box.blur();
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        box.value = box.defaultValue;
        close();
      }
    };
  }

  /**
   * A recipe link was followed with a plain click. In the phone sheet and the desktop's modal
   * panel the editor closes first (the page behind it changes); beside the Ingredients list the
   * page itself changes. A click that opens a new tab never gets here.
   */
  function leaving() {
    if (variant === 'sheet') onclose?.();
  }

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }

  const excluded = (f: Food) => [f.id, ...f.stand_ins.map((s) => s.id)];
</script>

<div class="editor {variant}">
  {#if !food}
    <header>
      <h2>{model.problem ? 'Ingredient' : 'Loading…'}</h2>
      {#if variant === 'sheet'}
        <button type="button" class="done" onclick={() => onclose?.()}>Done</button>
      {/if}
    </header>
    {#if model.problem}
      <p class="hint" role="alert">{model.problem}</p>
      <button type="button" class="quiet" onclick={() => void model.load()}>Try again</button>
    {/if}
  {:else}
    <header>
      {#if renaming}
        <input
          class="rename"
          aria-label="Name"
          value={food.name}
          use:focusOnShow
          onchange={rename}
          onblur={() => (renaming = false)}
          onkeydown={boxKeys(() => (renaming = false))}
        />
      {:else}
        <span class="title">
          <h2>{food.name}</h2>
          <button
            type="button"
            class="pencil"
            aria-label="Rename"
            title="Rename"
            onclick={() => (renaming = true)}><Icon name="pencil" size={16} stroke={2.2} /></button
          >
        </span>
      {/if}
      {#if variant === 'sheet'}
        <button type="button" class="done" onclick={() => onclose?.()}>Done</button>
      {:else}
        <span class="saves">Saves as you go</span>
      {/if}
    </header>

    {#if food.maybe_same.length}
      <section class="maybe" aria-labelledby="{uid}-maybe">
        <h3 id="{uid}-maybe">Maybe the same</h3>
        {#each food.maybe_same as other (other.id)}
          <div class="maybe-row">
            <span>Is it the same as <b>{other.name}</b>?</span>
            <span class="maybe-buttons">
              {#if other.merge_this}
                <button
                  type="button"
                  class="merge-now"
                  aria-label="Merge into {other.name}"
                  onclick={() => void model.mergeInto(other)}>Merge</button
                >
              {:else}
                <button
                  type="button"
                  class="merge-now"
                  aria-label="Merge {other.name} into this"
                  onclick={() => void model.absorb(other)}>Merge</button
                >
              {/if}
              <button type="button" class="quiet" onclick={() => void model.notTheSame(other)}
                >Not the same</button
              >
            </span>
          </div>
        {/each}
      </section>
    {/if}

    <section aria-labelledby="{uid}-names">
      <h3 id="{uid}-names">Other names</h3>
      <ul class="chips">
        {#each food.other_names as name (name.id)}
          <li class="chip">
            <button
              type="button"
              class="chip-name"
              aria-expanded={splitting?.id === name.id}
              aria-controls="{uid}-split"
              onclick={() => (splitting = splitting?.id === name.id ? null : name)}
              >{name.name}</button
            ><button
              type="button"
              class="remove"
              aria-label="Remove {name.name}"
              onclick={() => void model.removeName(name)}>✕</button
            >
          </li>
        {/each}
        <li>
          {#if addingName}
            <input
              class="chip-input"
              aria-label="Another name for {food.name}"
              use:focusOnShow
              onchange={addName}
              onblur={() => (addingName = false)}
              onkeydown={boxKeys(() => (addingName = false))}
            />
          {:else}
            <button type="button" class="add" onclick={() => (addingName = true)}>+ Add</button>
          {/if}
        </li>
      </ul>
      {#if splitting}
        {@const name = splitting}
        <div class="split" id="{uid}-split">
          <span>“{name.name}”</span>
          <button
            type="button"
            class="quiet"
            onclick={() => {
              const target = name;
              splitting = null;
              void model.split(target);
            }}>Make its own ingredient</button
          >
          <button type="button" class="link muted" onclick={() => (splitting = null)}>Cancel</button
          >
        </div>
      {/if}
      <p class="hint">
        Recipe imports match any of these names. Tap one to make it its own ingredient.
      </p>
    </section>

    <section aria-labelledby="{uid}-sold">
      <h3 id="{uid}-sold">How it’s sold</h3>
      <ul class="sold">
        {#each food.sizes as size (size.id)}
          <li>
            <span class="size-name">
              {size.display}
              {#if size.added_when_shopping && !size.usual}
                <span class="note">added when shopping</span>
              {/if}
            </span>
            <span class="size-end">
              {#if size.usual}
                <span class="tag">Usual</span>
              {:else}
                <button type="button" class="link" onclick={() => void model.makeUsual(size)}
                  >Make usual</button
                >
              {/if}
              <button
                type="button"
                class="remove"
                aria-label="Remove the {size.name} size"
                onclick={() => void model.removeSize(size)}>✕</button
              >
            </span>
          </li>
        {/each}
        <li class="add-row">
          {#if addingSize}
            <form class="size-form" onsubmit={addSize}>
              <label>
                Name
                <input name="name" placeholder="packet, tub, dozen…" use:focusOnShow />
              </label>
              <span class="equals" aria-hidden="true">=</span>
              <label>
                Amount
                <input name="amount" inputmode="decimal" placeholder="500" />
              </label>
              <label>
                Unit
                <select name="unit">
                  {#each sizeUnits as unit (unit)}<option>{unit}</option>{/each}
                </select>
              </label>
              <span class="size-buttons">
                <button type="submit" class="small-main">Add</button>
                <button type="button" class="quiet" onclick={() => (addingSize = false)}
                  >Cancel</button
                >
              </span>
              {#if sizeProblem}<p class="problem" role="alert">{sizeProblem}</p>{/if}
            </form>
          {:else}
            <button type="button" class="link" onclick={() => (addingSize = true)}>
              + Add a size
            </button>
          {/if}
        </li>
      </ul>
    </section>

    <div class="fields">
      <label>
        Counted
        <select value={food.counted_as} onchange={setCountedAs}>
          {#each COUNTED as option (option.value)}
            <option value={option.value}>{option.label}</option>
          {/each}
        </select>
      </label>
      {#if food.counted_as === 'count'}
        <label>
          Each one is a
          <input
            value={food.count_word ?? ''}
            placeholder="slice, piece…"
            onchange={setCountWord}
            onkeydown={boxKeys(() => {})}
          />
        </label>
        <label>
          Weight of one
          <input
            value={food.item_weight ? `${Math.round(food.item_weight.grams)} g` : ''}
            placeholder="e.g. 150 g"
            onchange={setItemWeight}
            onkeydown={boxKeys(() => {})}
          />
        </label>
      {:else}
        <label>
          Weight of 1 cup
          <input
            value={food.cup_weight ? `${Math.round(food.cup_weight.grams)} g` : ''}
            placeholder="e.g. 200 g"
            onchange={setCupWeight}
            onkeydown={boxKeys(() => {})}
          />
        </label>
      {/if}
      <label>
        Running low at
        <input
          value={food.running_low_at?.short ?? food.running_low_at?.display ?? ''}
          placeholder="e.g. ½ packet"
          aria-invalid={lowProblem ? true : undefined}
          aria-describedby={lowProblem ? `${uid}-low` : undefined}
          onchange={setRunningLow}
          onkeydown={boxKeys(() => {})}
        />
      </label>
      <label>
        Lives in
        <select value={food.place?.id ?? ''} onchange={setPlace}>
          {#if !food.place}<option value="">Not set</option>{/if}
          {#each placesAndShops.places as place (place.id)}
            <option value={place.id}>{place.name}</option>
          {/each}
        </select>
      </label>
      {#if lowProblem}<p id="{uid}-low" class="problem wide" role="alert">{lowProblem}</p>{/if}
      <div class="shop wide">
        <label>
          Usual shop
          <select
            value={food.shop?.id ?? ''}
            onchange={(event) => {
              const id = Number(valueOf(event)) || null;
              setShop(placesAndShops.shops.find((s) => s.id === id) ?? null);
            }}
          >
            <option value="">Any shop</option>
            {#each placesAndShops.shops as shop (shop.id)}
              <option value={shop.id}>{shop.name}</option>
            {/each}
          </select>
        </label>
        {#if addingShop}
          <input
            class="chip-input"
            aria-label="New shop’s name"
            use:focusOnShow
            onchange={addShop}
            onblur={() => (addingShop = false)}
            onkeydown={boxKeys(() => (addingShop = false))}
          />
        {:else}
          <button type="button" class="add" onclick={() => (addingShop = true)}>+ Shop</button>
        {/if}
      </div>
    </div>

    <div class="switch-row">
      <span class="switch-text">
        <span id="{uid}-staple" class="switch-label">Staple</span>
        <span id="{uid}-staple-hint" class="hint">Assume it’s in stock; don’t count it</span>
      </span>
      <Switch
        checked={food.staple}
        labelledby="{uid}-staple"
        describedby="{uid}-staple-hint"
        onchange={(on) =>
          void model.setField(
            { staple: on },
            (f) => (f.staple = on),
            on ? `${food.name} is a staple` : `${food.name} isn’t a staple`
          )}
      />
    </div>

    <section aria-labelledby="{uid}-instead">
      <h3 id="{uid}-instead">Can use instead</h3>
      <ul class="chips">
        {#each food.stand_ins as other (other.id)}
          <li class="chip">
            {other.name}<button
              type="button"
              class="remove"
              aria-label="Remove {other.name}"
              onclick={() => void model.removeStandIn(other)}>✕</button
            >
          </li>
        {/each}
        <li class:wide-item={picking === 'stand-in'}>
          {#if picking === 'stand-in'}
            <FoodPicker
              label="Can use instead of {food.name}"
              exclude={excluded(food)}
              onpick={pickStandIn}
              oncancel={() => (picking = null)}
            />
          {:else}
            <button type="button" class="add" onclick={() => (picking = 'stand-in')}>+ Add</button>
          {/if}
        </li>
      </ul>
    </section>

    <UsedInRecipes recipes={food.used_in} count={food.used_in_recipes} onfollow={leaving} />

    <footer>
      {#if picking === 'merge'}
        <FoodPicker
          label="Merge {food.name} into"
          exclude={[food.id]}
          onpick={pickMerge}
          oncancel={() => (picking = null)}
        />
      {:else}
        <button type="button" class="merge" onclick={() => (picking = 'merge')}>
          Merge with another…
        </button>
      {/if}
      <button
        type="button"
        class="link muted"
        disabled={!food.last_change?.can_undo}
        title={food.last_change?.can_undo ? `Undo: ${food.last_change.summary}` : undefined}
        onclick={() => void model.undoLast()}>Undo last change</button
      >
    </footer>

    <RemoveIngredient
      usedIn={food.used_in_recipes}
      madeBy={food.made_by}
      removable={canRemove(food)}
      onremove={() => void model.remove()}
      onfollow={leaving}
    />
  {/if}
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
    min-width: 0;
    font-size: 1.375rem;
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .pencil {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .pencil:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .rename {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-extrabold) 1.375rem var(--font-ui);
  }

  .done {
    flex: none;
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
    flex: none;
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

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .wide {
    grid-column: 1 / -1;
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

  .wide-item {
    flex-basis: 100%;
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

  .chip-name {
    min-height: var(--touch-target);
    margin: -6px 0;
    padding: 0;
    border: none;
    background: transparent;
    font: inherit;
    cursor: pointer;
  }

  .split {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  /* The ✕: small to look at, 44 px to tap. */
  .remove {
    position: relative;
    display: flex;
    flex: none;
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

  .link.muted {
    color: var(--color-text-muted);
  }

  .link:disabled {
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

  .quiet {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .small-main {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .maybe {
    padding: var(--space-6);
    border-radius: 14px;
    background: var(--color-maybe-row);
  }

  .maybe h3 {
    color: var(--color-maybe-text);
  }

  .maybe-row {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-base);
  }

  .maybe-buttons {
    display: flex;
    gap: var(--space-3);
  }

  .merge-now {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-maybe-button);
    color: var(--color-maybe-chip-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  /* How it's sold */
  .sold {
    padding: var(--space-1) var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: 14px;
  }

  .sold li {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-height: var(--touch-target);
    border-bottom: 1px solid var(--color-divider);
    font-size: var(--text-base);
  }

  .sold li.add-row {
    border-bottom: none;
  }

  .size-name {
    display: flex;
    flex-direction: column;
    padding: var(--space-2) 0;
    font-weight: var(--weight-semibold);
  }

  .size-end {
    display: flex;
    align-items: center;
    gap: var(--space-5);
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

  .size-form {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-4);
    width: 100%;
    padding: var(--space-4) 0;
  }

  .size-form label {
    flex: 1 1 5rem;
  }

  .equals {
    padding-bottom: 12px;
    font-weight: var(--weight-bold);
  }

  .size-buttons {
    display: flex;
    gap: var(--space-3);
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

  label input[aria-invalid='true'] {
    border-color: var(--color-warning-text);
  }

  .shop {
    display: flex;
    align-items: flex-end;
    gap: var(--space-4);
  }

  .shop label {
    flex: 1;
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
    gap: var(--space-4) var(--space-6);
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
</style>
