<script lang="ts">
  import '@fontsource-variable/plus-jakarta-sans';
  import '@fontsource-variable/newsreader';
  import '#lib/styles/tokens.css';
  import '#lib/styles/base.css';

  import type { Snippet } from 'svelte';
  import { endPendingSignOutWhenOnline } from '#lib/offline/signOutPending.js';
  import { theme } from '#lib/theme.svelte.js';

  let { children }: { children: Snippet } = $props();

  $effect(() => theme.start());
  // Signed out while offline: the server session ends once the browser is back online
  // (docs/dev/sync-protocol.md section 12). Any request to the server does that first, too.
  $effect(() => endPendingSignOutWhenOnline());
</script>

{@render children()}
