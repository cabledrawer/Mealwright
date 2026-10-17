<script lang="ts">
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ThemeSwitch from '$lib/components/ThemeSwitch.svelte';
</script>

<PageHeader title="Settings" />

<section class="section" aria-labelledby="appearance">
  <h2 id="appearance">Appearance</h2>
  <div class="card">
    <div class="row">
      <span class="label">Theme</span>
      <ThemeSwitch variant="pill" />
    </div>
  </div>
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 640px;
  }

  h2 {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: 54px;
    padding: var(--space-4) 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }
</style>
