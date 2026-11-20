<script lang="ts">
  // "Your kitchen" (Batch cook, Experimental; mockup Dark-BatchKit08-Phone): hob rings, pressure
  // cookers and the oven, asked once on first use (B2 opens it) and changed in Settings, under
  // Kitchen. A phone sheet: a real modal dialog, Esc closes it, the focus goes back where it
  // came from. On a computer it is a box in the middle of the screen.
  import { tick, untrack } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Segmented from '#lib/components/Segmented.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import Stepper from '#lib/components/Stepper.svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import {
    MAX_HOB_RINGS,
    MAX_PRESSURE_COOKERS,
    saveKitchen,
    type Kitchen
  } from '#lib/client/household.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import Icon from './Icon.svelte';

  let {
    open,
    kitchen,
    onsaved,
    onclose,
    save: send = saveKitchen
  }: {
    open: boolean;
    /** What the household has now (or the usual values before it has answered). */
    kitchen: Kitchen;
    /** Saved: the kitchen as the server stored it. */
    onsaved: (kitchen: Kitchen) => void;
    onclose: () => void;
    /** How it is saved (the gallery shows the sheet without saving anything). */
    save?: typeof saveKitchen;
  } = $props();

  const uid = $props.id();
  let form = $state<HTMLFormElement>();
  let rings = $state(4);
  let cookers = $state(1);
  let oven = $state(true);
  let saving = $state(false);
  let problem = $state<string | null>(null);

  $effect(() => {
    if (open) {
      untrack(() => {
        rings = kitchen.hob_rings;
        cookers = kitchen.pressure_cookers;
        oven = kitchen.oven;
        problem = null;
        saving = false;
      });
      void tick().then(() => form?.querySelector<HTMLElement>('.stepper button')?.focus());
    }
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (saving) return;
    saving = true;
    problem = null;
    try {
      onsaved(await send({ hob_rings: rings, pressure_cookers: cookers, oven }));
    } catch (error) {
      problem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    } finally {
      saving = false;
    }
  }
</script>

{#if open}
  <Sheet title="Your kitchen" {onclose}>
    <form class="body" bind:this={form} onsubmit={submit}>
      <button type="button" class="close" aria-label="Close" onclick={onclose}>
        <Icon name="close" size={18} stroke={2.4} />
      </button>
      <p class="about">
        Batch cook never plans more at once than your kitchen has. Asked once; change it any time in
        Settings › Your kitchen.
      </p>
      <div class="card">
        <div class="row">
          <span class="what">
            <span class="name">Hob rings</span>
            <span class="detail">Burners on the cooker</span>
          </span>
          <Stepper
            what="hob rings"
            onless={() => (rings -= 1)}
            onmore={() => (rings += 1)}
            lessOff={rings <= 1}
            moreOff={rings >= MAX_HOB_RINGS}>{rings}</Stepper
          >
        </div>
        <div class="row">
          <span class="what">
            <span class="name">Pressure cookers</span>
            <span class="detail">Including an Instant Pot</span>
          </span>
          <Stepper
            what="pressure cookers"
            onless={() => (cookers -= 1)}
            onmore={() => (cookers += 1)}
            lessOff={cookers <= 0}
            moreOff={cookers >= MAX_PRESSURE_COOKERS}>{cookers}</Stepper
          >
        </div>
        <div class="row">
          <span class="what"><span class="name" id="{uid}-oven">Oven</span></span>
          <Segmented
            options={[
              { value: true, label: 'Yes' },
              { value: false, label: 'No' }
            ]}
            value={oven}
            onchange={(v) => (oven = v)}
            labelledby="{uid}-oven"
            variant="pill"
          />
        </div>
      </div>
      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
      <ButtonRow>
        <Button type="submit" disabled={saving}>Save</Button>
      </ButtonRow>
    </form>
  </Sheet>
{/if}

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  /* The title is the Sheet's; the close button sits in its top corner. */
  .close {
    position: absolute;
    top: var(--space-4);
    right: var(--space-4);
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    cursor: pointer;
  }

  .about {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .card {
    padding: var(--space-2) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-fill);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 56px;
    border-bottom: 1px solid var(--color-border);
  }

  .row:last-child {
    border-bottom: none;
  }

  .what {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .problem {
    margin: 0;
    color: var(--color-warning-text);
    font-size: var(--text-base);
  }
</style>
