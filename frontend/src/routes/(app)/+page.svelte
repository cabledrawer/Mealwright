<script lang="ts">
  import EmptyState from '#lib/components/EmptyState.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';

  // "Saturday 17 October", in the browser's own language settings.
  const today = new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long'
  }).format(new Date());
</script>

<PageHeader title="Today" overline={today} />

<EmptyState title="Nothing here yet">
  This is where you’ll see what you’re eating today, the tubs you have left and what to use soon.
</EmptyState>
