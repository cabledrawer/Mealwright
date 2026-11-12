<script lang="ts">
  // Onboarding's "Who eats here?" (0.9 U2): the household's people, and "+ Add a person" by name
  // only. Logins, colours and portions are given later in Settings → Household (the brief: names
  // only here). The same people store and endpoint as Settings → Household.
  import { onMount } from 'svelte';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import { focusOnMount } from '#lib/focusOnMount.js';
  import { network } from '#lib/network.svelte.js';
  import { household, sentence } from '#lib/people.svelte.js';

  const uid = $props.id();
  let adding = $state(false);
  let newName = $state('');
  let problem = $state<string | null>(null);

  onMount(() => {
    if (!household.loaded) void household.load();
  });

  async function add(event: SubmitEvent) {
    event.preventDefault();
    if (household.busy || !newName.trim()) return;
    problem = null;
    try {
      // 4 quarters: one portion, as Settings → Household adds a person.
      if (!(await household.add(newName, null, 4))) return;
      newName = '';
      adding = false;
    } catch (error) {
      problem = sentence(error);
    }
  }
</script>

{#if household.problem}
  <p class="problem" role="alert">{household.problem}</p>
{/if}
{#if household.people.length}
  <ul class="people" aria-label="People">
    {#each household.people as person (person.id)}
      <li class="row">
        <PersonAvatar id={person.id} name={person.name} colour={person.colour} />
        <span class="label">{person.is_me ? `${person.name} (you)` : person.name}</span>
      </li>
    {/each}
  </ul>
{/if}
{#if adding}
  <form class="add-form" onsubmit={add}>
    <label class="sr" for="{uid}-name">Name</label>
    <input
      id="{uid}-name"
      use:focusOnMount
      type="text"
      autocomplete="off"
      maxlength="40"
      placeholder="Name"
      bind:value={newName}
      disabled={network.offline}
    />
    <button
      type="submit"
      class="solid"
      disabled={!newName.trim() || network.offline || household.busy}>Add</button
    >
    <button
      type="button"
      class="quiet"
      onclick={() => ((adding = false), (newName = ''), (problem = null))}>Cancel</button
    >
  </form>
{:else}
  <button type="button" class="add" disabled={network.offline} onclick={() => (adding = true)}
    >+ Add a person</button
  >
{/if}
{#if problem}<p class="problem" role="alert">{problem}</p>{/if}
<p class="note">Just names for now. Give someone a login later in Settings › Household.</p>
