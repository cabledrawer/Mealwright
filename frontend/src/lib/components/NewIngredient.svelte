<script lang="ts">
  // "How do you count it?" (newIngredient.svelte.ts): By weight · By volume · One by one ·
  // Don't count it, with the bundled table's guess first. Packet sizes can be added right
  // here, so they don't have to be added afterwards in the editor. A modal dialog:
  // Escape = Cancel.
  import { api, ApiError } from '$lib/api';
  import type { CountedAs } from '$lib/client/types';
  import { newIngredient, type HowCounted, type NewSize } from '$lib/newIngredient.svelte';
  import { radioKeys } from '$lib/radioKeys';

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  const OPTIONS: { value: HowCounted; label: string; hint: string }[] = [
    { value: 'weight', label: 'By weight', hint: 'Grams and kilos: rice, flour, paneer' },
    { value: 'volume', label: 'By volume', hint: 'Millilitres and litres: milk, oil' },
    { value: 'count', label: 'One by one', hint: 'Whole things: onions, eggs, lemons' },
    {
      value: 'staple',
      label: 'Don’t count it',
      hint: 'Always assumed in stock: salt, kitchen roll, soap'
    }
  ];

  const pending = $derived(newIngredient.current);
  let name = $state('');
  let how = $state<HowCounted>('weight');
  /** The table's guess, when the table knew the name. */
  let guess = $state<HowCounted | null>(null);
  let guessed = $state<CountedAs>('weight');
  /** The person has picked one: a guess that arrives later doesn't change it. */
  let touched = false;
  let sizes = $state<NewSize[]>([]);
  let addingSize = $state(false);
  let sizeProblem = $state<string | null>(null);
  let problem = $state<string | null>(null);
  let busy = $state(false);

  const typed = $derived(name.trim());
  const ordered = $derived(
    guess
      ? [OPTIONS.find((o) => o.value === guess)!, ...OPTIONS.filter((o) => o.value !== guess)]
      : OPTIONS
  );
  const units = $derived(
    how === 'volume' ? ['ml', 'L'] : how === 'count' ? ['items'] : ['g', 'kg']
  );

  $effect(() => {
    if (pending) {
      name = pending.name;
      how = 'weight';
      guess = null;
      guessed = 'weight';
      touched = false;
      sizes = [];
      addingSize = false;
      sizeProblem = null;
      problem = null;
      busy = false;
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  });

  // The server's table is the guess; nothing is looked up on the internet. If the name is
  // changed in the box, ask again after a pause.
  $effect(() => {
    const asked = typed;
    if (!pending || !asked) return;
    const timer = setTimeout(() => {
      api<{ counted_as: CountedAs; from_table: boolean }>(
        'GET',
        `/foods/guess?name=${encodeURIComponent(asked)}`
      )
        .then((answer) => {
          if (asked !== typed) return;
          guessed = answer.counted_as;
          guess = answer.from_table ? answer.counted_as : null;
          if (!touched) how = answer.counted_as;
        })
        .catch(() => {});
    }, 150);
    return () => clearTimeout(timer);
  });

  let sizeName = $state('');
  let sizeAmount = $state('');
  let sizeUnit = $state('g');

  function startSize() {
    sizeName = '';
    sizeAmount = '';
    sizeUnit = units[0]!;
    addingSize = true;
  }

  function sizeKey(event: KeyboardEvent) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    addSize();
  }

  function addSize() {
    const label = sizeName.trim().toLowerCase();
    const amount = Number(sizeAmount.replace(',', '.'));
    const unit = how === 'count' ? 'count' : sizeUnit.toLowerCase();
    if (!label || !(amount > 0)) {
      sizeProblem = 'Give the size a name and an amount, like packet = 500 g.';
      return;
    }
    if (!/\p{L}/u.test(label)) {
      sizeProblem = 'Give the size a name, like tub or packet.';
      return;
    }
    sizeProblem = null;
    sizes = [...sizes, { name: label, amount, unit }];
    addingSize = false;
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!typed || busy) return;
    if (pending?.mode === 'choose') {
      const staple = how === 'staple';
      newIngredient.pick({
        name: typed,
        staple,
        counted_as: staple ? guessed : (how as 'weight' | 'volume' | 'count'),
        sizes: staple ? [] : sizes
      });
      return;
    }
    busy = true;
    problem = null;
    try {
      await newIngredient.make(typed, how, sizes);
    } catch (error) {
      problem = error instanceof ApiError ? error.detail : 'Couldn’t add it — try again.';
      busy = false;
    }
  }

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

<dialog bind:this={dialog} aria-labelledby="{uid}-q" oncancel={() => newIngredient.cancel()}>
  {#if pending}
    <form onsubmit={submit}>
      <h2 id="{uid}-q">How do you count it?</h2>
      {#if pending.name}
        <p class="name">{pending.name}</p>
      {:else}
        <label class="field">
          Name
          <input bind:value={name} placeholder="Tahini" use:focusOnShow />
        </label>
      {/if}

      <div class="options" role="radiogroup" aria-labelledby="{uid}-q" use:radioKeys>
        {#each ordered as option (option.value)}
          <button
            type="button"
            role="radio"
            aria-checked={how === option.value}
            onclick={() => {
              touched = true;
              how = option.value;
            }}
          >
            <span class="label"
              >{option.label}{#if option.value === guess}<span class="guess">Our guess</span
                >{/if}</span
            >
            <span class="hint">{option.hint}</span>
          </button>
        {/each}
      </div>

      {#if how !== 'staple'}
        <section aria-labelledby="{uid}-sizes">
          <h3 id="{uid}-sizes">Packet sizes <span class="optional">(optional)</span></h3>
          {#if sizes.length}
            <ul class="sizes">
              {#each sizes as size, i (i)}
                <li>
                  <span
                    >{size.name} = {size.amount} {size.unit === 'count' ? 'items' : size.unit}</span
                  >
                  <button
                    type="button"
                    class="remove"
                    aria-label="Remove the {size.name} size"
                    onclick={() => (sizes = sizes.filter((_, j) => j !== i))}>✕</button
                  >
                </li>
              {/each}
            </ul>
          {/if}
          {#if addingSize}
            <div class="size-form" role="group" aria-label="Add a size">
              <label>
                Name
                <input
                  bind:value={sizeName}
                  placeholder="packet, tub, dozen…"
                  onkeydown={sizeKey}
                  use:focusOnShow
                />
              </label>
              <label>
                Amount
                <input
                  bind:value={sizeAmount}
                  inputmode="decimal"
                  placeholder="500"
                  onkeydown={sizeKey}
                />
              </label>
              {#if how !== 'count'}
                <label>
                  Unit
                  <select bind:value={sizeUnit}>
                    {#each units as unit (unit)}<option>{unit}</option>{/each}
                  </select>
                </label>
              {/if}
              <span class="size-buttons">
                <button type="button" class="small-main" onclick={addSize}>Add size</button>
                <button type="button" class="quiet" onclick={() => (addingSize = false)}
                  >Cancel</button
                >
              </span>
              {#if sizeProblem}<p class="problem" role="alert">{sizeProblem}</p>{/if}
            </div>
          {:else}
            <button type="button" class="link" onclick={startSize}>+ Add a size</button>
            <p class="hint">How it’s sold, like packet = 500 g, so lists can say “1 packet”.</p>
          {/if}
        </section>
      {/if}

      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
      <div class="buttons">
        <button type="button" class="quiet" onclick={() => newIngredient.cancel()}>Cancel</button>
        <button type="submit" class="main" disabled={!typed || busy}>Add</button>
      </div>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    width: min(460px, calc(100vw - 2 * var(--space-7)));
    max-height: calc(100dvh - 2 * var(--space-7));
    padding: var(--space-9);
    border: none;
    border-radius: var(--radius-panel);
    background: var(--color-surface);
    color: var(--color-text);
    overflow-y: auto;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  h3 {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .optional,
  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-regular);
  }

  .name {
    margin-top: calc(-1 * var(--space-4));
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .options button {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-height: var(--touch-target);
    padding: var(--space-5) var(--space-7);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
  }

  .options button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .options .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .options .hint {
    color: inherit;
  }

  .guess {
    margin-left: var(--space-4);
    padding: 1px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
  }

  .field,
  .size-form label {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  input,
  select {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .sizes {
    display: flex;
    flex-direction: column;
    margin: var(--space-3) 0;
    padding: 0;
    list-style: none;
  }

  .sizes li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: var(--touch-target);
    border-bottom: 1px solid var(--color-divider);
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
  }

  .size-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(7rem, 1fr));
    gap: var(--space-5);
    margin-top: var(--space-4);
  }

  .size-buttons {
    display: flex;
    grid-column: 1 / -1;
    gap: var(--space-4);
  }

  .link,
  .remove {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .remove {
    min-width: var(--touch-target);
    color: var(--color-text-muted);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-4);
  }

  .buttons button,
  .size-buttons button {
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-full);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .main,
  .small-main {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .main:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
</style>
