<script lang="ts">
  // Today's note when an import from Mealie has finished (0.9.5, cabledrawer 13 Nov: "runs on the
  // server, you can leave"). Shown for a day after it finished; the words are proposed, for
  // cabledrawer (words.md section 81). Fetched only when there is one.
  import { resolve } from '$app/paths';
  import Icon from '../Icon.svelte';
  import { session } from '#lib/session.svelte.js';
  import type { MealieNote } from '#lib/client/today.js';
  import { NOTE_FAILED, NOTE_FAILED_LINE, noteCheckWords, noteWords } from '#lib/mealieWords.js';

  let { note }: { note: MealieNote } = $props();
  const admin = $derived(session.me?.role === 'admin');
</script>

<section class="note" class:failed={note.state === 'failed'} data-testid="today-mealie">
  <Icon name={note.state === 'failed' ? 'alert' : 'check'} size={20} stroke={2.4} />
  <div class="words">
    {#if note.state === 'failed'}
      <strong>{NOTE_FAILED}</strong>
      <span>{NOTE_FAILED_LINE}</span>
    {:else}
      <strong>{noteWords(note.recipes)}</strong>
      {#if note.to_check}<span>{noteCheckWords(note.to_check)}</span>{/if}
    {/if}
  </div>
  {#if note.state === 'done' && note.to_check}
    <a href="{resolve('/(app)/recipes/drafts')}?from=mealie">Check them</a>
  {:else if admin}
    <!-- The import screen's buttons are the admin's; a member gets no arrow to it (round 2). -->
    <a href={resolve('/(app)/settings/your-data/mealie')} aria-label="Open Import from Mealie"
      ><Icon name="back" size={18} stroke={2.4} /></a
    >
  {/if}
</section>

<style>
  .note {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-5) var(--space-6);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-xl);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .note.failed {
    border-color: var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .note > :global(svg) {
    flex: none;
  }

  .words {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    font-size: var(--text-base);
    line-height: 1.4;
  }

  .words span {
    font-size: var(--text-md);
  }

  a {
    display: inline-flex;
    flex: none;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    color: inherit;
    font-weight: var(--weight-bold);
  }

  a :global(svg) {
    transform: scaleX(-1);
  }
</style>
