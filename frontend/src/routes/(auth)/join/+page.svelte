<script lang="ts">
  // The sign-in link, "/join#<secret>" (0.9 A1; link hardening, cabledrawer 13 Nov).
  import LinkPage from '#lib/components/people/LinkPage.svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();
</script>

<LinkPage plainHttpAllowed={data.setup.plain_http_allowed} signedIn={data.signedIn} />
