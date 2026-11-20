<script lang="ts">
  // FE25 (0.9.5-beta.3): three Settings pages moved to addresses named after them
  // (/settings/privacy → /settings/outside-connections, /settings/household → /settings/people,
  // /settings/kitchen → /settings/your-kitchen). A bookmark or an old link to the old address
  // lands on the new one, in the app, replacing the old address in the history. Where it goes is
  // fixed by the page that uses this, never read from the address: no query string is followed,
  // and only an anchor named in `anchors` is kept (proposed, for cabledrawer).
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import type { ResolvedPathname } from '$app/types';

  let {
    to,
    anchors = []
  }: {
    /** The new page's address, from resolve(). */
    to: ResolvedPathname;
    /** The anchors the new page has, kept when the old address named one of them. */
    anchors?: readonly string[];
  } = $props();

  onMount(() => {
    const asked = location.hash.slice(1);
    const anchor = anchors.includes(asked) ? `#${asked}` : '';
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- `to` is resolve()'s, and the anchor one of the page's own
    void goto(`${to}${anchor}`, { replace: true });
  });
</script>
