<script lang="ts">
  import PageHeader from '#lib/components/PageHeader.svelte';
  import RecentSection from '../RecentSection.svelte';
</script>

<PageHeader
  title="Recent changes"
  overline="Mealwright"
  subtitle="What changed lately, with Undo."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<section class="section" aria-label="Recent changes">
  <RecentSection />
</section>

<style>
  .section {
    max-width: var(--settings-width);
  }
</style>
