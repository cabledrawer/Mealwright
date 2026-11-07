<script lang="ts">
  // "How much Spinach did you use?" (mockup Dark-UseSoon08-Phone, `used-sheet`; F79): opened by
  // swiping a Pantry row or a Use soon item right (cabledrawer 21 Oct), or by Used… on Use soon.
  // ¼ · ½ · ¾ · All with nothing chosen until one is tapped (cabledrawer 7 Nov); one main button
  // follows the choice ("Used ¾ bag", "Used all of it"), and "Or exactly … g" turns it into
  // "Used 120 g". Weight and volume only get the quarters; a count ingredient (eggs) asks "How
  // many left?". A phone sheet: a real modal dialog, Esc closes it, and the focus goes back
  // where it came from. On a computer it is a box in the middle of the screen.
  import { tick } from 'svelte';
  import type { CountedAs } from '#lib/client/types.js';

  let {
    open,
    name,
    detail,
    countedAs,
    total,
    allWords,
    unitWord = null,
    onall,
    onpart,
    onleft,
    onclose
  }: {
    open: boolean;
    name: string;
    /** "Fridge · 200 g · use by Today". */
    detail: string;
    countedAs: CountedAs;
    /** How much there is, in g, ml or items. */
    total: number;
    /** "200 g": the words on the All button of a count ingredient. */
    allWords: string;
    /** What one pack is called ("bag"), for "Used ¾ bag"; null: "Used ¾ of it". */
    unitWord?: string | null;
    /** Used it all. */
    onall: () => void;
    /** Used this much (g or ml). */
    onpart: (amount: number) => void;
    /** Count ingredients: this many are left. */
    onleft: (amount: number) => void;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let typed = $state('');
  let problem = $state<string | null>(null);
  /** Nothing is chosen until a pick is tapped: 0.25, 0.5, 0.75 or 1 (All). */
  let chosen = $state<number | null>(null);

  const unit = $derived(countedAs === 'weight' ? 'g' : countedAs === 'volume' ? 'ml' : '');
  const QUARTERS: [string, number][] = [
    ['¼', 0.25],
    ['½', 0.5],
    ['¾', 0.75],
    ['All', 1]
  ];

  $effect(() => {
    if (open && !dialog.open) {
      typed = '';
      problem = null;
      chosen = null;
      dialog.showModal();
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  function round(value: number): number {
    return Math.round(value * 1000) / 1000;
  }

  const typedNumber = $derived(Number(typed.trim().replace(',', '.')));
  const typedOk = $derived(typed.trim() !== '' && typedNumber > 0);

  /** The main button: it says what pressing it does. */
  const mainWords = $derived.by(() => {
    if (typedOk) return `Used ${round(typedNumber)}${unit ? `\u00a0${unit}` : ''}`;
    if (chosen === 1) return 'Used all of it';
    if (chosen !== null) {
      const part = QUARTERS.find(([, p]) => p === chosen)?.[0] ?? '';
      return unitWord ? `Used ${part}\u00a0${unitWord}` : `Used ${part} of it`;
    }
    return 'Choose how much';
  });
  const ready = $derived(typedOk || chosen !== null);

  function pick(part: number) {
    chosen = part;
    typed = '';
    problem = null;
  }

  function typing() {
    if (typed.trim() !== '') chosen = null;
    problem = null;
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (countedAs === 'count') {
      const n = Number(typed.trim().replace(',', '.'));
      if (!typed.trim() || !(n >= 0)) {
        problem = 'Type how many are left.';
        return;
      }
      onleft(n);
      return;
    }
    if (typed.trim() !== '' && !typedOk) {
      problem = 'Type how much you used.';
      return;
    }
    if (typedOk) onpart(typedNumber);
    else if (chosen === 1) onall();
    else if (chosen !== null) onpart(round(total * chosen));
  }
</script>

<dialog
  bind:this={dialog}
  class="used-sheet"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  {#if open}
    <form class="body" onsubmit={submit}>
      <span class="grab" aria-hidden="true"></span>
      <p class="title" id="{uid}-title">
        {countedAs === 'count' ? `How many ${name} are left?` : `How much ${name} did you use?`}
      </p>
      <p class="detail">{detail}</p>
      {#if countedAs !== 'count'}
        <div class="quick" role="radiogroup" aria-label="How much">
          {#each QUARTERS as [words, part] (words)}
            <button
              type="button"
              role="radio"
              aria-checked={chosen === part}
              class:on={chosen === part}
              data-first={part === 0.25 ? '' : undefined}
              onclick={() => pick(part)}>{words}</button
            >
          {/each}
        </div>
      {/if}
      <label class="exact">
        {countedAs === 'count' ? 'Or type how many are left' : 'Or exactly'}
        <span class="field">
          <input
            inputmode="decimal"
            maxlength="20"
            placeholder="for example {countedAs === 'count' ? 3 : round(total * 0.75)}"
            data-first={countedAs === 'count' ? '' : undefined}
            bind:value={typed}
            oninput={typing}
            aria-describedby={problem ? `${uid}-problem` : undefined}
          />{#if unit}<span>{unit}</span>{/if}
        </span>
      </label>
      {#if problem}<p class="problem" id="{uid}-problem" role="alert">{problem}</p>{/if}
      {#if countedAs === 'count'}
        <button type="submit" class="main save">Save</button>
        <button type="button" class="main" onclick={onall}>Used all {allWords}</button>
      {:else}
        <button type="submit" class="main" disabled={!ready}>{mainWords}</button>
      {/if}
      <button type="button" class="cancel" onclick={onclose}>Cancel</button>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: var(--space-4) var(--space-8) max(28px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .grab {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .title {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .detail {
    margin-top: calc(-1 * var(--space-3));
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .quick {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .quick button {
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: 14px;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    cursor: pointer;
  }

  /* The chosen pick: one at a time, and none until one is tapped. */
  .quick button.on {
    border: 2px solid var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .exact {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .field {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: 48px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: 12px;
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-base);
  }

  .main {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-extrabold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .main:disabled {
    background: var(--color-fill);
    color: var(--color-text-muted);
    cursor: default;
  }

  .main.save {
    background: var(--color-fill);
    color: var(--color-text);
  }

  /* A computer: a box in the middle of the screen, not a sheet the width of it. */
  @media (min-width: 768px) {
    dialog {
      inset: 0;
      width: min(420px, 100%);
      margin: auto;
      border-radius: var(--radius-xl);
    }

    .grab {
      display: none;
    }
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }
</style>
