<script lang="ts">
  // Signing in over plain http:// must never fail silently (cabledrawer 17 Oct, spec
  // section 7). Browsers count https:// and localhost as secure. On any other plain
  // http:// address:
  //   - if the admin hasn't allowed it, say so before anyone types a password
  //     (the page hides its form);
  //   - if the admin has allowed it for testing, show a clear warning.
  import type { Connection } from '$lib/session.svelte';

  let { kind }: { kind: Connection } = $props();
</script>

{#if kind === 'plain-refused'}
  <div class="notice refused" role="alert">
    <p class="title">This connection isn't secure</p>
    <p>
      Signing in needs a secure connection. Open Mealwright at its https:// address, through your
      reverse proxy.
    </p>
  </div>
{:else if kind === 'plain-allowed'}
  <div class="notice allowed" role="status">
    <p>
      This connection isn't secure. Passwords travel unencrypted. Use only for testing on a network
      you trust.
    </p>
  </div>
{/if}

<style>
  .notice {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-button);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .title {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }
</style>
