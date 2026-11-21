<script lang="ts">
  // Test fixture for FoodPicker.svelte: inside the shared Sheet, as "Add to pantry" has it,
  // with or without an `oncancel` of its own.
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import Sheet from '#lib/components/Sheet.svelte';

  let { withCancel = false, log = [] }: { withCancel?: boolean; log?: string[] } = $props();
  let open = $state(false);
</script>

<button type="button" onclick={() => (open = true)}>Open it</button>
{#if open}
  <Sheet
    title="Add to pantry"
    onclose={() => {
      log.push('sheet closed');
      open = false;
    }}
  >
    <FoodPicker
      label="Find an ingredient"
      onpick={() => log.push('picked')}
      oncancel={withCancel ? () => log.push('picker cancelled') : undefined}
    />
  </Sheet>
{/if}
