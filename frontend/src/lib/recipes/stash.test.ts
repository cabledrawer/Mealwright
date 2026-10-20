import { describe, expect, it } from 'vitest';
import { RecipeDraft } from './draft.svelte';
import { claim, editorKey, keep, reopen } from './stash';

describe('the cancelled editor', () => {
  it('has a key for a new recipe and one for each recipe being edited', () => {
    expect(editorKey(null)).toBe('new');
    expect(editorKey(7)).toBe('edit:7');
  });

  it('comes back only when Undo asked for it, and only once', () => {
    const draft = new RecipeDraft();
    keep('new', draft);
    expect(claim('new')).toBeNull(); // a fresh editor never takes it
    expect(reopen('edit:3')).toBe(false);
    expect(reopen('new')).toBe(true);
    expect(claim('edit:3')).toBeNull();
    expect(claim('new')).toBe(draft);
    expect(claim('new')).toBeNull();
  });
});
