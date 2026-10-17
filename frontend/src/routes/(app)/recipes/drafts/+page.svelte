<script lang="ts">
  // Drafts: recipes you started importing but didn't save, kept for 15 days. Import
  // comes in 0.5; until then this page is empty.
  import EmptyState from '$lib/components/EmptyState.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
</script>

<PageHeader title="Drafts" parent={{ href: '/recipes', label: 'Recipes' }} />

<EmptyState title="No drafts">
  When you import a recipe and leave before saving it, it waits here for 15 days.
</EmptyState>
