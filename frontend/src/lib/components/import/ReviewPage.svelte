<script lang="ts">
  // The review's page: its header (a phone says "Step 2 of 3" under the title; a computer has the
  // three steps beside it, mockups Import05-Phone and Import05-Desktop) and the review itself.
  // Used by Import a recipe, and by a draft being carried on.
  import type { ComponentProps } from 'svelte';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import PageHeader from '../PageHeader.svelte';
  import ImportSteps from './ImportSteps.svelte';
  import ReviewScreen from './ReviewScreen.svelte';

  let {
    flow,
    phone,
    parent = { href: '/(app)/recipes', label: 'Recipes' }
  }: {
    flow: ImportFlow;
    phone: boolean;
    /** The page above this one: Recipes, or Drafts for a draft. */
    parent?: ComponentProps<typeof PageHeader>['parent'];
  } = $props();
</script>

{#if phone}
  <PageHeader title="Check before saving" {parent} subtitle="Step 2 of 3" />
{:else}
  <PageHeader title="Check before saving" {parent}>
    {#snippet actions()}<ImportSteps step={2} pasted={flow.review?.source.kind} />{/snippet}
  </PageHeader>
{/if}
<ReviewScreen {flow} {phone} />
