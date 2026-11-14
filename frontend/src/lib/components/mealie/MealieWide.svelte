<script lang="ts">
  // Import from Mealie on a computer (mockup Dark-MealieImport095-Desktop): the four steps,
  // a drop zone, and on the preview a table of every recipe in the file with tick boxes to
  // leave some out, chips and a search (cabledrawer 13 Nov). Fetched the first time it's needed.
  import { resolve } from '$app/paths';
  import Icon from '../Icon.svelte';
  import Switch from '../Switch.svelte';
  import type { MealieFlow, Step } from '#lib/mealieFlow.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { ADMINS_ONLY } from '#lib/yourDataWords.js';
  import {
    LEAD_WIDE,
    NOTE_FAILED,
    NOTE_FAILED_LINE,
    READS_ONLY,
    RUNS_ON_SERVER_WIDE,
    STEPS,
    UNDONE,
    UNREAD_LEAD,
    bringInWords,
    broughtIn,
    fileWords,
    fromFileWords,
    linesWords,
    moreWords,
    notBroughtIn,
    tooManyIngredientsWords,
    photosWords,
    recipesWords,
    saveAllWords,
    showingWords,
    undoWords,
    undoneWords,
    unreadWords
  } from '#lib/mealieWords.js';

  let { flow }: { flow: MealieFlow } = $props();

  /** Rows the table shows at first, and each "Show more" adds (proposed, for cabledrawer). */
  const PAGE = 100;

  let picker = $state<HTMLInputElement | null>(null);
  let dragging = $state(false);
  let show = $state<'all' | 'new' | 'already'>('all');
  let search = $state('');
  let limit = $state(PAGE);

  function picked(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) void flow.send(file);
  }

  function dropped(event: DragEvent) {
    event.preventDefault();
    dragging = false;
    const file = event.dataTransfer?.files?.[0];
    if (file && flow.admin && !flow.busy && !network.offline) void flow.send(file);
  }

  /** Lower case, no accents: "Pâté" finds "pate" (as Recipes' own search). */
  const fold = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();

  const job = $derived(flow.job);
  const preview = $derived(job?.preview);
  const recipes = $derived(preview?.recipes ?? []);
  const found = $derived.by(() => {
    const words = fold(search.trim());
    return recipes.filter(
      (r) =>
        (show === 'all' || (show === 'new') !== r.already) &&
        (!words || fold(r.name).includes(words))
    );
  });
  const shown = $derived(found.slice(0, limit));
  const leftOut = $derived(preview ? notBroughtIn(preview.left_out) : null);
  const tooMany = $derived(preview ? tooManyIngredientsWords(preview) : null);
  const share = $derived(job && job.total ? Math.round((job.done / job.total) * 100) : 0);
  const offline = $derived(network.offline);
  const at: Record<Step, number> = { start: 0, preview: 1, running: 2, done: 3 };
</script>

<input
  bind:this={picker}
  class="file-input"
  type="file"
  accept=".zip,application/zip"
  tabindex="-1"
  aria-hidden="true"
  onchange={picked}
/>

{#snippet problem()}
  {#if flow.problem}<p class="problem" role="alert">{flow.problem}</p>{/if}
{/snippet}

<div class="wide">
  <ol class="steps" aria-label="Steps">
    {#each STEPS as step, i (step)}
      {#if i}<li class="sep" aria-hidden="true">›</li>{/if}
      <li class:on={at[flow.step] === i} aria-current={at[flow.step] === i ? 'step' : undefined}>
        {step}
      </li>
    {/each}
  </ol>

  {#if flow.step === 'start'}
    {#if flow.undone}
      <div class="ok" role="status">
        <Icon name="check" size={20} stroke={2.4} />
        <span><strong>{UNDONE}</strong> · {undoneWords(flow.undone)}</span>
      </div>
    {/if}
    <section class="dcard">
      <h2>Import from Mealie</h2>
      <p class="sub">{LEAD_WIDE}</p>
      {#if flow.admin}
        <div
          class="drop"
          class:dragging
          role="group"
          aria-label="Drop the Mealie backup here"
          ondragover={(event) => {
            event.preventDefault();
            dragging = true;
          }}
          ondragleave={() => (dragging = false)}
          ondrop={dropped}
        >
          <strong>Drop the Mealie backup (.zip) here</strong>
          <span class="sub">or</span>
          <button
            type="button"
            class="btn"
            disabled={flow.busy || offline}
            onclick={() => picker?.click()}
            >{flow.sending ? 'Reading the file…' : 'Choose file…'}</button
          >
        </div>
      {:else}
        <p class="sub" data-testid="mealie-admins-only">{ADMINS_ONLY}</p>
      {/if}
      {@render problem()}
      <div class="two">
        <div>
          <strong>Getting the file from Mealie</strong>
          <span class="sub"
            >In Mealie: Settings › Admin Settings › Backups › Create Backup, then download it. You
            get one .zip file.</span
          >
        </div>
        <div>
          <strong>What comes across</strong>
          <span class="sub"
            >Recipes (steps, ingredients, nutrition, tags, photos) and ingredients. Not meal plans,
            shopping lists, users or cookbooks.</span
          >
        </div>
      </div>
      <div class="info">
        <Icon name="info" size={18} stroke={2} />
        <span>{READS_ONLY}</span>
      </div>
    </section>
  {:else if flow.step === 'preview' && job && preview}
    <section class="dcard">
      <div class="head">
        <h2>{job.file_name} <span class="sub light">· {fileWords(job)}</span></h2>
        {#if flow.admin}
          <button
            type="button"
            class="btn2"
            disabled={flow.busy || offline}
            onclick={() => picker?.click()}
            >{flow.sending ? 'Reading the file…' : 'Choose another file'}</button
          >
        {/if}
      </div>
      <div class="stats four">
        <div class="stat">
          <span class="num">{preview.new}</span><span
            >new recipes, {preview.with_photo} with a photo</span
          >
        </div>
        <div class="stat">
          <span class="num dim">{preview.already}</span><span>you already have: left out</span>
        </div>
        <div class="stat">
          <span class="num">{preview.foods_matching}</span><span>ingredients you already have</span>
        </div>
        <div class="stat">
          <span class="num">{preview.foods_new}</span><span
            >new ingredients, marked “from Mealie”</span
          >
        </div>
      </div>
      <div class="filters">
        <div class="chips" role="group" aria-label="Show">
          <button
            type="button"
            class="chip"
            aria-pressed={show === 'all'}
            onclick={() => ((show = 'all'), (limit = PAGE))}>All {recipes.length}</button
          >
          <button
            type="button"
            class="chip"
            aria-pressed={show === 'new'}
            onclick={() => ((show = 'new'), (limit = PAGE))}>New {preview.new}</button
          >
          <button
            type="button"
            class="chip"
            aria-pressed={show === 'already'}
            onclick={() => ((show = 'already'), (limit = PAGE))}
            >Already here {preview.already}</button
          >
        </div>
        <input
          type="search"
          class="search"
          placeholder="Find a recipe"
          aria-label="Find a recipe"
          bind:value={search}
          oninput={() => (limit = PAGE)}
        />
      </div>
      <table>
        <thead>
          <tr>
            <th scope="col" class="tick"><span class="sr">Bring in</span></th>
            <th scope="col">Recipe</th>
            <th scope="col">Mealie tags</th>
            <th scope="col">Photo</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as recipe (recipe.key)}
            <tr>
              <td class="tick">
                <!-- The whole cell is the target, 44 px (round 1, review 3). -->
                <label class="hit">
                  <input
                    type="checkbox"
                    aria-label="Bring in {recipe.name}"
                    checked={!recipe.already && !flow.leaveOut.has(recipe.key)}
                    disabled={recipe.already || flow.busy || !flow.admin}
                    onchange={(event) => flow.toggle(recipe.key, event.currentTarget.checked)}
                  />
                </label>
              </td>
              <th scope="row" class:dim={recipe.already}>{recipe.name}</th>
              <td class="dim">{recipe.tags.join(', ')}</td>
              <td class="dim">{recipe.photo ? 'Yes' : 'No'}</td>
              <td>
                {#if recipe.already}<span class="dim">You already have it</span>{:else}New{/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <div class="showing">
        <span class="sub">{showingWords(shown.length, found.length)}</span>
        {#if shown.length < found.length}
          <button type="button" class="btn2" onclick={() => (limit += PAGE)}>Show more</button>
        {/if}
      </div>
      {#if preview.with_photo}
        <div class="row">
          <span class="lbl"
            ><span id="mealie-photos-wide">Bring in photos</span><small
              >{photosWords(preview)}</small
            ></span
          >
          <Switch
            bind:checked={flow.photos}
            labelledby="mealie-photos-wide"
            disabled={!flow.admin}
          />
        </div>
      {/if}
      {#if tooMany}<p class="sub" data-testid="mealie-too-many">{tooMany}</p>{/if}
      {#if leftOut}<p class="sub">{leftOut}</p>{/if}
      {@render problem()}
      {#if flow.admin}
        <div class="buttons">
          <button
            type="button"
            class="btn2"
            disabled={flow.busy || offline}
            onclick={() => void flow.cancel()}>Cancel</button
          >
          <button
            type="button"
            class="btn"
            disabled={flow.busy || offline || flow.chosen === 0}
            onclick={() => void flow.start()}>{bringInWords(flow.chosen)}</button
          >
        </div>
      {:else}
        <p class="sub" data-testid="mealie-admins-only">{ADMINS_ONLY}</p>
      {/if}
    </section>
  {:else if flow.step === 'running' && job}
    <section class="dcard">
      <h2>Bringing in recipes… {job.done} of {job.total}</h2>
      <div
        class="bar"
        role="progressbar"
        aria-label="Recipes brought in"
        aria-valuemin={0}
        aria-valuemax={job.total}
        aria-valuenow={job.done}
      >
        <span style:width="{share}%"></span>
      </div>
      <div class="stats three">
        <div class="stat"><span class="num">{job.counts.saved}</span><span>ready</span></div>
        <div class="stat">
          <span class="num need">{job.counts.drafts}</span><span>with lines to check</span>
        </div>
        <div class="stat">
          <span class="num dim">{Math.max(0, job.total - job.done)}</span><span>still to go</span>
        </div>
      </div>
      <div class="info">
        <Icon name="info" size={18} stroke={2} />
        <span>{RUNS_ON_SERVER_WIDE}</span>
      </div>
      {@render problem()}
    </section>
  {:else if flow.step === 'done' && job}
    {#if job.state === 'failed'}
      <div class="warn" role="status">
        <Icon name="alert" size={20} stroke={2.2} />
        <span><strong>{NOTE_FAILED}</strong> · {NOTE_FAILED_LINE}</span>
      </div>
    {:else}
      <div class="ok" role="status">
        <Icon name="check" size={20} stroke={2.4} />
        <span
          ><strong>{recipesWords(broughtIn(job))} brought in</strong>
          {fromFileWords(job).replace(/^From/, 'from')}.</span
        >
      </div>
    {/if}
    <div class="stats four">
      <a class="stat" href={resolve('/(app)/recipes')}>
        <span class="num">{job.counts.saved}</span><span>ready to cook, in Recipes</span>
      </a>
      <a
        class="stat"
        class:needs={job.counts.drafts}
        href="{resolve('/(app)/recipes/drafts')}?from=mealie"
      >
        <span class="num" class:need={job.counts.drafts}>{job.counts.drafts}</span><span
          >have lines to check, in Drafts</span
        >
      </a>
      <a class="stat" href={resolve('/(app)/recipes/ingredients')}>
        <span class="num">{job.counts.new_foods}</span><span>new ingredients</span>
      </a>
      <div class="stat">
        <span class="num dim">{job.counts.already}</span><span>left out, already here</span>
      </div>
    </div>
    {#if job.counts.drafts}
      <section class="dcard">
        <div class="head">
          <h2>{recipesWords(job.counts.drafts)} to check</h2>
          {#if flow.admin}
            <button
              type="button"
              class="btn2"
              disabled={flow.busy || offline}
              onclick={() => void flow.saveAll()}>{saveAllWords()}</button
            >
          {/if}
        </div>
        <p class="sub">{UNREAD_LEAD}</p>
        <table>
          <thead>
            <tr>
              <th scope="col">Recipe</th>
              <th scope="col">Lines it couldn’t read</th>
              <th scope="col"><span class="sr">How many</span></th>
              <th scope="col"><span class="sr">Check</span></th>
            </tr>
          </thead>
          <tbody>
            {#each job.to_check as result (result.key)}
              <tr>
                <th scope="row">{result.name}</th>
                <td class="dim">{unreadWords(result.unread, result.unread_count, true)}</td>
                <td><span class="need small">{linesWords(result.unread_count)}</span></td>
                <td class="end">
                  {#if result.draft_id}
                    <a
                      class="btn2"
                      href={resolve('/(app)/recipes/drafts/[id]', { id: String(result.draft_id) })}
                      aria-label="Check {result.name}">Check</a
                    >
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
        {#if job.counts.drafts > job.to_check.length}
          <span class="sub">{moreWords(job.counts.drafts - job.to_check.length)}</span>
        {/if}
      </section>
    {/if}
    {#if flow.admin}
      <section class="dcard">
        <div class="row">
          <span class="lbl">Undo this import<small>{undoWords(job)}</small></span>
          <button
            type="button"
            class="btn2"
            disabled={flow.busy || offline}
            onclick={() => void flow.undo()}>Undo</button
          >
        </div>
      </section>
    {/if}
    {@render problem()}
    {#if flow.admin}
      <button type="button" class="link" onclick={() => flow.another()}>Import another file</button>
    {/if}
  {/if}
</div>

<style>
  .wide {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
    max-width: 900px;
  }

  .file-input {
    display: none;
  }

  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .steps {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    margin: 0;
    padding: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    list-style: none;
  }

  .steps .on {
    color: var(--color-accent);
  }

  .dcard {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px 22px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  h2 {
    flex: 1;
    margin: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .light {
    font-weight: var(--weight-medium);
  }

  .dim {
    color: var(--color-text-muted);
  }

  .need {
    color: var(--color-warning-text);
  }

  .small {
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .head {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .drop {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 36px 24px;
    border: 2px dashed var(--color-border-strong);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
    text-align: center;
  }

  .drop strong {
    font-size: 17px;
  }

  .drop.dragging {
    border-color: var(--color-accent);
  }

  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  }

  .two > div {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .two strong {
    font-size: var(--text-base);
  }

  .info,
  .ok,
  .warn {
    display: flex;
    align-items: flex-start;
    gap: var(--space-5);
    padding: var(--space-5) 12px;
    border-radius: var(--radius-lg);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .info :global(svg),
  .ok :global(svg),
  .warn :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  .info {
    border: 1px solid var(--color-info-muted);
    background: var(--color-info);
    color: var(--color-info-text);
  }

  .ok {
    border: 1px solid var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: 15px;
  }

  .warn {
    border: 1px solid var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: 15px;
  }

  .stats {
    display: grid;
    gap: 12px;
  }

  .four {
    grid-template-columns: repeat(4, 1fr);
  }

  .three {
    grid-template-columns: repeat(3, 1fr);
  }

  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 12px 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-ground);
    color: inherit;
    text-decoration: none;
  }

  .stat.needs {
    border-color: var(--color-warning-border);
  }

  .stat span:not(.num) {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  .num {
    font-size: 28px;
    font-weight: var(--weight-extrabold);
    letter-spacing: -0.02em;
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 12px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    white-space: nowrap;
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .search {
    width: 220px;
    min-height: var(--touch-target);
    padding: 0 12px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui); /* 16px: iOS zooms in on smaller fields */
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-base);
  }

  th,
  td {
    padding: 10px 8px;
    border-bottom: 1px solid var(--color-border);
    text-align: left;
    vertical-align: middle;
  }

  thead th {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  tbody th {
    font-weight: var(--weight-bold);
  }

  .tick {
    width: var(--touch-target);
  }

  td.tick {
    padding: 0;
  }

  .hit {
    display: grid;
    place-items: center;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    cursor: pointer;
  }

  .tick input {
    width: 18px;
    height: 18px;
    accent-color: var(--color-accent);
  }

  .end {
    text-align: right;
  }

  .showing {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--color-border);
  }

  .dcard > .row:first-child {
    padding-top: 0;
    border-top: none;
  }

  .lbl {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    font-weight: var(--weight-semibold);
  }

  .lbl small {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
    line-height: 1.4;
  }

  .bar {
    height: 10px;
    overflow: hidden;
    border-radius: 5px;
    background: var(--color-fill-strong);
  }

  .bar span {
    display: block;
    height: 100%;
    border-radius: 5px;
    background: var(--color-accent);
    transition: width 0.4s ease;
  }

  .buttons {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
  }

  .btn,
  .btn2 {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    min-height: var(--touch-target);
    padding: 0 16px;
    border-radius: var(--radius-full);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    text-decoration: none;
    white-space: nowrap;
    cursor: pointer;
  }

  .btn {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .btn2 {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .link {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .problem {
    color: var(--color-danger-text);
    font-size: var(--text-md);
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }
</style>
