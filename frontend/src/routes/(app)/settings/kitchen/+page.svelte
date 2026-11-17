<script lang="ts">
  import { onMount } from 'svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import YourKitchen from '#lib/components/YourKitchen.svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import { batchCook } from '#lib/batchCook.svelte.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { getKitchen, type Kitchen } from '#lib/client/household.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';

  const admin = session.me?.role === 'admin';

  /** The kitchen's equipment for Batch cook (B1), once the server has said. */
  let kitchenNow = $state<Kitchen | null>(null);
  let kitchenOpen = $state(false);
  let kitchenOpener = $state<HTMLElement | null>(null);
  function readKitchen() {
    getKitchen().then(
      (found) => (kitchenNow = found),
      () => {} // offline or unreachable: the page stays empty, as Amounts does
    );
  }

  /** One string, so the two sentences always have their space between them (RF5). */
  const kitchenWords = $derived(
    'Batch cook never plans more at once than your kitchen has.' +
      (kitchenNow && !kitchenNow.asked
        ? ' Not asked yet: Batch cook asks the first time you use it.'
        : '')
  );

  /** An admin hides or shows Batch cook (Experimental); it flips back if the server can't take it. */
  let batchProblem = $state<string | null>(null);
  async function setBatchCook(on: boolean) {
    batchProblem = null;
    const before = batchCook.shown;
    batchCook.shown = on;
    try {
      await batchCook.set(on);
      kitchen.wroteSettings(); // Recent changes shows "Switched Batch cook off" (RF5, H8)
    } catch (error) {
      batchCook.shown = before;
      batchProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }

  onMount(() => {
    readKitchen();
    void batchCook.load();
  });
  // An Undo from Recent changes (or the toast) may have put the Batch cook switch or the kitchen's
  // equipment back: read them again (RF5, H8).
  let undoneSeen = kitchen.elsewhere;
  $effect(() => {
    if (kitchen.elsewhere === undoneSeen) return;
    undoneSeen = kitchen.elsewhere;
    readKitchen();
    void batchCook.load();
  });
  // Opened offline: the page fills in once the connection comes back.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      if (kitchenNow === null) readKitchen();
    }
  });
</script>

<PageHeader
  title="Your kitchen"
  overline="Kitchen"
  subtitle="Hob rings, pressure cookers and oven, for Batch cook."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

{#if network.down && kitchenNow === null}
  <OfflineNote screen="Settings" />
{/if}
{#if kitchenNow !== null}
  <section class="section" aria-label="Your kitchen">
    <div class="card" data-testid="your-kitchen">
      <div class="row">
        <span class="label">Hob rings</span><span class="value">{kitchenNow.hob_rings}</span>
      </div>
      <div class="row">
        <span class="label">Pressure cookers</span><span class="value"
          >{kitchenNow.pressure_cookers}</span
        >
      </div>
      <div class="row">
        <span class="label">Oven</span><span class="value">{kitchenNow.oven ? 'Yes' : 'No'}</span>
      </div>
      <div class="row">
        <span class="who">
          <span class="label" id="batch-label">Show Batch cook</span>
          <span class="detail" id="batch-detail">
            Experimental. Switched off, it leaves the sidebar and the Plan.
            {#if !admin}Only an admin can change this.{/if}
          </span>
        </span>
        <Switch
          bind:checked={() => batchCook.shown, (on) => void setBatchCook(on)}
          labelledby="batch-label"
          describedby="batch-detail"
          disabled={!admin || network.offline}
        />
      </div>
      {#if batchProblem}<p class="warning-line" role="alert">{batchProblem}</p>{/if}
      <div class="row">
        <span class="who">
          <span class="detail">{kitchenWords}</span>
        </span>
        <button
          type="button"
          class="change"
          disabled={network.offline}
          onclick={(event) => {
            kitchenOpener = event.currentTarget;
            kitchenOpen = true;
          }}>Change</button
        >
      </div>
    </div>
  </section>
  <YourKitchen
    open={kitchenOpen}
    kitchen={kitchenNow}
    onsaved={(saved) => {
      kitchenNow = saved;
      kitchen.wroteSettings(); // Recent changes shows "Changed your kitchen…" (RF5, H8)
      kitchenOpen = false;
      kitchenOpener?.focus();
    }}
    onclose={() => {
      kitchenOpen = false;
      kitchenOpener?.focus();
    }}
  />
{/if}

<style>
  .section {
    max-width: 760px;
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

  .value {
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }

  .change {
    min-height: var(--touch-target);
    padding: 0 18px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
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
