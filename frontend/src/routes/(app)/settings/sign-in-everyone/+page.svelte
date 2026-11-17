<script lang="ts">
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { session } from '#lib/session.svelte.js';
  import SignInSection from '../SignInSection.svelte';

  // Admins only: the Settings layout shows anyone else "Only admins can change this." instead.
  const admin = session.me?.role === 'admin';
  const device = matchMedia('(max-width: 767px)').matches ? 'phone' : 'computer';
</script>

<PageHeader
  title="Sign-in for everyone"
  overline="Household"
  subtitle="How the whole household signs in."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<section class="section" aria-label="Sign-in for everyone">
  <SignInSection {device} {admin} part="everyone" />
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 760px;
  }
</style>
