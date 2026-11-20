<script lang="ts">
  import Button from '#lib/components/Button.svelte';

  let {
    onclick,
    disabled = false,
    testid,
    describedby,
    both = false
  }: {
    onclick?: () => void;
    disabled?: boolean;
    testid?: string;
    describedby?: string;
    both?: boolean;
  } = $props();
</script>

<Button {onclick} {disabled} data-testid={testid} aria-describedby={describedby}>Save</Button>
{#if both}
  <Button quiet>Quiet</Button>
  <Button danger>Danger</Button>
  <Button small>Small</Button>
{/if}
