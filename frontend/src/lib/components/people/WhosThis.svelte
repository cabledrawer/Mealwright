<script lang="ts">
  import Sheet from '#lib/components/Sheet.svelte';
  // The "Who's this?" sheet (0.9 A1, mockup Dark-WhosThis09-Phone): on a shared login, pick
  // yourself so Recent changes says who did what. A bottom sheet on a phone, a dialog on a
  // computer. Escape is "Just looking".
  import { session } from '#lib/session.svelte.js';
  import { whosThis } from '#lib/whosThis.svelte.js';
  import PersonAvatar from './PersonAvatar.svelte';

  /** For the gallery: what a pick does instead of telling the server. */
  let {
    onpick = (id: number | null) => whosThis.pick(id)
  }: {
    onpick?: (id: number | null) => unknown;
  } = $props();

  const uid = $props.id();
</script>

{#if whosThis.open}
  <Sheet
    title="Who’s this?"
    testid="whos-this"
    outside={false}
    describedby="{uid}-sub"
    onclose={() => void onpick(null)}
  >
    <p class="sub" id="{uid}-sub">
      This is {session.me?.name ?? 'a shared login'}. Pick yourself so Recent changes says who did
      what.
    </p>
    <div class="grid">
      {#each whosThis.people as person (person.id)}
        <button
          type="button"
          class="who"
          disabled={whosThis.busy}
          onclick={() => void onpick(person.id)}
        >
          <PersonAvatar id={person.id} name={person.name} colour={person.colour} size={52} />
          <span class="name">{person.name}</span>
        </button>
      {/each}
    </div>
    {#if whosThis.problem}
      <p class="problem" role="alert">{whosThis.problem}</p>
    {/if}
    <button type="button" class="looking" disabled={whosThis.busy} onclick={() => void onpick(null)}
      >Just looking (don’t ask again for an hour)</button
    >
    <p class="note">
      Asked again after 30 minutes without use.{#if session.me?.role === 'admin'}
        Turn this off in Settings › People.{/if}
    </p>
  </Sheet>
{/if}

<style>
  .sub {
    margin-top: -6px;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .who {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    padding: var(--space-7) var(--space-4);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-xl);
    background: var(--color-field);
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .name {
    max-width: 100%;
    overflow-wrap: anywhere;
    text-align: center;
  }

  .looking {
    min-height: 48px;
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .note {
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
  }
</style>
