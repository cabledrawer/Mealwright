<script lang="ts">
  // "Always show whether you're connected" (UX principle 16, mockups Shop and Desktop-Shop).
  //   phone:   a bar above the bottom tabs: "Offline" and Try now;
  //   desktop: at the foot of the sidebar: "Offline" and Try now, under it a line about
  //            changes waiting when there are some;
  //   dot:     the collapsed sidebar: a small dot that is also the Try now button.
  // Nothing shows while connected, or for a blip (network.svelte.ts). The live region is
  // always on the page, so screen readers hear "Offline" when it appears.
  import { network, offlineText } from '#lib/network.svelte.js';

  let { layout }: { layout: 'phone' | 'desktop' | 'dot' } = $props();

  // The word follows the cause, like the page notes (cabledrawer 30 Oct): "Offline" or "Can’t
  // reach server".
  const text = $derived(
    offlineText(layout === 'phone' ? 'phone' : 'desktop', network.waiting, network.deviceOffline)
  );
  // The folded sidebar has no room for the line about waiting changes, so the dot says it (F252).
  const dotLabel = $derived(
    text.detail ? `${text.title}. ${text.detail} Try now` : `${text.title}. Try now`
  );
</script>

<div
  class="status {layout}"
  role="status"
  data-testid={`connection-${layout}`}
  hidden={!network.offline}
>
  {#if network.offline}
    {#if layout === 'dot'}
      <button
        type="button"
        class="dot-button"
        aria-label={dotLabel}
        title={dotLabel}
        disabled={network.trying}
        onclick={() => void network.tryNow()}
      >
        <span class="dot" aria-hidden="true"></span>
      </button>
    {:else}
      <div class="line">
        <span class="dot" aria-hidden="true"></span>
        <span class="title">{text.title}</span>
        <button
          type="button"
          class="try"
          disabled={network.trying}
          onclick={() => void network.tryNow()}
        >
          Try now
        </button>
      </div>
      {#if text.detail}<p class="detail">{text.detail}</p>{/if}
    {/if}
  {/if}
</div>

<style>
  .status[hidden] {
    display: none;
  }

  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: var(--radius-full);
    background: var(--color-offline-dot);
  }

  .line {
    display: flex;
    align-items: center;
    gap: var(--space-5);
  }

  .title {
    flex: 1;
    min-width: 0;
    font-weight: var(--weight-semibold);
  }

  .try,
  .dot-button {
    border: none;
    background: transparent;
    font-family: inherit;
    cursor: pointer;
  }

  .try {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    color: var(--color-offline-action);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .try:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .try:hover,
  .dot-button:hover {
    text-decoration: underline;
  }

  /* Phone: a full-width bar between the page and the bottom tabs. */
  .phone {
    position: fixed;
    inset: auto 0 calc(var(--tabbar-height) + env(safe-area-inset-bottom)) 0;
    z-index: 9;
    box-sizing: border-box;
    min-height: var(--connection-bar-height);
    padding: 0 var(--space-4) 0 var(--space-8);
    background: var(--color-offline);
    border-top: 1px solid var(--color-border);
    color: var(--color-text);
    font-size: var(--text-base);
  }

  .phone .line {
    min-height: var(--connection-bar-height);
  }

  /* Desktop: a quiet panel at the foot of the sidebar. */
  .desktop {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-offline);
    border: 1px solid var(--color-border);
    color: var(--color-text);
  }

  .desktop .title {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .detail {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  /* Collapsed sidebar: only the dot, in a full-size touch target. */
  .dot-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border-radius: var(--radius-md);
  }

  .dot-button .dot {
    background: var(--color-text-muted);
    width: 10px;
    height: 10px;
  }

  @media (forced-colors: active) {
    .dot {
      background: CanvasText;
    }
  }

  /* Not on paper. */
  @media print {
    .status {
      display: none;
    }
  }
</style>
