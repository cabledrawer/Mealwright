<script lang="ts">
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';

  let { stack = false }: { stack?: boolean } = $props();
</script>

<ButtonRow {stack}>
  <Button quiet>First in the source</Button>
  <Button>Second in the source</Button>
  <Button quiet>Third in the source</Button>
</ButtonRow>
