<script lang="ts">
  import Button from '#lib/components/Button.svelte';

  let {
    onclick,
    disabled = false,
    testid,
    describedby,
    both = false,
    looks = false
  }: {
    onclick?: () => void;
    disabled?: boolean;
    testid?: string;
    describedby?: string;
    both?: boolean;
    looks?: boolean;
  } = $props();
</script>

<Button {onclick} {disabled} data-testid={testid} aria-describedby={describedby}>Save</Button>
{#if both}
  <Button quiet>Quiet</Button>
  <Button danger>Danger</Button>
  <Button small>Small</Button>
{/if}
{#if looks}
  <Button outline>Outline</Button>
  <Button plain>Plain</Button>
  <Button soft>Soft</Button>
  <Button yes>Yes</Button>
  <Button stop>Stop</Button>
  <Button warn>Warn</Button>
{/if}
