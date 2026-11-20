<script lang="ts">
  // The old address of Settings › Your kitchen (FE25): goes to the new one.
  import { resolve } from '$app/paths';
  import OldAddress from '../OldAddress.svelte';
</script>

<OldAddress to={resolve('/(app)/settings/your-kitchen')} />
