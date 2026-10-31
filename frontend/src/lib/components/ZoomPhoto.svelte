<script lang="ts">
  // A photo you can tap to see full size (spec F29, cabledrawer 28 Oct: "when I click on the pic
  // should it become bigger"; mockup Dark-ImportCheck07-Desktop, the "Full size" pill). The
  // picture is a button; it opens the photo on its own over the page. Esc, a tap anywhere or the
  // Close button closes it, and focus goes back to the picture. Only ever our own server's
  // address, the same one the box shows: nothing else is fetched.
  import { onMount, tick, type Snippet } from 'svelte';
  import Icon from './Icon.svelte';

  let {
    src,
    width,
    height,
    alt,
    name,
    onerror,
    children
  }: {
    src: string;
    width: number;
    height: number;
    alt: string;
    /** The recipe's name, for the button's words. */
    name: string;
    onerror?: () => void;
    /** Extra things drawn over the picture, inside the button. */
    children?: Snippet;
  } = $props();

  let open = $state(false);
  let dialog = $state<HTMLDialogElement>();
  let opener = $state<HTMLButtonElement>();

  $effect(() => {
    if (open && dialog && !dialog.open) dialog.showModal();
  });

  async function close() {
    open = false;
    await tick(); // the page is usable again only once the photo's dialog is gone
    opener?.focus();
  }

  onMount(() => () => dialog?.close());
</script>

<button
  bind:this={opener}
  type="button"
  class="open"
  aria-label="Show the photo of {name} full size"
  onclick={() => (open = true)}
>
  <img {src} {alt} {width} {height} decoding="async" {onerror} />
  <span class="pill" aria-hidden="true"
    ><Icon name="full-size" size={13} stroke={2.4} />Full size</span
  >
  {@render children?.()}
</button>

{#if open}
  <dialog
    bind:this={dialog}
    class="viewer"
    aria-label={alt}
    oncancel={(e) => {
      e.preventDefault();
      void close();
    }}
    onclick={() => void close()}
  >
    <img class="big" {src} {alt} />
    <button
      type="button"
      class="close"
      onclick={(e) => {
        e.stopPropagation();
        void close();
      }}>Close</button
    >
  </dialog>
{/if}

<style>
  .open {
    position: absolute;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    padding: 0;
    border: none;
    background: none;
    cursor: zoom-in;
  }

  .open img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .pill {
    position: absolute;
    right: 8px;
    bottom: 8px;
    display: inline-flex;
    gap: 5px;
    align-items: center;
    padding: 4px 9px;
    border-radius: var(--radius-full);
    background: rgb(0 0 0 / 60%);
    color: #fff;
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  .viewer {
    width: 100vw;
    max-width: 100vw;
    height: 100dvh;
    max-height: 100dvh;
    margin: 0;
    padding: var(--space-5);
    box-sizing: border-box;
    border: none;
    background: rgb(0 0 0 / 88%);
    cursor: zoom-out;
  }

  .viewer[open] {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .viewer::backdrop {
    background: rgb(0 0 0 / 88%);
  }

  .big {
    display: block;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: var(--radius-lg);
  }

  .close {
    position: absolute;
    top: var(--space-5);
    right: var(--space-5);
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: rgb(0 0 0 / 60%);
    color: #fff;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
