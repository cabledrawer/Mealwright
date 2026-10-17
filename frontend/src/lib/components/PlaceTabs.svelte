<script lang="ts" module>
  export interface Tab {
    id: string;
    label: string;
  }
</script>

<script lang="ts">
  // The phone Pantry's tabs (lead's ruling, 17 Oct): All · every place · Use soon, as a
  // pill segmented control. Places that don't fit go under "More", so nothing scrolls
  // sideways (spec "Decided for 0.2", Places on screen).
  import Icon from './Icon.svelte';

  let {
    tabs,
    selected = $bindable(),
    panelId
  }: {
    /** All, then each place, then Use soon. The first and last always show. */
    tabs: Tab[];
    selected: string;
    panelId: string;
  } = $props();

  const uid = $props.id();
  let width = $state(0);
  let widths = $state<number[]>([]);
  let moreWidth = $state(0);
  let menuOpen = $state(false);

  const GAP = 2;
  const PADDING = 6;

  /** How many of the middle tabs (places) fit beside All, Use soon and maybe More. */
  const fitting = $derived.by(() => {
    const middle = tabs.length - 2;
    if (!width || widths.length !== tabs.length) return middle;
    const total = (n: number, withMore: boolean) =>
      widths[0]! +
      widths.at(-1)! +
      widths.slice(1, 1 + n).reduce((sum, w) => sum + w, 0) +
      (withMore ? moreWidth : 0) +
      GAP * (n + 1 + (withMore ? 1 : 0)) +
      PADDING;
    if (total(middle, false) <= width) return middle;
    let n = middle - 1;
    while (n > 0 && total(n, true) > width) n--;
    return n;
  });

  const shown = $derived([tabs[0]!, ...tabs.slice(1, 1 + fitting)]);
  const hidden = $derived(tabs.slice(1 + fitting, -1));
  const last = $derived(tabs.at(-1)!);
  const hiddenSelected = $derived(hidden.find((t) => t.id === selected));

  function choose(id: string) {
    selected = id;
    menuOpen = false;
  }

  function measure(node: HTMLElement, index: number) {
    const update = () => {
      const next = [...widths];
      next[index] = node.offsetWidth;
      widths = next;
    };
    update();
    return { update };
  }

  /** Arrow keys move between tabs, as in any tab list. */
  function keys(event: KeyboardEvent) {
    const visible = [...shown, ...(hiddenSelected ? [hiddenSelected] : []), last];
    const i = visible.findIndex((t) => t.id === selected);
    if (event.key === 'ArrowRight') choose(visible[(i + 1) % visible.length]!.id);
    else if (event.key === 'ArrowLeft')
      choose(visible[(i - 1 + visible.length) % visible.length]!.id);
    else return;
    event.preventDefault();
    (event.currentTarget as HTMLElement)
      .querySelector<HTMLElement>('[aria-selected="true"]')
      ?.focus();
  }
</script>

<div class="wrap" bind:clientWidth={width}>
  <!-- Invisible copies, to measure each label. -->
  <div class="measure" aria-hidden="true">
    {#each tabs as tab, i (tab.id)}<span class="tab" use:measure={i}>{tab.label}</span>{/each}
    <span class="tab" bind:offsetWidth={moreWidth}>More <Icon name="chevron-down" size={14} /></span
    >
  </div>

  <div class="tabs" role="tablist" aria-label="Where" tabindex="-1" onkeydown={keys}>
    {#each shown as tab (tab.id)}
      <button
        type="button"
        role="tab"
        class="tab"
        aria-selected={selected === tab.id}
        aria-controls={panelId}
        tabindex={selected === tab.id ? 0 : -1}
        onclick={() => choose(tab.id)}>{tab.label}</button
      >
    {/each}
    {#if hidden.length}
      <button
        type="button"
        role="tab"
        class="tab more"
        aria-selected={!!hiddenSelected}
        aria-controls={panelId}
        aria-haspopup="true"
        aria-expanded={menuOpen}
        tabindex={hiddenSelected ? 0 : -1}
        onclick={() => (menuOpen = !menuOpen)}
        >{hiddenSelected?.label ?? 'More'} <Icon name="chevron-down" size={14} /></button
      >
    {/if}
    <button
      type="button"
      role="tab"
      class="tab"
      aria-selected={selected === last.id}
      aria-controls={panelId}
      tabindex={selected === last.id ? 0 : -1}
      onclick={() => choose(last.id)}>{last.label}</button
    >
  </div>

  {#if menuOpen}
    <ul class="menu" id="{uid}-menu" aria-label="More places">
      {#each hidden as tab (tab.id)}
        <li>
          <button
            type="button"
            aria-current={selected === tab.id ? 'true' : undefined}
            onclick={() => choose(tab.id)}
            onkeydown={(event) => {
              if (event.key === 'Escape') menuOpen = false;
            }}>{tab.label}</button
          >
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
    min-width: 0;
  }

  .measure {
    position: absolute;
    visibility: hidden;
    display: flex;
    white-space: nowrap;
    pointer-events: none;
  }

  .tabs {
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-segment-track);
  }

  .tab {
    display: inline-flex;
    flex: 1 0 auto;
    align-items: center;
    justify-content: center;
    gap: var(--space-1);
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    white-space: nowrap;
    cursor: pointer;
  }

  .tab[aria-selected='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  .menu {
    position: absolute;
    z-index: 6;
    right: 0;
    top: calc(100% + var(--space-2));
    display: flex;
    flex-direction: column;
    min-width: 10rem;
    margin: 0;
    padding: var(--space-2);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    box-shadow: var(--shadow-toast);
    list-style: none;
  }

  .menu button {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    text-align: left;
    cursor: pointer;
  }

  .menu button[aria-current='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }
</style>
