<script lang="ts">
  // Settings → Household (0.9 A1, mockup Dark-Household09-Phone): the household's name, its
  // people (each opens their Person screen), "+ Add a person", and the "Who's this?" switch for
  // shared logins. Everyone in the household sees it; only an admin changes it. Offline it shows
  // what was last loaded and can't be changed.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { onMount, tick } from 'svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import { personLine } from '#lib/client/people.js';
  import { network } from '#lib/network.svelte.js';
  import { household, sentence } from '#lib/people.svelte.js';

  const locked = $derived(!household.canChange || network.offline);

  let name = $state('');
  let nameError = $state<string | undefined>();
  let adding = $state(false);
  let newName = $state('');
  let addError = $state<string | undefined>();
  let switchProblem = $state<string | null>(null);
  let addField = $state<HTMLInputElement>();

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
      // The new person opens, to choose their colour, portion and login (proposed, for cabledrawer).
      const wanted = newName.trim().toLocaleLowerCase();
      const made = household.people.find((p) => p.name.toLocaleLowerCase() === wanted);
      newName = '';
      adding = false;
      if (made) await goto(resolve('/(app)/settings/household/[id]', { id: String(made.id) }));
    } catch (error) {
      addError = sentence(error);
    }
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
  title="Household"
  subtitle="Everyone who eats from this kitchen. People can sign in, or just be a name for portions and “who did it”."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

{#if !household.loaded}
  {#if network.down}
    <OfflineNote screen="Household" />
  {:else if household.problem}
    <p class="problem" role="alert">
      {household.problem}
      <button type="button" class="link" onclick={() => void household.load()}>Try again</button>
    </p>
  {:else}
    <p class="loading" role="status">Loading…</p>
  {/if}
{:else}
  <div class="page">
    {#if household.problem && !network.offline}
      <p class="problem" role="alert">
        {household.problem}
        <button type="button" class="link" onclick={() => void household.load()}>Try again</button>
      </p>
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
            <a
              class="row"
              href={resolve('/(app)/settings/household/[id]', { id: String(person.id) })}
            >
              <PersonAvatar id={person.id} name={person.name} colour={person.colour} />
              <span class="words">
                <span class="label">{person.is_me ? `${person.name} (you)` : person.name}</span>
                <span class="detail">{personLine(person)}</span>
              </span>
              <svg
                class="chev"
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg
              >
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
            <div class="add-buttons">
              <button
                class="small primary"
                type="submit"
                disabled={network.offline || household.busy}>Add</button
              >
              <button
                class="small quiet"
                type="button"
                onclick={() => {
                  adding = false;
                  newName = '';
                  addError = undefined;
                }}>Cancel</button
              >
            </div>
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

    <p class="note">
      Portions decide how much the plan and shopping list allow for each meal. Only admins can add,
      change or remove people.
    </p>
  </div>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: 640px;
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
    font-size: var(--text-lg);
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

  .add-buttons {
    display: flex;
    gap: var(--space-4);
  }

  .small {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-md);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .primary {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .quiet {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
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

  .loading {
    color: var(--color-text-muted);
    font-size: var(--text-base);
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
