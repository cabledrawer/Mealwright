import { describe, expect, it } from 'vitest';
import type { ImportReview } from './client/imports';
import { SAMPLE_REVIEW } from './testing/importSamples';
import { headingAbove, needsYou, walkItems } from './importWalk';

const review = (over: Partial<ImportReview> = {}): ImportReview => ({
  ...SAMPLE_REVIEW,
  lines: structuredClone(SAMPLE_REVIEW.lines),
  steps: structuredClone(SAMPLE_REVIEW.steps),
  ...over
});

describe('the order of One at a time', () => {
  it('walks the lines that need you (to confirm and needs you), then every step, none skipped', () => {
    const r = review();
    const labels = r.lines.map((l) => (l.kind === 'ingredient' ? l.label : 'heading'));
    const items = walkItems(r);
    const lines = items.filter((i) => i.kind === 'line');
    const steps = items.filter((i) => i.kind === 'step');
    // Every line the Check screen marks as needing the person, and no other.
    expect(lines.map((i) => r.lines[i.at]!.label)).toEqual(
      labels.filter((l) => l === 'to_confirm' || l === 'needs_you')
    );
    expect(lines.length).toBe(r.counts.to_confirm + r.counts.needs_you);
    // Every step, in order; a heading is not a step.
    expect(steps.map((i) => r.steps[i.at]!.text)).toEqual([
      'Boil the dal until soft.',
      'Add the vegetables and simmer.'
    ]);
    // Lines first, then steps.
    expect(items.map((i) => i.kind)).toEqual([
      ...lines.map(() => 'line'),
      ...steps.map(() => 'step')
    ]);
    // Places are in the review's own order.
    expect(lines.map((i) => i.at)).toEqual([...lines.map((i) => i.at)].sort((a, b) => a - b));
  });

  it('stops at a ready line the save refused, among the lines in the review’s own order', () => {
    const r = review();
    const ready = r.lines.findIndex((l) => l.kind === 'ingredient' && l.label === 'matched');
    expect(walkItems(r).some((i) => i.kind === 'line' && i.at === ready)).toBe(false);
    const items = walkItems(r, ready);
    const lines = items.filter((i) => i.kind === 'line').map((i) => i.at);
    expect(lines).toContain(ready);
    expect(lines).toEqual([...lines].sort((a, b) => a - b));
    // A heading is never a stop, whatever the save said.
    const heading = r.lines.findIndex((l) => l.kind === 'heading');
    expect(walkItems(r, heading)).toEqual(walkItems(r));
  });

  it('walks every step, not only the long ones', () => {
    const r = review({
      steps: [
        { kind: 'step', text: 'Boil.' },
        { kind: 'step', text: 'One. Two. Three. Four. Five.' },
        { kind: 'heading', text: 'To serve' },
        { kind: 'step', text: 'Eat.' }
      ]
    });
    expect(walkItems(r).filter((i) => i.kind === 'step')).toEqual([
      { kind: 'step', at: 0 },
      { kind: 'step', at: 1 },
      { kind: 'step', at: 3 }
    ]);
  });

  it('has only steps when no line needs you, and nothing when there are none either', () => {
    const ready = review({
      lines: SAMPLE_REVIEW.lines.filter((l) => l.kind === 'ingredient' && l.label === 'matched')
    });
    expect(walkItems(ready).every((i) => i.kind === 'step')).toBe(true);
    expect(walkItems(ready)).toHaveLength(2);
    expect(walkItems({ lines: ready.lines, steps: [] })).toEqual([]);
  });

  it('does not count headings, matched lines or staples', () => {
    const [heading, matched, , toConfirm, , , staple] = SAMPLE_REVIEW.lines;
    expect([heading, matched, staple].some((l) => needsYou(l!))).toBe(false);
    expect(needsYou(toConfirm!)).toBe(true);
  });

  it('finds the heading a step is under', () => {
    const steps = SAMPLE_REVIEW.steps;
    expect(headingAbove(steps, 1)).toBe('The tempering');
    expect(headingAbove(steps, 2)).toBe('The tempering');
    expect(headingAbove([{ kind: 'step', text: 'Boil.' }], 0)).toBeNull();
  });
});
