<script lang="ts">
  import Lazy from '#lib/components/Lazy.svelte';
  // Check, two ways of cooking it found (M2, mockup CheckWait08): "Two ways to cook this:
  // Stovetop and Instant Pot. They're kept as two methods, and Cook mode asks which one on the
  // day." and the second way's steps, so both are looked at before Save. Both ways start with the
  // page's ingredients and its one time; change them in the editor. Loaded only when the page had
  // two ways (it stays out of the import page's size). Words are proposed, for cabledrawer.
  // The second way's waits are confirmed the same way as the first's (StepWait: Yes, it waits ·
  // Change · No wait), so nothing the reader suggested is saved without being looked at.
  import type { ImportReview } from '#lib/client/imports.js';
  import type { ImportFlow } from '#lib/import.svelte.js';

  let {
    flow,
    review,
    showSteps = true
  }: { flow: ImportFlow; review: ImportReview; showSteps?: boolean } = $props();
  const second = $derived(review.second_method);
</script>

{#if second}
  <div class="methods" data-testid="two-methods">
    <p class="note">
      Two ways to cook this: <b>{review.method_name}</b> and <b>{second.name}</b>. They’re kept as
      two methods, and Cook mode asks which one on the day.
    </p>
    {#if showSteps}
      <h3>Steps · {second.name}</h3>
      <ol>
        {#each second.steps.filter((s) => s.kind === 'step') as step, n (n)}
          <li>
            {step.text}
            {#if step.wait}
              <Lazy
                load={() => import('./StepWait.svelte')}
                {flow}
                {step}
                name="{second.name} step {n + 1}"
              />
            {/if}
          </li>
        {/each}
      </ol>
    {/if}
  </div>
{/if}

<style>
  .methods {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .note {
    margin: 0;
    padding: var(--space-5) var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding-left: var(--space-8);
  }

  li {
    font-size: var(--text-md);
    line-height: 1.45;
  }
</style>
