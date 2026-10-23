<script lang="ts">
  // Import a recipe (spec section 6, "Recipe import, decided for 0.5"): the one box, then the
  // review, then Save. Everything the server reads is shown before anything is saved. Online
  // only; leaving the page just leaves (the draft that keeps it for 15 days comes with Drafts).
  import AlreadySheet from '$lib/components/import/AlreadySheet.svelte';
  import ImportStart from '$lib/components/import/ImportStart.svelte';
  import ReviewScreen from '$lib/components/import/ReviewScreen.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { ImportFlow } from '$lib/import.svelte';

  const flow = new ImportFlow();
  let phone = $state(matchMedia('(max-width: 767px)').matches);

  $effect(() => {
    const media = matchMedia('(max-width: 767px)');
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });
</script>

{#if flow.phase === 'review' && flow.review}
  <PageHeader
    title="Check before saving"
    parent={{ href: '/recipes', label: 'Recipes' }}
    subtitle="This is what Mealwright found. Nothing is saved until you choose."
  />
  <ReviewScreen {flow} {phone} />
{:else}
  <PageHeader title="Import a recipe" parent={{ href: '/recipes', label: 'Recipes' }} />
  <ImportStart {flow} />
{/if}

{#if flow.already}
  <AlreadySheet
    already={flow.already}
    busy={flow.phase === 'reading'}
    oncopy={() => void flow.read(true)}
    onclose={() => (flow.already = null)}
  />
{/if}
