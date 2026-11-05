<script lang="ts">
  // Cook mode (mockups CookMode-Phone/Desktop and the Dark- ones, Experimental07; spec section 6,
  // "Cook mode", "Cook mode timers", "Cook mode ingredients" and "Cook mode (K4)", cabledrawer 17, 28
  // and 31 Oct): big text, one step at a time, Back and Next (the arrow keys and a swipe do the
  // same), "Show ingredients" always, timers found in the step's words, Keep screen awake, and
  // per-step ingredients as an Experimental option. The last step ends with Cooked it and Not cooked yet (Close where no meal is planned).
  // A heading in the method is a section title, never a step. All the words here are proposed,
  // for cabledrawer, unless the spec gives them.
  import { tick, untrack } from 'svelte';
  import type { Recipe } from '#lib/client/recipes.js';
  import { clock, cookSteps, findTimers, stepLines } from '#lib/cookSteps.js';
  import type { CookTimers } from '#lib/cookTimers.svelte.js';
  import { lineAmount } from '#lib/recipeAmounts.js';
  import { linkedWords } from '#lib/recipes/linkedWords.js';
  import type { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import Icon from '../Icon.svelte';
  import KeepAwake from '../KeepAwake.svelte';
  import Switch from '../Switch.svelte';

  let {
    recipe,
    timers,
    awake,
    perStep,
    onperstep,
    onexit,
    oncooked = null,
    notice = null,
    problem = null
  }: {
    recipe: Recipe;
    timers: CookTimers;
    awake: ScreenAwake;
    /** Whether per-step ingredients (Experimental) are on, and the household's way to change it. */
    perStep: boolean;
    onperstep: (on: boolean) => void;
    /** Leave Cook mode (Not cooked yet, Close, or the cross). Asked first when a timer is running. */
    onexit: () => void;
    /** "Cooked it": into the review. Not there when nothing has been planned to cook. */
    oncooked?: (() => void) | null;
    /** Where Cook now planned the recipe, with its Undo (the toast would be under this screen). */
    notice?: { text: string; undo?: () => void } | null;
    /** One short line, e.g. when the per-step switch went back. */
    problem?: string | null;
  } = $props();

  const uid = $props.id();
  const steps = $derived(cookSteps(recipe.steps));
  let at = $state(0);
  const index = $derived(Math.min(at, Math.max(steps.length - 1, 0)));
  const step = $derived(steps[index] ?? null);
  const last = $derived(steps.length === 0 || index === steps.length - 1);
  const found = $derived(step ? findTimers(step.text) : []);
  const mine = $derived(step ? stepLines(step, recipe.lines) : []);
  const keyOf = (n: number, i: number) => `${n}:${i}`;
  /** Timers started on other steps, still running or ended: seen from every step. */
  const elsewhere = $derived(
    timers.timers.filter((t) => !step || !t.key.startsWith(`${step.number}:`))
  );
  const ended = $derived(timers.timers.filter((t) => t.state === 'ended'));

  let ingredients: HTMLDialogElement;
  let leaving: HTMLDialogElement;
  let body: HTMLElement;
  let sheetOpen = $state(false);
  let askingLeave = $state(false);

  const dialogOpen = () => sheetOpen || askingLeave;

  function go(to: number) {
    if (steps.length === 0) return;
    at = Math.min(Math.max(to, 0), steps.length - 1);
    void tick().then(() => body?.scrollTo({ top: 0 }));
  }

  /** The cross, Not cooked yet or Close: straight out, or asks first when a timer is running. */
  function leave() {
    if (timers.running) askingLeave = true;
    else onexit();
  }

  /** For the page, when the browser is about to leave (Back, a link): ask first if need be. */
  export function leaveOr(proceed: () => void) {
    if (!timers.running) return proceed();
    pending = proceed;
    askingLeave = true;
  }
  let pending: (() => void) | null = null;

  function stay() {
    askingLeave = false;
    pending = null;
  }

  function reallyLeave() {
    askingLeave = false;
    timers.stopAll();
    const proceed = pending ?? onexit;
    pending = null;
    proceed();
  }

  $effect(() => {
    if (sheetOpen && !ingredients.open) ingredients.showModal();
    else if (!sheetOpen && ingredients.open) ingredients.close();
  });
  $effect(() => {
    if (askingLeave && !leaving.open) leaving.showModal();
    else if (!askingLeave && leaving.open) leaving.close();
  });

  function onkeydown(event: KeyboardEvent) {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (dialogOpen()) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      go(index + 1);
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      go(index - 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      leave();
    }
  }

  // Swiping the step sideways: left for the next step, right for the one before. The buttons do
  // the same (cabledrawer 21 Oct: every swipe has a visible button). Mostly sideways, and far enough
  // that a tap or a scroll is never read as one.
  const SWIPE_FAR = 60;
  let down: { x: number; y: number; id: number } | null = null;
  function pointerdown(event: PointerEvent) {
    if ((event.target as HTMLElement).closest('button, a, input, [role="switch"]')) return;
    down = { x: event.clientX, y: event.clientY, id: event.pointerId };
  }
  function pointerup(event: PointerEvent) {
    const start = down;
    down = null;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) < SWIPE_FAR || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    go(dx < 0 ? index + 1 : index - 1);
  }

  // The screen stays on while cooking (turns itself on with Cook mode; "Keep screen awake" is
  // the switch). Asked once, when the screen opens, and again when it comes back to the front.
  $effect(() => {
    untrack(() => {
      if (awake.supported) void awake.set(true);
    });
    return () => void awake.leave();
  });

  function onVisible() {
    if (document.visibilityState !== 'visible') return;
    void awake.comeBack();
    timers.tick();
  }

  const amountFor = (line: Recipe['lines'][number]) => lineAmount(line, 1);
  const wordsFor = (line: Recipe['lines'][number]) => linkedWords(line.words, line.food);
  const progress = $derived(steps.length ? `Step ${index + 1} of ${steps.length}` : 'No steps');
  /** Between the bold amount and the words. */
  const SPACE = ' ';
  const timerNote = 'No alarm if the phone is locked or Mealwright is in the background.';
</script>

<svelte:window {onkeydown} />
<svelte:document onvisibilitychange={onVisible} />
<svelte:head><title>Cooking {recipe.name} · Mealwright</title></svelte:head>

<div class="cook" role="region" aria-label="Cook mode">
  <header>
    <div class="bar">
      <button type="button" class="exit" aria-label="Leave Cook mode" onclick={leave}>
        <Icon name="close" size={20} stroke={2.4} />
      </button>
      <div class="who">
        <h1>{recipe.name}</h1>
        <p class="count" data-testid="step-count">{progress}</p>
      </div>
      {#if awake.on}
        <span class="awake"><Icon name="light" size={14} stroke={2.4} />Awake</span>
      {:else}
        <span class="awake spacer" aria-hidden="true"></span>
      {/if}
    </div>
    {#if steps.length}
      <div class="progress" aria-hidden="true">
        {#each steps as s, i (s.number)}
          <span class:filled={i <= index}></span>
        {/each}
      </div>
    {/if}
    {#if notice}
      <p class="notice" role="status" data-testid="cook-notice">
        <span>{notice.text}</span>
        {#if notice.undo}<button type="button" onclick={notice.undo}>Undo</button>{/if}
      </p>
    {/if}
    {#if problem}<p class="notice problem" role="status">{problem}</p>{/if}
  </header>

  <!-- The swipe is the extra; the Back and Next buttons are the way for the keyboard and screen readers. -->
  <div
    class="body"
    role="presentation"
    bind:this={body}
    onpointerdown={pointerdown}
    onpointerup={pointerup}
  >
    {#if elsewhere.length}
      <ul class="elsewhere" aria-label="Timers on other steps">
        {#each elsewhere as t (t.key)}
          {@const number = Number(t.key.split(':')[0])}
          <li>
            <button type="button" class:over={t.state === 'ended'} onclick={() => go(number - 1)}>
              Step {number} ·
              {#if t.state === 'ended'}time’s up{:else}{clock(t.left)}{/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    {#if step}
      {#if step.section}<h2 class="section">{step.section}</h2>{/if}
      <span class="big" aria-hidden="true">{step.number}</span>
      <p class="text" data-testid="step-text">{step.text}</p>

      {#each found as t, i (i)}
        {@const timer = timers.get(keyOf(step.number, i))}
        <div class="timer" class:ended={timer?.state === 'ended'} data-testid="timer">
          <span class="when">
            <span class="label">{t.words}</span>
            <span class="clock" role="timer"
              >{#if timer?.state === 'ended'}Time’s up{:else}{clock(
                  timer ? timer.left : t.seconds
                )}{/if}</span
            >
          </span>
          {#if !timer}
            <button
              type="button"
              class="go"
              onclick={() => timers.start(keyOf(step.number, i), t.words, t.seconds)}
              >Start timer<span class="visually-hidden"> for {t.words}</span></button
            >
          {:else if timer.state === 'running'}
            <button type="button" class="go" onclick={() => timers.clear(timer.key)}
              >Stop<span class="visually-hidden"> the timer for {t.words}</span></button
            >
          {:else}
            <button type="button" class="go" onclick={() => timers.clear(timer.key)}
              >Done<span class="visually-hidden"> with the timer for {t.words}</span></button
            >
          {/if}
        </div>
      {/each}
      {#if found.length || elsewhere.length}<p class="quiet">{timerNote}</p>{/if}

      {#if perStep}
        <div class="forstep" data-testid="per-step">
          <p class="forhead">
            <span class="lead">For this step</span>
            <span class="badge"
              ><Icon name="flask" size={14} stroke={2.4} />Experimental · guessed</span
            >
          </p>
          {#if mine.length}
            <ul class="chips">
              {#each mine as line (line.id)}
                <li>
                  {#if amountFor(line)}<b>{amountFor(line)}</b>{SPACE}{/if}{wordsFor(line)}
                </li>
              {/each}
            </ul>
          {:else}
            <p class="quiet">No ingredient guessed for this step.</p>
          {/if}
          <p class="quiet">Wrong? Fix it when you edit the recipe.</p>
        </div>
      {/if}
    {:else}
      <p class="text" data-testid="step-text">This recipe has no steps yet.</p>
    {/if}

    <button type="button" class="show" onclick={() => (sheetOpen = true)}>
      <Icon name="note" size={18} stroke={2.2} />Show ingredients
    </button>

    <section class="options" aria-label="Options">
      <KeepAwake {awake} />
      <div class="row">
        <span class="what" id="{uid}-perstep">
          <span class="flask"><Icon name="flask" size={18} /></span>Ingredients for each step
          <span class="badge small">Experimental</span>
        </span>
        <Switch checked={perStep} labelledby="{uid}-perstep" onchange={onperstep} />
      </div>
    </section>
  </div>

  <footer class:three={last && !!oncooked}>
    {#if last}
      <button
        type="button"
        class="quiet-button"
        disabled={index === 0}
        onclick={() => go(index - 1)}>← Back</button
      >
      <button type="button" class="quiet-button" onclick={leave}
        >{oncooked ? 'Not cooked yet' : 'Close'}</button
      >
      {#if oncooked}
        <button type="button" class="main" onclick={oncooked}>Cooked it</button>
      {/if}
    {:else}
      <button
        type="button"
        class="quiet-button"
        disabled={index === 0}
        onclick={() => go(index - 1)}>← Back</button
      >
      <button type="button" class="main" onclick={() => go(index + 1)}>Next →</button>
    {/if}
  </footer>

  <p class="visually-hidden" role="status">
    {#each ended as t (t.key)}Timer finished: {t.words}.
    {/each}
  </p>
  <p class="visually-hidden" aria-live="polite">{step ? `${progress}. ${step.text}` : ''}</p>
</div>

<dialog
  bind:this={ingredients}
  aria-label="All ingredients"
  oncancel={(event) => {
    event.preventDefault();
    sheetOpen = false;
  }}
  onclick={(event) => {
    if (event.target === ingredients) sheetOpen = false;
  }}
>
  <div class="sheet">
    <span class="handle" aria-hidden="true"></span>
    <div class="sheethead">
      <h2>All ingredients</h2>
      <button type="button" class="done" onclick={() => (sheetOpen = false)}>Done</button>
    </div>
    {#if recipe.lines.length}
      <ul class="all">
        {#each recipe.lines as line (line.id)}
          {#if line.kind === 'heading'}
            <li class="sub"><h3>{line.words}</h3></li>
          {:else}
            <li>
              {#if amountFor(line)}<b>{amountFor(line)}</b>{SPACE}{/if}{wordsFor(
                line
              )}{#if line.note}<span class="note">, {line.note}</span>{/if}
            </li>
          {/if}
        {/each}
      </ul>
    {:else}
      <p class="quiet">Nothing written down yet.</p>
    {/if}
  </div>
</dialog>

<dialog
  bind:this={leaving}
  aria-labelledby="{uid}-leave"
  class="small"
  oncancel={(event) => {
    event.preventDefault();
    stay();
  }}
>
  <div class="sheet">
    <h2 id="{uid}-leave">Stop the timer and leave?</h2>
    <div class="choices">
      <button type="button" class="quiet-button" onclick={stay}>Stay</button>
      <button type="button" class="main" onclick={reallyLeave}>Leave</button>
    </div>
  </div>
</dialog>

<style>
  .cook {
    position: fixed;
    inset: 0;
    z-index: 60;
    display: flex;
    flex-direction: column;
    background: var(--color-surface);
    color: var(--color-text);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: max(var(--space-6), env(safe-area-inset-top)) var(--space-7) var(--space-6);
  }

  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .exit {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    cursor: pointer;
  }

  .who {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 0;
    text-align: center;
  }

  h1 {
    margin: 0;
    max-width: 100%;
    font-size: var(--text-lg);
    font-weight: 800;
    overflow-wrap: anywhere;
  }

  .count {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold, 600);
  }

  .awake {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .spacer {
    visibility: hidden;
  }

  .progress {
    display: flex;
    gap: var(--space-2);
  }

  .progress span {
    flex: 1 1 0;
    min-width: 2px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-fill-strong);
  }

  .progress span.filled {
    background: var(--color-accent);
  }

  footer.three {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 2fr);
  }

  footer.three .quiet-button {
    padding-left: var(--space-3);
    padding-right: var(--space-3);
  }

  /* A narrow screen (a 320 px phone): Back and Not cooked yet share the first row, and Cooked it
     has the row under them, so the words have room and the button grows rather than the text
     shrinking. */
  @media (max-width: 26rem) {
    footer.three {
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }

    footer.three .main {
      grid-column: 1 / -1;
    }
  }

  .body {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    gap: var(--space-8);
    width: 100%;
    max-width: 760px;
    min-height: 0;
    margin: 0 auto;
    padding: var(--space-6) var(--space-9) var(--space-9);
    overflow-x: hidden;
    overflow-y: auto;
    touch-action: pan-y;
  }

  .section {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-lg);
    font-weight: 800;
    letter-spacing: 0.02em;
    overflow-wrap: anywhere;
  }

  .big {
    color: var(--color-accent-soft);
    font-size: 4rem;
    font-weight: 800;
    line-height: 0.9;
    letter-spacing: -0.04em;
  }

  .text {
    margin: 0;
    font-family: var(--font-reading);
    font-size: clamp(1.75rem, 1.2rem + 2vw, 2.5rem);
    font-weight: 500;
    line-height: 1.3;
    overflow-wrap: anywhere;
  }

  .timer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    padding: var(--space-7);
    border-radius: 20px;
    background: var(--color-timer);
    color: var(--color-timer-text);
  }

  .timer .when {
    display: flex;
    flex-direction: column;
  }

  .timer .label {
    color: var(--color-timer-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .timer .clock {
    font-size: 2.125rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
  }

  .go {
    min-height: 48px;
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  .notice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    margin: 0;
    padding: var(--space-2) var(--space-2) var(--space-2) var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .notice button {
    flex: none;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .elsewhere {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .elsewhere button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-timer);
    color: var(--color-timer-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .forstep {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-ground);
  }

  .forhead {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    margin: 0;
  }

  .lead {
    font-size: var(--text-md);
    font-weight: 800;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-experimental-bg);
    color: var(--color-experimental-text);
    font-size: var(--text-sm);
    font-weight: 800;
  }

  .flask {
    display: inline-flex;
    color: var(--color-experimental);
  }

  .badge.small {
    padding: 2px var(--space-4);
    font-size: var(--text-xs);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chips li {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    font-size: var(--text-xl);
  }

  .show {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-4);
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: 0 14px;
    border-radius: var(--radius-lg);
    background: var(--color-ground);
  }

  .what {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  footer {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
    gap: var(--space-5);
    padding: var(--space-6) var(--space-7) max(var(--space-9), env(safe-area-inset-bottom));
    border-top: 1px solid var(--color-border);
  }

  .main,
  .quiet-button {
    min-height: 64px;
    padding: 0 var(--space-6);
    border: none;
    border-radius: 18px;
    font-size: 1.0625rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .main {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .quiet-button {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .quiet-button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  button:focus-visible {
    outline: 3px solid var(--color-accent);
    outline-offset: 2px;
  }

  .timer.ended {
    outline: 3px solid var(--color-timer-muted);
  }

  .elsewhere button.over {
    outline: 2px solid var(--color-timer-muted);
  }

  dialog {
    max-width: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5) var(--space-8) var(--space-9);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .sheethead {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .sheethead h2,
  dialog.small h2 {
    margin: 0;
    font-size: var(--text-2xl);
    font-weight: 800;
  }

  .done {
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

  .all {
    margin: 0;
    padding: 0;
    list-style: none;
    overflow-y: auto;
  }

  .all li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    min-height: 46px;
    padding: var(--space-4) 0;
    border-top: 1px solid var(--color-border);
    font-size: var(--text-xl);
  }

  .all b {
    margin-right: 0.25em;
  }

  .all .sub {
    border-top: 1px solid var(--color-border);
  }

  .all h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-lg);
    font-weight: 800;
  }

  .note {
    color: var(--color-text-muted);
  }

  .choices {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-5);
    margin-top: var(--space-4);
  }

  dialog.small {
    width: min(420px, calc(100vw - 2 * var(--space-7)));
    margin: auto;
    border-radius: var(--radius-panel);
  }

  /* On a phone the ingredients slide up from the bottom, as a sheet. */
  dialog:not(.small) {
    inset: auto 0 0 0;
    width: 100%;
    max-height: 85dvh;
    margin: 0;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
  }

  @media (min-width: 768px) {
    dialog:not(.small) {
      inset: 0;
      width: min(560px, calc(100vw - 2 * var(--space-7)));
      margin: auto;
      border-radius: var(--radius-panel);
    }
  }

  @media (min-width: 768px) {
    .body {
      padding-top: var(--space-9);
    }
  }
</style>
