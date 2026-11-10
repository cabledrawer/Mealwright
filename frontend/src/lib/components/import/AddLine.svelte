<script lang="ts">
  // "Add a line to the batter" at the end of a section on Check (F187, mockup
  // Dark-CheckSections08-Phone): a new, empty line the person names. Used by See all and by One
  // at a time.
  import Icon from '#lib/components/Icon.svelte';

  let { label, onclick }: { label: string; onclick: () => void } = $props();
</script>

<button type="button" class="add" {onclick}>
  <Icon name="plus" size={16} stroke={2.6} />{label}
</button>

<style>
  .add {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    width: 100%;
    min-height: 48px;
    padding: 0 var(--space-5);
    border: 1px dashed var(--color-add-border);
    border-radius: 14px;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
