<script lang="ts">
  // One at a time (F141, cabledrawer 3 Nov; mockups Dark-ImportCheckOne07-Phone and
  // Dark-ImportCheckOneStep07-Phone): each line that needs the person, then every method step
  // (not only long ones), one to a screen, with the options the Check screen offers for that line
  // or step. A line is the Check screen's own ReviewLineRow, so Same as, Pick another, New
  // ingredient, Treat as staple, Made in this recipe, Remove line (with Undo), Split into two and
  // the amount and note boxes are all here, the same words doing the same work. A step has Change
  // the words, Remove step (with Undo), Split into shorter steps and Put the steps back as they
  // were. Back and Next; Next on the last screen is Save recipe. Close keeps the recipe in
  // Drafts. Loaded the first time it is chosen, so the import page stays small.
  // Words are the mockups', except those marked "proposed, for cabledrawer".
  import { tick } from 'svelte';
  import { downLine } from '#lib/downWords.js';
  import { leftOutWords, type ImportFlow } from '#lib/import.svelte.js';
  import { removeStep } from '#lib/importStepEdits.js';
  import { sentenceCount } from '#lib/importSteps.js';
  import { headingAbove, walkItems } from '#lib/importWalk.js';
  import { network } from '#lib/network.svelte.js';
  import Icon from '#lib/components/Icon.svelte';
  import CheckFrame from './CheckFrame.svelte';
  import ReviewLineRow from './ReviewLineRow.svelte';
  import StepEdit from './StepEdit.svelte';

  let {
    flow,
    closing,
    onclose,
    onsave,
    onseeall
  }: {
    flow: ImportFlow;
    /** Keeping the draft is on its way. */
    closing: boolean;
    onclose: () => void;
    onsave: () => void;
    onseeall: () => void;
  } = $props();

  const review = $derived(flow.review!);
  const items = $derived(walkItems(review));
  /** Where the person is. It holds a number, so after a line or step is taken out the next one
   *  takes its place, and after the last is taken out the one before shows. */
  let pos = $state(0);
  const at = $derived(Math.min(pos, Math.max(items.length - 1, 0)));
  const item = $derived(items[at] ?? null);
  const lineTotal = $derived(items.filter((i) => i.kind === 'line').length);
  const stepTotal = $derived(items.length - lineTotal);
  /** The place among its own kind: "2 of 3" lines, "4 of 9" steps. */
  const nth = $derived(item?.kind === 'step' ? at - lineTotal + 1 : at + 1);
  const total = $derived(item?.kind === 'step' ? stepTotal : lineTotal);
  const last = $derived(at >= items.length - 1);

  const name = $derived(flow.name.trim() || 'This recipe');
  const title = $derived(
    !item
      ? 'Nothing to check'
      : item.kind === 'line'
        ? `Ingredients · ${nth} of ${total} to check`
        : `Method · step ${nth} of ${total}`
  );

  // --- A step ---------------------------------------------------------------------------------
  const step = $derived(item?.kind === 'step' ? review.steps[item.at] : undefined);
  const stepAt = $derived(item?.kind === 'step' ? item.at : -1);
  const heading = $derived(step ? headingAbove(review.steps, stepAt) : null);
  const pieces = $derived(step ? flow.splitOf(stepAt) : null);
  const previewing = $derived(pieces !== null && flow.previewStep === stepAt);
  let editing = $state<NonNullable<typeof step> | null>(null);

  // The step being changed went from the list (taken out, split or put back): the box goes too.
  $effect(() => {
    if (editing && !review.steps.includes(editing)) editing = null;
  });

  // A new screen starts at its top, with no preview open for another step.
  let region: HTMLElement | undefined = $state();
  function go(to: number) {
    editing = null;
    flow.previewStep = null;
    pos = to;
    region?.scrollIntoView({ block: 'start' });
  }

  async function takeOut() {
    if (stepAt < 0) return;
    removeStep(flow, stepAt);
    await tick();
    region?.focus();
  }
</script>

<CheckFrame>
  {#snippet header()}
    <div class="head">
      <button
        type="button"
        class="x"
        aria-label="Close (kept in Drafts)"
        disabled={closing}
        onclick={onclose}><Icon name="close" size={18} stroke={2.4} /></button
      >
      <div class="titles">
        <h1 aria-live="polite">{title}</h1>
        <span class="muted">{name} · nothing saved yet</span>
      </div>
      <button type="button" class="see-all" onclick={onseeall}>See all</button>
    </div>
  {/snippet}

  <div class="one" bind:this={region} tabindex="-1">
    {#if item}
      <div class="progress">
        <span class="overline"
          >{item.kind === 'line' ? 'Lines that need you' : 'Every step'} · {nth} of {total}</span
        >
        <span class="bars" aria-hidden="true">
          {#each Array.from({ length: total }, (_, i) => i) as i (i)}
            <span class="bar" class:done={i < nth}></span>
          {/each}
        </span>
      </div>
    {/if}

    {#if item?.kind === 'line'}
      {#key review.lines[item.at]}
        <ul class="line">
          <ReviewLineRow
            {flow}
            index={item.at}
            line={flow.withPints(review.lines[item.at]!)}
            problem={flow.saveProblem?.line === item.at ? flow.saveProblem.message : null}
          />
        </ul>
      {/key}
    {:else if step && item}
      {#if editing === step}
        <StepEdit
          {flow}
          {step}
          name="step {nth}"
          onclose={() => {
            editing = null;
          }}
          onremove={() => {
            editing = null;
            void takeOut();
          }}
        />
      {:else}
        <div class="card">
          {#if heading}<span class="section">{heading}</span>{/if}
          <button
            type="button"
            class="words"
            aria-label="Change step {nth}: {step.text}"
            onclick={() => {
              flow.previewStep = null;
              editing = step;
            }}>{step.text}</button
          >
          {#if pieces}
            <span class="long">A long step ({sentenceCount(step.text)} sentences)</span>
          {/if}
        </div>
      {/if}

      {#if previewing && pieces}
        <div class="preview" role="group" aria-label="Preview of the split">
          <span class="preview-title">Preview: this step as {pieces.length} steps</span>
          {#each pieces as piece, n (n)}
            <span class="piece"><b>{n + 1}.</b> {piece}</span>
          {/each}
        </div>
      {/if}

      {#if editing !== step}
        <div class="actions">
          {#if previewing}
            <button type="button" class="primary" onclick={() => flow.keepSplit(stepAt)}
              >Keep the split</button
            >
            <button type="button" class="quiet" onclick={() => (flow.previewStep = null)}
              >Keep as one</button
            >
          {:else}
            {#if pieces}
              <button
                type="button"
                class="primary"
                onclick={() => {
                  flow.previewStep = stepAt;
                }}>Split into shorter steps</button
              >
            {/if}
            <div class="two">
              <button
                type="button"
                class="option"
                onclick={() => {
                  flow.previewStep = null;
                  editing = step;
                }}>Change the words</button
              >
              <button type="button" class="option" onclick={() => void takeOut()}
                >Remove step</button
              >
            </div>
          {/if}
          {#if flow.stepsBefore}
            <button type="button" class="quiet" onclick={() => flow.putStepsBack()}
              >Put the steps back as they were</button
            >
          {/if}
          <span class="hint"
            >A step that looks fine: just press Next. After the last step: Save recipe.</span
          >
        </div>
      {/if}
    {:else}
      <!-- Nothing needs the person and there is no method: proposed, for cabledrawer. -->
      <p class="empty">
        Nothing needs you here, and there are no steps to look at. Press Save recipe, or See all to
        look at the whole recipe.
      </p>
    {/if}

    {#if review.steps_cut && item?.kind === 'step' && last}
      <p class="hint">The page had more than 100 steps. The first 100 are here.</p>
    {/if}
    {#if item?.kind === 'step' && last}
      {#each review.left_out as left (left.heading)}
        <p class="hint">{leftOutWords(left.heading, left.lines)}. You can add them by hand.</p>
      {/each}
    {/if}
  </div>

  {#snippet footer()}
    <div class="foot">
      {#if flow.unlinked > 0 && last}
        <p class="muted" role="status">
          {flow.unlinked}
          {flow.unlinked === 1 ? 'line' : 'lines'} will be saved without an ingredient. You can link
          {flow.unlinked === 1 ? 'it' : 'them'} in the recipe.
        </p>
      {/if}
      {#if flow.saveProblem && flow.saveProblem.line === null}
        <p class="error" role="alert">{flow.saveProblem.message}</p>
      {:else if flow.saveProblem && flow.saveProblem.line !== null}
        <p class="error" role="alert">
          Line {flow.saveProblem.line + 1}: {flow.saveProblem.message}
        </p>
      {/if}
      {#if flow.draftProblem}<p class="error" role="alert">{flow.draftProblem}</p>{/if}
      <div class="buttons">
        {#if item}
          <button
            type="button"
            class="back"
            disabled={at === 0 || editing !== null}
            onclick={() => go(at - 1)}>← Back</button
          >
        {/if}
        {#if last}
          <button
            type="button"
            class="next"
            disabled={flow.saving || network.offline || editing !== null}
            onclick={onsave}>{flow.saving ? 'Saving…' : 'Save recipe'}</button
          >
        {:else}
          <button type="button" class="next" disabled={editing !== null} onclick={() => go(at + 1)}
            >Next →</button
          >
        {/if}
      </div>
      {#if network.offline && last}
        <p class="muted" role="status">
          {downLine(network.deviceOffline, (b) => `Save ${b.when}.`)}
        </p>
      {/if}
    </div>
  {/snippet}
</CheckFrame>

<style>
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-5);
  }

  .x {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text);
    cursor: pointer;
  }

  .titles {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  h1 {
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .see-all {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .one {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
    outline: none;
  }

  .progress {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .bars {
    display: flex;
    gap: var(--space-2);
  }

  .bar {
    flex: 1;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .bar.done {
    background: var(--color-accent);
  }

  .line {
    margin: 0;
    padding: 0;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-7);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .section {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .words {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) 1rem / 1.5 var(--font-reading);
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }

  .long {
    color: var(--color-maybe-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .preview {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) var(--space-6);
    border: 2px solid var(--color-accent);
    border-radius: 14px;
    font-size: var(--text-md);
  }

  .preview-title {
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .actions {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
  }

  .primary,
  .option,
  .quiet {
    min-height: var(--touch-target);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .primary {
    min-height: 52px;
    border: none;
    border-radius: 14px;
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .option {
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: transparent;
    color: var(--color-text);
  }

  .quiet {
    border: none;
    background: transparent;
    color: var(--color-text-muted);
  }

  .hint,
  .empty {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    text-align: center;
  }

  .empty {
    padding: var(--space-9) 0;
    font-size: var(--text-base);
  }

  .foot {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .foot .muted,
  .foot .error {
    text-align: center;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    gap: var(--space-5);
  }

  .back,
  .next {
    min-height: 52px;
    border-radius: var(--radius-full);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .back {
    flex: 1;
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .next {
    flex: 1.4;
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .back:disabled,
  .next:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
