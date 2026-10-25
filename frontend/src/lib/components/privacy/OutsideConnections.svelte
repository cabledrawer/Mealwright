<script lang="ts">
  // "Outside connections": one switch for each kind of connection Mealwright may make
  // (spec section 7). All start off. Only an admin changes them; a member sees them
  // and a note saying why. Offline they show as last loaded and can't be changed.
  import type { SwitchName } from '#lib/client/privacy.js';
  import {
    LEARN_IMPORT_LIMITS,
    MEMBER_NOTE,
    OFFLINE_NOTE,
    OUTSIDE_CONNECTIONS_ANCHOR,
    SWITCH_ORDER,
    SWITCH_WORDS,
    type Locked
  } from '#lib/privacyWords.js';
  import Switch from '../Switch.svelte';

  let {
    values,
    locked = null,
    problem = null,
    anchor = OUTSIDE_CONNECTIONS_ANCHOR,
    onchange
  }: {
    values: Record<SwitchName, boolean>;
    locked?: Locked;
    /** A switch didn't save: why. */
    problem?: string | null;
    /** The heading's id, which the import screen links to. Only the gallery changes it. */
    anchor?: string;
    onchange: (name: SwitchName, on: boolean) => void;
  } = $props();
</script>

<section class="section" aria-labelledby={anchor}>
  <h2 id={anchor}>Outside connections</h2>
  <div class="card">
    <ul>
      {#each SWITCH_ORDER as name (name)}
        <li>
          <span class="words">
            <span class="label" id="{anchor}-{name}">{SWITCH_WORDS[name].label}</span>
            <span class="detail" id="{anchor}-{name}-detail">{SWITCH_WORDS[name].detail}</span>
          </span>
          <Switch
            checked={values[name]}
            labelledby="{anchor}-{name}"
            describedby="{anchor}-{name}-detail"
            disabled={locked !== null}
            onchange={(on) => onchange(name, on)}
          />
        </li>
      {/each}
    </ul>
  </div>
  {#if problem}
    <p class="problem" role="alert">{problem}</p>
  {/if}
  {#if locked === 'member'}
    <p class="note">{MEMBER_NOTE}</p>
  {:else if locked === 'offline'}
    <p class="note">{OFFLINE_NOTE}</p>
  {/if}
  <p class="note">{LEARN_IMPORT_LIMITS}</p>
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  h2 {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
    /* Landing here from the import screen, the heading isn't tucked under the header. */
    scroll-margin-top: 80px;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  ul {
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 60px;
    padding: var(--space-4) 0;
  }

  li + li {
    border-top: 1px solid var(--color-divider);
  }

  .words {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .note {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }
</style>
