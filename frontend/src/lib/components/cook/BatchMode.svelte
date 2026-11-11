<script lang="ts">
  // Batch cook mode (mockup Dark-BatchSession08; spec section 6, "Batch cook (Experimental)";
  // cabledrawer 11 Nov): Cook mode for a whole session. Big text, the one hands-on task for now, a
  // timer for each recipe, what is in use, the quiet next line, Show ingredients and Done, next.
  // Where the schedule comes from and how it carries on is in `batchMode.svelte.ts`. The words the
  // mockup shows are as drawn; the others are proposed, for cabledrawer.
  import { getRecipe, type Recipe } from '#lib/client/recipes.js';
  import type { BatchModeModel } from '#lib/batchMode.svelte.js';
  import {
    inUseWords,
    lacksWords,
    nextWords,
    optionalWords,
    progressWords,
    sharedWords,
    startsWords,
    tagWords
  } from '#lib/batchModeWords.js';
  import { clock } from '#lib/cookSteps.js';
  import { lineAmount } from '#lib/recipeAmounts.js';
  import type { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { linkedWords } from '#lib/recipes/linkedWords.js';
  import Icon from '../Icon.svelte';
  import KeepAwake from '../KeepAwake.svelte';

  let {
    model,
    awake,
    onexit,
    oncooked
  }: {
    model: BatchModeModel;
    awake: ScreenAwake;
    /** The cross: leave (timers are kept on the server, so nothing is lost by leaving). */
    onexit: () => void;
    /** "Cooked it" once every task is done: into the one review for the whole session. */
    oncooked: () => void;
  } = $props();

  const uid = $props.id();
  const schedule = $derived(model.schedule);
  const worked = $derived(model.worked);
  const recipes = $derived(schedule?.recipes ?? []);
  const now = $derived(worked?.now ?? null);
  const next = $derived(worked?.next ?? null);
  const total = $derived(worked?.tasks.length ?? 0);
  const done = $derived(worked?.doneCount ?? 0);
  const waitingOnly = $derived(now === null && !model.finished);
  const lastDone = $derived(
    model.lastDone ? (worked?.tasks.find((t) => t.id === model.lastDone) ?? null) : null
  );

  // Show ingredients: every ingredient of the recipes the task is for, read when first asked.
  let sheet = $state<HTMLDialogElement>();
  let sheetOpen = $state(false);
  let read = $state<Record<number, Recipe>>({});
  let failed = $state(false);
  $effect(() => {
    if (sheet && sheetOpen && !sheet.open) sheet.showModal();
    else if (sheet && !sheetOpen && sheet.open) sheet.close();
  });

  async function showIngredients() {
    sheetOpen = true;
    failed = false;
    const ids = (now ?? next)?.recipe_ids ?? recipes.map((r) => r.recipe_id ?? 0);
    for (const id of ids) {
      if (id && !read[id]) {
        try {
          read[id] = await getRecipe(id);
        } catch {
          failed = true;
        }
      }
    }
  }
  const shownRecipes = $derived(
    ((now ?? next)?.recipe_ids ?? recipes.map((r) => r.recipe_id ?? 0))
      .map((id) => read[id])
      .filter((r): r is Recipe => r !== undefined)
  );

  const nameOf = (id: number) => recipes.find((r) => r.recipe_id === id)?.recipe_name ?? '';

  function press() {
    model.prime(); // from a tap: the only moment a browser lets a page make sound later
    if (now) model.mark('done', now.id);
  }
</script>

<svelte:head><title>Batch cook · Mealwright</title></svelte:head>

<div class="batch" role="region" aria-label="Batch cook mode">
  <header>
    <div class="bar">
      <button type="button" class="exit" aria-label="Leave Batch cook" onclick={onexit}>
        <Icon name="close" size={20} stroke={2.4} />
      </button>
      <div class="who">
        <h1>Batch cook · {recipes.length} {recipes.length === 1 ? 'recipe' : 'recipes'}</h1>
        <p class="count" data-testid="batch-progress">
          {progressWords(done, total, worked?.minutesLeft ?? 0)}
        </p>
      </div>
      {#if awake.on}
        <span class="awake"><Icon name="light" size={14} stroke={2.4} />Awake</span>
      {:else}
        <span class="awake spacer" aria-hidden="true"></span>
      {/if}
    </div>
    <div class="progress" aria-hidden="true">
      <span style:width="{total ? (done / total) * 100 : 0}%"></span>
    </div>
    {#if awake.refused}
      <p class="asleep" role="status">
        <Icon name="dark" size={18} stroke={2.2} />Couldn’t keep the screen awake.
      </p>
    {/if}
    {#if network.offline || model.pending.length}
      <p class="notice" role="status" data-testid="batch-offline">
        {#if model.pending.length}
          Saved on this phone, sent when you’re back online.
        {:else}
          You’re offline. Timers and Done, next keep working.
        {/if}
      </p>
    {/if}
    {#if schedule?.stale}
      <p class="notice" role="status" data-testid="batch-stale">
        <span>A recipe or your kitchen changed since this was planned.</span>
        <button type="button" onclick={() => void model.load(true)}>Plan again</button>
      </p>
    {/if}
    {#if model.problem}<p class="notice problem" role="alert">{model.problem}</p>{/if}
    {#if schedule && schedule.before.length}
      <p class="quiet" data-testid="batch-before">
        The night before: {schedule.before.map((b) => b.text).join(' ')}
      </p>
    {/if}
  </header>

  <div class="body">
    {#if model.loading && !schedule}
      <p class="quiet" aria-busy="true">Loading…</p>
    {:else if !schedule}
      <p class="quiet">{model.problem}</p>
    {:else}
      <section class="now" aria-labelledby="{uid}-now">
        {#if now}
          <div class="line">
            <h2 id="{uid}-now">Now</h2>
            <span class="tag hands">{tagWords(now)}</span>
          </div>
          {#if optionalWords(now)}<span class="opt" data-testid="batch-optional"
              >{optionalWords(now)}</span
            >{/if}
          <p class="text" data-testid="batch-now">{now.title}</p>
          {#if sharedWords(now, recipes)}<p class="quiet">{sharedWords(now, recipes)}</p>{:else}
            <p class="quiet">{now.recipe_ids.map(nameOf).join(' and ')}</p>
          {/if}
          {#if now.lacks}<p class="quiet" data-testid="batch-lacks">{lacksWords(now)}</p>{/if}
        {:else if model.finished}
          <h2 id="{uid}-now">All done</h2>
          <p class="text" data-testid="batch-now">Everything is cooked.</p>
          <p class="quiet">Cooked it takes the ingredients out of the pantry for every recipe.</p>
        {:else}
          <h2 id="{uid}-now">Now</h2>
          <p class="text" data-testid="batch-now">Nothing for your hands right now.</p>
          <p class="quiet">The next timer is below.</p>
        {/if}
      </section>

      <ul class="timers" aria-label="A timer for each recipe">
        {#each model.rows as row (row.recipe.batch_id)}
          <li data-testid="batch-timer" data-kind={row.kind}>
            <span class="rn">
              {row.recipe.recipe_name}
              {#if row.kind === 'running' && row.task}
                <span class="tag wait">{tagWords(row.task)}</span>
              {:else if row.kind === 'ready' && row.task}
                <span class="tag wait">{tagWords(row.task)}</span>
              {:else if row.kind === 'over'}
                <span class="tag wait">Time’s up</span>
              {:else if row.kind === 'later'}
                <span class="quiet">{startsWords(row.inMinutes)}</span>
              {:else}
                <span class="quiet">Done</span>
              {/if}
            </span>
            {#if row.kind === 'running' && row.task}
              <span class="acts">
                <span class="clock" role="timer">{clock(row.left)}</span>
                <button
                  type="button"
                  class="go"
                  onclick={() => {
                    if (row.task) model.mark('done', row.task.id);
                  }}
                  >End timer<span class="visually-hidden">
                    early for {row.recipe.recipe_name}</span
                  ></button
                >
              </span>
            {:else if row.kind === 'ready' && row.task}
              <span class="acts">
                <button
                  type="button"
                  class="go"
                  onclick={() => {
                    model.prime();
                    if (row.task) model.mark('timer', row.task.id);
                  }}
                  >Start timer<span class="visually-hidden">
                    for {row.recipe.recipe_name}</span
                  ></button
                >
                <button
                  type="button"
                  class="go"
                  onclick={() => {
                    if (row.task) model.mark('done', row.task.id);
                  }}
                  >Skip wait<span class="visually-hidden">
                    for {row.recipe.recipe_name}</span
                  ></button
                >
              </span>
            {:else}
              <span class="quiet">—</span>
            {/if}
          </li>
        {/each}
      </ul>

      <p class="quiet" data-testid="batch-in-use">
        {inUseWords(worked?.inUse ?? { hob: 0, pressure: 0, oven: 0 }, schedule.kitchen)}
      </p>

      {#if lastDone}
        <p class="notice" role="status" data-testid="batch-undo">
          <span>Done: {lastDone.title}</span>
          <button type="button" onclick={() => model.mark('undo', lastDone.id)}>Undo</button>
        </p>
      {/if}

      {#if next}
        <div class="next" data-testid="batch-next">
          <span class="next-label">NEXT</span>
          <span class="next-text">{nextWords(next, recipes)}</span>
        </div>
      {/if}

      <section class="options" aria-label="Options"><KeepAwake {awake} /></section>
    {/if}
  </div>

  <footer>
    <button type="button" class="quiet-button" onclick={() => void showIngredients()}
      >Show ingredients</button
    >
    {#if model.finished}
      <button type="button" class="main" onclick={oncooked}>Cooked it</button>
    {:else if now}
      <button type="button" class="main" onclick={press}>Done, next →</button>
    {:else}
      <button type="button" class="main" disabled={waitingOnly}>Waiting for a timer</button>
    {/if}
  </footer>

  <p class="visually-hidden" aria-live="polite">
    {#if now}{progressWords(done, total, worked?.minutesLeft ?? 0)}. {now.title}{/if}
  </p>
  <p class="visually-hidden" role="status">
    {#each model.rows.filter((r) => r.over !== null) as r (r.recipe.batch_id)}Timer finished for {r
        .recipe.recipe_name}.
    {/each}
  </p>
</div>

<dialog
  bind:this={sheet}
  aria-label="All ingredients"
  oncancel={(event) => {
    event.preventDefault();
    sheetOpen = false;
  }}
  onclick={(event) => {
    if (event.target === sheet) sheetOpen = false;
  }}
>
  <div class="sheet">
    <span class="handle" aria-hidden="true"></span>
    <div class="sheethead">
      <h2>Ingredients</h2>
      <button type="button" class="done" onclick={() => (sheetOpen = false)}>Done</button>
    </div>
    {#each shownRecipes as recipe (recipe.id)}
      <h3>{recipe.name}</h3>
      <ul class="all">
        {#each recipe.lines.filter((l) => l.kind !== 'heading') as line (line.id)}
          <li>
            {#if lineAmount(line, 1)}<b>{lineAmount(line, 1)}</b>&nbsp;{/if}{linkedWords(
              line.words,
              line.food
            )}
          </li>
        {/each}
      </ul>
    {/each}
    {#if failed}<p class="quiet">Couldn’t read every recipe. Try again when you’re online.</p>{/if}
  </div>
</dialog>

<style>
  .batch {
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
    border-bottom: 1px solid var(--color-border);
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
    font-size: var(--text-md);
    font-weight: 800;
    overflow-wrap: anywhere;
  }

  .count {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .awake {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-width: var(--touch-target);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .awake.spacer {
    visibility: hidden;
  }

  .progress {
    height: 5px;
    border-radius: 3px;
    background: var(--color-border);
  }

  .progress span {
    display: block;
    height: 5px;
    border-radius: 3px;
    background: var(--color-accent);
  }

  .asleep,
  .notice,
  .quiet {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .notice {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-info);
    color: var(--color-info-text);
  }

  .notice.problem {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .notice button {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid currentcolor;
    border-radius: var(--radius-full);
    background: transparent;
    color: inherit;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-6);
    min-height: 0;
    padding: var(--space-6) var(--space-7);
    overflow-y: auto;
  }

  .now {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .line {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  h2 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: 800;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .text {
    margin: 0;
    font-family: var(--font-reading);
    font-size: clamp(1.75rem, 1.2rem + 2vw, 2.5rem);
    font-weight: 500;
    line-height: 1.3;
    overflow-wrap: anywhere;
  }

  .tag {
    display: inline-flex;
    align-items: center;
    align-self: flex-start;
    padding: 3px 9px;
    border-radius: var(--radius-full);
    font-size: var(--text-sm);
    font-weight: 800;
  }

  .tag.hands {
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .tag.wait {
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
  }

  .timers {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: var(--space-2) var(--space-6);
    border-radius: 18px;
    background: var(--color-fill);
    list-style: none;
  }

  .timers li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    min-height: 48px;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--color-border);
  }

  .timers li:last-child {
    border-bottom: none;
  }

  .rn {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  /* "Optional step", as on the recipe page: its own line above the step's words. */
  .opt {
    display: block;
    width: fit-content;
    padding: 2px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-muted);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
  }

  .acts {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-3);
  }

  .clock {
    font-size: 1.25rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
  }

  .go {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .next {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin-top: auto;
    padding-top: var(--space-5);
    border-top: 1px solid var(--color-border);
  }

  .next-label {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: 800;
    letter-spacing: 0.05em;
  }

  .next-text {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
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

  .main:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .quiet-button {
    background: var(--color-fill);
    color: var(--color-text);
  }

  button:focus-visible {
    outline: 3px solid var(--color-accent);
    outline-offset: 2px;
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

  .sheethead h2 {
    color: var(--color-text);
    font-size: var(--text-2xl);
    letter-spacing: 0;
    text-transform: none;
  }

  .done {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  h3 {
    margin: var(--space-4) 0 0;
    font-size: var(--text-md);
  }

  .all {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-lg);
  }

  @media (min-width: 900px) {
    .body,
    header,
    footer {
      width: 100%;
      max-width: 720px;
      margin-inline: auto;
    }
  }
</style>
