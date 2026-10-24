<script lang="ts">
  // "How much Spinach did you use?" (mockup PantrySwipe-Phone, `used-sheet`): opened by swiping a
  // Pantry row or a Use soon item right (cabledrawer 21 Oct). ¼ · ½ · ¾ · All, or exactly how much.
  // Weight and volume only get the quarters; a count ingredient (eggs) asks "How many left?".
  // A phone sheet: a real modal dialog, Esc closes it, and the focus goes back where it came from.
  import { tick } from 'svelte';
  import type { CountedAs } from '$lib/client/types';

  let {
    open,
    name,
    detail,
    countedAs,
    total,
    allWords,
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
    /** "200 g": the words on the All button. */
    allWords: string;
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

  const unit = $derived(countedAs === 'weight' ? 'g' : countedAs === 'volume' ? 'ml' : '');
  const QUARTERS: [string, number][] = [
    ['¼', 0.25],
    ['½', 0.5],
    ['¾', 0.75]
  ];

  $effect(() => {
    if (open && !dialog.open) {
      typed = '';
      problem = null;
      dialog.showModal();
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  function round(value: number): number {
    return Math.round(value * 1000) / 1000;
  }

  function exactly(event: SubmitEvent) {
    event.preventDefault();
    const n = Number(typed.trim().replace(',', '.'));
    if (!typed.trim() || !(n >= 0) || (countedAs !== 'count' && n === 0)) {
      problem = countedAs === 'count' ? 'Type how many are left.' : 'Type how much you used.';
      return;
    }
    if (countedAs === 'count') onleft(n);
    else onpart(n);
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
    <div class="body">
      <span class="grab" aria-hidden="true"></span>
      <p class="title" id="{uid}-title">
        {countedAs === 'count' ? `How many ${name} are left?` : `How much ${name} did you use?`}
      </p>
      <p class="detail">{detail}</p>
      {#if countedAs !== 'count'}
        <div class="quick" role="group" aria-label="Quick amounts">
          {#each QUARTERS as [words, part] (words)}
            <button
              type="button"
              data-first={part === 0.25 ? '' : undefined}
              onclick={() => onpart(round(total * part))}>{words}</button
            >
          {/each}
          <button type="button" class="all" onclick={onall}>All</button>
        </div>
      {/if}
      <form class="exact" onsubmit={exactly}>
        <label>
          {countedAs === 'count' ? 'Or type how many are left' : 'Or exactly'}
          <span class="field">
            <input
              inputmode="decimal"
              maxlength="20"
              placeholder="e.g. {countedAs === 'count' ? 3 : round(total * 0.75)}"
              data-first={countedAs === 'count' ? '' : undefined}
              bind:value={typed}
              aria-describedby={problem ? `${uid}-problem` : undefined}
            />{#if unit}<span>{unit}</span>{/if}
          </span>
        </label>
        {#if problem}<p class="problem" id="{uid}-problem" role="alert">{problem}</p>{/if}
        <button type="submit" class="main">{countedAs === 'count' ? 'Save' : 'Used'}</button>
      </form>
      <button type="button" class="main all-button" onclick={onall}>Used all {allWords}</button>
      <button type="button" class="cancel" onclick={onclose}>Cancel</button>
    </div>
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

  .quick .all {
    border: 2px solid var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .exact {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  label {
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

  .exact .main,
  .all-button {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .exact .main {
    align-self: flex-start;
    padding: 0 var(--space-10);
    background: var(--color-fill);
    color: var(--color-text);
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
