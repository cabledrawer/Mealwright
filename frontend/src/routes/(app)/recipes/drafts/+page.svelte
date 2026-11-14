<script lang="ts">
  // Drafts: imports left unfinished, kept for 15 days (spec "Drafts (cabledrawer 21 Oct)").
  // ?from=mealie opens it on the "From Mealie" chip (0.9.5: Import from Mealie's Done, Today).
  import { page } from '$app/state';
  import DraftsScreen from '#lib/components/drafts/DraftsScreen.svelte';
</script>

<DraftsScreen fromMealie={page.url.searchParams.get('from') === 'mealie'} />
