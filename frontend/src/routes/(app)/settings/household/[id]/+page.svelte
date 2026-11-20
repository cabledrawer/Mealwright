<script lang="ts">
  // The old address of a person's page (FE25): goes to their page at the new address. Only a
  // number is taken from the old address; anything else goes to the People list.
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import OldAddress from '../../OldAddress.svelte';

  const id = page.params.id ?? '';
  const to = /^\d{1,12}$/.test(id)
    ? resolve('/(app)/settings/people/[id]', { id })
    : resolve('/(app)/settings/people');
</script>

<OldAddress {to} />
