import { describe, expect, it } from 'vitest';
import { linkedWords } from './linkedWords';

const toor = { name: 'Toor Dal', other_names: ['thuvaram paruppu', 'arhar dal'] };

describe('the words of a linked line (cabledrawer 25 Oct)', () => {
  it('fills in the full name when the words are only the start of it', () => {
    expect(linkedWords('thu', toor)).toBe('Toor Dal');
    expect(linkedWords('  TOO ', { name: 'Toor Dal' })).toBe('Toor Dal');
    expect(linkedWords('E', { name: 'Egg' })).toBe('Egg');
    expect(linkedWords('pan', { name: 'Paneer' })).toBe('Paneer');
  });

  it('fills in the full name from the start of another name', () => {
    expect(linkedWords('thuvaram', toor)).toBe('Toor Dal');
  });

  it('keeps words typed in full, and words that say something else', () => {
    expect(linkedWords('toor dal', toor)).toBe('toor dal');
    expect(linkedWords('thuvaram paruppu', toor)).toBe('thuvaram paruppu');
    expect(linkedWords('fresh coriander', { name: 'Coriander' })).toBe('fresh coriander');
    expect(linkedWords('the podi', { name: 'Sambar podi' })).toBe('the podi');
    expect(linkedWords('dal', toor)).toBe('dal');
    expect(linkedWords('thu', { name: 'Toor Dal' })).toBe('thu');
  });

  it('keeps a full other name even when it starts the ingredient’s own name', () => {
    expect(linkedWords('Dal', { name: 'Dal makhani', other_names: ['dal'] })).toBe('Dal');
  });

  it('never changes the words of a line with no ingredient, or with no words', () => {
    expect(linkedWords('thu', null)).toBe('thu');
    expect(linkedWords('', toor)).toBe('');
  });
});
