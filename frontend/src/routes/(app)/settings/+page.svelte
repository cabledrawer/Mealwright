<script lang="ts">
  // /settings. On the phone it is the grouped list (F193, cabledrawer 9 Nov; mockup
  // Dark-Settings2-Phone): each row with its icon, its current value and an arrow, opening that
  // item on its own page with "‹ Settings" to come back. On a computer the list is beside every
  // page (+layout.svelte), so this address opens the first item, Appearance. An older link
  // ("/settings#about", "/settings?section=sign-in") goes to the item that section is now.
  import { onMount, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { getShops, getPlaces } from '#lib/client/foods.js';
  import { getKitchen, type Kitchen } from '#lib/client/household.js';
  import { getMealSlots } from '#lib/client/plan.js';
  import { getPeople } from '#lib/client/people.js';
  import { network } from '#lib/network.svelte.js';
  import { privacy } from '#lib/privacy.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { updates } from '#lib/updates.svelte.js';
  import { UPDATE_AVAILABLE } from '#lib/aboutWords.js';
  import { VERSION_WORDS } from '#lib/version.js';
  import { THEME_LABELS, theme } from '#lib/theme.svelte.js';
  import PhoneList from './PhoneList.svelte';
  import { FINISH_SETUP_WORDS, SETUP_STEPS } from './finishRing.js';
  import { settingsKnown } from './finishSetup.svelte.js';
  import { GROUPS, ITEMS, adminOnly, itemForOldSection, type Item } from './items.js';
  import type { Group, Row } from './sectionIcons.js';

  const admin = $derived(session.me?.role === 'admin');

  // --- Where a computer, or an older link, goes -----------------------------------------------
  const FINISH_SETUP = 'Finish setup';
  const COMPUTER = '(min-width: 768px)';
  onMount(() => {
    const old = page.url.searchParams.get('section') ?? page.url.hash.slice(1);
    const item = old ? itemForOldSection(old) : undefined;
    if (item) {
      void goto(resolve(item.route), { replace: true });
      return;
    }
    const media = matchMedia(COMPUTER);
    const toFirst = () => {
      const first = ITEMS[0];
      if (first && media.matches) void goto(resolve(first.route), { replace: true });
    };
    toFirst();
    media.addEventListener('change', toFirst);
    return () => media.removeEventListener('change', toFirst);
  });

  // --- What the list's rows show (proposed, for cabledrawer: the words under "Settings") -----
  let slotsOn = $state<number | null>(null);
  let shopsCount = $state<number | null>(null);
  let placesCount = $state<number | null>(null);
  let peopleCount = $state<number | null>(null);
  let kitchenNow = $state<Kitchen | null>(null);
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const privacyOn = $derived(
    privacy.loaded && privacy.problem === null
      ? Object.values(privacy.switches).filter(Boolean).length + (privacy.entries.length ? 1 : 0)
      : null
  );

  function readRowValues() {
    getMealSlots().then(
      (slots) => (slotsOn = slots.filter((s) => s.enabled).length),
      () => {}
    );
    getShops().then(
      (shops) => (shopsCount = shops.length),
      () => {}
    );
    getPlaces().then(
      (places) => (placesCount = places.length),
      () => {}
    );
    getKitchen().then(
      (found) => (kitchenNow = found),
      () => {}
    );
    if (admin) {
      void privacy.load().catch(() => {});
      getPeople().then(
        (found) => (peopleCount = found.people.length),
        () => {}
      );
      void updates.load();
    }
  }
  // Only the phone shows these rows; a computer is on its way to Appearance, so reads nothing.
  onMount(() => {
    if (!matchMedia(COMPUTER).matches) untrack(readRowValues);
  });

  /** The value on an item's row, once known. */
  function valueFor(item: Item): string | undefined {
    switch (item.id) {
      case 'appearance':
        return THEME_LABELS[theme.choice];
      case 'amounts':
        return settingsKnown.pints === null
          ? undefined
          : settingsKnown.pints === 'us'
            ? 'US pints'
            : 'UK pints';
      case 'meal-slots':
        return slotsOn === null ? undefined : `${slotsOn} on`;
      case 'shops-places':
        return shopsCount === null || placesCount === null
          ? undefined
          : `${plural(shopsCount, 'shop', 'shops')} · ${plural(placesCount, 'place', 'places')}`;
      case 'your-kitchen':
        return kitchenNow === null
          ? undefined
          : `${kitchenNow.hob_rings} hob ${kitchenNow.hob_rings === 1 ? 'ring' : 'rings'}`;
      case 'people':
        return peopleCount === null ? undefined : plural(peopleCount, 'person', 'people');
      case 'privacy':
        return privacyOn === null ? undefined : privacyOn === 0 ? 'All off' : `${privacyOn} on`;
      default:
        return undefined;
    }
  }

  function rowFor(item: Item): Row {
    return {
      id: item.id,
      label: item.label,
      icon: item.icon,
      value: valueFor(item),
      href: resolve(item.route),
      // An admin, when the last check found a newer version (spec "Updates", level 3).
      badge: item.id === 'about' && updates.available ? UPDATE_AVAILABLE : undefined
    };
  }

  // The groups: the Household group only for an admin. "Report a problem" (mockup
  // Dark-Settings09-Phone; proposed, for cabledrawer) is a row of its own after About, for everyone.
  const groups: Group[] = $derived(
    GROUPS.filter((group) => admin || !group.adminOnly).map((group) => {
      const rows = ITEMS.filter((item) => item.group === group.name && (admin || !adminOnly(item)))
        .filter((item) => item.id !== 'your-kitchen' || kitchenNow !== null)
        .map(rowFor);
      if (group.name === 'You' && admin && settingsKnown.onboardingDone === false)
        rows.unshift({
          id: 'finish-setup',
          label: FINISH_SETUP,
          sub: FINISH_SETUP_WORDS,
          ring: { done: settingsKnown.done, of: SETUP_STEPS.length },
          href: resolve('/(app)/onboarding')
        });
      if (group.name === 'Mealwright')
        rows.push({
          id: 'report',
          label: 'Report a problem',
          icon: 'report',
          href: resolve('/(app)/settings/about/report')
        });
      return { ...group, rows };
    })
  );
</script>

<div class="phone-list">
  <PageHeader title="Settings" />

  <!-- Settings needs the server (spec section 6, "Opening the app offline"); the theme and Sign out
       still work offline, on their own pages. -->
  {#if network.down && settingsKnown.pints === null}
    <OfflineNote screen="Settings" />
  {/if}
  <PhoneList {groups} />
  <!-- The sidebar shows the version on a computer; this is the phone's place for it (N1). -->
  <p class="version">{VERSION_WORDS}</p>
</div>

<style>
  .phone-list {
    display: contents;
  }

  .version {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    text-align: center;
  }

  /* A computer is sent on to the first item; nothing flashes meanwhile. */
  @media (min-width: 768px) {
    .phone-list {
      display: none;
    }
  }
</style>
