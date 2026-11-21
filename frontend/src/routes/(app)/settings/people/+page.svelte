<script lang="ts">
  import Loading from '#lib/components/Loading.svelte';
  import Icon from '#lib/components/Icon.svelte';
  // Settings › People (0.9 A1, mockup Dark-Household09-Phone): the household's name, its
  // people (each opens their Person screen), "+ Add a person", and the "Who's this?" switch for
  // shared logins. Everyone in the household sees it; only an admin changes it. Offline it shows
  // what was last loaded and can't be changed. An admin sees single sign-on sign-ins that match
  // nobody, and says who each is ("Who is this?", 0.9.5 Pe3/M2, Dark-HouseholdWaiting095-Phone).
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { onMount, tick } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import { labelOf } from '../items.js';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import WhoIsThis from '#lib/components/people/WhoIsThis.svelte';
  import { personLine } from '#lib/client/people.js';
  import { network } from '#lib/network.svelte.js';
  import { household, sentence } from '#lib/people.svelte.js';
  import { waitingLine, waitingTitle } from '#lib/ssoWaitingWords.js';

  const locked = $derived(!household.canChange || network.offline);

  let name = $state('');
  let nameError = $state<string | undefined>();
  let adding = $state(false);
  let newName = $state('');
  let addError = $state<string | undefined>();
  let switchProblem = $state<string | null>(null);
  let addField = $state<HTMLInputElement>();
  /** The waiting sign-in whose "Who is this?" sheet is open. */
  let whoId = $state<number | null>(null);
  const who = $derived(household.waiting.find((w) => w.id === whoId) ?? null);
  // The newest waits first: one "Who is this?" at a time.
  const nextWaiting = $derived(household.waiting[0] ?? null);

  onMount(() => {
    void household.load().then(() => (name = household.name));
  });

  // The connection came back: look again, in case an admin changed something meanwhile.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void household.load();
    }
  });

  // An Undo elsewhere puts the old name back: show it, unless it's being typed.
  let typing = false;
  $effect(() => {
    const now = household.name;
    if (!typing) name = now;
  });

  async function saveName() {
    typing = false;
    const wanted = name.trim();
    if (locked || wanted === household.name) return;
    nameError = undefined;
    try {
      await household.rename(wanted);
      name = household.name;
    } catch (error) {
      nameError = sentence(error);
    }
  }

  async function startAdding() {
    adding = true;
    addError = undefined;
    await tick();
    addField?.focus();
  }

  async function add(event: SubmitEvent) {
    event.preventDefault();
    if (household.busy) return;
    addError = undefined;
    try {
      if (!(await household.add(newName, null, 4))) return;
      // The new person opens, to choose their colour, portion and login (cabledrawer 12 Nov).
      const wanted = newName.trim().toLocaleLowerCase();
      const made = household.people.find((p) => p.name.toLocaleLowerCase() === wanted);
      newName = '';
      adding = false;
      if (made) await goto(resolve('/(app)/settings/people/[id]', { id: String(made.id) }));
    } catch (error) {
      addError = sentence(error);
    }
  }

  async function linkWho(memberId: number | null) {
    if (whoId === null) return;
    if (await household.link(whoId, memberId)) whoId = null;
  }

  async function refuseWho() {
    if (whoId === null) return;
    if (await household.refuse(whoId)) whoId = null;
  }

  async function ask(on: boolean) {
    switchProblem = null;
    household.askWhosThis = on;
    try {
      await household.ask(on);
    } catch (error) {
      switchProblem = sentence(error);
      household.askWhosThis = !on;
    }
  }
</script>

<PageHeader
  title="People"
  overline="Household"
  subtitle="Everyone who eats from this kitchen. People can sign in, or just be a name for portions and “who did it”."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

{#if !household.loaded}
  {#if network.down}
    <OfflineNote screen={labelOf('people')} />
  {:else if household.problem}
    <p class="problem" role="alert">
      {household.problem}
      <button type="button" class="link" onclick={() => void household.load()}>Try again</button>
    </p>
  {:else}
    <Loading />
  {/if}
{:else}
  <div class="page">
    {#if household.problem && !network.offline}
      <p class="problem" role="alert">
        {household.problem}
        <button type="button" class="link" onclick={() => void household.load()}>Try again</button>
      </p>
    {/if}

    {#if household.canChange && nextWaiting}
      <div class="waiting">
        <div class="warn" role="status">
          <Icon name="alert" size={20} />
          <span class="warn-words">
            <strong>{waitingTitle(household.waiting.length)}</strong>
            {#each household.waiting as waiting (waiting.id)}
              <span>{waitingLine(waiting, new Date(), household.zone)}</span>
            {/each}
          </span>
        </div>
        <button
          class="who"
          type="button"
          disabled={network.offline}
          onclick={() => (whoId = nextWaiting?.id ?? null)}>Who is this?</button
        >
      </div>
    {/if}

    <div class="field">
      <label for="household-name">Household name</label>
      <input
        id="household-name"
        type="text"
        autocomplete="off"
        maxlength="100"
        bind:value={name}
        disabled={locked}
        aria-invalid={nameError ? true : undefined}
        aria-describedby={nameError ? 'household-name-error' : undefined}
        oninput={() => (typing = true)}
        onblur={() => void saveName()}
        onkeydown={(event) => {
          if (event.key === 'Enter') void saveName();
        }}
      />
      {#if nameError}
        <p id="household-name-error" class="error" role="alert">{nameError}</p>
      {/if}
    </div>

    <section class="section" aria-labelledby="people-heading">
      <h2 id="people-heading">People</h2>
      <ul class="card" aria-labelledby="people-heading">
        {#each household.people as person (person.id)}
          <li>
            <a class="row" href={resolve('/(app)/settings/people/[id]', { id: String(person.id) })}>
              <PersonAvatar id={person.id} name={person.name} colour={person.colour} />
              <span class="words">
                <span class="label">{person.is_me ? `${person.name} (you)` : person.name}</span>
                <span class="detail">{personLine(person)}</span>
              </span>
              <span class="chev"><Icon name="chevron-right" size={18} /></span>
            </a>
          </li>
        {/each}
      </ul>

      {#if household.canChange}
        {#if adding}
          <form class="add-form" onsubmit={add}>
            <div class="field">
              <label for="new-person">Name</label>
              <input
                id="new-person"
                type="text"
                autocomplete="off"
                maxlength="40"
                required
                bind:this={addField}
                bind:value={newName}
                disabled={network.offline}
                aria-invalid={addError ? true : undefined}
                aria-describedby={addError ? 'new-person-error' : undefined}
              />
              {#if addError}
                <p id="new-person-error" class="error" role="alert">{addError}</p>
              {/if}
            </div>
            <ButtonRow>
              <Button
                quiet
                onclick={() => {
                  adding = false;
                  newName = '';
                  addError = undefined;
                }}>Cancel</Button
              >
              <Button type="submit" disabled={network.offline || household.busy}>Add</Button>
            </ButtonRow>
          </form>
        {:else}
          <button
            class="add"
            type="button"
            disabled={network.offline}
            onclick={() => void startAdding()}>+ Add a person</button
          >
        {/if}
      {/if}
    </section>

    <section class="section" aria-labelledby="shared-heading">
      <h2 id="shared-heading">Shared logins</h2>
      <div class="card">
        <div class="row">
          <span class="words">
            <span class="label" id="ask-label">Ask “Who’s this?”</span>
            <span class="detail" id="ask-detail">So Recent changes says who did what</span>
          </span>
          <Switch
            checked={household.askWhosThis}
            labelledby="ask-label"
            describedby="ask-detail"
            disabled={locked}
            onchange={(on) => void ask(on)}
          />
        </div>
      </div>
      {#if switchProblem}
        <p class="problem" role="alert">{switchProblem}</p>
      {/if}
    </section>

    <WhoIsThis
      waiting={who}
      people={household.people}
      zone={household.zone}
      busy={household.busy}
      offline={network.offline}
      onlink={linkWho}
      onrefuse={refuseWho}
      onclose={() => (whoId = null)}
    />

    <p class="note">
      Portions are kept for later: the plan and shopping list don’t use them yet. Only admins can
      add, change or delete people.
    </p>
  </div>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: var(--settings-width);
  }

  .waiting {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .warn {
    display: flex;
    align-items: flex-start;
    gap: var(--space-5);
    padding: var(--space-6) 14px;
    border: 1px solid var(--color-caution-border);
    border-radius: var(--radius-xl);
    background: var(--color-caution);
    color: var(--color-caution-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .warn :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  .warn-words {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .who {
    align-self: stretch;
    min-height: 52px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h2 {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    margin: 0;
    padding: 0;
    overflow: hidden;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
  }

  li + li {
    border-top: 1px solid var(--color-divider);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: var(--space-6) 14px;
    color: var(--color-text);
    text-decoration: none;
  }

  .words {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    font-size: 1rem;
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
    line-height: 1.4;
  }

  .chev {
    flex: none;
    color: var(--color-text-muted);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .field label {
    color: var(--color-text-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .field input {
    width: 100%;
    min-height: 46px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem;
    font-weight: var(--weight-medium);
  }

  .field input:disabled {
    opacity: 0.7;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .add {
    align-self: flex-start;
    min-height: 44px;
    padding: 0 14px;
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .add-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: 14px var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .note {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }
</style>
