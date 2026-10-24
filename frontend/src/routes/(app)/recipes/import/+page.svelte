<script lang="ts">
  // Import a recipe (spec section 6, "Recipe import, decided for 0.5"): the one box, then the
  // review, then Save. Everything the server reads is shown before anything is saved. Online
  // only; leaving the page just leaves (the draft that keeps it for 15 days comes with Drafts).
  import AlreadySheet from '$lib/components/import/AlreadySheet.svelte';
  import ImportStart from '$lib/components/import/ImportStart.svelte';
  import ImportSteps from '$lib/components/import/ImportSteps.svelte';
  import ReviewScreen from '$lib/components/import/ReviewScreen.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { ImportFlow } from '$lib/import.svelte';
  import { network } from '$lib/network.svelte';
  import { privacy } from '$lib/privacy.svelte';
  import { onMount } from 'svelte';

  const flow = new ImportFlow();

  // The box's note about photos needs to know whether that switch is on. It reads it through
  // Settings → Privacy's own client; if that can't be had, the box shows no note.
  onMount(() => {
    void privacy.load();
  });
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void privacy.load();
    }
  });
  let phone = $state(matchMedia('(max-width: 767px)').matches);

  $effect(() => {
    const media = matchMedia('(max-width: 767px)');
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });
</script>

<!-- A phone says "Step 1 of 3" under the title; a computer has the three steps beside it
     (mockups Import05-Phone, Import05-Desktop and their review screens). -->
{#if flow.phase === 'review' && flow.review}
  {#if phone}
    <PageHeader
      title="Check before saving"
      parent={{ href: '/recipes', label: 'Recipes' }}
      subtitle="Step 2 of 3"
    />
  {:else}
    <PageHeader title="Check before saving" parent={{ href: '/recipes', label: 'Recipes' }}>
      {#snippet actions()}<ImportSteps step={2} pasted={flow.review?.source.kind} />{/snippet}
    </PageHeader>
  {/if}
  <ReviewScreen {flow} {phone} />
{:else}
  {#if phone}
    <PageHeader
      title="Import a recipe"
      parent={{ href: '/recipes', label: 'Recipes' }}
      subtitle="Step 1 of 3"
    />
  {:else}
    <PageHeader title="Import a recipe" parent={{ href: '/recipes', label: 'Recipes' }}>
      {#snippet actions()}<ImportSteps step={1} />{/snippet}
    </PageHeader>
  {/if}
  <ImportStart {flow} photosOff={privacy.photosOff} />
{/if}

{#if flow.already}
  <AlreadySheet
    already={flow.already}
    busy={flow.phase === 'reading'}
    oncopy={() => void flow.read(true)}
    onclose={() => (flow.already = null)}
  />
{/if}
