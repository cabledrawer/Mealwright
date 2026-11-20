<script lang="ts">
  import Stepper from '#lib/components/Stepper.svelte';

  let { start = 2, min = 1, max = 3 }: { start?: number; min?: number; max?: number } = $props();
  // svelte-ignore state_referenced_locally
  let n = $state(start);
</script>

<Stepper
  what="portions"
  label="Portions cooked"
  onless={() => n--}
  onmore={() => n++}
  lessOff={n <= min}
  moreOff={n >= max}
>
  {n}
</Stepper>
