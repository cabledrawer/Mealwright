<script lang="ts">
  import '#lib/styles/fields.css';
  // "How much Spinach did you use?" (mockup Dark-UseSoon08-Phone, `used-sheet`; F79): opened by
  // swiping a Pantry row or a Use soon item right (cabledrawer 21 Oct), or by Used… on Use soon.
  // ¼ · ½ · ¾ · All with nothing chosen until one is tapped (cabledrawer 7 Nov); one main button
  // follows the choice ("Used ¾ bag", "Used all of it"), and "Or exactly … g" turns it into
  // "Used 120 g". Weight and volume only get the quarters; a count ingredient (eggs) asks "How
  // many left?". A phone sheet: a real modal dialog, Esc closes it, and the focus goes back
  // where it came from. On a computer it is a box in the middle of the screen.
  import Button from '#lib/components/Button.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
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
    if (open) {
      typed = '';
      problem = null;
      chosen = null;
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

{#if open}
  <Sheet
    title={countedAs === 'count' ? `How many ${name} are left?` : `How much ${name} did you use?`}
    {onclose}
  >
    <form class="body" onsubmit={submit}>
      <p class="detail">{detail}</p>
      {#if countedAs !== 'count'}
        <div class="quick" role="radiogroup" aria-label="How much">
          {#each QUARTERS as [words, part] (words)}
            <button
              type="button"
              role="radio"
              aria-checked={chosen === part}
              class:on={chosen === part}
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
            bind:value={typed}
            oninput={typing}
            aria-describedby={problem ? `${uid}-problem` : undefined}
          />{#if unit}<span>{unit}</span>{/if}
        </span>
      </label>
      {#if problem}<p class="mw-error" id="{uid}-problem" role="alert">{problem}</p>{/if}
      {#if countedAs === 'count'}
        <Button type="submit">Save</Button>
        <Button onclick={onall}>Used all {allWords}</Button>
      {:else}
        <Button type="submit" disabled={!ready}>{mainWords}</Button>
      {/if}
      <Button quiet onclick={onclose}>Cancel</Button>
    </form>
  </Sheet>
{/if}

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
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
    border-radius: var(--radius-lg);
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
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  /* A computer: a box in the middle of the screen, not a sheet the width of it. */
</style>
