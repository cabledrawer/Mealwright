<script lang="ts">
  // The old address of Settings › Outside connections (FE25): goes to the new one.
  import { resolve } from '$app/paths';
  import { OUTSIDE_CONNECTIONS_ANCHOR, OWN_NETWORK_ANCHOR } from '#lib/privacyWords.js';
  import OldAddress from '../OldAddress.svelte';
</script>

<OldAddress
  to={resolve('/(app)/settings/outside-connections')}
  anchors={[OUTSIDE_CONNECTIONS_ANCHOR, OWN_NETWORK_ANCHOR]}
/>
