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
  import { toasts } from '#lib/toast.svelte.js';

  let {
    actions,
    session,
    dense = false
  }: {
    actions: Pick<PlanActions, 'model' | 'readonly'>;
    session: PlanSession;
    /** In a narrow column of the week grid: less padding, the buttons the whole width. */
    dense?: boolean;
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

  /**
   * Start batch cook: batch cook mode for the whole session (B3). The plan is read again first
   * (RF5, H3): another person may have pressed Change meanwhile, which makes a new session, so the
   * card on screen could hold an id that is gone. It opens the one now on that cook day, or says
   * plainly that it changed.
   */
  async function start() {
    await actions.model.refresh();
    const sessions = actions.model.plan?.batch_sessions;
    let id = session.id;
    if (sessions && !sessions.some((s) => s.id === id)) {
      const there = sessions.filter((s) => s.cook_day === session.cook_day);
      if (there.length !== 1) {
        toasts.show('That batch cook was changed or removed. The Plan is up to date now.');
        return;
      }
      id = there[0]!.id;
    }
    await goto(resolve('/(app)/batch-cook/session/[id]/cook', { id: String(id) }));
  }

  async function change() {
    const to = resolve('/(app)/batch-cook');
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
    await goto(`${to}?change=${session.id}`);
  }
</script>

<section
  class="card"
  class:dense
  aria-label="Batch cook, {batches.length} recipes"
  data-testid="batch-card"
>
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
  <!-- While an admin has Batch cook hidden, the card has no buttons: every Batch cook route,
       taking a session off included, is refused then (cabledrawer 11 Nov). -->
  {#if batchCook.shown}
    <div class="buttons">
      <button
        type="button"
        class="go"
        disabled={actions.readonly || batches.length === 0}
        onclick={start}>Start batch cook</button
      >
      <button type="button" class="btn" disabled={actions.readonly} onclick={change}>Change</button>
      <button
        type="button"
        class="btn"
        disabled={actions.readonly}
        onclick={() => void actions.model.removeBatch(session.id)}>Remove</button
      >
    </div>
  {/if}
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

  .card.dense {
    gap: var(--space-4);
    padding: var(--space-5);
  }

  .dense .buttons > * {
    flex: 1 1 100%;
    padding: 0 var(--space-4);
  }

  .dense strong {
    font-size: var(--text-md);
  }

  .head {
    flex-wrap: wrap;
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
