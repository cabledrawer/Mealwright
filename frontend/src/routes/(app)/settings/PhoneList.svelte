<script lang="ts">
  // Settings on the phone, option B (F193, cabledrawer 9 Nov; mockup Dark-Settings08-Phone): a grouped
  // list, You · Kitchen · Household, each row with its icon, its current value and an arrow. A row
  // opens that section on its own page, with "‹ Settings" to come back (the computer keeps its
  // list of sections beside all of them). The values are worked out by the page and are blank
  // until they are known; Privacy opens its own page.
  import { resolve } from '$app/paths';
  import Icon from '#lib/components/Icon.svelte';
  import FinishRing from './FinishRing.svelte';
  import { ringWords } from './finishRing.js';
  import { SECTION_ICONS, type Group } from './sectionIcons.js';

  let { groups }: { groups: Group[] } = $props();
</script>

{#each groups as group (group.name)}
  <h2 class="group-name">{group.name}</h2>
  <nav class="card" aria-label={group.label}>
    {#each group.rows as row (row.id)}
      <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- resolve()'s answer, plus this page's own ?section= -->
      <a class="row" href={row.href ?? `${resolve('/(app)/settings')}?section=${row.id}`}>
        {#if row.ring}
          <span class="ico ring"><FinishRing done={row.ring.done} of={row.ring.of} /></span>
        {:else if row.icon}
          <span class="ico {SECTION_ICONS[row.icon].tone}">
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
            >
              {#each SECTION_ICONS[row.icon].paths as d (d)}<path {d} />{/each}
            </svg>
          </span>
        {/if}
        <span class="lbl"
          >{row.label}{#if row.sub}<span class="sub">{row.sub}</span>{/if}</span
        >
        {#if row.badge}<span class="badge">{row.badge}</span>{/if}
        {#if row.ring}<span class="val">{ringWords(row.ring.done, row.ring.of)}</span
          >{:else if row.value}<span class="val">{row.value}</span>{/if}
        <span class="chev"><Icon name="back" size={18} stroke={2} /></span>
      </a>
    {/each}
  </nav>
{/each}

<style>
  .group-name {
    margin: var(--space-3) var(--space-2) calc(-1 * var(--space-3));
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .badge {
    flex: none;
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.02em;
    white-space: nowrap;
  }

  .card {
    overflow: hidden;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 54px;
    padding: 0 var(--space-6);
    border-top: 1px solid var(--color-divider);
    color: var(--color-text);
    text-decoration: none;
  }

  .row:first-child {
    border-top: none;
  }

  .ico {
    display: grid;
    flex: none;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: 9px;
  }

  /* One tone per kind of setting: a soft background and its own colour. */
  .ico.you {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .ico.kitchen {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  /* The Finish setup ring (mockup Dark-FinishSetup095-Phone): 36px tile, amber. */
  .ico.ring {
    width: 36px;
    height: 36px;
    border-radius: 12px;
    background: var(--color-caution);
    color: var(--color-caution-text);
  }

  .ico.quiet {
    background: var(--color-fill);
    color: var(--color-text-soft);
  }

  .lbl {
    flex: 1;
    min-width: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
  }

  .sub {
    display: block;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-regular);
  }

  .val {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    white-space: nowrap;
  }

  /* The back arrow, turned round, points on. */
  .chev {
    display: inline-flex;
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }
</style>
