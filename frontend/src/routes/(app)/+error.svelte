<script lang="ts">
  // A page that could not be shown, inside the normal frame (the menu stays). The usual cause
  // is a page whose code can't be fetched: the server is down and this device hasn't saved
  // that page yet (F86, cabledrawer 30 Oct). Then it says what the other pages say, chosen by the
  // cause (downWords.ts). It never shows a bare "500 Internal Error".
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import { downTitle } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';

  // Ask our own server whether it is there, so the words fit the cause. Until it has answered
  // (or something else has already said the server is down) nothing is said: no wrong first
  // words that change a few seconds later.
  let asked = $state(false);
  let trying = $state(false);
  onMount(() => {
    void network.check().finally(() => (asked = true));
  });

  /** Try again: reload only once the server answers. While it is still down, a reload would
   *  load the proxy's bare page and lose the app, so the note and the menu stay. */
  async function tryAgain() {
    trying = true;
    await network.check();
    trying = false;
    if (!network.down) location.reload();
  }

  /** The note appears after the first check: the screen reader hears it, and focus is on it. */
  let heading = $state<HTMLElement>();
  $effect(() => {
    if (heading) heading.focus();
  });

  const down = $derived(network.down || network.deviceOffline);
  const device = $derived(network.deviceOffline);
  const title = $derived(down ? downTitle(device) : 'Something went wrong.');
  const body = $derived(
    down
      ? `This page isn’t on this device yet. Try again ${device ? 'when you’re back online' : 'when it answers'}. Your shopping list works offline.`
      : 'This page didn’t open. Try again.'
  );
</script>

<svelte:head>
  <title
    >{!asked && !down
      ? 'Mealwright'
      : `${down ? 'Can’t reach your server' : 'Something went wrong'} · Mealwright`}</title
  >
</svelte:head>

{#if asked || down}
  <section class="note" aria-labelledby="error-title">
    <h1 id="error-title" tabindex="-1" bind:this={heading}>{title}</h1>
    <p>{body}</p>
    <div class="buttons">
      <button type="button" class="again" disabled={trying} onclick={() => void tryAgain()}
        >Try again</button
      >
      <a class="shopping" href={resolve('/(app)/shopping')}>Shopping</a>
    </div>
  </section>
{/if}

<style>
  .note {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    max-width: 860px;
    padding: var(--space-8);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  h1 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .again,
  .shopping {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 54px;
    padding: 0 var(--space-8);
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .again {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    border: 0;
    cursor: pointer;
  }

  .shopping {
    background: transparent;
    color: var(--color-text);
    border: 1px solid var(--color-border-strong);
  }

  @media (min-width: 768px) {
    .note {
      padding: 28px;
    }
  }
</style>
