<script lang="ts">
  // Tags (cabledrawer 19 Oct, questions 9 and 40): chips. Typing shows tags the household already
  // uses; Enter or a comma adds one; × takes it off. A new tag is just typed. No tag screen.
  import '#lib/styles/fields.css';
  import Icon from '../Icon.svelte';
  import { MAX_TAG_CHARS, MAX_TAGS } from '#lib/recipes/draft.svelte.js';

  let {
    tags = $bindable(),
    suggest,
    error
  }: {
    tags: string[];
    /** Tags already used, starting with what was typed (suggestTags). */
    suggest: (q: string) => Promise<{ name: string }[]>;
    error?: string;
  } = $props();

  const uid = $props.id();
  let text = $state('');
  let focused = $state(false);
  let known = $state<string[]>([]);
  let problem = $state<string | null>(null);
  let asked = 0;

  const has = (name: string) =>
    tags.some((t) => t.toLocaleLowerCase() === name.toLocaleLowerCase());
  const offered = $derived(known.filter((name) => !has(name)).slice(0, 8));

  $effect(() => {
    const q = text.trim();
    const mine = ++asked;
    if (!focused) return;
    const timer = setTimeout(() => {
      suggest(q)
        .then((list) => {
          if (mine === asked) known = list.map((t) => t.name);
        })
        .catch(() => {
          if (mine === asked) known = [];
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  function add(raw: string) {
    problem = null;
    text = '';
    // A pasted "quick, kids" is two tags.
    for (const part of raw.split(',')) {
      const name = part.replace(/\s+/g, ' ').trim();
      if (!name || has(name)) continue;
      if (name.length > MAX_TAG_CHARS) {
        problem = `A tag can have up to ${MAX_TAG_CHARS} characters.`;
        text = name;
      } else if (tags.length >= MAX_TAGS) {
        problem = `A recipe can have up to ${MAX_TAGS} tags.`;
        text = name;
      } else {
        tags.push(name);
      }
    }
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault();
      add(text);
    } else if (event.key === 'Backspace' && !text && tags.length) {
      tags.pop();
    }
  }
</script>

<div class="tags">
  <label class="mw-label" for="{uid}-in">Tags <span class="mw-optional">(optional)</span></label>
  <div class="box" class:invalid={!!(problem || error)}>
    {#each tags as tag (tag)}
      <span class="chip">
        {tag}
        <button
          type="button"
          aria-label="Remove tag {tag}"
          onclick={() => tags.splice(tags.indexOf(tag), 1)}
        >
          <Icon name="close" size={14} stroke={2.6} />
        </button>
      </span>
    {/each}
    <input
      id="{uid}-in"
      type="text"
      placeholder="Add a tag"
      autocomplete="off"
      aria-describedby="{uid}-hint"
      bind:value={text}
      onkeydown={keydown}
      onfocus={() => (focused = true)}
      onblur={() => {
        focused = false;
        add(text);
      }}
    />
  </div>
  {#if offered.length}
    <ul class="offered" aria-label="Tags you’ve used before">
      {#each offered as name (name)}
        <li>
          <!-- A press here would blur the box first; keep the box's text out of it. -->
          <button
            type="button"
            class="mw-add"
            onpointerdown={(e) => e.preventDefault()}
            onclick={() => add(name)}
          >
            {name}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
  {#if problem || error}<p class="mw-error" role="alert">{problem ?? error}</p>{/if}
  <p id="{uid}-hint" class="mw-hint">
    Type a tag and press Enter. Tags you’ve used before are suggested.
  </p>
</div>

<style>
  .tags {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .box {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    min-height: 52px;
    padding: var(--space-3);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
  }

  .box:focus-within {
    outline: 2px solid var(--color-focus);
    outline-offset: 1px;
  }

  .box.invalid {
    border-color: var(--color-warning-text);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1) var(--space-1) var(--space-1) var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .chip button {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: inherit;
    cursor: pointer;
  }

  /* A touch area of at least 44 × 44 px around the smaller button. */
  .chip button::before {
    content: '';
    position: absolute;
    inset: -8px;
  }

  input {
    flex: 1 1 6rem;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  input:focus {
    outline: none;
  }

  .offered {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }
</style>
