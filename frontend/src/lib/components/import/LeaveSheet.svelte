<script lang="ts">
  // "Save as draft?" (mockups Import05-Phone and Import05-Desktop, the leave sheet; spec "Import
  // drafts", cabledrawer 17 Oct): asked when leaving the review without saving. Save draft · Keep
  // checking · Discard. A sheet on a phone, a dialog on a computer. For a draft that was opened
  // and then changed, the same three choices are worded for that (proposed, for cabledrawer): the
  // draft is saved over, or left as it was.
  import { onMount } from 'svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import { holdUndo } from '#lib/undo.svelte.js';

  let {
    name,
    again = false,
    busy = false,
    problem = null,
    onsave,
    onstay,
    ondiscard
  }: {
    /** The recipe's name as it is in the box. */
    name: string;
    /** A draft that was opened and changed (not one being kept for the first time). */
    again?: boolean;
    busy?: boolean;
    /** Why the draft wasn't kept ("You have 50 drafts. Finish or delete one first."). */
    problem?: string | null;
    onsave: () => void;
    onstay: () => void;
    ondiscard: () => void;
  } = $props();

  const uid = $props.id();

  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move the lines behind this sheet
    return letGo;
  });

  const title = $derived(again ? 'Save your changes?' : 'Save as draft?');
  const words = $derived(name.trim() || 'this recipe');
</script>

<Sheet {title} size="medium" describedby="{uid}-text" onclose={onstay} locked={busy}>
  {#if again}
    <p id="{uid}-text">
      You’ve changed {words} since you opened this draft. Saving keeps your choices for another 15 days.
      Anyone in your household can carry on.
    </p>
  {:else}
    <p id="{uid}-text">
      You haven’t finished checking {words}. A draft keeps your choices so far for 15 days, in
      Recipes → Drafts. Anyone in your household can carry on.
    </p>
  {/if}
  {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
  <div class="buttons">
    <button type="button" class="save" disabled={busy} onclick={onsave}>
      {busy ? 'Saving…' : 'Save draft'}
    </button>
    <button type="button" class="stay" onclick={onstay}>Keep checking</button>
    <button type="button" class="discard" disabled={busy} onclick={ondiscard}>
      {again ? 'Discard changes' : 'Discard'}
    </button>
  </div>
</Sheet>

<style>
  p {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .problem {
    color: var(--color-warning-text);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .save,
  .stay,
  .discard {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .save {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .stay {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .discard {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-warning-text);
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  /* A computer: side by side, the main button last (the mockup's dialog). */
  @media (min-width: 768px) {
    .buttons {
      flex-direction: row-reverse;
      flex-wrap: wrap;
      justify-content: flex-start;
      align-items: center;
      padding-top: var(--space-3);
    }

    .save,
    .stay {
      min-height: var(--touch-target);
      padding: 0 var(--space-7);
      border-radius: var(--radius-full);
    }

    .discard {
      padding: 0 var(--space-5);
    }
  }
</style>
