<script lang="ts">
  // Full Onboarding (0.9 U2; spec "Layout decisions": Onboarding, and section 2 "Onboarding";
  // mockups Dark-Onboard09-Phone and Dark-Onboard09-Desktop). First-run
  // setup makes the admin account (step 1) and comes here once. The phone shows one step per
  // screen (steps 2 to 6 of 6); a computer shows one page of cards, then "Finish setup". Skip
  // passes over just that step and shows the next (cabledrawer 12 Nov); Skip on step 5 (the last with
  // a Skip), Finish setup and "Go to Today" mark it done for the household and go to Today: it
  // never shows again. The computer page has no Skip (the mockup draws none).
  // Nothing here is needed: every step saves at once through the same /api/v1 calls as Settings and Ingredients, and has a sensible default. Anyone else (a member, or a
  // household that has finished) is sent to Today.
  import { onMount, tick } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { ApiError, cantReach } from '#lib/api.js';
  import { changeAmountsShown, finishOnboarding, getHousehold } from '#lib/client/household.js';
  import type { AmountsShown } from '#lib/client/types.js';
  import AmountsChoice from '#lib/components/AmountsChoice.svelte';
  import { nothingChanged } from '#lib/downWords.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import PacksStep from './PacksStep.svelte';
  import PeopleStep from './PeopleStep.svelte';
  import ShopsStep from './ShopsStep.svelte';
  import { PHONE_QUERY } from '#lib/layout.js';

  let phone = $state(matchMedia(PHONE_QUERY).matches);
  let ready = $state(false);
  /** The phone's step: 2 Amounts, 3 Who eats here?, 4 Shops, 5 Starter packs, 6 You're set. */
  let step = $state(2);
  let amounts = $state<AmountsShown>('as_written');
  let amountsProblem = $state<string | null>(null);
  let finishing = $state(false);
  let finishProblem = $state<string | null>(null);
  let heading = $state<HTMLHeadingElement>();
  let peopleStep = $state<PeopleStep>();
  let shopsStep = $state<ShopsStep>();

  const TITLES: Record<number, string> = {
    2: 'How do you measure?',
    3: 'Who eats here?',
    4: 'Where do you shop?',
    5: 'Start with common ingredients?',
    6: 'You’re set'
  };

  const toToday = () => goto(resolve('/(app)'), { replace: true });

  onMount(() => {
    // The phone layout has no bottom tabs here: onboarding is a page of its own.
    document.documentElement.setAttribute('data-full-page', '');
    const media = matchMedia(PHONE_QUERY);
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    if (session.me?.role !== 'admin') {
      void toToday();
    } else {
      getHousehold().then(
        (household) => {
          if (household.onboarding_done) return void toToday();
          amounts = household.amounts_shown;
          ready = true;
        },
        () => void toToday() // can't reach the server: Today says so
      );
    }
    return () => {
      document.documentElement.removeAttribute('data-full-page');
      media.removeEventListener('change', onchange);
    };
  });

  function wordsOf(error: unknown): string {
    return error instanceof ApiError && !cantReach(error)
      ? error.detail
      : nothingChanged(network.deviceOffline);
  }

  /** The choice moves at once and is saved; if it can't be, it goes back and says so. */
  async function setAmounts(next: AmountsShown) {
    const before = amounts;
    amountsProblem = null;
    amounts = next;
    try {
      amounts = (await changeAmountsShown(next)).amounts_shown;
      kitchen.wroteSettings();
    } catch (error) {
      amounts = before;
      amountsProblem = wordsOf(error);
    }
  }

  /** The phone's Skip passes over this step (nothing more is saved); the last step with a Skip
   *  (5) finishes setup, as Finish does (cabledrawer 12 Nov). */
  function skip() {
    return step < 5 ? next(step + 1) : finish();
  }

  /** A name or shop that was typed but not added is added before Next, Skip or Finish setup moves
   *  on (M3); if it can't be added, its step says why and we stay. */
  async function typedAdded(): Promise<boolean> {
    const people = (await peopleStep?.addTypedName()) ?? true;
    const shops = (await shopsStep?.addTypedShop()) ?? true;
    return people && shops;
  }

  async function next(to: number) {
    if (await typedAdded()) await go(to);
  }

  /** Finish setup, Go to Today and the last Skip: done for the household, then Today. */
  async function finish() {
    if (finishing) return;
    finishing = true;
    finishProblem = null;
    try {
      if (!(await typedAdded())) return;
      await finishOnboarding();
      await toToday();
    } catch (error) {
      finishProblem = wordsOf(error);
    } finally {
      finishing = false;
    }
  }

  async function go(to: number) {
    step = to;
    await tick();
    heading?.focus();
  }
</script>

<svelte:head><title>Welcome · Mealwright</title></svelte:head>

{#snippet amountsBody()}
  <AmountsChoice value={amounts} onchange={(next) => void setAmounts(next)} />
  {#if amountsProblem}<p class="problem" role="alert">{amountsProblem}</p>{/if}
{/snippet}

{#snippet finishLine()}
  {#if finishProblem}<p class="problem" role="alert">{finishProblem}</p>{/if}
{/snippet}

{#if ready}
  <div class="onboarding">
    {#if phone}
      <div class="phone">
        <div class="top">
          <span class="count">Step {step} of 6</span>
          {#if step < 6}
            <button type="button" class="skip" disabled={finishing} onclick={() => void skip()}
              >Skip</button
            >
          {/if}
        </div>
        <div class="bar" aria-hidden="true">
          <div class="fill" style:width="{Math.round((step / 6) * 100)}%"></div>
        </div>
        <h1 bind:this={heading} tabindex="-1">{TITLES[step]}</h1>

        {#if step === 2}
          {@render amountsBody()}
          <p class="note">Change it any time in Settings › Amounts.</p>
        {:else if step === 3}
          <PeopleStep bind:this={peopleStep} />
        {:else if step === 4}
          <ShopsStep bind:this={shopsStep} />
        {:else if step === 5}
          <PacksStep />
        {:else}
          <p class="ok">
            <svg
              aria-hidden="true"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              ><path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z"></path></svg
            >
            <span
              >Everything stays on your server. Nothing connects outside until you switch it on in
              Outside connections.</span
            >
          </p>
          <p class="note">Next: import a recipe or add your own, then plan a week.</p>
        {/if}

        {@render finishLine()}
        <div class="nav">
          {#if step === 6}
            <button type="button" class="main" disabled={finishing} onclick={() => void finish()}
              >Go to Today</button
            >
          {:else}
            {#if step > 2}
              <button type="button" class="second" onclick={() => void go(step - 1)}>Back</button>
            {/if}
            <button type="button" class="main" onclick={() => void next(step + 1)}>Next</button>
          {/if}
        </div>
      </div>
    {:else}
      <div class="desk">
        <div class="desk-top">
          <div class="desk-words">
            <h1>Welcome to Mealwright. Five quick things.</h1>
            <p class="note">
              Only the first is needed. Everything else has a sensible default and can change later
              in Settings.
            </p>
          </div>
        </div>
        <div class="cards">
          <section class="card" aria-labelledby="ob-account">
            <h2 id="ob-account">1 · Your account</h2>
            <p class="done">
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M5 12l5 5L20 7"></path></svg
              >
              <span>Made: {session.me?.name}, the admin.</span>
            </p>
          </section>
          <section class="card" aria-labelledby="ob-amounts">
            <h2 id="ob-amounts">2 · Amounts</h2>
            {@render amountsBody()}
          </section>
          <section class="card" aria-labelledby="ob-shops">
            <h2 id="ob-shops">3 · Shops</h2>
            <ShopsStep bind:this={shopsStep} />
          </section>
          <section class="card" aria-labelledby="ob-people">
            <h2 id="ob-people">4 · Who eats here?</h2>
            <PeopleStep bind:this={peopleStep} />
          </section>
          <section class="card wide" aria-labelledby="ob-packs">
            <h2 id="ob-packs">5 · Start with common ingredients?</h2>
            <PacksStep />
          </section>
        </div>
        {@render finishLine()}
        <div class="desk-end">
          <button type="button" class="main" disabled={finishing} onclick={() => void finish()}
            >Finish setup</button
          >
          <p class="note">
            Nothing connects outside until you switch it on in Outside connections.
          </p>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .onboarding {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  h1 {
    margin: 0;
    font-size: 28px;
    font-weight: var(--weight-extrabold);
    letter-spacing: -0.02em;
    outline: none;
  }

  h2 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  /* --- Phone: one step per screen -------------------------------------------------------- */

  .phone {
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-height: calc(100dvh - 140px);
    padding-top: var(--space-4);
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: var(--touch-target);
  }

  .count {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .skip {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .bar {
    height: 6px;
    border-radius: 3px;
    background: var(--color-border);
  }

  .fill {
    height: 6px;
    border-radius: 3px;
    background: var(--color-accent);
  }

  .nav {
    display: flex;
    gap: var(--space-5);
    margin-top: auto;
    padding-bottom: var(--space-6);
  }

  .nav .second {
    flex: 1;
  }

  .nav .main {
    flex: 2;
  }

  /* --- Computer: one page of cards ------------------------------------------------------- */

  .desk {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: 1000px;
  }

  .desk-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-6);
  }

  .desk-words {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: var(--space-7);
    align-items: start;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .card.wide {
    grid-column: 1 / -1;
  }

  .done {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin: 0;
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }

  .desk-end {
    display: flex;
    align-items: center;
    gap: var(--space-7);
    flex-wrap: wrap;
  }

  /* --- Shared by the steps (their bodies sit in either layout) --------------------------- */

  .onboarding :global(.note) {
    margin: 0;
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .onboarding :global(.problem) {
    margin: 0;
    color: var(--color-warning-text);
    font-size: var(--text-sm);
  }

  .ok {
    display: flex;
    gap: var(--space-5);
    margin: 0;
    padding: var(--space-6) var(--space-7);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-lg);
    background: var(--color-accent-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .ok svg {
    flex: none;
  }

  .onboarding :global(.people) {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    overflow: hidden;
  }

  .card :global(.people) {
    border: 1px solid var(--color-border);
  }

  .onboarding :global(.people .row) {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: var(--space-5) var(--space-6);
    border-top: 1px solid var(--color-border);
  }

  .onboarding :global(.people .row:first-child) {
    border-top: none;
  }

  .onboarding :global(.people .label) {
    flex: 1;
    min-width: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .onboarding :global(.remove) {
    flex: none;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    cursor: pointer;
  }

  .onboarding :global(.add) {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-lg);
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .onboarding :global(.add-form) {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .onboarding :global(.add-form input) {
    flex: 1 1 160px;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
  }

  .main,
  .second,
  .onboarding :global(.solid),
  .onboarding :global(.quiet) {
    min-height: 48px;
    padding: 0 var(--space-7);
    border-radius: var(--radius-lg);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .main,
  .onboarding :global(.solid) {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .second,
  .onboarding :global(.quiet) {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .onboarding :global(button:disabled) {
    opacity: 0.55;
    cursor: not-allowed;
  }
</style>
