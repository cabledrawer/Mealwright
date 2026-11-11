<script lang="ts">
  // The household's people (0.9 A1): each person's round initial in every colour and size, and
  // the "Who's this?" sheet a shared login shows. Nothing is sent: a pick just closes the sheet,
  // because there is no server behind this page.
  import { COLOURS } from '#lib/client/people.js';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import WhosThis from '#lib/components/people/WhosThis.svelte';
  import { whosThis } from '#lib/whosThis.svelte.js';

  const names = ['Joss', 'Tess', 'Mira', 'Sam', 'Tom'];

  function show() {
    whosThis.people = [
      { id: 1, name: 'Tess', colour: 'green' },
      { id: 3, name: 'Joss', colour: 'amber' },
      { id: 4, name: 'Mira', colour: 'violet' },
      { id: 5, name: 'Sam', colour: null }
    ];
    whosThis.problem = null;
    whosThis.open = true;
  }
</script>

<section id="people">
  <h2>People</h2>
  <p class="note">
    A person’s initial in their colour; someone with no colour gets one from their number.
  </p>
  {#each [36, 52, 56] as const as size (size)}
    <div class="row">
      {#each COLOURS as colour, i (colour)}
        <PersonAvatar id={i} name={names[i] ?? 'A'} {colour} {size} />
      {/each}
      <PersonAvatar id={7} name="Zoë" colour={null} {size} />
    </div>
  {/each}
  <div class="row">
    <button type="button" class="open" onclick={show}>Show “Who’s this?”</button>
  </div>
  <WhosThis onpick={() => (whosThis.open = false)} />
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-5);
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .open {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
