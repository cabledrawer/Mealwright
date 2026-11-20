<script lang="ts">
  // Test fixture: Settings' layout (the list beside the page) around Appearance, in a box of a
  // given width, as the room left beside the main menu (F253).
  import Layout from '../../routes/(app)/settings/+layout.svelte';
  import Appearance from '../../routes/(app)/settings/appearance/+page.svelte';

  let { width }: { width: number } = $props();
</script>

<div class="room" style:width="{width}px" data-testid="room">
  <Layout><Appearance /></Layout>
</div>
