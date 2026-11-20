<script lang="ts">
  // Test fixture for Sheet.svelte: a button that opens it, and a log of what it was asked to do.
  import Sheet from '#lib/components/Sheet.svelte';

  let {
    outside = true,
    locked = false,
    log = []
  }: { outside?: boolean; locked?: boolean; log?: string[] } = $props();

  let open = $state(false);
</script>

<button type="button" onclick={() => (open = true)}>Open it</button>
{#if open}
  <Sheet
    title="Remove Onion?"
    {outside}
    {locked}
    onclose={() => {
      log.push('close');
      open = false;
    }}
  >
    <input aria-label="First" />
    <button type="button">Last</button>
  </Sheet>
{/if}
