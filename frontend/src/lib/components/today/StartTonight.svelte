<script lang="ts">
  import { fetchCode } from '#lib/lazyCode.svelte.js';
  import Icon from '../Icon.svelte';
  // "Start tonight at 21:00" (M3, F124; cabledrawer 31 Oct and 9 Nov, mockup TodayTonight08): the plan
  // works backwards. A recipe whose long wait has a start time of today (or earlier, and not
  // begun) shows here with what to start, for which meal, and two buttons: Start it in Cook mode,
  // and Done already (the wait is marked begun at this moment; Undo is in the toast). In the app
  // only: nothing is sent and nothing sounds. Loaded when there is one to show (size limit).
  // Words: docs/dev/words.md section 58 (the mockup's are agreed, the rest proposed, for cabledrawer).
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { markStarted } from '#lib/startNow.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { timeWords } from '#lib/timeWords.js';
  import {
    forMeal,
    kindName,
    startOptionWords,
    startWords,
    stepTitle,
    waitRange,
    type StartEntry
  } from '#lib/startWords.js';
  import { itemName } from '#lib/planMeals.js';
  import type { Plan } from '#lib/client/plan.js';

  let {
    entry,
    plan,
    today,
    slotName,
    disabled = false,
    onchanged
  }: {
    entry: StartEntry;
    plan: Plan;
    today: string;
    slotName: string;
    /** The server can't be reached: the buttons wait (as every answer on Today). */
    disabled?: boolean;
    /** Marked begun: Today is read again. */
    onchanged: () => void;
  } = $props();

  const uid = $props.id();
  const ahead = $derived(entry.ahead);
  const name = $derived(itemName(entry.item, plan));
  /** "Start tonight at 21:00"; a start that has gone by without being marked says "Start now". */
  const heading = $derived(entry.day < today ? 'Start now' : startWords(entry.time));
  const late = $derived(
    entry.day < today ? `You planned to start ${startOptionWords(entry.day, entry.time)}.` : null
  );
  const readyBy = $derived(
    `Start by ${entry.time} so it’s ready by ${ahead.eats_at}.` // proposed, for cabledrawer
  );

  async function cookMode() {
    if (entry.item.recipe?.removed || !entry.item.recipe) return;
    const recipeId = entry.item.recipe.id;
    const code = await fetchCode(
      () => import('#lib/cookNow.svelte.js'),
      () => void cookMode()
    );
    if (!code) return;
    code.cookNow.open(recipeId, entry.meal.id, entry.item.id);
    const to = resolve('/(app)/recipes/[id]/cook', { id: String(recipeId) });
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- resolved above; only the query is added
    await goto(`${to}?meal=${entry.meal.id}&day=${entry.meal.date}`);
  }

  async function doneAlready() {
    const outcome = await markStarted(entry.item.id, name);
    if (outcome.ok) {
      kitchen.changed();
      onchanged();
    }
  }
</script>

<section class="card" aria-labelledby="{uid}-t" data-testid="start-tonight">
  <div class="row">
    <h2 id="{uid}-t">{heading}</h2>
    <span class="wt"
      ><Icon name="clock" size={14} stroke={2.4} />{kindName(ahead.wait.kind)} · {waitRange(
        ahead.wait
      )}</span
    >
  </div>
  <div class="words">
    <span class="title">{stepTitle(ahead.step_text)}</span>
    <span class="sub"
      >For {forMeal(entry.meal.date, slotName)} · {name}{ahead.active_minutes
        ? ` · ${timeWords(ahead.active_minutes)} of work`
        : ''}</span
    >
  </div>
  <span class="note">{late ?? readyBy}</span>
  <ButtonRow>
    <Button outline {disabled} onclick={() => void doneAlready()}>Done already</Button>
    <Button {disabled} onclick={() => void cookMode()}>Start it in Cook mode</Button>
  </ButtonRow>
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6);
    border: 1px solid var(--color-wait-border);
    border-radius: var(--radius-xl, 18px);
    background: var(--color-wait-card);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  h2 {
    margin: 0;
    color: var(--color-wait-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .wt {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: var(--radius-full);
    background: var(--color-wait-chip);
    color: var(--color-wait-text);
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .title {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }
</style>
