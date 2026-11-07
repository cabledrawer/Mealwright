<script lang="ts">
  // Settings → Meal slots (spec "Settings (drawn 17 Oct)"; admins only, cabledrawer 7 Nov): switch a
  // meal on or off, rename it, put the meals in order, add one. No removing: switching off is
  // the way, and a switched-off meal keeps its planned meals. The server refuses anyone else.
  import { onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { getMealSlots, switchMealSlot, type MealSlot } from '#lib/client/plan.js';
  import { addMealSlot, orderMealSlots, renameMealSlot } from '#lib/client/settingsLists.js';
  import Switch from '#lib/components/Switch.svelte';
  import { nothingChanged } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { save } from '#lib/save.js';
  import OrderedRows from './OrderedRows.svelte';

  let slots = $state<MealSlot[]>([]);
  let loaded = $state(false);
  /** The server answered (so a problem is worth a Try again). */
  let reached = $state(true);
  let problem = $state<string | null>(null);
  let note = $state<string | null>(null);

  async function load() {
    try {
      slots = await getMealSlots();
      problem = null;
    } catch (error) {
      problem = cantReach(error) ? cantReachWords() : 'Couldn’t load your meals.';
      reached = !cantReach(error);
    } finally {
      loaded = true;
    }
  }
  onMount(() => void load());
  // Opened while the server couldn't be reached: fetch again once the connection is back.
  let seen = network.backAgain;
  $effect(() => {
    if (network.backAgain === seen) return;
    seen = network.backAgain;
    void load();
  });

  function wordsOf(error: unknown): string {
    return error instanceof ApiError && !cantReach(error)
      ? error.detail
      : nothingChanged(network.deviceOffline);
  }

  /** The undo of a plan write: the answer's change, put back, and the list read again. */
  function undoOf(label: string) {
    return {
      label,
      skip: (done: { change: { can_undo: boolean; id: number } | null }) => done.change === null,
      run: (done: { change: { can_undo: boolean; id: number } | null }) =>
        done.change?.can_undo ? serverUndo(done.change.id, () => void load())() : false
    };
  }

  function orderTo(ids: number[]) {
    const before = slots;
    void save({
      apply: () => (slots = ids.map((id) => before.find((s) => s.id === id)!)),
      rollback: () => (slots = before),
      send: (key) => orderMealSlots(ids, key),
      undo: undoOf('Changed the order of the meals')
    });
  }

  async function rename(slot: MealSlot, name: string): Promise<boolean> {
    note = null;
    const before = slots;
    return new Promise<boolean>((done) => {
      void save({
        apply: () => (slots = before.map((s) => (s.id === slot.id ? { ...s, name } : s))),
        rollback: () => (slots = before),
        send: (key) => renameMealSlot(slot.id, name, key),
        quiet: true,
        undo: undoOf(`Renamed ${slot.name} to ${name}`)
      }).then((outcome) => {
        if (!outcome.ok) note = wordsOf(outcome.error);
        done(outcome.ok);
      });
    });
  }

  function switchTo(slot: MealSlot, enabled: boolean) {
    const before = slots;
    void save({
      apply: () => (slots = before.map((s) => (s.id === slot.id ? { ...s, enabled } : s))),
      rollback: () => (slots = before),
      send: (key) => switchMealSlot(slot.id, enabled, key),
      undo: undoOf(`${enabled ? 'Showed' : 'Hid'} ${slot.name} in the plan`)
    });
  }

  let adding = $state(false);
  let name = $state('');
  async function add(event: Event) {
    event.preventDefault();
    const wanted = name.trim();
    if (!wanted) return;
    note = null;
    try {
      const slot = await addMealSlot(wanted);
      slots = [...slots, slot];
      name = '';
      adding = false;
    } catch (error) {
      note = wordsOf(error);
    }
  }
</script>

{#if problem}
  <p class="note" role="status">
    {problem}
    {#if reached}<button type="button" class="link" onclick={() => void load()}>Try again</button
      >{/if}
  </p>
{/if}

<div class="card">
  <p class="detail">
    Switch a meal off to hide it from the plan. Hidden meals keep what’s planned.
  </p>
  <OrderedRows
    items={slots}
    noun="meal"
    disabled={network.offline}
    onorder={orderTo}
    onrename={rename}
  >
    {#snippet after(slot)}
      <Switch
        label="Show {slot.name} in the plan"
        checked={slot.enabled}
        disabled={network.offline}
        onchange={(on) => switchTo(slot, on)}
      />
    {/snippet}
  </OrderedRows>
  {#if adding}
    <form class="add" onsubmit={add}>
      <label class="sr" for="new-slot">New meal</label>
      <input id="new-slot" type="text" maxlength="40" placeholder="Meal name" bind:value={name} />
      <button type="submit" class="solid" disabled={!name.trim() || network.offline}>Add</button>
      <button type="button" class="quiet" onclick={() => ((adding = false), (name = ''))}
        >Cancel</button
      >
    </form>
  {:else}
    <button type="button" class="addb" disabled={network.offline} onclick={() => (adding = true)}
      >+ New meal</button
    >
  {/if}
  {#if note}<p class="note" role="alert">{note}</p>{/if}
  {#if loaded && slots.length === 0 && !problem}
    <p class="detail">No meals yet.</p>
  {/if}
</div>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .detail {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .addb {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .addb:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .add {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-weight: var(--weight-semibold);
  }

  .solid {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-field);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .solid:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .quiet,
  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .note {
    margin: 0;
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .sr {
    position: absolute;
    left: -9999px;
  }
</style>
