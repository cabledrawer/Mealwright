<script lang="ts">
  // Cook mode (mockups CookMode-Phone/Desktop and the Dark- ones, Experimental07; spec section 6,
  // "Cook mode", "Cook mode timers", "Cook mode ingredients" and "Cook mode (K4)", cabledrawer 17, 28
  // and 31 Oct): big text, one step at a time, Back and Next (the arrow keys and a swipe do the
  // same), "Show ingredients" always, timers found in the step's words, Keep screen awake, and
  // per-step ingredients as an Experimental option. The last step ends with Back and Cooked it (Back alone where no meal is planned); the cross at the top leaves.
  // A heading in the method is a section title, never a step. All the words here are proposed,
  // for cabledrawer, unless the spec gives them.
  import { tick, untrack } from 'svelte';
  import type { Recipe } from '#lib/client/recipes.js';
  import type { AheadView } from '#lib/cookAhead.js';
  import { clock, cookSteps, findTimers, stepLines } from '#lib/cookSteps.js';
  import type { CookTimers } from '#lib/cookTimers.svelte.js';
  import { lineAmount } from '#lib/recipeAmounts.js';
  import { waitLength, waitName } from '#lib/timeWords.js';
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
    settling = false,
    notice = null,
    problem = null,
    way = null,
    ahead = null,
    onbegun = null
  }: {
    recipe: Recipe;
    timers: CookTimers;
    awake: ScreenAwake;
    /** Whether per-step ingredients (Experimental) are on, and the household's way to change it. */
    perStep: boolean;
    onperstep: (on: boolean) => void;
    /** Leave Cook mode (the cross, Escape, or the page leaving). Asked first when a timer is running. */
    onexit: () => void;
    /** "Cooked it": into the review. Not there when nothing has been planned to cook. */
    oncooked?: (() => void) | null;
    /** The plan is still loading, so whether Cooked it is there isn't known yet: the last step's
     * Cooked it keeps its place but shows nothing (no flicker). */
    settling?: boolean;
    /** Where Cook now planned the recipe, with its Undo (the toast would be under this screen). */
    notice?: { text: string; undo?: () => void } | null;
    /** One short line, e.g. when the per-step switch went back. */
    problem?: string | null;
    /** The way of cooking it picked, for a recipe with two (M2): shown on the first step, where it
     *  can be switched. */
    way?: { name: string; onswitch: () => void } | null;
    /** The recipe's long wait in the planned meal (M3): where it is, and how it went. When it was
     *  begun, Cook mode opens after it. */
    ahead?: AheadView | null;
    /** Cook mode moved past the step that waits for the first time: the wait is begun (M3). */
    onbegun?: (() => void) | null;
  } = $props();

  const uid = $props.id();
  const steps = $derived(cookSteps(recipe.steps));
  let at = $state(0);
  /** The person moved on their own: the step that Cook mode opened at is not forced again. */
  let moved = false;
  let reported = false;
  // Opened on day two: the steps up to the one that waited are done (M3). The plan may arrive
  // after Cook mode opens, so this runs when it does, until the person has moved themselves.
  $effect(() => {
    if (ahead?.begun && !moved && steps.length) {
      at = Math.min(ahead.index + 1, steps.length - 1);
    }
  });
  const index = $derived(Math.min(at, Math.max(steps.length - 1, 0)));
  const step = $derived(steps[index] ?? null);
  /** The step after this one, for the quiet NEXT line (M2, cabledrawer 9 Nov). */
  const next = $derived(steps[index + 1] ?? null);
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

  /** Go to a step. A press (Back, Next, a key) while a swipe is still sliding is ignored: the
   *  slide ends on the step it was heading for, and the press would only be overridden. */
  function go(to: number, fromSlide = false) {
    if (steps.length === 0 || (busy && !fromSlide)) return;
    moved = true;
    const was = at;
    at = Math.min(Math.max(to, 0), steps.length - 1);
    // Past the step that waits, for the first time: the wait is begun (M3).
    if (ahead && !ahead.begun && !reported && onbegun && was <= ahead.index && at > ahead.index) {
      reported = true;
      onbegun();
    }
    void tick().then(() => body?.scrollTo({ top: 0 }));
  }

  /** The cross or Escape: straight out, or asks first when a timer is running. */
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
  // the same (cabledrawer 21 Oct: every swipe has a visible button). The step follows the finger,
  // slides out and the next slides in; a swipe that doesn't go far enough springs back, and one
  // at the first or last step does too (F145, cabledrawer 6 Nov). With "reduce motion" on, nothing
  // slides: the step just changes. Mostly sideways, and far enough that a tap or a scroll is
  // never read as one.
  const SWIPE_FAR = 60;
  const LOOK = 10;
  let down: { x: number; y: number; id: number; sideways: boolean | null } | null = null;
  /** How far the step is moved from the middle, in px; 0 when at rest. */
  let drag = $state(0);
  /** The step is moving by itself (sliding out or in, or springing back). */
  let sliding = $state(false);
  let busy = $state(false);
  let captured = false;
  let slide: HTMLElement | undefined;

  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function pointerdown(event: PointerEvent) {
    if (busy || (event.target as HTMLElement).closest('button, a, input, [role="switch"]')) return;
    down = { x: event.clientX, y: event.clientY, id: event.pointerId, sideways: null };
  }

  function pointermove(event: PointerEvent) {
    if (!down || down.id !== event.pointerId) return;
    const dx = event.clientX - down.x;
    const dy = event.clientY - down.y;
    if (down.sideways === null) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < LOOK) return;
      down.sideways = Math.abs(dx) >= Math.abs(dy) * 1.5;
    }
    if (!down.sideways || reducedMotion()) return;
    // Held by the step, so a mouse released outside it still ends the drag (pointerup comes here).
    if (!captured) {
      captured = true;
      try {
        (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      } catch {
        // a pointer that is already gone: the lift or cancel below still ends the drag
      }
    }
    sliding = false;
    // Where there is no step to go to, the step gives a little and no more.
    const to = index + (dx < 0 ? 1 : -1);
    drag = to < 0 || to >= steps.length ? dx / 4 : dx;
  }

  function pointercancel() {
    down = null;
    captured = false;
    if (drag && !busy) void springBack();
  }

  function pointerup(event: PointerEvent) {
    const start = down;
    down = null;
    captured = false;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    const to = index + (dx < 0 ? 1 : -1);
    const far = Math.abs(dx) >= SWIPE_FAR && Math.abs(dx) >= Math.abs(dy) * 1.5;
    if (!far || to < 0 || to >= steps.length) {
      if (drag) void springBack();
      return;
    }
    if (reducedMotion()) {
      drag = 0;
      go(to);
      return;
    }
    void slideTo(to, dx < 0 ? -1 : 1);
  }

  /** Resolves when the step has finished moving (or soon after, where nothing moves). */
  function arrived(): Promise<void> {
    return new Promise((resolve) => {
      const done = () => {
        slide?.removeEventListener('transitionend', done);
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(done, 400);
      slide?.addEventListener('transitionend', done);
    });
  }

  async function springBack() {
    if (reducedMotion()) {
      drag = 0;
      return;
    }
    busy = true;
    sliding = true;
    drag = 0;
    await arrived();
    sliding = false;
    busy = false;
  }

  /** Slide the step out the way the finger went (`way` -1: left), change step, slide the next in. */
  async function slideTo(to: number, way: 1 | -1) {
    busy = true;
    const width = slide?.offsetWidth ?? window.innerWidth;
    sliding = true;
    drag = way * width;
    await arrived();
    sliding = false;
    go(to, true);
    drag = -way * width;
    await tick();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    sliding = true;
    drag = 0;
    await arrived();
    sliding = false;
    busy = false;
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
  const progress = $derived(
    steps.length
      ? `${ahead?.begun && ahead.day ? `Day ${ahead.day} · Step` : 'Step'} ${index + 1} of ${steps.length}`
      : 'No steps'
  );
  /** The folded steps and how long it waited, on the step after the one that waited (M3). */
  const folded = $derived(ahead?.begun && index === ahead.index + 1 ? ahead : null);
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
        {#if way && index === 0}
          <button type="button" class="way" onclick={way.onswitch}>{way.name} · switch</button>
        {:else if way}
          <p class="count" data-testid="way-name">{way.name}</p>
        {/if}
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
    {#if awake.refused}
      <p class="asleep" role="status" data-testid="cook-asleep">
        <Icon name="dark" size={18} stroke={2.2} />Couldn’t keep the screen awake.
      </p>
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
    onpointermove={pointermove}
    onpointerup={pointerup}
    onpointercancel={pointercancel}
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

    <div
      class="slide"
      bind:this={slide}
      class:sliding
      style:transform={drag ? `translateX(${drag}px)` : undefined}
      data-testid="slide"
      data-moving={busy}
    >
      {#if step}
        {#if folded}
          <div class="folded" data-testid="folded-steps">
            <span class="folded-title">{folded.range} · {folded.title}</span>
            {#if folded.done}<span class="folded-done">{folded.done}</span>{/if}
          </div>
          {#if folded.waited}
            <div class="waited" data-testid="waited">
              <span class="waited-chip" class:short={!folded.enough}>{folded.waited}</span>
              <span class="waited-needed">{folded.needed}</span>
            </div>
          {/if}
        {/if}
        {#if step.section}<h2 class="section">{step.section}</h2>{/if}
        <span class="big" aria-hidden="true">{step.number}</span>
        <p class="text" data-testid="step-text">{step.text}</p>
        {#if ahead && !ahead.begun && index === ahead.index}
          <p class="ahead-note" data-testid="ahead-note">
            Then it waits ({ahead.needed.replace('needed ', '')}). Cook mode picks up after this step
            when you come back.
          </p>
        {/if}

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
      {:else}
        <p class="text" data-testid="step-text">This recipe has no steps yet.</p>
      {/if}
      {#if next}
        <div class="next" data-testid="next-step">
          <span class="next-label">NEXT</span>
          <span class="next-text">{next.text}</span>
          {#if next.wait}
            <span class="next-wait">{waitName(next.wait.kind)} · {waitLength(next.wait)}</span>
          {/if}
        </div>
      {/if}
    </div>

    <section class="perstep" aria-label="Ingredients for each step">
      <div class="head">
        <span class="what" id="{uid}-perstep">
          <span class="label">Ingredients for each step</span>
          <span class="badge"><Icon name="flask" size={13} stroke={2.4} />Experimental</span>
        </span>
        <Switch checked={perStep} large labelledby="{uid}-perstep" onchange={onperstep} />
      </div>
      {#if perStep}
        <div class="guess" data-testid="per-step">
          {#if mine.length}
            <ul class="chips">
              {#each mine as line (line.id)}
                <li>
                  {#if amountFor(line)}<b>{amountFor(line)}</b>{SPACE}{/if}{wordsFor(line)}
                </li>
              {/each}
            </ul>
          {:else}
            <p class="note">No ingredient guessed for this step.</p>
          {/if}
          <p class="note">
            Guessed from the step, so it may be wrong. Fix it when you edit the recipe.
          </p>
        </div>
      {/if}
    </section>

    <button type="button" class="show" onclick={() => (sheetOpen = true)}>
      <Icon name="note" size={18} stroke={2.2} />Show ingredients
    </button>

    <section class="options" aria-label="Options">
      <KeepAwake {awake} />
    </section>
  </div>

  <footer>
    {#if last}
      <button
        type="button"
        class="quiet-button"
        disabled={index === 0}
        onclick={() => go(index - 1)}>← Back</button
      >
      {#if oncooked}
        <button type="button" class="main" onclick={oncooked}>Cooked it</button>
      {:else if settling}
        <!-- Keeps Cooked it's place until the plan says whether it is there (no flicker). -->
        <span class="main waiting" aria-hidden="true">Cooked it</span>
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

  .slide {
    /* A mouse drag across the words would select them and start dragging them (and cancel the
       swipe); the step is for reading and swiping. */
    user-select: none;
    -webkit-user-select: none;
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  .slide.sliding {
    transition: transform 200ms ease-out;
  }

  @media (prefers-reduced-motion: reduce) {
    .slide.sliding {
      transition: none;
    }
  }

  .asleep {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    margin: 0;
    padding: 10px 12px;
    border-radius: 14px;
    background: var(--color-timer);
    color: var(--color-timer-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.35;
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

  /* The "Ingredients for each step" box (mockup Dark-CookStep08-Phone, F148): the label on its
     own line, the Experimental badge under it, the switch centred against both; the guesses
     under a thin divider. */
  .perstep {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-7);
    border: 1px solid var(--color-border);
    border-radius: 18px;
    background: var(--color-ground);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
  }

  .what {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    min-width: 0;
  }

  .label {
    font-size: 0.9375rem;
    font-weight: var(--weight-bold);
    line-height: 1.3;
  }

  .guess {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding-top: var(--space-5);
    border-top: 1px solid var(--color-border);
  }

  .note {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
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

  .waiting {
    visibility: hidden;
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

  .folded {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: 44px;
    margin-bottom: var(--space-4);
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-lg);
    background: var(--color-fill);
  }

  .folded-title {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .folded-done {
    color: var(--color-accent-on-soft, var(--color-text));
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .waited {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    margin-bottom: var(--space-6);
  }

  .waited-chip {
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }

  .waited-chip.short {
    outline: 2px solid var(--color-warning-text);
  }

  .waited-needed {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .ahead-note {
    margin: var(--space-6) 0 0;
    color: var(--color-wait-text);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  .next {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: var(--space-8);
    padding-top: var(--space-5);
    border-top: 1px solid var(--color-border);
  }

  .next-label {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.05em;
  }

  .next-text {
    color: var(--color-text-soft);
    font-size: var(--text-lg);
    line-height: 1.45;
  }

  .next-wait {
    width: fit-content;
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
  }

  .way {
    width: fit-content;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }
</style>
