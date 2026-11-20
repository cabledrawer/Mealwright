<script lang="ts">
  import { timeWords } from '#lib/timeWords.js';
  // "Wren’s version" (cabledrawer 19 Oct, editor brief decision 4): the recipe as the other person
  // saved it, in a sheet over the editor (not a new tab: the installed app has none). Closing
  // brings you back to your own edit, untouched. Nothing here can be edited.
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import type { RecipeOut } from '#lib/client/recipes.js';
  import { compareLines, compareSteps, otherChanges } from '#lib/recipes/compare.js';
  import { plural } from '#lib/words.js';

  let {
    who,
    opened,
    theirs,
    phone,
    busy = false,
    offline = false,
    onclose,
    onsave
  }: {
    who: string;
    /** The recipe as you opened it. */
    opened: RecipeOut;
    theirs: RecipeOut;
    phone: boolean;
    /** Save mine anyway can't go now (saving, offline, or a photo still going up). */
    busy?: boolean;
    offline?: boolean;
    onclose: () => void;
    onsave: () => void;
  } = $props();

  const lines = $derived(compareLines(opened.lines, theirs.lines));
  const changedLines = $derived(lines.filter((l) => l.status !== 'same'));
  const sameLines = $derived(lines.length - changedLines.length);
  const steps = $derived(compareSteps(opened.steps, theirs.steps));
  const stepsChanged = $derived(
    steps.some((s) => s.changed) || opened.steps.length !== steps.length
  );
  const others = $derived(otherChanges(opened, theirs));
  const timeChanged = $derived(opened.time_minutes !== theirs.time_minutes);
  const servesChanged = $derived(opened.serves !== theirs.serves);
  const meta = $derived(
    [theirs.description, theirs.time_minutes ? timeWords(theirs.time_minutes) : null].filter(
      Boolean
    )
  );
</script>

<Sheet title="{who}’s version" {onclose}>
  <div class="body">
    <p class="sub">
      Saved by {who} after you opened this recipe. Your edit is still here, {phone
        ? 'underneath'
        : 'untouched'}.
    </p>

    <div class="recipe">
      <p class="name">{theirs.name}</p>
      <p class="sub">
        {#if meta.length}{meta.join(' · ')}{#if theirs.serves !== null}
            ·
          {/if}{/if}
        {#if theirs.serves !== null}<b class:changed={servesChanged}>Serves {theirs.serves}</b>{/if}
        {#if timeChanged && theirs.time_minutes === null}<b class="changed">no time</b>{/if}
      </p>
    </div>

    <ul class="list">
      {#each changedLines as line, i (i)}
        <li class:changed={line.status !== 'same'} class:gone={line.status === 'removed'}>
          {#if line.quantity}<b>{line.quantity}</b>{/if}
          {line.words}{#if line.note}, {line.note}{/if}
          {#if line.status === 'changed'}<span class="why">· was {line.was}</span>{/if}
          {#if line.status === 'added'}<span class="why">· added by {who}</span>{/if}
          {#if line.status === 'removed'}<span class="why">· taken out by {who}</span>{/if}
        </li>
      {/each}
      {#if sameLines > 0}
        <li class="quiet">
          {changedLines.length ? '+ ' : ''}{sameLines}
          {changedLines.length ? 'more ' : ''}{plural(sameLines, 'line', 'lines')}, unchanged
        </li>
      {/if}
    </ul>

    {#if stepsChanged}
      <p class="section">Method</p>
      <ol class="list steps">
        {#each steps as step, i (i)}
          <li class:changed={step.changed}>
            {#if step.n}<b>{step.n}.</b>{/if}
            {step.text}
          </li>
        {/each}
      </ol>
    {:else}
      <p class="quiet">The method is unchanged.</p>
    {/if}

    {#if others.length}
      <p class="quiet">{who} also changed: {others.join(', ')}.</p>
    {/if}

    <p class="hint">Highlighted: what {who} changed. Nothing here can be edited.</p>

    {#if offline}<p class="hint" role="status">
        {downLine(network.deviceOffline, (b) => `Save ${b.when}.`)}
      </p>{/if}

    <ButtonRow>
      <Button quiet disabled={busy} onclick={onsave}>Save mine anyway</Button>
      <Button onclick={onclose}>Back to my edit</Button>
    </ButtonRow>
  </div>
</Sheet>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .sub,
  .hint,
  .quiet {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .hint {
    font-size: var(--text-sm);
  }

  .name {
    font: var(--weight-semibold) 1.625rem var(--font-reading);
    overflow-wrap: anywhere;
  }

  b.changed,
  li.changed {
    background: var(--color-changed);
  }

  b.changed {
    padding: 0 var(--space-2);
    border-radius: var(--space-2);
  }

  .list {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-base);
  }

  .list li {
    padding: var(--space-4) 0;
    border-bottom: 1px solid var(--color-divider);
    overflow-wrap: anywhere;
  }

  .list li.changed {
    margin: 0 calc(-1 * var(--space-4));
    padding-right: var(--space-4);
    padding-left: var(--space-4);
  }

  .list li.gone {
    text-decoration: line-through;
  }

  .list li.quiet {
    border-bottom: none;
    color: var(--color-text-muted);
  }

  .why {
    color: var(--color-text-muted);
  }

  .section {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }
</style>
