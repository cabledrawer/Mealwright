<script lang="ts">
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Lazy from '#lib/components/Lazy.svelte';
  // One at a time (F141, cabledrawer 3 Nov; mockups Dark-ImportCheckOne07-Phone and
  // Dark-ImportCheckOneStep07-Phone): each line that needs the person, then every method step
  // (not only long ones), one to a screen, with the options the Check screen offers for that line
  // or step. A line is the Check screen's own ReviewLineRow, so Same as, Pick another, New
  // ingredient, Treat as staple, Made in this recipe, Remove line (with Undo), Split into two and
  // the amount and note boxes are all here, the same words doing the same work. A step has Change
  // the words, Remove step (with Undo), Split into shorter steps and Put the steps back as they
  // were. Back and Next; Next on the last screen is Save recipe. Close keeps the recipe in
  // Drafts. Loaded the first time it is chosen, so the import page stays small.
  // Words are the mockups', except those marked "proposed, for cabledrawer". The label
  // "Back to drafts (kept in Drafts)" on the X (was "Close", F211) is cabledrawer 5 Nov (F141).
  import { tick, untrack } from 'svelte';
  import { downLine } from '#lib/downWords.js';
  import { leftOutWords, type ImportFlow } from '#lib/import.svelte.js';
  import { removeStep } from '#lib/importStepEdits.js';
  import { sentenceCount } from '#lib/importSteps.js';
  import { headingAbove, walkItems } from '#lib/importWalk.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { OUTSIDE_CONNECTIONS_ANCHOR } from '#lib/privacyWords.js';
  import Icon from '#lib/components/Icon.svelte';
  import { timeWithWait } from '#lib/timeWords.js';
  import Switch from '#lib/components/Switch.svelte';
  import AddLine from './AddLine.svelte';
  import OwnRecipeHead from './OwnRecipeHead.svelte';
  import { headingOf } from '#lib/importOwn.js';
  import CheckFrame from './CheckFrame.svelte';
  import ReviewLineRow from './ReviewLineRow.svelte';
  import StepEdit from './StepEdit.svelte';
  import '#lib/styles/fields.css';
  import { plural } from '#lib/words.js';

  let {
    flow,
    closing,
    // eslint-disable-next-line no-useless-assignment -- only written, for the parent's bind:
    boxOpen = $bindable(false),
    onclose,
    onsave,
    onseeall,
    onleave,
    ondiscard,
    discardProblem = null
  }: {
    flow: ImportFlow;
    /** Keeping the draft is on its way. */
    closing: boolean;
    /** A step's box is open: the Check screen keeps the page from being left meanwhile (F143). */
    boxOpen?: boolean;
    onclose: () => void;
    onsave: () => void;
    onseeall: () => void;
    /** Leave without keeping the draft (the leave sheet's Discard). */
    onleave: () => void;
    /** Discard draft (F211): the screen asks once, then deletes the draft. */
    ondiscard: () => void;
    /** Why a Discard draft didn't go through. */
    discardProblem?: string | null;
  } = $props();

  const uid = $props.id();
  const privacy = `/settings/privacy#${OUTSIDE_CONNECTIONS_ANCHOR}`;
  const review = $derived(flow.review!);
  /** A line the save refused that is not one of the lines that need the person: the walk shows
   *  it too, once the refusal names it, and keeps it for the rest of the visit. Held as the line
   *  itself, so a line taken out before it doesn't make it another line. */
  let refused = $state.raw<(typeof review.lines)[number] | null>(null);
  const refusedAt = $derived(refused ? review.lines.indexOf(refused) : -1);
  const items = $derived(walkItems(review, refusedAt >= 0 ? refusedAt : null));
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

  /** "Add a line" for the section the line at `from` is in (F187): the new line is named on its
   *  own screen, which the walk goes to and keeps (a line the person just named stays, even when
   *  it matches an ingredient). */
  async function addHere(end: { at: number }) {
    const place = flow.addLine(end.at);
    if (place < 0) return;
    refused = review.lines[place] ?? null;
    await tick();
    const to = items.findIndex((i) => i.kind === 'line' && i.at === place);
    if (to >= 0) await go(to);
    // Going to the new screen puts the focus on the screen; the name box is where typing starts.
    await tick();
    region?.querySelector<HTMLInputElement>('input[id$="-add-name"]')?.focus();
  }
  const title = $derived(
    !item
      ? 'Nothing to check'
      : item.kind === 'line'
        ? `Ingredients · ${nth} of ${total} to check`
        : `Method · step ${nth} of ${total}`
  );

  // A save refused for a line: the walk goes to that line, which says what is wrong (the line may
  // be one the walk doesn't stop at, or one the person has gone past).
  /** The refused line the walk is to go to once no step box is open (going there would close
   *  the box and lose the words typed in it). */
  let jumpTo: (typeof review.lines)[number] | null = $state.raw(null);
  // Before the screen is drawn, so the walk's new stop doesn't draw the wrong screen for a moment.
  $effect.pre(() => {
    const line = flow.saveProblem?.line;
    if (line === null || line === undefined) return;
    untrack(() => {
      const row = review.lines[line];
      if (!row || row.kind !== 'ingredient') return;
      refused = row;
      jumpTo = row;
    });
  });
  $effect(() => {
    const row = jumpTo;
    if (!row || editing !== null) return;
    jumpTo = null;
    void tick().then(() => {
      const to = items.findIndex((i) => i.kind === 'line' && review.lines[i.at] === row);
      if (to >= 0 && to !== at) void go(to);
    });
  });

  // Undo (or anything else) putting a line or step back, or taking one out, doesn't move the
  // person: the screen stays on the same line or step, though its place in the walk has changed.
  let onScreen: unknown = null;
  const thing = (i: (typeof items)[number] | undefined) =>
    i ? (i.kind === 'line' ? review.lines[i.at] : review.steps[i.at]) : null;
  $effect.pre(() => {
    const list = items;
    untrack(() => {
      if (!onScreen) return;
      const found = list.findIndex((i) => thing(i) === onScreen);
      // Taken out (found < 0): the next one stands in its place, at the same number.
      if (found >= 0 && found !== pos) pos = found;
    });
  });
  $effect.pre(() => {
    const now = thing(item ?? undefined);
    untrack(() => {
      if (now !== onScreen) onScreen = now;
    });
  });

  // --- A step ---------------------------------------------------------------------------------
  const step = $derived(item?.kind === 'step' ? review.steps[item.at] : undefined);
  const stepAt = $derived(item?.kind === 'step' ? item.at : -1);
  const heading = $derived(step ? headingAbove(review.steps, stepAt) : null);
  const pieces = $derived(step ? flow.splitOf(stepAt) : null);
  const previewing = $derived(pieces !== null && flow.previewStep === stepAt);
  let editing = $state<NonNullable<typeof step> | null>(null);

  $effect.pre(() => {
    boxOpen = editing !== null;
    // This screen goes (the phone turned to a wide screen): its box goes with it.
    return () => (boxOpen = false);
  });

  // The step being changed went from the list (taken out, split or put back): the box goes too.
  $effect(() => {
    if (editing && !review.steps.includes(editing)) editing = null;
  });

  // A new screen starts at its top, with no preview open for another step.
  let region: HTMLElement | undefined = $state();
  async function go(to: number) {
    editing = null;
    flow.previewStep = null;
    pos = to;
    region?.scrollIntoView({ block: 'start' });
    await tick();
    region?.focus();
  }

  // A line or step that went (Remove line, Split into two, Keep the split) takes the focused
  // button with it, so the focus goes to the top of the screen, as after Back and Next.
  let shown: unknown = undefined;
  $effect(() => {
    const now = item
      ? item.kind === 'line'
        ? review.lines[item.at]
        : review.steps[item.at]
      : null;
    const changed = shown !== undefined && now !== shown;
    shown = now;
    if (!changed) return;
    void tick().then(() => {
      const active = document.activeElement;
      if (!active || active === document.body) region?.focus();
    });
  });

  // Swiping sideways does what Next and Back do, and waits while a step's box is open, as they
  // do (F145, cabledrawer 6 Nov). The buttons stay: they are the way for the keyboard and screen
  // readers. Mostly sideways and far enough that a tap or a scroll is never read as a swipe.
  const SWIPE_FAR = 60;
  let down: { x: number; y: number; id: number } | null = null;
  function pointerdown(event: PointerEvent) {
    if (
      (event.target as HTMLElement).closest('button, a, input, textarea, select, [role="switch"]')
    )
      return;
    down = { x: event.clientX, y: event.clientY, id: event.pointerId };
  }
  function pointerup(event: PointerEvent) {
    const start = down;
    down = null;
    if (!start || start.id !== event.pointerId || editing !== null || !item) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) < SWIPE_FAR || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    const to = dx < 0 ? at + 1 : at - 1;
    if (to < 0 || to >= items.length) return;
    void go(to);
  }

  async function takeOut() {
    if (stepAt < 0) return;
    removeStep(flow, stepAt);
    await tick();
    region?.focus();
  }
</script>

{#snippet addLine(from: number)}
  {@const end = flow.sectionEnds.find((e) => e.at > from)}
  {#if end && flow.canAddLine}
    <AddLine label={end.label} onclick={() => void addHere(end)} />
  {/if}
{/snippet}

<CheckFrame>
  {#snippet header()}
    <div class="head">
      <button
        type="button"
        class="x"
        aria-label="Back to drafts (kept in Drafts)"
        disabled={closing || flow.saving || editing !== null}
        onclick={onclose}><Icon name="close" size={18} stroke={2.4} /></button
      >
      <div class="titles">
        <h1 aria-live="polite">{title}</h1>
        <span class="muted">{name} · nothing saved yet</span>
      </div>
      <!-- Waits while a step box is open, as Close does: the box keeps its words until Done. -->
      <button type="button" class="see-all" disabled={editing !== null} onclick={onseeall}
        >See all</button
      >
    </div>
  {/snippet}

  <!-- The swipe is the extra; Back and Next are the way for the keyboard and screen readers. -->
  <div
    class="one"
    role="presentation"
    bind:this={region}
    tabindex="-1"
    onpointerdown={pointerdown}
    onpointerup={pointerup}
    onpointercancel={() => (down = null)}
  >
    {#if at === 0}
      <!-- The recipe's name, Serves and minutes, and the photo note, at the top of the first
           screen, as Focus shows them (F141 follow-up, cabledrawer 6 Nov). -->
      <section class="details" aria-label="Recipe details">
        <label class="field" for="{uid}-name">
          <span>Name</span>
          <input
            id="{uid}-name"
            class="mw-input title"
            type="text"
            maxlength="200"
            bind:value={flow.name}
          />
        </label>
        <div class="two">
          <label class="field" for="{uid}-serves">
            <span>Serves</span>
            <input
              id="{uid}-serves"
              class="mw-input"
              type="text"
              inputmode="numeric"
              maxlength="2"
              bind:value={flow.serves}
            />
          </label>
          <label class="field" for="{uid}-time">
            <span>Minutes</span>
            <input
              id="{uid}-time"
              class="mw-input"
              type="text"
              inputmode="numeric"
              maxlength="5"
              bind:value={flow.minutes}
            />
          </label>
        </div>
        {#if flow.waitTotal}
          <p class="time-split">
            {timeWithWait(flow.minutes.trim() === '' ? null : Number(flow.minutes), flow.waitTotal)}
          </p>
        {/if}
        {#if review.photo.state === 'off' || review.photo.state === 'failed'}
          <p class="photo-note">
            {#if review.photo.state === 'off'}
              <b>Photo not downloaded.</b> Photo downloads are off in
              {#if session.me?.role === 'admin'}
                <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings › Outside connections is built beside this page -->
                <a href={privacy}>Settings › Outside connections</a>.
              {:else}
                Settings › Outside connections; an admin can switch them on.
              {/if}
              You can add your own photo later.
            {:else}
              <b>Photo not downloaded</b>
              — {review.photo.message} You can add your own photo later.
            {/if}
          </p>
        {/if}
      </section>
    {/if}
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
      {@const above = headingOf(review.lines, item.at)}
      {#if above !== null && review.lines[above]}
        <!-- The section this line is in, with "Make this its own recipe" (F190). -->
        <div class="section-own">
          <span class="section">{review.lines[above].words}</span>
          <OwnRecipeHead {flow} heading={above} />
        </div>
      {/if}
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
      {@render addLine(item.at)}
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
          <!-- Optional (R3, F151): shown with "Optional step" on the recipe. -->
          <p class="optional-row">
            <Switch
              checked={!!step.optional}
              labelledby="optional-step-{nth}"
              onchange={(on) => (step.optional = on)}
            />
            <span id="optional-step-{nth}">Optional step</span>
          </p>
          {#if step.wait}
            <Lazy load={() => import('./StepWait.svelte')} {flow} {step} name="step {nth}" />
          {/if}
        </div>
      {/if}

      {#if nth === 1 && flow.review?.second_method}
        <Lazy load={() => import('./ImportMethods.svelte')} {flow} review={flow.review} />
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
            <Button soft onclick={() => flow.keepSplit(stepAt)}>Keep the split</Button>
            <Button plain small onclick={() => (flow.previewStep = null)}>Keep as one</Button>
          {:else}
            {#if pieces}
              <Button
                soft
                onclick={() => {
                  flow.previewStep = stepAt;
                }}>Split into shorter steps</Button
              >
            {/if}
            <div class="two">
              <Button
                outline
                small
                onclick={() => {
                  flow.previewStep = null;
                  editing = step;
                }}>Change the words</Button
              >
              <Button outline small onclick={() => void takeOut()}>Remove step</Button>
            </div>
          {/if}
          {#if flow.stepsBefore}
            <Button plain small onclick={() => flow.putStepsBack()}
              >Put the steps back as they were</Button
            >
          {/if}
          <span class="hint"
            >A step that looks fine: just press Next. After the last step: Save recipe.</span
          >
        </div>
      {/if}
    {:else}
      <!-- Nothing needs the person and there is no method: words cabledrawer 5 Nov (F141). -->
      <p class="empty">
        Nothing to check here. Press Save recipe, or See all to look at the whole recipe.
      </p>
    {/if}

    <!-- No line needs the person, so no line screen has the button: the first screen has it, for
         the last section (the other sections are on See all). -->
    {#if item?.kind !== 'line' && at === 0 && lineTotal === 0}
      {@render addLine(review.lines.length - 1)}
    {/if}

    <!-- The notes the whole list shows, on the screen they are about. -->
    {#if review.lines_cut && (item?.kind === 'line' ? nth === total : at === 0 && lineTotal === 0)}
      <p class="hint">The page had more than 200 ingredient lines. The first 200 are here.</p>
    {/if}
    {#if review.steps_shortened && item?.kind === 'step' && last}
      <p class="hint">
        {review.steps_shortened}
        {plural(review.steps_shortened, 'step was', 'steps were')} shortened to 5,000 characters.
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
      {#if flow.saveProblem && flow.saveProblem.line === null}
        <p class="error" role="alert">{flow.saveProblem.message}</p>
      {:else if flow.saveProblem && flow.saveProblem.line !== null}
        <p class="error" role="alert">
          Line {flow.saveProblem.line + 1}: {flow.saveProblem.message}
        </p>
      {/if}
      {#if flow.draftProblem}
        <p class="error" role="alert">{flow.draftProblem}</p>
        <!-- The leave sheet's own words and action, for a draft that was changed and can't be
             kept: the draft stays as it was last kept. A review never kept is left with Discard
             draft below. -->
        {#if flow.draftId !== null}
          <Button plain disabled={flow.saving || editing !== null} onclick={onleave}
            >Discard changes</Button
          >
        {/if}
      {/if}
      {#if discardProblem}<p class="error" role="alert">{discardProblem}</p>{/if}
      <ButtonRow>
        <!-- One button for Next and Save recipe, so the focus stays on it at the last screen. -->
        <Button
          disabled={editing !== null || (last && (flow.saving || closing || network.offline))}
          onclick={() => (last ? onsave() : void go(at + 1))}
          >{last ? (flow.saving ? 'Saving…' : 'Save recipe') : 'Next →'}</Button
        >
        {#if item}
          <Button outline disabled={at === 0 || editing !== null} onclick={() => void go(at - 1)}
            >← Back</Button
          >
        {/if}
      </ButtonRow>
      <Button
        plain
        disabled={flow.saving ||
          closing ||
          editing !== null ||
          (flow.draftId !== null && network.offline)}
        onclick={ondiscard}>Discard draft</Button
      >
      {#if network.offline}
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

  .details {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .title {
    font: var(--weight-semibold) 1.375rem var(--font-reading);
  }

  /* Boxes are 16 px or more, so a phone doesn't zoom in on them. */
  .two input {
    font-size: 1rem;
  }

  .two {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .photo-note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .photo-note b {
    color: var(--color-text);
  }

  .photo-note a {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }

  .one {
    min-height: 100%;
    touch-action: pan-y;
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

  .section-own {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
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

  .optional-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
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
    border-radius: var(--radius-lg);
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

  /* A blocked button looks blocked, the same as Save recipe (F154): Close and See all too. */
  .x:disabled,
  .see-all:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .time-split {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }
</style>
