<script lang="ts">
  // The method (cabledrawer 19 Oct, questions 4 and 5): plain text steps, one box each, numbered by
  // themselves, with optional headings. Up to 100, headings included. Reordered like the lines.
  import '$lib/styles/fields.css';
  import { tick } from 'svelte';
  import Icon from '../Icon.svelte';
  import {
    blankStep,
    MAX_STEPS,
    type DraftStep,
    type Errors,
    type RecipeDraft
  } from '$lib/recipes/draft.svelte';
  import { autosize } from '$lib/recipes/autosize';
  import { move, reorder } from '$lib/recipes/reorder';
  import { undoHistory, type UndoEntry } from '$lib/undo.svelte';

  let {
    draft,
    errors,
    announce
  }: {
    draft: RecipeDraft;
    errors: Errors;
    announce: (message: string) => void;
  } = $props();

  const uid = $props.id();
  let root: HTMLElement;
  const removed: UndoEntry[] = [];

  const full = $derived(draft.steps.length >= MAX_STEPS);
  /** A step's number: headings are not counted. */
  const numberOf = (index: number) =>
    draft.steps.slice(0, index + 1).filter((s) => s.kind === 'step').length;

  async function add(kind: DraftStep['kind']) {
    const step = blankStep(kind);
    draft.steps.push(step);
    await tick();
    root.querySelector<HTMLElement>(`[data-step="${step.key}"] [data-words]`)?.focus();
  }

  function takeOut(index: number) {
    const [step] = draft.steps.splice(index, 1);
    if (!step) return;
    const entry: UndoEntry = {
      label: step.kind === 'heading' ? 'Took out the heading' : 'Took out a step',
      undo: () => {
        draft.steps.splice(Math.min(index, draft.steps.length), 0, step);
      }
    };
    removed.push(entry);
    undoHistory.record(entry);
    void tick().then(() => {
      const handles = [...root.querySelectorAll<HTMLElement>('[data-reorder-handle]')];
      (
        handles[index] ??
        handles[index - 1] ??
        root.querySelector<HTMLElement>('[data-add]')
      )?.focus();
    });
  }

  $effect(() => () => removed.forEach((entry) => undoHistory.forget(entry)));
</script>

<section class="steps" aria-labelledby="{uid}-title" bind:this={root}>
  <div class="title">
    <h2 id="{uid}-title">Method</h2>
    <span class="note">Plain text, one step per box</span>
  </div>

  <ol>
    {#each draft.steps as step, i (step.key)}
      {@const problem = errors[`step:${step.key}`]}
      <li class="row" data-reorder-row data-step={step.key}>
        <button
          type="button"
          class="mw-icon handle"
          data-reorder-handle
          aria-label="Move {step.kind === 'heading'
            ? 'heading'
            : `step ${numberOf(i)}`}. Alt and the up or down arrow moves it."
          aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown"
          use:reorder={{
            index: () => draft.steps.indexOf(step),
            count: () => draft.steps.length,
            move: (from, to) => move(draft.steps, from, to),
            announce
          }}
        >
          <Icon name="grip" size={18} />
        </button>
        {#if step.kind === 'heading'}
          <input
            class="mw-input head-input"
            aria-label="Method heading"
            data-words
            maxlength="200"
            placeholder="e.g. The tempering"
            bind:value={step.text}
          />
        {:else}
          <span class="number" aria-hidden="true">{numberOf(i)}</span>
          <textarea
            class="mw-input"
            aria-label="Step {numberOf(i)}"
            data-words
            rows="3"
            maxlength="5000"
            placeholder="Describe this step"
            aria-invalid={problem ? true : undefined}
            bind:value={step.text}
            use:autosize={step.text}></textarea>
        {/if}
        <button
          type="button"
          class="mw-icon take-out"
          aria-label={step.kind === 'heading'
            ? 'Take out this heading'
            : `Take out step ${numberOf(i)}`}
          onclick={() => takeOut(i)}
        >
          <Icon name="close" size={18} />
        </button>
        {#if problem}<p class="mw-error msg" role="alert">{problem}</p>{/if}
      </li>
    {/each}
  </ol>

  <span class="adds">
    <button type="button" class="mw-add" data-add disabled={full} onclick={() => void add('step')}
      >+ Add step</button
    >
    <button type="button" class="mw-add" disabled={full} onclick={() => void add('heading')}
      >+ Add heading</button
    >
  </span>
  {#if full}<p class="mw-hint">
      A recipe can have up to {MAX_STEPS} steps, headings included.
    </p>{/if}
</section>

<style>
  .steps {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .title {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-2) var(--space-6);
  }

  h2 {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-3);
  }

  .row:global([data-dragging]) {
    box-shadow: var(--shadow-toast);
    outline: 2px solid var(--color-focus);
  }

  .handle,
  .take-out {
    position: relative;
    touch-action: none;
  }

  .handle {
    width: 28px;
    border-radius: var(--radius-sm);
    cursor: grab;
  }

  .take-out {
    width: 36px;
    touch-action: manipulation;
  }

  .handle::before {
    content: '';
    position: absolute;
    inset: 0 -8px;
  }

  .take-out::before {
    content: '';
    position: absolute;
    inset: 0 -4px;
  }

  .number {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    margin-top: var(--space-5);
    border-radius: 14px;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }

  textarea {
    flex: 1 1 0;
    resize: vertical;
    line-height: 1.45;
  }

  .head-input {
    flex: 1;
    border-style: dashed;
    background: transparent;
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
  }

  .msg {
    flex: 1 1 100%;
  }

  .adds {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    padding-top: var(--space-2);
  }
</style>
