<script lang="ts">
  // A step that waits, on the Check screen (M1, mockup CheckWait08): what the reader found in the
  // words ("Marinate · 4 h – overnight"), "To confirm" until the person answers, and the three
  // answers: Yes, it waits · Change · No wait. Nothing is saved here: the step's own `wait` goes
  // with Save. Loaded only when a step has a wait (it stays out of the page's size). Words are
  // proposed, for cabledrawer (docs/dev/words.md, steps that wait).
  import type { ImportFlow } from '#lib/import.svelte.js';
  import type { ReviewStep } from '#lib/client/imports.js';
  import { confirmWait, reworkMinutes, takeOffWait } from '#lib/importStepEdits.js';
  import { waitLength, waitName } from '#lib/timeWords.js';
  import WaitFields from '../recipe/WaitFields.svelte';

  let { flow, step, name }: { flow: ImportFlow; step: ReviewStep; name: string } = $props();

  let changing = $state(false);
  let invalid = $state(false);
  const wait = $derived(step.wait);
  // Save on the review is blocked while these boxes aren't right (the flow reads this).
  $effect(() => {
    step.wait_invalid = changing && invalid;
  });
</script>

{#if wait}
  <div class="wait" data-step-wait>
    <span class="line">
      <span class="chip">
        <svg
          aria-hidden="true"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.4"
          stroke-linecap="round"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 2" />
        </svg>
        {waitName(wait.kind)} · {waitLength(wait)}
      </span>
      {#if !step.wait_confirmed}<span class="confirm">To confirm</span>{/if}
    </span>
    {#if changing}
      <WaitFields bind:wait={step.wait!} bind:invalid {name} onchange={() => reworkMinutes(flow)} />
      <span class="buttons">
        <button
          type="button"
          class="yes"
          disabled={invalid}
          onclick={() => {
            confirmWait(flow, step);
            changing = false;
          }}>Done</button
        >
      </span>
    {:else}
      <span class="buttons">
        {#if !step.wait_confirmed}
          <button type="button" class="yes" onclick={() => confirmWait(flow, step)}
            >Yes, it waits</button
          >
        {/if}
        <button type="button" class="no" onclick={() => (changing = true)}>Change</button>
        <button type="button" class="no" onclick={() => takeOffWait(flow, step)}>No wait</button>
      </span>
    {/if}
  </div>
{/if}

<style>
  .wait {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .confirm {
    color: var(--color-maybe-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border-radius: var(--radius-md);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .yes {
    border: none;
    background: var(--color-wait-yes);
    color: var(--color-wait-yes-text);
    font-weight: var(--weight-bold);
  }

  .no {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }
</style>
