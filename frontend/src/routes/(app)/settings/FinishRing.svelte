<script lang="ts">
  // The Finish setup row's picture: a part-filled amber ring (cabledrawer 13 Nov, option A; mockup
  // Dark-FinishSetup095-Phone). Drawn only, so it is hidden from a screen reader: the row says
  // "2 of 5" in words beside it.
  import { ringArc, SETUP_STEPS } from './finishRing.js';

  let {
    done,
    of = SETUP_STEPS.length,
    size = 22
  }: { done: number; of?: number; size?: number } = $props();
  const arc = $derived(ringArc(done, of));
</script>

<svg
  aria-hidden="true"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke-linecap="round"
  data-ring={arc === null ? 'empty' : 'part'}
>
  <circle cx="12" cy="12" r="8.5" stroke="var(--color-caution-border)" stroke-width="3" />
  {#if arc}<path d={arc} stroke="currentColor" stroke-width="3" />{/if}
</svg>
