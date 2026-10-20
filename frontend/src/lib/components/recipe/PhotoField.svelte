<script lang="ts">
  // The recipe's photo (mockups RecipeEditor-*, EditorState-uploading and -photo-error).
  // Picking uploads at once; the editor keeps the upload's id for Save. On a phone the
  // browser's own picker offers "Take photo" or the photo library: Mealwright never asks
  // for the camera itself.
  import '$lib/styles/fields.css';
  import Icon from '../Icon.svelte';
  import type { DraftPhoto } from '$lib/recipes/draft.svelte';

  let {
    photo,
    onpick,
    onremove
  }: {
    photo: DraftPhoto;
    onpick: (file: File) => void;
    onremove: () => void;
  } = $props();

  const uid = $props.id();
  let picker: HTMLInputElement;

  function chosen() {
    const file = picker.files?.[0];
    picker.value = ''; // the same file can be picked again
    if (file) onpick(file);
  }
</script>

<div class="photo">
  <input
    bind:this={picker}
    class="visually-hidden"
    type="file"
    accept="image/jpeg,image/png,image/webp"
    tabindex="-1"
    aria-hidden="true"
    onchange={chosen}
  />

  {#if photo.uploading}
    <div class="frame uploading" role="status">
      <span class="words">Uploading photo…</span>
      <span class="bar" role="progressbar" aria-label="Uploading photo"><span></span></span>
    </div>
  {:else if photo.shown}
    <img class="frame" src={photo.shown.url} alt="Cover for this recipe" />
    <span class="buttons">
      <button type="button" class="mw-pill" onclick={() => picker.click()}>Change photo</button>
      <button type="button" class="mw-pill" onclick={onremove}>Remove photo</button>
    </span>
  {:else}
    <button
      type="button"
      class="frame empty"
      class:problem={!!photo.error}
      aria-describedby={photo.error ? `${uid}-error` : undefined}
      onclick={() => picker.click()}
    >
      <span class="camera"><Icon name="photo" size={26} /></span>
      <span class="title">Add a photo</span>
      {#if !photo.error}<span class="sub">Take one or choose from your photos</span>{/if}
    </button>
  {/if}

  {#if photo.error}
    <p id="{uid}-error" class="error" role="alert">
      <Icon name="alert" size={18} /><span>{photo.error}</span>
    </p>
  {/if}

  <p class="note">
    <Icon name="info" size={16} />Hidden details like location are removed before the photo is kept.
  </p>
</div>

<style>
  .photo {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .frame {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    width: 100%;
    height: 150px;
    border-radius: var(--radius-xl);
    background: var(--color-photo);
    color: var(--color-photo-text);
  }

  img.frame {
    object-fit: cover;
  }

  .empty {
    border: 2px dashed var(--color-add-border);
    background: var(--color-surface);
    color: var(--color-text);
    cursor: pointer;
  }

  .empty.problem {
    height: 120px;
    border-color: var(--color-warning-text);
  }

  .camera {
    display: flex;
    color: var(--color-accent);
  }

  .title {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .uploading {
    gap: var(--space-5);
  }

  .words {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .bar {
    width: 60%;
    height: 8px;
    overflow: hidden;
    border-radius: 4px;
    background: var(--color-surface);
  }

  .bar span {
    display: block;
    width: 40%;
    height: 100%;
    background: var(--color-accent);
    animation: slide 1.2s ease-in-out infinite alternate;
  }

  @keyframes slide {
    to {
      transform: translateX(150%);
    }
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .error {
    display: flex;
    align-items: flex-start;
    gap: var(--space-4);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .note {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  @media (min-width: 768px) {
    .frame {
      height: 170px;
    }
  }
</style>
