<script lang="ts" generics="P extends Record<string, any>">
  // A screen's code that is fetched when first wanted (the size limit), as one tag:
  //   <Lazy load={() => import('./Sheet.svelte')} open={open} onclose={close} />
  // Every other prop goes straight to the loaded component. If the fetch fails, the person
  // gets the toast "Couldn’t open that. Try again." with a real Try again button that fetches
  // again, and `onfail` runs so the ask can end as if cancelled (FE2, words.md §6).
  import type { Component } from 'svelte';
  import { couldntOpen } from '#lib/lazyCode.svelte.js';

  let {
    load,
    onfail,
    ...rest
  }: {
    load: () => Promise<{ default: Component<P> }>;
    onfail?: () => void;
  } & (string extends keyof P ? object : P) = $props();

  // The fetch starts when this is first shown, so a closed screen costs nothing.
  // svelte-ignore state_referenced_locally
  let code = $state.raw(start());

  function start(): Promise<Component<P> | null> {
    return load().then(
      (module) => module.default,
      () => {
        couldntOpen(() => (code = start()));
        onfail?.();
        return null;
      }
    );
  }
</script>

{#await code then Loaded}
  {#if Loaded}
    <Loaded {...(rest as unknown as P)} />
  {/if}
{/await}
