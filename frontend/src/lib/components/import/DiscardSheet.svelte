<script lang="ts">
  // "Discard this draft?" (F211, cabledrawer 10 Nov: Discard draft on Check asks once, deletes the
  // draft and its waiting photo, and Undo is in Recent changes, as on the Drafts list). The words
  // here are accepted, cabledrawer 11 Nov; the button's name is his. A sheet on a phone, a dialog on a
  // computer, the same shape as the leave sheet.
  import { onMount } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import { holdUndo } from '#lib/undo.svelte.js';

  let {
    name,
    kept,
    busy = false,
    ondiscard,
    onstay
  }: {
    /** The recipe's name as it is in the box. */
    name: string;
    /** The review is a draft on the server (so the delete can be undone). */
    kept: boolean;
    busy?: boolean;
    ondiscard: () => void;
    onstay: () => void;
  } = $props();

  const uid = $props.id();

  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move the lines behind this sheet
    return letGo;
  });

  const words = $derived(name.trim() || 'this recipe');
</script>

<Sheet
  title="Discard this draft?"
  size="medium"
  describedby="{uid}-text"
  onclose={onstay}
  locked={busy}
>
  <p id="{uid}-text">
    {#if kept}
      {words} will be deleted from Drafts, with its waiting photo. You can undo it from Recent changes.
    {:else}
      {words} isn’t kept in Drafts yet, so nothing of it is kept. Its waiting photo is deleted.
    {/if}
  </p>
  <ButtonRow stack>
    <Button disabled={busy} onclick={ondiscard}>{busy ? 'Discarding…' : 'Discard draft'}</Button>
    <Button quiet disabled={busy} onclick={onstay}>Keep checking</Button>
  </ButtonRow>
</Sheet>

<style>
  p {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }
</style>
