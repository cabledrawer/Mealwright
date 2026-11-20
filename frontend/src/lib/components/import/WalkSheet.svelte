<script lang="ts">
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Lazy from '#lib/components/Lazy.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  // "2 lines aren’t linked yet" (mockup Dark-ImportSave07-Phone, spec "Importer consistency",
  // F4): Save found lines with no ingredient behind them. This goes through them one at a time:
  // New ingredient · Pick another · Treat as staple, with Skip this line, Back to Check and Save
  // anyway. A sheet on a phone, a dialog on a computer. Words proposed, for cabledrawer, except where
  // the mockup has them.
  import { keptBySaid } from '#lib/keptByWords.js';
  import { network } from '#lib/network.svelte.js';
  import { onMount, tick } from 'svelte';
  import { holdUndo } from '#lib/undo.svelte.js';
  import type { LinePick } from './PickLine.svelte';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { amountWords } from '#lib/import.svelte.js';
  import { unitFor } from '#lib/recipeAmounts.js';
  import { plural } from '#lib/words.js';

  let { flow, onsave }: { flow: ImportFlow; onsave: () => void } = $props();

  const uid = $props.id();
  let body: HTMLElement | undefined = $state();
  let picking = $state(false);
  /** The pick-list starts with recipes only ("Made in another recipe"). */
  let pickingRecipes = $state(false);

  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move the lines behind this sheet
    return letGo;
  });

  const walk = $derived(flow.walk);
  const total = $derived(walk?.queue.length ?? 0);
  const at = $derived(walk?.at ?? 0);
  const index = $derived(flow.walkLine ?? 0);
  /** Null on the last card, when every line has had its turn. */
  const line = $derived(flow.walkLine === null ? undefined : flow.review?.lines[index]);
  const guess = $derived(flow.guessFor(index));
  /** The last card says how many lines are left; a line card, how many are still to do. */
  const title = $derived(
    line
      ? `${total} ${plural(total, 'line isn’t', 'lines aren’t')} linked yet`
      : `${flow.unlinkedLines().length} ${plural(flow.unlinkedLines().length, 'line', 'lines')} left unlinked`
  );

  const amount = $derived.by(() => {
    if (!line || line.amount === null) return '';
    const shown = flow.withPints(line);
    const text = shown.amount_text ?? amountWords(shown.amount ?? 0);
    return [text, shown.unit ? unitFor(shown.unit, shown.amount ?? 0) : ''].join(' ').trim();
  });
  const sub = $derived(
    guess ? `${keptBySaid(guess.counted_as)}${guess.place ? ` · ${guess.place.name}` : ''}` : ''
  );

  // A new line starts with its buttons, not the picker.
  $effect(() => {
    void index;
    picking = false;
  });

  $effect(() => {
    if (!placesAndShops.places.length) void placesAndShops.load().catch(() => {});
  });

  function newIngredient(staple: boolean) {
    flow.newIngredient(index, staple);
    flow.walkNext();
  }

  function madeHere() {
    flow.madeHere(index);
    flow.walkNext();
  }

  /** An ingredient ("Same as"), or a recipe that makes it (F188). */
  function pick(picked: LinePick) {
    if (picked.kind === 'ingredient') flow.sameAs(index, picked.food);
    else flow.useRecipe(index, picked.recipe);
    flow.walkNext();
  }

  /** The words of the button that opened the pick-list: Cancel puts the cursor back on that
   *  button (drawn again when the list closes, so found by its words). */
  let opener: string | null = null;

  function openPick(recipesOnly: boolean) {
    opener = document.activeElement?.textContent?.trim() || null;
    pickingRecipes = recipesOnly;
    picking = true;
  }

  async function closePick() {
    picking = false;
    await tick();
    const back = [...(body?.querySelectorAll<HTMLElement>('button') ?? [])].find(
      (b) => b.textContent?.trim() === opener
    );
    back?.focus();
    opener = null;
  }
</script>

<Sheet {title} describedby="{uid}-text" onclose={() => flow.walkClose()}>
  {#if line}
    <div class="body" bind:this={body}>
      <p id="{uid}-text">
        Unlinked lines can’t be counted in your pantry or added to the shopping list properly. Sort
        them now, or save anyway and link them later in the recipe.
      </p>

      <div class="progress">
        <span class="count">Line {at + 1} of {total}</span>
        <span class="bars" aria-hidden="true">
          {#each Array.from({ length: total }, (_, i) => i) as i (i)}
            <span class="bar" class:done={i <= at}></span>
          {/each}
        </span>
      </div>

      <div class="card" class:confirm={line.label === 'to_confirm'}>
        <span class="written">{line.written}</span>
        <span class="name"
          >{line.readable ? line.words : 'Couldn’t read this line'}
          {#if amount}<span class="amount">· {amount}</span>{/if}</span
        >
        <span class="not"
          >{line.label === 'to_confirm' && line.food
            ? `Close to “${line.food.name}”`
            : 'Not in your ingredients'}</span
        >
      </div>

      {#if picking}
        <Lazy
          load={() => import('./PickLine.svelte')}
          written={line.written}
          words={line.words}
          recipesOnly={pickingRecipes}
          onpick={pick}
          onnew={() => {
            picking = false;
            newIngredient(false);
          }}
          oncancel={closePick}
        />
      {:else}
        <div class="choices">
          {#if flow.offersMadeHere(index)}
            <!-- The note says "from the …", or the name is a section heading (F108). -->
            <Button onclick={madeHere}>Made in this recipe</Button>
          {/if}
          {#if line.label === 'to_confirm' && line.food}
            <Button onclick={() => pick({ kind: 'ingredient', food: line.food! })}
              >Same as “{line.food.name}”</Button
            >
          {:else}
            <Button onclick={() => newIngredient(false)}>
              <span class="words">
                New ingredient{guess?.name ? ` “${guess.name}”` : ''}
                {#if sub}<span class="sub">{sub}</span>{/if}
              </span>
            </Button>
          {/if}
          <div class="grid">
            {#if !flow.offersMadeHere(index)}
              <Button quiet onclick={madeHere}>Made in this recipe</Button>
            {/if}
            <Button quiet onclick={() => openPick(false)}>Pick another</Button>
            <Button quiet onclick={() => openPick(true)}>Made in another recipe</Button>
            {#if line.label === 'to_confirm' && line.food}
              <Button quiet onclick={() => newIngredient(false)}>New ingredient</Button>
            {/if}
            <Button quiet onclick={() => newIngredient(true)}>Treat as staple</Button>
          </div>
          <button type="button" class="skip" onclick={() => flow.walkNext()}>Skip this line</button>
        </div>
      {/if}

      <div class="foot">
        <ButtonRow>
          <Button disabled={flow.saving || network.offline} onclick={onsave}>Save anyway</Button>
          <Button quiet onclick={() => flow.walkClose()}>Back to Check</Button>
        </ButtonRow>
      </div>
    </div>
  {:else if walk}
    <!-- The last card: every line has had its turn, and some are still not linked. -->
    {@const left = flow.unlinkedLines().length}
    <div class="body">
      <p id="{uid}-text">
        You can save now and link {plural(left, 'it', 'them')} later in the recipe, or go back to Check
        and sort {plural(left, 'it', 'them')} there.
      </p>
      <!-- On the last card the button just pressed has gone with the line card: focus Back to
           Check, so a keyboard or screen-reader user keeps their place (C2 review 2). -->
      <ButtonRow>
        <Button disabled={flow.saving || network.offline} onclick={onsave}>Save anyway</Button>
        <Button quiet autofocus onclick={() => flow.walkClose()}>Back to Check</Button>
      </ButtonRow>
    </div>
  {/if}
</Sheet>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  p {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  .progress {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .bars {
    display: flex;
    gap: 4px;
  }

  .bar {
    width: 22px;
    height: 6px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .bar.done {
    background: var(--color-accent);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 14px;
    border: 1px solid var(--color-warning-border);
    border-radius: var(--radius-button);
  }

  .card.confirm {
    border-color: var(--color-maybe-chip-border);
  }

  .written {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }

  .name {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .amount {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .not {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .card.confirm .not {
    color: var(--color-maybe-text);
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .skip {
    cursor: pointer;
    font-family: inherit;
    min-height: 44px;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .foot {
    padding-top: 12px;
    border-top: 1px solid var(--color-border);
  }

  .words {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1px;
  }

  .sub {
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    opacity: 0.8;
  }
</style>
