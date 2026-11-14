<script lang="ts">
  // A Reset password link, "/reset#<secret>" (Pe1, cabledrawer 13 Nov): the sign-in link's page,
  // where the server says the link is a reset.
  import LinkPage from '#lib/components/people/LinkPage.svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();
</script>

<LinkPage plainHttpAllowed={data.setup.plain_http_allowed} signedIn={data.signedIn} />
