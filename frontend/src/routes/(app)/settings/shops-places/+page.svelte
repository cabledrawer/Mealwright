<script lang="ts">
  import PageHeader from '#lib/components/PageHeader.svelte';
  import ShopsPlaces from '../ShopsPlaces.svelte';
</script>

<PageHeader
  title="Shops & places"
  overline="Kitchen"
  subtitle="Where you shop and where ingredients are kept."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<section class="section" aria-label="Shops &amp; places">
  <ShopsPlaces />
</section>

<style>
  .section {
    max-width: 760px;
  }
</style>
