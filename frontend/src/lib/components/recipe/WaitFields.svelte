<script lang="ts">
  // The boxes for one step's wait (M1; the Waits field in the recipe editor and "Change" on Check):
  // what it is for, the shortest and longest length, and "ends overnight". It writes `wait` each
  // time the boxes make a wait that can be kept, and says what is wrong when they don't. Words
  // are proposed, for cabledrawer (docs/dev/words.md, steps that wait).
  import '#lib/styles/fields.css';
  import Switch from '../Switch.svelte';
  import { WAIT_KINDS, type StepWait } from '#lib/timeWords.js';

  let {
    wait = $bindable(),
    name,
    invalid = $bindable(),
    onchange
  }: {
    wait: StepWait;
    /** "step 2": what the boxes are for, read aloud. */
    name: string;
    /** True while the boxes don't make a wait that can be kept: the caller blocks Save/Done. */
    invalid?: boolean | undefined;
    /** Called after the boxes made a wait that can be kept. */
    onchange?: () => void;
  } = $props();

  const uid = $props.id();
  const MOST = 14_400;
  const OVERNIGHT = 720;

  type Unit = 'min' | 'h' | 'day';
  const PER: Record<Unit, number> = { min: 1, h: 60, day: 1440 };

  /** The unit that shows a length without a fraction: days, then hours, else minutes. */
  function unitOf(...lengths: number[]): Unit {
    if (lengths.every((n) => n % 1440 === 0)) return 'day';
    if (lengths.every((n) => n % 60 === 0)) return 'h';
    return 'min';
  }

  // The boxes start with the wait as it is now, and are typed in from there.
  const start = wait;
  const startUnit = unitOf(start.min_minutes, start.overnight ? 1440 : start.max_minutes);
  let unit = $state<Unit>(startUnit);
  let from = $state(String(start.min_minutes / PER[startUnit]));
  let to = $state(
    !start.overnight && start.max_minutes > start.min_minutes
      ? String(start.max_minutes / PER[startUnit])
      : ''
  );
  let overnight = $state(start.overnight);
  let kind = $state(start.kind);
  let problem = $state('');

  function number(text: string): number | null {
    const t = text.trim().replace(',', '.');
    if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
    return Math.round(Number(t) * PER[unit]);
  }

  function commit() {
    const low = number(from);
    const high = to.trim() === '' ? low : number(to);
    if (low === null || low < 1 || high === null || low > MOST || high > MOST) {
      problem = 'Type how long it waits, such as 4 hours.';
      invalid = true;
      return;
    }
    if (high < low) {
      problem = 'The longest can’t be shorter than the shortest.';
      invalid = true;
      return;
    }
    problem = '';
    invalid = false;
    wait = {
      kind,
      min_minutes: low,
      max_minutes: overnight ? Math.max(high, OVERNIGHT) : high,
      overnight
    };
    onchange?.();
  }
</script>

<div class="wait">
  <label class="field" for="{uid}-kind">
    <span class="mw-label">Waiting for<span class="visually-hidden">, {name}</span></span>
    <select id="{uid}-kind" class="mw-input" bind:value={kind} onchange={commit}>
      {#each WAIT_KINDS as k (k.kind)}<option value={k.kind}>{k.name}</option>{/each}
    </select>
  </label>
  <label class="field" for="{uid}-from">
    <span class="mw-label"
      >{to.trim() === '' && !overnight ? 'Length' : 'Shortest'}<span class="visually-hidden"
        >, {name}</span
      ></span
    >
    <input
      id="{uid}-from"
      class="mw-input num"
      type="text"
      inputmode="decimal"
      maxlength="6"
      aria-invalid={problem ? true : undefined}
      bind:value={from}
      oninput={commit}
    />
  </label>
  <label class="field" for="{uid}-to">
    <span class="mw-label"
      >Longest <span class="mw-optional">(if it varies)</span><span class="visually-hidden"
        >, {name}</span
      ></span
    >
    <input
      id="{uid}-to"
      class="mw-input num"
      type="text"
      inputmode="decimal"
      maxlength="6"
      aria-invalid={problem ? true : undefined}
      bind:value={to}
      oninput={commit}
    />
  </label>
  <label class="field" for="{uid}-unit">
    <span class="mw-label">In<span class="visually-hidden">, {name}</span></span>
    <select id="{uid}-unit" class="mw-input" bind:value={unit} onchange={commit}>
      <option value="min">minutes</option>
      <option value="h">hours</option>
      <option value="day">days</option>
    </select>
  </label>
  <p class="over">
    <Switch bind:checked={overnight} labelledby="{uid}-over" onchange={commit} />
    <span id="{uid}-over">Ends overnight<span class="visually-hidden">, {name}</span></span>
  </p>
  {#if problem}<p class="mw-error problem" role="alert">{problem}</p>{/if}
</div>

<style>
  .wait {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-4);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .num {
    width: 6rem;
  }

  select.mw-input {
    width: auto;
  }

  .over {
    display: flex;
    flex: 1 1 100%;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .problem {
    flex: 1 1 100%;
    margin: 0;
  }
</style>
