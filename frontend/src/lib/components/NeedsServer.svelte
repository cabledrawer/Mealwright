<script lang="ts">
  // The one line under a screen whose changes need the server while it can't be reached (FE12).
  // The controls are greyed out with `disabled={network.offline}`, and this says why in the
  // usual words (downWords.ts: "You’re offline…" or "Can’t reach your Mealwright server…").
  // Reading stays; nothing here is queued (only shopping-list changes are: sync protocol §4).
  import { cantReachWords } from '#lib/api.js';
  import { network } from '#lib/network.svelte.js';

  let { id }: { id?: string } = $props();
</script>

{#if network.offline}
  <p class="needs-server" {id} role="status">{cantReachWords()}</p>
{/if}

<style>
  .needs-server {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }
</style>
