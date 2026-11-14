<script lang="ts">
  // Settings → Your data → Import from Mealie (0.9.5, cabledrawer 13 Nov; mockups
  // Dark-Mealie{Start,Preview,Running,Done}095-Phone and Dark-MealieImport095-Desktop): Mealie's
  // backup file is read on the server and shown before anything is added; "Bring in" runs on
  // the server, so the screen can be left; one Undo for the whole import, for 7 days.
  //
  // A phone (and a narrow window) has the simple screens; a computer has the four steps with
  // the recipe table, its tick boxes, chips and search. The computer's screen is fetched the
  // first time it's needed, so a phone never loads it. Online only: the file goes to the server.
  import { onDestroy, onMount } from 'svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import MealiePhone from '#lib/components/mealie/MealiePhone.svelte';
  import { MealieFlow } from '#lib/mealieFlow.svelte.js';
  import { network } from '#lib/network.svelte.js';

  /** The table needs room beside the sidebar: from here the computer's screen (proposed, for
   *  cabledrawer; below it, the phone's). */
  const WIDE = '(min-width: 1024px)';

  const flow = new MealieFlow();
  let wide = $state(matchMedia(WIDE).matches);
  $effect(() => {
    const media = matchMedia(WIDE);
    const onchange = () => (wide = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });

  onMount(() => {
    if (!network.offline) void flow.load();
  });
  onDestroy(() => flow.stop());

  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void flow.load();
    }
  });
</script>

<PageHeader
  title="Import from Mealie"
  parent={{ href: '/(app)/settings/your-data', label: 'Your data' }}
/>

{#if network.down && !flow.loaded}
  <OfflineNote screen="Settings" />
{:else if !flow.loaded}
  <p class="loading" aria-busy="true">Loading…</p>
{:else if wide}
  {#await import('#lib/components/mealie/MealieWide.svelte')}
    <p class="loading" aria-busy="true">Loading…</p>
  {:then { default: MealieWide }}
    <MealieWide {flow} />
  {:catch}
    <MealiePhone {flow} />
  {/await}
{:else}
  <MealiePhone {flow} />
{/if}

<style>
  .loading {
    color: var(--color-text-muted);
  }
</style>
