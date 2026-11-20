<script lang="ts">
  import PageHeader from '#lib/components/PageHeader.svelte';
  import MealSlots from '../MealSlots.svelte';
</script>

<PageHeader
  title="Meal slots"
  overline="Kitchen"
  subtitle="Breakfast, lunch, dinner and any of your own."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<!-- For admins only (items.ts): the Settings layout shows a member "Only admins can change this." -->
<section class="section" aria-label="Meal slots">
  <MealSlots />
</section>

<style>
  .section {
    max-width: var(--settings-width);
  }
</style>
