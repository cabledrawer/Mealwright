<script lang="ts">
  // The Batch cook (Experimental) card on a cook day (mockup Dark-PlanBatch08-Phone): "Batch cook
  // · 3 recipes", the rough time and when it starts, each recipe in its batch colour with its tubs,
  // Start batch cook (batch cook mode), Change. Remove takes the whole session off in one change with one Undo.
  import { resolve } from '$app/paths';
  import { goto } from '$app/navigation';
  import { batchCook } from '#lib/batchCook.svelte.js';
  import type { PlanBatch, PlanSession } from '#lib/client/plan.js';
  import Icon from '#lib/components/Icon.svelte';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayShort } from '#lib/planDates.js';
  import { colourOfBatch } from '#lib/planMeals.js';
  import { timeWords } from '#lib/timeWords.js';

  let {
    actions,
    session
  }: {
    actions: Pick<PlanActions, 'model' | 'readonly'>;
    session: PlanSession;
  } = $props();

  const batches = $derived(
    (actions.model.plan?.batch_cooks ?? []).filter((b) => b.session_id === session.id)
  );
  const when = $derived.by(() => {
    const parts: string[] = [];
    if (session.together_minutes) parts.push(`About ${timeWords(session.together_minutes)}`);
    if (session.start_time) {
      const day = session.start_day && session.start_day !== session.cook_day;
      parts.push(`from ${day ? `${dayShort(session.start_day!)} ` : ''}${session.start_time}`);
    }
    return parts.join(' · ');
  });
  const tubs = (b: PlanBatch) => `${b.tub_count} ${b.tub_count === 1 ? 'tub' : 'tubs'}`;

  /** Start batch cook: batch cook mode for the whole session (B3). */
  async function start() {
    await goto(resolve('/(app)/batch-cook/session/[id]/cook', { id: String(session.id) }));
  }

  async function change() {
    const to = resolve('/(app)/batch-cook');
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
    await goto(`${to}?change=${session.id}`);
  }
</script>

<section class="card" aria-label="Batch cook, {batches.length} recipes" data-testid="batch-card">
  <div class="head">
    <span class="title">
      <strong>Batch cook · {batches.length} {batches.length === 1 ? 'recipe' : 'recipes'}</strong>
      {#if when}<span class="when">{when}</span>{/if}
    </span>
    <span class="exp"><Icon name="flask" size={13} stroke={2.4} />Experimental</span>
  </div>
  <ul>
    {#each batches as batch (batch.id)}
      <li>
        <span class="dot" style:background="var(--batch-{colourOfBatch(batch)})" aria-hidden="true"
        ></span>{batch.recipe_name} · {tubs(batch)}
      </li>
    {/each}
  </ul>
  <div class="buttons">
    <!-- While an admin has Batch cook hidden, its screens are gone: only Remove stays. -->
    {#if batchCook.shown}
      <button
        type="button"
        class="go"
        disabled={actions.readonly || batches.length === 0}
        onclick={start}>Start batch cook</button
      >
      <button type="button" class="btn" disabled={actions.readonly} onclick={change}>Change</button>
    {/if}
    <button
      type="button"
      class="btn"
      disabled={actions.readonly}
      onclick={() => void actions.model.removeBatch(session.id)}>Remove</button
    >
  </div>
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .title {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  strong {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .when {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .exp {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: var(--radius-full);
    background: var(--color-experimental-bg);
    color: var(--color-experimental-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 5px;
    flex: none;
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .go,
  .btn {
    min-height: var(--touch-target);
    border-radius: var(--radius-full);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .go {
    padding: 0 22px;
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .btn {
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text-soft);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
