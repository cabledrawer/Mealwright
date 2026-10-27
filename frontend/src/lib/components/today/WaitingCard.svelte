<script lang="ts">
  // "Did you cook Sambar?" (mockups Main, Desktop-Today): a calm card for a planned meal whose
  // day has come, with Cooked it · Didn't · Move it. One card at a time: the newest meal first,
  // and a line saying how many more are waiting behind it. Nothing changes in the pantry until
  // it is answered (spec, "Meals nobody cooked"). The words are proposed, for cabledrawer.
  import type { TodayModel } from '#lib/today.svelte.js';
  import type { WaitingMeal } from '#lib/client/today.js';
  import { moreWords, whenWords } from '#lib/todayWords.js';

  let {
    model,
    waiting,
    oncooked,
    onmove
  }: {
    model: TodayModel;
    waiting: WaitingMeal;
    oncooked: () => void;
    onmove: () => void;
  } = $props();

  const uid = $props.id();
  const name = $derived(model.nameOf(waiting));
  const when = $derived(
    model.data
      ? `${whenWords(waiting.date, model.data.today)} · ${model.slotName(waiting.slot_id).toLowerCase()}`
      : ''
  );
</script>

<section class="card" aria-labelledby="{uid}-t" data-testid="did-you-cook">
  <div class="words">
    <span class="when">{when}</span>
    <span class="title" id="{uid}-t">Did you cook {name}?</span>
    <span class="note">Nothing changes in the pantry until you say.</span>
  </div>
  <div class="buttons">
    <button type="button" class="yes" disabled={model.readonly} onclick={oncooked}>Cooked it</button
    >
    <button type="button" disabled={model.readonly} onclick={() => void model.didnt(waiting)}
      >Didn’t</button
    >
    <button type="button" disabled={model.readonly} onclick={onmove}>Move it</button>
  </div>
  {#if model.readonly}
    <p class="offline" role="status">You’re offline. Today changes when you’re back online.</p>
  {/if}
  {#if model.moreWaiting}
    <p class="more">{moreWords(model.moreWaiting)}</p>
  {/if}
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-8);
    border: 1.5px solid #9fcdb4;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .when {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .title {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .buttons {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(5.5rem, 1fr));
    gap: var(--space-3);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-lg);
    background: var(--color-fill);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  button.yes {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .offline,
  .more {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }
</style>
