<script lang="ts">
  import { onMount } from 'svelte';
  import AmountsChoice from '#lib/components/AmountsChoice.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import { labelOf } from '../items.js';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { changeAmountsShown, changePints, getHousehold } from '#lib/client/household.js';
  import type { AmountsShown, Pints } from '#lib/client/types.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { ADMIN_ONLY } from '#lib/adminWords.js';

  const admin = session.me?.role === 'admin';

  // --- Pints (0.6 import; the words are proposed, for cabledrawer) ---------------------------
  /** The household's pint, once the server has said (null until then, and when it can't). */
  let pints = $state<Pints | null>(null);
  let pintsProblem = $state<string | null>(null);
  /** How amounts are shown (0.9 U2; cabledrawer 12 Nov). Read with the pint. */
  let amountsShown = $state<AmountsShown>('as_written');

  function readPint() {
    getHousehold().then(
      (household) => {
        pints = household.pints;
        amountsShown = household.amounts_shown ?? 'as_written';
      },
      () => {} // offline or unreachable: the rows stay hidden
    );
  }
  onMount(readPint);
  // An Undo from Recent changes (or the toast) may have put these back: read them again.
  let undoneSeen = kitchen.elsewhere;
  $effect(() => {
    if (kitchen.elsewhere === undoneSeen) return;
    undoneSeen = kitchen.elsewhere;
    readPint();
  });
  // Opened offline: the rows show once the connection comes back.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      if (pints === null) readPint();
    }
  });

  /** How amounts are shown (0.9 U2): the choice moves at once; if it can't be saved it goes back. */
  async function setAmountsShown(next: AmountsShown) {
    const before = amountsShown;
    pintsProblem = null;
    amountsShown = next;
    try {
      amountsShown = (await changeAmountsShown(next)).amounts_shown;
      kitchen.wroteSettings();
    } catch (error) {
      amountsShown = before;
      pintsProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }

  /** The switch flips at once and is sent; if it can't be saved it flips back and says so. */
  async function setPints(us: boolean) {
    const before = pints;
    pintsProblem = null;
    pints = us ? 'us' : 'uk';
    try {
      pints = (await changePints(pints)).pints;
      kitchen.wroteSettings();
    } catch (error) {
      pints = before;
      pintsProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }
</script>

<PageHeader
  title="Amounts"
  overline="You"
  subtitle="Metric or cups, and how amounts are rounded."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<!-- Needs the server; once loaded it stays, with its switch greyed out while the server can't be
     reached. -->
{#if network.down && pints === null}
  <OfflineNote screen={labelOf('amounts')} />
{/if}
{#if pints !== null}
  <section class="section" aria-label="Amounts">
    <AmountsChoice
      value={amountsShown}
      disabled={!admin || network.offline}
      onchange={(next) => void setAmountsShown(next)}
      describedby={admin ? undefined : 'amounts-admin'}
    />
    <div class="card">
      <div class="row">
        <span class="who">
          <span class="label" id="pints-label">Read pints as US pints</span>
          <span class="detail" id="pints-detail">
            {pints === 'us'
              ? 'A pint is 473 ml (US).'
              : 'A pint is 568 ml (UK). Switch on for 473 ml (US).'}
          </span>
        </span>
        <Switch
          bind:checked={() => pints === 'us', (on) => void setPints(on)}
          labelledby="pints-label"
          describedby={admin ? 'pints-detail' : 'pints-detail amounts-admin'}
          disabled={!admin || network.offline}
        />
      </div>
    </div>
    {#if !admin}<p class="detail" id="amounts-admin">{ADMIN_ONLY}</p>{/if}
    {#if pintsProblem}<p class="warning-line" role="alert">{pintsProblem}</p>{/if}
  </section>
{/if}

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: var(--settings-width);
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

  .who {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .warning-line {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }
</style>
