<script lang="ts">
  import Loading from '#lib/components/Loading.svelte';
  // Settings › Outside connections (spec section 7 and section 6, "Recipe import, decided for 0.5"):
  // the switches for outside connections, and "Your own network". Two places on it can be
  // linked to: #outside-connections (the import screen's "Photo not downloaded" and
  // "switched off" links) and #your-own-network.
  //
  // Everyone in the household sees it; only an admin changes it. Offline it shows what was
  // last loaded, and can't be changed.
  import { onMount, tick } from 'svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import OutsideConnections from '#lib/components/privacy/OutsideConnections.svelte';
  import OwnNetwork from '#lib/components/privacy/OwnNetwork.svelte';
  import { network } from '#lib/network.svelte.js';
  import { privacy } from '#lib/privacy.svelte.js';
  import { LEAD, type Locked } from '#lib/privacyWords.js';

  let text = $state('');

  const locked: Locked = $derived(
    !privacy.canChange ? 'member' : network.offline ? 'offline' : null
  );

  /** Landing on #outside-connections or #your-own-network: the answer comes after the page
   *  is drawn, so the browser's own jump to the heading has nothing to jump to yet. */
  async function scrollToAnchor() {
    let id: string;
    try {
      id = decodeURIComponent(location.hash.slice(1));
    } catch {
      return; // a hash that isn't valid text (#%E0): there is nowhere to jump to
    }
    if (!id) return;
    await tick();
    document.getElementById(id)?.scrollIntoView();
  }

  onMount(() => {
    void privacy.load().then(scrollToAnchor);
  });

  // The connection came back: look again, in case an admin changed something meanwhile.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void privacy.load();
    }
  });

  async function add() {
    if (await privacy.add(text)) text = '';
  }
</script>

<PageHeader
  title="Outside connections"
  overline="Household"
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

{#if !privacy.loaded}
  {#if network.down}
    <OfflineNote screen="Privacy" />
  {:else if privacy.problem}
    <p class="problem" role="alert">
      {privacy.problem}
      <button type="button" class="link" onclick={() => void privacy.load()}>Try again</button>
    </p>
  {:else}
    <Loading />
  {/if}
{:else}
  <div class="page">
    {#if privacy.problem && !network.offline}
      <p class="problem" role="alert">
        {privacy.problem}
        <button type="button" class="link" onclick={() => void privacy.load()}>Try again</button>
      </p>
    {/if}
    <p class="lead">{LEAD}</p>
    <div class="columns">
      <OutsideConnections
        values={privacy.switches}
        {locked}
        problem={privacy.switchProblem}
        onchange={(name, on) => void privacy.setSwitch(name, on)}
      />
      <OwnNetwork
        entries={privacy.entries}
        {locked}
        bind:value={text}
        problem={privacy.addProblem}
        removeProblem={privacy.removeProblem}
        removeNotice={privacy.removeNotice}
        adding={privacy.adding}
        onadd={() => void add()}
        onremove={(entry) => void privacy.remove(entry)}
      />
    </div>
  </div>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  .lead {
    max-width: 1100px; /* as wide as the two cards below (F75) */
    padding: 14px var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    line-height: 1.4;
  }

  /* One column on a phone; side by side on a computer, wrapping when it's too narrow
     (and at 200% text) for two. */
  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr));
    align-items: start;
    gap: var(--space-8) var(--space-9);
    max-width: 1100px;
  }

  .problem {
    max-width: var(--settings-width);
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }
</style>
