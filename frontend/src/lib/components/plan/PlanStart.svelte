<script lang="ts">
  // "When will you start it?" (M3, F124; cabledrawer 9 Nov, mockup PlanStart08): the times offered
  // (Fri 21:00 · ready by 08:00), Another time…, and "Add to plan" (or "Save", when the meal's
  // time is being changed). Shown over everything by the app layout, fetched when first asked
  // (size limit); startAsk.svelte.ts holds the question. A bottom sheet on a phone, a dialog on
  // a computer. Words are in docs/dev/words.md section 58: the mockup's are agreed, the rest is
  // proposed, for cabledrawer.
  import { BAD_DATE, isSaneDay } from '#lib/dates.js';
  import { startAsk } from '#lib/startAsk.svelte.js';
  import {
    hasToWords,
    isLate,
    lateWords,
    readyAt,
    startOptionWords,
    startWords,
    waitRange
  } from '#lib/startWords.js';

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  /** The option ticked ("2026-11-13 21:00"), or "other". */
  let picked = $state('');
  let otherDay = $state('');
  let otherTime = $state('');
  let problem = $state<string | null>(null);

  const pending = $derived(startAsk.current);
  const question = $derived(pending?.question);
  const keyOf = (day: string, time: string) => `${day} ${time}`;

  /** The times on offer: the meal's own time first when it is not one of the suggestions. */
  const choices = $derived.by(() => {
    if (!question) return [];
    const list = question.options.map((o) => ({
      day: o.day,
      time: o.time,
      note: `ready by ${o.ready_by}`
    }));
    const now = question.current;
    if (now && !list.some((o) => o.day === now.day && o.time === now.time)) {
      list.unshift({ day: now.day, time: now.time, note: 'as it is now' });
    }
    return list;
  });

  $effect(() => {
    if (question) {
      const now = question.current;
      const first = choices[0];
      const start = now ?? first;
      picked = start ? keyOf(start.day, start.time) : 'other';
      otherDay = start?.day ?? question.day;
      otherTime = start?.time ?? '';
      problem = null;
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  });

  /** What Today says for the time on screen: "Start tonight at 21:00", or "Start at 07:00" in the
   *  morning (the "day before" only fits the evening). */
  const startHint = $derived.by(() => {
    const time = (picked === 'other' ? otherTime : picked.split(' ')[1]) || '21:00';
    return { words: startWords(time), evening: Number(time.slice(0, 2)) >= 17 };
  });

  /** When the start on screen is ready, if that can't be by the meal (F228): an offered time
   *  says when it is ready itself; any other is the start, the shortest wait and the work. */
  const late = $derived.by(() => {
    if (!question) return null;
    const meal = { day: question.day, time: question.eatsAt };
    let ready: { day: string; time: string } | null = null;
    const offered = question.options.find((o) => keyOf(o.day, o.time) === picked);
    if (offered) {
      ready = { day: offered.ready_by_day, time: offered.ready_by };
    } else {
      const [day, time] = picked === 'other' ? [otherDay, otherTime] : picked.split(' ');
      if (day && time) {
        ready = readyAt(day, time, question.wait.min_minutes + (question.activeMinutes ?? 0));
      }
    }
    return ready && isLate(ready, meal) ? lateWords(ready) : null;
  });

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!question) return;
    let day: string;
    let time: string;
    if (picked === 'other') {
      day = otherDay;
      time = otherTime;
      if (!day || !time) {
        problem = 'Pick a day and a time.'; // proposed, for cabledrawer
        return;
      }
      if (!isSaneDay(day)) {
        problem = BAD_DATE;
        return;
      }
      // Before the meal (the server says the same).
      if (keyOf(day, time) >= keyOf(question.day, question.eatsAt)) {
        problem = 'Pick a time before the meal.'; // proposed, for cabledrawer
        return;
      }
    } else {
      [day, time] = picked.split(' ') as [string, string];
    }
    startAsk.answer({ day, time });
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    startAsk.dismiss();
  }}
  data-testid="plan-start"
>
  {#if question}
    <form onsubmit={submit}>
      <span class="handle" aria-hidden="true"></span>
      <header>
        <h2 id="{uid}-title">{question.recipeName} · {question.where}</h2>
        <p class="sub">{question.eatsWords}</p>
      </header>
      <div class="first">
        <span class="has">{hasToWords(question.wait.kind)}</span>
        <span class="wt"
          ><svg
            aria-hidden="true"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.4"
            stroke-linecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg
          >{waitRange(question.wait)}</span
        >
      </div>
      <fieldset>
        <legend>When will you start it?</legend>
        <div class="times">
          {#each choices as choice (keyOf(choice.day, choice.time))}
            <label class="time">
              <input
                type="radio"
                name="{uid}-start"
                value={keyOf(choice.day, choice.time)}
                bind:group={picked}
              />
              <b>{startOptionWords(choice.day, choice.time)}</b>
              <span>{choice.note}</span>
            </label>
          {/each}
        </div>
        {#if picked === 'other'}
          <div class="other">
            <label>
              Day
              <input type="date" bind:value={otherDay} max={question.day} required />
            </label>
            <label>
              Time
              <input type="time" bind:value={otherTime} required />
            </label>
          </div>
          {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
        {:else}
          <button type="button" class="another" onclick={() => (picked = 'other')}
            >Another time…</button
          >
        {/if}
        {#if late}<p class="problem" role="status" data-testid="plan-start-late">{late}</p>{/if}
        <p class="hint">
          {startHint.evening ? 'The day before, ' : ''}Today and the Cook view say “{startHint.words}”.
          You can change the time from the meal.
        </p>
      </fieldset>
      <button type="submit" class="main">{question.button}</button>
      {#if question.adding}
        <!-- proposed, for cabledrawer -->
        <button type="button" class="quiet" onclick={() => startAsk.skip()}>No time yet</button>
      {/if}
      <button type="button" class="quiet" onclick={() => startAsk.dismiss()}>Cancel</button>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    overscroll-behavior: contain;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .first {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .has {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
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

  fieldset {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    border: none;
  }

  legend {
    padding: 0;
    margin-bottom: var(--space-4);
    color: var(--color-text-muted);
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
  }

  .times {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }

  .time {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 56px;
    padding: 0 var(--space-3);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    cursor: pointer;
  }

  .time input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  .time:has(input:checked) {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .time:has(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .time b {
    font-size: var(--text-lg);
  }

  .time span {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .time:has(input:checked) span {
    color: inherit;
  }

  .another {
    min-height: var(--touch-target);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  .other {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }

  .other label {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .other input {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .problem {
    margin: 0;
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  button {
    min-height: 52px;
    border-radius: var(--radius-full);
    font: var(--weight-bold) var(--text-xl) var(--font-ui);
    cursor: pointer;
  }

  .another {
    border-radius: var(--radius-md);
    font-size: var(--text-lg);
  }

  .main {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .quiet {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text);
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: min(680px, calc(100dvh - 120px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }

    .handle {
      display: none;
    }
  }
</style>
