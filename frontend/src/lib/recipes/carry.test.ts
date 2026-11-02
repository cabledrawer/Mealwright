import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearCarried, readCarried, writeCarried } from './carry';
import { RecipeDraft } from './draft.svelte';

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe('carrying the editor in the tab', () => {
  it('writes, reads and clears by editor', () => {
    const draft = new RecipeDraft();
    draft.name = 'Sambar';
    writeCarried('new', draft.toCarried());
    writeCarried('edit:3', draft.toCarried());
    expect((readCarried('new') as { name: string }).name).toBe('Sambar');
    clearCarried('new');
    expect(readCarried('new')).toBeNull();
    expect(readCarried('edit:3')).not.toBeNull();
  });

  it('puts the boxes back into a fresh draft', () => {
    const draft = new RecipeDraft();
    draft.name = 'Dosa';
    draft.tags = ['quick'];
    draft.lines[0]!.words = 'rice';
    draft.steps[0]!.text = 'Soak.';
    writeCarried('new', draft.toCarried());
    const fresh = new RecipeDraft();
    fresh.markSaved();
    expect(fresh.applyCarried(readCarried('new'))).toBe(true);
    expect(fresh.name).toBe('Dosa');
    expect(fresh.tags).toEqual(['quick']);
    expect(fresh.lines[0]!.words).toBe('rice');
    expect(fresh.steps[0]!.text).toBe('Soak.');
    expect(fresh.dirty).toBe(true);
  });

  it('a draft typed on an older version keeps that version, so Save meets the changed-recipe note', () => {
    const typed = new RecipeDraft();
    typed.opened = { version: 3 } as RecipeDraft['opened'];
    typed.name = 'Mine';
    const fresh = new RecipeDraft();
    fresh.opened = { version: 5, photo: null } as RecipeDraft['opened'];
    expect(fresh.applyCarried(typed.toCarried())).toBe(true);
    expect(fresh.name).toBe('Mine');
    expect(fresh.opened?.version).toBe(3);
  });

  it('ignores something that is not a kept editor', () => {
    const fresh = new RecipeDraft();
    expect(fresh.applyCarried(null)).toBe(false);
    expect(fresh.applyCarried({ name: 5 })).toBe(false);
    expect(fresh.applyCarried('x')).toBe(false);
    expect(fresh.name).toBe('');
  });

  it('reads nothing from broken text', () => {
    sessionStorage.setItem('mw.recipeDraft.new', '{oops');
    expect(readCarried('new')).toBeNull();
  });

  it('works when the tab cannot keep anything', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('full');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => writeCarried('new', new RecipeDraft().toCarried())).not.toThrow();
    expect(readCarried('new')).toBeNull();
    expect(() => clearCarried('new')).not.toThrow();
  });
});
