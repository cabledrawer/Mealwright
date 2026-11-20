<script lang="ts">
  // The way up from a page inside another (FE31): "‹ Recipes" on a phone, "Recipes › Sambar" on a
  // computer. One part for the page header and the recipe page, so they read and look the same.
  // `href` is already resolved (resolve()'s answer, plus a section if the parent has one).
  import Icon from './Icon.svelte';

  let { href, label, current }: { href: string; label: string; current: string } = $props();
</script>

<div class="trail">
  <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved by the caller -->
  <a class="back" {href}><Icon name="back" size={18} stroke={2.4} />{label}</a>
  <nav class="crumbs" aria-label="Breadcrumb">
    <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- as above -->
    <a {href}>{label}</a>
    <span class="sep" aria-hidden="true">›</span>
    <span class="here" aria-current="page">{current}</span>
  </nav>
</div>

<style>
  .trail {
    display: contents;
  }

  .back {
    display: flex;
    align-items: center;
    align-self: flex-start;
    gap: var(--space-2);
    min-height: var(--touch-target);
    margin-left: calc(-1 * var(--space-2));
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .crumbs {
    display: none;
    align-items: center;
    gap: var(--space-3);
    min-width: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .crumbs a {
    text-decoration: none;
  }

  .sep,
  .here {
    color: var(--color-text-muted);
  }

  .here {
    overflow-wrap: anywhere;
  }

  @media (min-width: 768px) {
    .back {
      display: none;
    }

    .crumbs {
      display: flex;
    }
  }

  @media print {
    .back,
    .crumbs {
      display: none;
    }
  }
</style>
