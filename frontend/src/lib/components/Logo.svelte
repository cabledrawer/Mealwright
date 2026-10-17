<script lang="ts">
  // The Mealwright mark: green tub on light, mint tub on dark (docs/brand).
  let { size = 32 }: { size?: number } = $props();
</script>

<span class="logo">
  <img class="light" src="/mark.svg" alt="" width={size} height={size} />
  <img class="dark" src="/mark-dark.svg" alt="" width={size} height={size} />
</span>

<style>
  .logo {
    display: inline-flex;
    flex: none;
  }
  .dark {
    display: none;
  }
  :global([data-theme='dark']) .light {
    display: none;
  }
  :global([data-theme='dark']) .dark {
    display: block;
  }
</style>
