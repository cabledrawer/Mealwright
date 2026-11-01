<script lang="ts">
  // Cook mode for one recipe (spec section 6, "Cook mode"). Full screen, over the app's own
  // menus. Leaving with a timer running asks "Stop the timer and leave?" (Stay · Leave), also for
  // the browser's Back and for a link; closing the tab asks the browser's own question.
  import { beforeNavigate, goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { onDestroy, onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { getRecipe, type Recipe } from '#lib/client/recipes.js';
  import CookMode from '#lib/components/cook/CookMode.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import { cookPrefs } from '#lib/cookPrefs.svelte.js';
  import { CookTimers } from '#lib/cookTimers.svelte.js';
  import { ScreenAwake } from '#lib/screenAwake.svelte.js';

  const id = $derived(Number(page.params.id));
  const here = $derived(resolve('/(app)/recipes/[id]', { id: String(id) }));

  const timers = new CookTimers();
  const awake = new ScreenAwake();
  let cook = $state<ReturnType<typeof CookMode>>();
  let recipe = $state<Recipe | null>(null);
  let gone = $state(false);
  let problem = $state<string | null>(null);
  /** Set when the person has chosen to leave: the next navigation goes through. */
  let leaving = false;

  async function load() {
    try {
      recipe = await getRecipe(id);
      gone = false;
      problem = null;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) gone = true;
      else problem = cantReach(error) ? cantReachWords() : 'Couldn’t load this recipe. Try again.';
    }
  }
  onMount(() => void load());

  function exit() {
    leaving = true;
    void goto(here);
  }

  beforeNavigate((navigation) => {
    if (leaving || !timers.running) return;
    navigation.cancel();
    // A closed tab or a typed address can't be asked about here: the browser asks (cancel()
    // does that); any other way out is asked with our own question.
    const to = navigation.to?.url;
    if (navigation.willUnload || !to) return;
    cook?.leaveOr(() => {
      leaving = true;
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- the page the person was going to
      void goto(to);
    });
  });

  onDestroy(() => {
    timers.stopAll();
    void awake.leave();
  });
</script>

{#if recipe}
  <CookMode
    bind:this={cook}
    {recipe}
    {timers}
    {awake}
    perStep={cookPrefs.perStep}
    onperstep={(on) => cookPrefs.setPerStep(on)}
    onexit={exit}
  />
{:else if gone}
  <EmptyState title="Recipe not found">
    This recipe isn’t here any more. It may have been deleted.
  </EmptyState>
{:else if problem}
  <div class="failed" role="alert">
    <p>{problem}</p>
    <button type="button" onclick={() => void load()}>Try again</button>
  </div>
{:else}
  <p class="loading" aria-busy="true">Loading…</p>
{/if}

<style>
  .loading,
  .failed {
    color: var(--color-text-muted);
  }

  .failed button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
