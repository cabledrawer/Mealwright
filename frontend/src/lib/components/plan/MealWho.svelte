<script lang="ts">
  // Who's eating this meal (0.7 P1; spec "The Plan redesign", F57). Proposed, for cabledrawer: by
  // sign-in (the household's logins, as tubs already are) until member profiles arrive in 0.8.
  // Nothing ticked means everyone. A few quick taps are one change, sent a moment after the last
  // tap (or when the menu closes), so there is one Undo.
  import { onDestroy } from 'svelte';
  import type { PlanMeal } from '#lib/client/plan.js';
  import type { PlanModel } from '#lib/plan.svelte.js';

  let {
    model,
    meal,
    disabled = false
  }: { model: PlanModel; meal: PlanMeal; disabled?: boolean } = $props();

  /** The ticked people while taps are waiting to be sent (null: none waiting). */
  let draft = $state<number[] | null>(null);
  // The meal as the plan holds it now (the menu's own copy goes stale after a change).
  const live = $derived(model.plan?.meals.find((m) => m.id === meal.id) ?? meal);
  const ticked = $derived(draft ?? live.eater_member_ids);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function send(): void {
    clearTimeout(timer);
    timer = undefined;
    const wanted = draft;
    draft = null;
    if (wanted === null) return;
    const now = [...live.eater_member_ids].sort((a, b) => a - b);
    if (wanted.length !== now.length || wanted.some((id, i) => id !== now[i]))
      void model.setEaters(live, wanted);
  }

  function set(next: number[]): void {
    // Everyone ticked one by one is the same as nobody in particular.
    draft = (next.length >= model.people.length ? [] : next).sort((a, b) => a - b);
    clearTimeout(timer);
    timer = setTimeout(send, 700);
  }

  const toggle = (id: number) =>
    set(ticked.includes(id) ? ticked.filter((i) => i !== id) : [...ticked, id]);

  onDestroy(() => {
    if (timer !== undefined) send();
  });
</script>

{#if model.people.length > 1}
  <div class="who" role="group" aria-label="Who’s eating?">
    <strong>Who’s eating?</strong>
    <div class="chips">
      <button type="button" aria-pressed={ticked.length === 0} {disabled} onclick={() => set([])}
        >Everyone</button
      >
      {#each model.people as person (person.member_id)}
        <button
          type="button"
          aria-pressed={ticked.includes(person.member_id)}
          {disabled}
          onclick={() => toggle(person.member_id)}>{person.name}</button
        >
      {/each}
    </div>
  </div>
{/if}

<style>
  .who {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  strong {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
