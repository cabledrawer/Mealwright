<script lang="ts">
  // Batch cook mode for one session (spec section 6, "Batch cook (Experimental)"): Cook mode for
  // several recipes at once, then one Cooked it for all of them. Full screen, over the app's own
  // menus. Opened from the Plan's Batch cook card. Timers and what is done are kept on the server,
  // so leaving, a reload or another phone carries on where it was; two phones agree through the
  // live updates. It loads on first use (the page size limit).
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { BatchModeModel } from '#lib/batchMode.svelte.js';
  import BatchMode from '#lib/components/cook/BatchMode.svelte';
  import { CookReview } from '#lib/cookReview.svelte.js';
  import { cookedTitle } from '#lib/cookTargets.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { dayShort, dayWords } from '#lib/planDates.js';
  import { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';

  const id = $derived(Number(page.params.id));
  const model = untrack(() => new BatchModeModel(Number(page.params.id)));
  const awake = new ScreenAwake();
  const review = new CookReview();
  let confirmed = false;

  /** "Sun 15 Nov". */
  function dayOf(iso: string): string {
    const month = new Date(`${iso}T12:00:00Z`).toLocaleString('en-GB', {
      month: 'short',
      timeZone: 'UTC'
    });
    return `${dayShort(iso)} ${dayWords(iso).split(' ')[1]} ${month}`;
  }

  onMount(() => {
    model.start();
    void model.load();
    if (awake.supported) void awake.set(true);
    // Back online: what was marked while offline is sent.
    const online = () => void model.flush();
    window.addEventListener('online', online);
    return () => window.removeEventListener('online', online);
  });

  // Another phone marked something (or this one's own change came back): ask again.
  let heard = untrack(() => live.batchCook);
  $effect(() => {
    const now = live.batchCook;
    if (now === heard) return;
    heard = now;
    untrack(() => void model.refresh());
  });
  $effect(() => {
    if (!network.offline) untrack(() => void model.flush());
  });

  function exit() {
    void goto(resolve('/(app)/plan'));
  }

  function openCooked() {
    const schedule = model.schedule;
    if (!schedule) return;
    // What was cooked already on its own, or removed, is left out and said so (review B3 r1).
    const left = schedule.recipes.filter((r) => r.left_out);
    const todo = schedule.recipes.filter((r) => !r.left_out);
    if (todo.length === 0) {
      toasts.show('Everything in this batch cook was already cooked.'); // proposed, for cabledrawer
      return;
    }
    void review.open({
      title: `Cooked it · ${dayOf(schedule.cook_day)}`,
      subtitle: cookedTitle(todo.map((r) => r.recipe_name)),
      already: left.map((r) => ({ name: r.recipe_name, why: r.left_out as 'cooked' | 'removed' })),
      mealId: null,
      sessionId: id,
      parts: todo.map((r) => ({
        itemId: null,
        batchId: r.batch_id,
        name: r.recipe_name
      }))
    });
  }

  function closeCooked() {
    review.close();
    if (confirmed) exit();
  }

  onDestroy(() => {
    model.stop();
    void awake.leave();
  });
</script>

<BatchMode {model} {awake} onexit={exit} oncooked={openCooked} />

<!-- Cooked it is only needed at the end: it loads when it is first opened (size limit). -->
{#if review.target}
  {#await import('#lib/components/cooked/SessionCooked.svelte') then { default: SessionCooked }}
    <SessionCooked
      {review}
      onclose={closeCooked}
      onconfirmed={() => {
        confirmed = true;
        closeCooked();
      }}
    />
  {/await}
{/if}
