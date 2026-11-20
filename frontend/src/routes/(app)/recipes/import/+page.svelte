<script lang="ts">
  // Import a recipe (spec section 6, "Recipe import, decided for 0.5"): the one box, then the
  // review, then Save. Everything the server reads is shown before anything is saved. Online
  // only; leaving the review without saving asks "Save as draft?" (ReviewScreen).
  import Button from '#lib/components/Button.svelte';
  import AlreadySheet from '#lib/components/import/AlreadySheet.svelte';
  import ImportStart from '#lib/components/import/ImportStart.svelte';
  import ImportSteps from '#lib/components/import/ImportSteps.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { loadReviewPage, REVIEW_LOAD_FAILED } from '#lib/components/import/loadReviewPage.js';
  import { ImportFlow } from '#lib/import.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { privacy } from '#lib/privacy.svelte.js';
  import { onMount } from 'svelte';
  import { PHONE_QUERY } from '#lib/layout.js';

  const flow = new ImportFlow();

  // The Check screen loads when the reading starts, so it has usually come by the time the answer
  // does (loadReviewPage.ts).
  $effect(() => {
    if (flow.phase !== 'start') void loadReviewPage();
  });

  // The box's note about photos needs to know whether that switch is on. It reads it through
  // Settings › Outside connections's own client; if that can't be had, the box shows no note.
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
  let phone = $state(matchMedia(PHONE_QUERY).matches);

  $effect(() => {
    const media = matchMedia(PHONE_QUERY);
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });
</script>

<!-- A phone says "Step 1 of 3" under the title; a computer has the three steps beside it
     (mockups Import05-Phone, Import05-Desktop and their review screens). -->
{#if flow.phase === 'review' && flow.review}
  {#await loadReviewPage()}
    <PageHeader title="Check before saving" parent={{ href: '/(app)/recipes', label: 'Recipes' }} />
  {:then { default: ReviewPage }}
    <ReviewPage {flow} {phone} />
  {:catch}
    <PageHeader title="Check before saving" parent={{ href: '/(app)/recipes', label: 'Recipes' }} />
    <div class="failed" role="alert">
      <p>{REVIEW_LOAD_FAILED}</p>
      <Button small quiet onclick={() => location.reload()}>Try again</Button>
    </div>
  {/await}
{:else}
  {#if phone}
    <PageHeader
      title="Import a recipe"
      parent={{ href: '/(app)/recipes', label: 'Recipes' }}
      subtitle="Step 1 of 3"
    />
  {:else}
    <PageHeader
      title="Import a recipe"
      parent={{ href: '/(app)/recipes', label: 'Recipes' }}
      dropActions
    >
      {#snippet actions()}<ImportSteps step={1} />{/snippet}
    </PageHeader>
  {/if}
  <ImportStart {flow} photosOff={privacy.photosOff} linksOff={privacy.linksOff} />
{/if}

{#if flow.already}
  <AlreadySheet
    already={flow.already}
    busy={flow.phase === 'reading'}
    oncopy={() => void flow.read(true)}
    onclose={() => (flow.already = null)}
  />
{/if}

<style>
  .failed {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    color: var(--color-text-muted);
  }
</style>
