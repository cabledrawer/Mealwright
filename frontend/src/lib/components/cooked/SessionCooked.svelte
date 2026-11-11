<script lang="ts">
  // One "Cooked it" review for a whole Batch cook session (mockup Dark-BatchCooked08; spec section
  // 6, "Batch cook (Experimental)"; cabledrawer 11 Nov): each recipe's ingredients as a short list,
  // its tubs, and Change to open that recipe's rows (the same rows as the Cooked it review), then
  // one Cooked it. One change in Recent changes, with one Undo that puts every recipe's stock and
  // tubs back. The words the mockup shows are as drawn; the others are proposed, for cabledrawer.
  import { TOO_MANY_ANSWERS, amountWords, shown } from '#lib/cookRows.js';
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import type { CookReview, CookTab } from '#lib/cookReview.svelte.js';
  import Icon from '../Icon.svelte';
  import CookRowView from './CookRowView.svelte';

  let {
    review,
    onclose,
    onconfirmed
  }: {
    review: CookReview;
    onclose: () => void;
    /** After the pantry was changed: the screen leaves. */
    onconfirmed: () => void;
  } = $props();

  let dialog = $state<HTMLDialogElement>();
  /** The recipe whose rows are open (Change). */
  let open = $state<number | null>(null);

  const target = $derived(review.target);

  $effect(() => {
    if (!dialog) return;
    if (target !== null && !dialog.open) dialog.showModal();
    else if (target === null && dialog.open) dialog.close();
  });

  function tubsLine(tab: CookTab): string {
    const places = tab.tubs
      .map((t) => (t.place ? `${t.count} ${t.place}` : null))
      .filter((p): p is string => p !== null);
    const loose = tab.tubs.filter((t) => !t.place).reduce((n, t) => n + t.count, 0);
    const count = tab.tubs.reduce((n, t) => n + t.count, 0);
    if (count === 0) return 'Eaten today · no tubs';
    const where = [...places, ...(loose ? [`${loose} in meals`] : [])].join(', ');
    return `${count} ${count === 1 ? 'tub' : 'tubs'} · ${where}`; // "in meals": proposed
  }

  const lines = (tab: CookTab) => tab.rows.filter((r) => r.status !== 'staple');

  function rowWords(tab: CookTab, row: CookTab['rows'][number]): string {
    const view = shown(row, tab.state(row.key));
    if (row.status === 'none_in_pantry') return 'Not in pantry';
    if (!view.use || view.taken === 0) return 'Not taken';
    return amountWords(view.taken, row.unit);
  }

  async function confirm() {
    const { ok } = await review.confirm();
    if (ok) onconfirmed();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={target?.title ?? 'Cooked it'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  data-testid="session-cooked"
>
  {#if target}
    <div class="screen">
      <header>
        <div class="bar">
          <button type="button" class="x" aria-label="Back to Batch cook" onclick={onclose}>
            <Icon name="close" size={20} stroke={2.4} />
          </button>
          <h2>{target.title}</h2>
          <span class="spacer" aria-hidden="true"></span>
        </div>
        <p class="quiet">
          Check what came out of the pantry and where the tubs go. One entry in Recent changes, with
          Undo.
        </p>
      </header>

      <div class="body">
        {#if network.offline}
          <p class="note" role="status">
            {downLine(network.deviceOffline, (b) => `Cooked it changes ${b.when}.`)}
          </p>
        {/if}
        {#if review.tooMany}<p class="problem" role="alert">{TOO_MANY_ANSWERS}</p>{/if}
        {#if review.problem}<p class="problem" role="alert">{review.problem}</p>{/if}

        {#each review.tabs as tab, i (tab.part.batchId)}
          <section class="group" data-testid="session-recipe">
            <div class="head">
              <span class="nm">{tab.part.name}</span>
              <button
                type="button"
                class="change"
                aria-expanded={open === i}
                onclick={() => (open = open === i ? null : i)}
                >Change<span class="visually-hidden"> {tab.part.name}</span></button
              >
            </div>
            {#if !tab.proposal}
              <p class="quiet" role="status">Working out what to take…</p>
            {:else}
              <ul class="card">
                {#each lines(tab) as row (row.key)}
                  <li>
                    <span class="rn"
                      >{row.food?.name ?? row.recipe?.name ?? row.lines[0]?.words}</span
                    ><span class="am">{rowWords(tab, row)}</span>
                  </li>
                {/each}
                <li class="tubs"><span class="rn">{tubsLine(tab)}</span></li>
              </ul>
              {#if open === i}
                <div class="edit" class:busy={review.loading}>
                  <div class="portions">
                    <span><b>Portions cooked</b></span>
                    <span class="stepper" role="group" aria-label="Portions cooked">
                      <button
                        type="button"
                        aria-label="Fewer portions"
                        disabled={tab.portions <= 1 || review.saving}
                        onclick={() => void review.setPortions(tab, tab.portions - 1)}>−</button
                      >
                      <b aria-live="polite">{tab.portions}</b>
                      <button
                        type="button"
                        aria-label="More portions"
                        disabled={tab.portions >= 999 || review.saving}
                        onclick={() => void review.setPortions(tab, tab.portions + 1)}>+</button
                      >
                    </span>
                  </div>
                  <ul class="rows" aria-label="Taken from the pantry">
                    {#each lines(tab) as row (row.key)}
                      <CookRowView {review} {tab} {row} disabled={review.saving} />
                    {/each}
                  </ul>
                </div>
              {/if}
            {/if}
          </section>
        {/each}
      </div>

      <footer>
        <button
          type="button"
          class="main"
          disabled={review.saving || network.offline || review.tabs.some((t) => !t.proposal)}
          onclick={() => void confirm()}>Cooked it</button
        >
      </footer>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    width: 100%;
    max-width: none;
    height: 100%;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .screen {
    display: flex;
    flex-direction: column;
    height: 100%;
    max-width: 720px;
    margin-inline: auto;
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: max(var(--space-6), env(safe-area-inset-top)) var(--space-7) var(--space-6);
    border-bottom: 1px solid var(--color-border);
  }

  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .x,
  .spacer {
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
  }

  .x {
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    cursor: pointer;
  }

  h2 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: 800;
    text-align: center;
    overflow-wrap: anywhere;
  }

  .quiet,
  .note {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .problem {
    margin: 0;
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-7);
    min-height: 0;
    padding: var(--space-6) var(--space-7);
    overflow-y: auto;
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .nm {
    font-size: var(--text-md);
    font-weight: 800;
    overflow-wrap: anywhere;
  }

  .change {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: 10px;
    background: transparent;
    color: var(--color-text);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .card {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: var(--space-2) var(--space-6);
    border-radius: 18px;
    background: var(--color-fill);
    list-style: none;
  }

  .card li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    min-height: 48px;
    border-bottom: 1px solid var(--color-border);
  }

  .card li:last-child {
    border-bottom: none;
  }

  .rn {
    flex: 1;
    min-width: 0;
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .am {
    color: var(--color-text-muted);
    text-align: right;
  }

  .tubs .rn {
    color: var(--color-note-text);
  }

  .edit {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
    border: 1px solid var(--color-border);
    border-radius: 18px;
  }

  .edit.busy {
    opacity: 0.6;
  }

  .portions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .stepper {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
  }

  .stepper button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: 1.25rem;
    cursor: pointer;
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  footer {
    padding: var(--space-6) var(--space-7) max(var(--space-9), env(safe-area-inset-bottom));
    border-top: 1px solid var(--color-border);
  }

  .main {
    width: 100%;
    min-height: 56px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: 800;
    cursor: pointer;
  }

  .main:disabled {
    opacity: 0.5;
    cursor: default;
  }

  button:focus-visible {
    outline: 3px solid var(--color-accent);
    outline-offset: 2px;
  }
</style>
