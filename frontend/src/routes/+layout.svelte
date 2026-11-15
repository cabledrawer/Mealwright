<script lang="ts">
  import '#lib/styles/fonts.css';
  import '#lib/styles/tokens.css';
  import '#lib/styles/base.css';

  import type { Snippet } from 'svelte';
  import { watchLeaving } from '#lib/leaving.js';
  import { endPendingSignOutWhenOnline } from '#lib/offline/signOutPending.js';
  import { tellWorkerPageIsQuiet } from '#lib/offline/precacheWait.js';
  import { theme } from '#lib/theme.svelte.js';

  let { children }: { children: Snippet } = $props();

  $effect(() => theme.start());
  // Signed out while offline: the server session ends once the browser is back online
  // (docs/dev/sync-protocol.md section 12). Any request to the server does that first, too.
  $effect(() => endPendingSignOutWhenOnline());
  // Leaving the page (a reload, a typed address): what it was still asking the server is
  // neither sent nor reported as a failure (leaving.ts).
  $effect(() => watchLeaving());
  // The service worker's first download of the app's files waits for this (precacheWait.ts).
  $effect(() => {
    void tellWorkerPageIsQuiet();
  });
</script>

{@render children()}
