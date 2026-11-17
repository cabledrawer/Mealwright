<script lang="ts">
  // Import from Mealie on a phone (mockups Dark-Mealie{Start,Preview,Running,Done}095-Phone):
  // the simple version, with no table (cabledrawer 13 Nov). The words: words.md section 81.
  import { resolve } from '$app/paths';
  import Icon from '../Icon.svelte';
  import Switch from '../Switch.svelte';
  import type { MealieFlow } from '#lib/mealieFlow.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { ADMINS_ONLY } from '#lib/yourDataWords.js';
  import {
    LEAD,
    count,
    MENU_PATH,
    NOTE_FAILED,
    NOTE_FAILED_LINE,
    READS_ONLY,
    RUNS_ON_SERVER,
    UNDONE,
    bringInWords,
    broughtInWords,
    fileWords,
    fromFileWords,
    newIngredientsWords,
    alreadyWords,
    notBroughtIn,
    tooManyIngredientsWords,
    photosWords,
    resultWords,
    undoWords,
    undoneWords
  } from '#lib/mealieWords.js';

  let { flow }: { flow: MealieFlow } = $props();

  let picker = $state<HTMLInputElement | null>(null);
  let seeWhich = $state(false);
  let seeNew = $state(false);

  function picked(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) void flow.send(file);
  }

  const job = $derived(flow.job);
  const preview = $derived(job?.preview);
  const already = $derived(preview?.recipes.filter((r) => r.already) ?? []);
  const newNames = $derived(preview?.foods_new_names ?? []);
  const leftOut = $derived(preview ? notBroughtIn(preview.left_out) : null);
  const tooMany = $derived(preview ? tooManyIngredientsWords(preview) : null);
  const share = $derived(job && job.total ? Math.round((job.done / job.total) * 100) : 0);
  const offline = $derived(network.offline);
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

<div class="mealie">
  {#if flow.step === 'start'}
    {#if flow.undone}
      <div class="ok" role="status">
        <Icon name="check" size={20} stroke={2.4} />
        <span><strong>{UNDONE}</strong><br />{undoneWords(flow.undone)}</span>
      </div>
    {/if}
    <p class="sub">{LEAD}</p>
    <h2>How</h2>
    <ol class="card">
      <li class="step">
        <span class="n" aria-hidden="true">1</span>
        <span class="rn"><b>Make a backup in Mealie</b><span>{MENU_PATH}</span></span>
      </li>
      <li class="step">
        <span class="n" aria-hidden="true">2</span>
        <span class="rn"
          ><b>Download it</b><span>You get one .zip file. Save it on this phone or computer.</span
          ></span
        >
      </li>
      <li class="step">
        <span class="n" aria-hidden="true">3</span>
        <span class="rn"
          ><b>Choose it here</b><span
            >Mealwright reads it and shows you what’s inside before anything is added.</span
          ></span
        >
      </li>
    </ol>
    <h2>What comes across</h2>
    <ul class="card">
      <li class="r">
        <span class="yes"><Icon name="check" size={20} stroke={2.4} /></span>
        <span class="rn"
          ><b>Recipes</b><span>Steps, ingredients, nutrition, tags and photos</span></span
        >
      </li>
      <li class="r">
        <span class="yes"><Icon name="check" size={20} stroke={2.4} /></span>
        <span class="rn"
          ><b>Ingredients</b><span>Matched to your ingredients; new ones are added</span></span
        >
      </li>
      <li class="r">
        <span class="dash" aria-hidden="true"></span>
        <span class="rn"
          ><b>Not brought in</b><span>Meal plans, shopping lists, users and cookbooks</span></span
        >
      </li>
    </ul>
    <div class="note">
      <Icon name="info" size={18} stroke={2} />
      <span>{READS_ONLY}</span>
    </div>
    {@render problem()}
    {#if flow.admin}
      <div class="foot">
        <button
          type="button"
          class="primary"
          disabled={flow.busy || offline}
          onclick={() => picker?.click()}
          >{flow.sending ? 'Reading the file…' : 'Choose the Mealie file (.zip)'}</button
        >
      </div>
    {:else}
      <p class="fine" data-testid="mealie-admins-only">{ADMINS_ONLY}</p>
    {/if}
  {:else if flow.step === 'preview' && job && preview}
    <div class="file">
      <span class="ic"><Icon name="note" size={18} stroke={2.2} /></span>
      <span class="rn"><b>{job.file_name}</b><span>{fileWords(job)}</span></span>
      {#if flow.admin}
        <button
          type="button"
          class="small"
          disabled={flow.busy || offline}
          onclick={() => picker?.click()}>{flow.sending ? 'Reading…' : 'Change'}</button
        >
      {/if}
    </div>
    <h2>In this file</h2>
    <ul class="card">
      <li class="r">
        <span class="num">{count(preview.new)}</span>
        <span class="rn"
          ><b>New recipes</b><span>{count(preview.with_photo)} with a photo</span></span
        >
      </li>
      {#if preview.already}
        <li class="r">
          <span class="num dim">{count(preview.already)}</span>
          <span class="rn"
            ><b>You already have these</b><span>Same name and source: left out</span></span
          >
          {#if already.length}
            <button
              type="button"
              class="link"
              aria-expanded={seeWhich}
              onclick={() => (seeWhich = !seeWhich)}>See which</button
            >
          {/if}
        </li>
        {#if seeWhich}
          <li class="which" aria-label="You already have these">
            {alreadyWords(already.map((r) => r.name))}
          </li>
        {/if}
      {/if}
      <li class="r">
        <span class="num">{count(preview.foods_matching)}</span>
        <span class="rn"
          ><b>Ingredients you already have</b><span>Linked, nothing new added</span></span
        >
      </li>
      <li class="r">
        <span class="num">{count(preview.foods_new)}</span>
        <span class="rn"
          ><b>New ingredients</b><span>Added to Ingredients, marked “from Mealie”</span></span
        >
        {#if newNames.length}
          <button
            type="button"
            class="link"
            aria-expanded={seeNew}
            onclick={() => (seeNew = !seeNew)}>See</button
          >
        {/if}
      </li>
      {#if seeNew && preview}
        <li class="which" aria-label="New ingredients">
          {newIngredientsWords(newNames, preview.foods_new)}
        </li>
      {/if}
    </ul>
    {#if preview.with_photo}
      <div class="card">
        <div class="r">
          <span class="rn"
            ><b id="mealie-photos">Bring in photos</b><span>{photosWords(preview)}</span></span
          >
          <Switch bind:checked={flow.photos} labelledby="mealie-photos" disabled={!flow.admin} />
        </div>
      </div>
    {/if}
    {#if tooMany}<p class="fine" data-testid="mealie-too-many">{tooMany}</p>{/if}
    {#if leftOut}<p class="fine">{leftOut}</p>{/if}
    {@render problem()}
    {#if flow.admin}
      <div class="foot">
        <button
          type="button"
          class="outline"
          disabled={flow.busy || offline}
          onclick={() => void flow.cancel()}>Cancel</button
        >
        <button
          type="button"
          class="primary grow"
          disabled={flow.busy || offline || flow.chosen === 0}
          onclick={() => void flow.start()}>{bringInWords(flow.chosen)}</button
        >
      </div>
    {:else}
      <p class="fine" data-testid="mealie-admins-only">{ADMINS_ONLY}</p>
    {/if}
  {:else if flow.step === 'running' && job}
    <div class="running">
      <span class="big">Bringing in recipes…</span>
      <span class="of">{count(job.done)} of {count(job.total)}</span>
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
    </div>
    {#if job.recent.length}
      <ul class="card" aria-label="Brought in so far">
        {#each job.recent as result (result.key)}
          <li class="r">
            <span class="rn"><b>{result.name}</b><span>{resultWords(result)}</span></span>
            {#if result.state === 'draft'}
              <span class="need">To check</span>
            {:else if result.state === 'saved' || result.state === 'saved_all' || result.state === 'answered'}
              <span class="yes"><Icon name="check" size={20} stroke={2.4} /></span>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
    <div class="note">
      <Icon name="info" size={18} stroke={2} />
      <span>{RUNS_ON_SERVER}</span>
    </div>
    {@render problem()}
    <div class="foot">
      <a class="outline grow" href={resolve('/(app)')}>Leave it running</a>
    </div>
  {:else if flow.step === 'done' && job}
    {#if job.state === 'failed'}
      <div class="warn" role="status">
        <Icon name="alert" size={20} stroke={2.2} />
        <span><strong>{NOTE_FAILED}</strong><br />{NOTE_FAILED_LINE}</span>
      </div>
    {:else}
      <div class="ok" role="status">
        <Icon name="check" size={20} stroke={2.4} />
        <span><strong>{broughtInWords(job)}</strong><br />{fromFileWords(job)}</span>
      </div>
    {/if}
    <div class="card">
      <a class="r to" href={resolve('/(app)/recipes')}>
        <span class="num">{count(job.counts.saved)}</span>
        <span class="rn"
          ><b>Ready to cook</b><span>In Recipes, tagged as they were in Mealie</span></span
        >
      </a>
      {#if job.counts.drafts}
        <a class="r to" href="{resolve('/(app)/recipes/drafts')}?from=mealie">
          <span class="num need-num">{count(job.counts.drafts)}</span>
          <span class="rn"
            ><b>Have lines to check</b><span
              >Mealwright couldn’t read some ingredient lines. They wait in Drafts.</span
            ></span
          >
        </a>
      {/if}
      {#if job.counts.new_foods}
        <a class="r to" href={resolve('/(app)/recipes/ingredients')}>
          <span class="num">{count(job.counts.new_foods)}</span>
          <span class="rn"
            ><b>New ingredients</b><span>In Ingredients, marked “from Mealie”</span></span
          >
        </a>
      {/if}
      {#if job.counts.already}
        <div class="r">
          <span class="num dim">{count(job.counts.already)}</span>
          <span class="rn"><b>Left out</b><span>You already had them</span></span>
        </div>
      {/if}
    </div>
    {#if flow.admin}
      <div class="card">
        <div class="r">
          <span class="rn"><b>Undo this import</b><span>{undoWords(job)}</span></span>
          <button
            type="button"
            class="small"
            disabled={flow.busy || offline}
            onclick={() => void flow.undo()}>Undo</button
          >
        </div>
      </div>
    {/if}
    {@render problem()}
    {#if flow.admin}
      <button type="button" class="link another" onclick={() => flow.another()}
        >Import another file</button
      >
    {/if}
    <div class="foot">
      <a class="outline grow" href={resolve('/(app)/recipes')}>Go to Recipes</a>
      {#if job.counts.drafts}
        <a class="primary grow" href="{resolve('/(app)/recipes/drafts')}?from=mealie"
          >Check the {count(job.counts.drafts)}</a
        >
      {/if}
    </div>
  {/if}
</div>

<style>
  .mealie {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 640px;
  }

  .file-input {
    display: none;
  }

  h2 {
    margin: 0 2px;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .sub {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .fine {
    margin: 0 2px;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .card {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 2px 14px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
  }

  .r,
  .step {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: var(--space-4) 0;
    border-bottom: 1px solid var(--color-border);
    color: var(--color-text);
  }

  .step {
    align-items: flex-start;
  }

  .r:last-child,
  .step:last-child {
    border-bottom: none;
  }

  a.r {
    text-decoration: none;
  }

  .rn {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .rn b {
    font-size: 15px;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .rn span {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  .num {
    min-width: 44px;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    text-align: right;
    flex: none;
  }

  .dim {
    color: var(--color-text-muted);
  }

  .need-num,
  .need {
    color: var(--color-warning-text);
  }

  .need {
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .yes {
    display: inline-flex;
    flex: none;
    color: var(--color-accent);
  }

  .dash {
    flex: none;
    width: 14px;
    height: 2.4px;
    margin: 0 3px;
    border-radius: 2px;
    background: var(--color-text-muted);
  }

  .n {
    display: grid;
    flex: none;
    place-items: center;
    width: 26px;
    height: 26px;
    border-radius: 13px;
    background: var(--color-fill);
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }

  .which {
    padding: 0 0 var(--space-4);
    border-bottom: 1px solid var(--color-border);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .note,
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

  .note :global(svg),
  .ok :global(svg),
  .warn :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  .note {
    border: 1px solid var(--color-info-muted);
    background: var(--color-info);
    color: var(--color-info-text);
  }

  .ok {
    border: 1px solid var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-base);
  }

  .warn {
    border: 1px solid var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .file {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-5) 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }

  .ic {
    display: grid;
    flex: none;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: 12px;
    background: var(--color-fill);
    color: var(--color-text-soft);
  }

  .running {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding-top: var(--space-4);
  }

  .big {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: -0.01em;
  }

  .of {
    color: var(--color-text-soft);
    font-size: 15px;
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

  .problem {
    color: var(--color-danger-text);
    font-size: var(--text-md);
  }

  .foot {
    position: sticky;
    bottom: calc(var(--tabbar-height) + env(safe-area-inset-bottom, 0px));
    display: flex;
    gap: var(--space-5);
    padding: var(--space-5) 0;
    border-top: 1px solid var(--color-border);
    background: var(--color-ground);
  }

  .grow,
  .foot .primary:only-child {
    flex: 1;
  }

  .primary,
  .outline {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    padding: 0 18px;
    border-radius: var(--radius-full);
    font: var(--weight-extrabold) 15px var(--font-ui);
    text-align: center;
    text-decoration: none;
    cursor: pointer;
  }

  .primary {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .outline {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  button.small {
    flex: none;
    min-height: var(--touch-target);
    margin: 0;
    padding: 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-field);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .link {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-2);
    border: none;
    background: none;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .another {
    align-self: center;
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  @media (min-width: 768px) {
    .foot {
      bottom: 0;
    }
  }
</style>
