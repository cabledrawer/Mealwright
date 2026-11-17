// About's update words (X1): how old a version is, the release day, the last check's answer.

import { describe, expect, it } from 'vitest';
import {
  OLD_AFTER_MONTHS,
  ageWords,
  agoWords,
  dailyWords,
  lastWords,
  monthsBetween,
  releasedWords,
  shortLink,
  sourceAtVersion,
  sourceLink,
  versionHeading
} from './aboutWords';

describe('how old a version is', () => {
  it('counts whole months', () => {
    expect(monthsBetween('2026-11-12', '2026-11-12')).toBe(0);
    expect(monthsBetween('2026-11-12', '2027-02-11')).toBe(2);
    expect(monthsBetween('2026-11-12', '2027-02-12')).toBe(3);
    expect(monthsBetween('2026-11-30', '2027-03-15')).toBe(3);
    expect(monthsBetween('2026-11-12', '2026-10-01')).toBe(0); // a clock set wrong: never negative
  });

  it('says nothing for the first three months (cabledrawer 12 Nov)', () => {
    expect(OLD_AFTER_MONTHS).toBe(3);
    expect(ageWords('2026-11-12', '2027-02-11')).toBeNull();
    expect(ageWords('2026-11-12', '2027-02-12')).toBe('This version is 3 months old.');
    expect(ageWords('2026-11-12', '2027-03-20')).toBe('This version is 4 months old.');
    expect(ageWords('2026-11-12', '2029-01-01')).toBe('This version is 2 years old.');
  });

  it('writes the release day as the mockup does', () => {
    expect(releasedWords('2026-11-12')).toBe('Released 12 Nov 2026');
  });

  it('shortens the releases page', () => {
    expect(shortLink('https://github.com/placeholder_until_1_0/mealwright/releases')).toBe(
      'github.com/…/mealwright/releases'
    );
    expect(shortLink('not a link')).toBe('not a link');
  });

  it('shows the version without its v, pre-releases in tag form', () => {
    expect(versionHeading('0.9.0')).toBe('Mealwright 0.9.0');
    expect(versionHeading('0.9.0b1')).toBe('Mealwright 0.9.0-beta.1');
  });
});

describe('the last check', () => {
  const now = new Date('2026-12-01T12:00:00Z');
  const at = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();

  it('says when', () => {
    expect(agoWords(at(0), now)).toBe('just now');
    expect(agoWords(at(1), now)).toBe('1 minute ago');
    expect(agoWords(at(5), now)).toBe('5 minutes ago');
    expect(agoWords(at(60), now)).toBe('1 hour ago');
    expect(agoWords(at(60 * 5), now)).toBe('5 hours ago');
    expect(agoWords(at(60 * 24), now)).toBe('1 day ago');
    expect(agoWords(at(60 * 72), now)).toBe('3 days ago');
  });

  it('says each answer in plain words', () => {
    expect(lastWords({ outcome: 'newer', latest: 'v0.9.1', checked_at: at(0) }, now)).toEqual({
      title: 'Mealwright 0.9.1 is out',
      detail: 'Checked just now · see what’s new',
      outcome: 'newer'
    });
    expect(lastWords({ outcome: 'up_to_date', latest: null, checked_at: at(5) }, now).title).toBe(
      'You have the newest version'
    );
    expect(lastWords({ outcome: 'failed', latest: null, checked_at: at(5) }, now)).toMatchObject({
      title: 'Couldn’t check for updates',
      detail: 'Checked 5 minutes ago. Try again later.'
    });
  });

  it('says whether the daily check is on', () => {
    expect(dailyWords(false)).toEqual({ detail: 'Turn on in Outside connections', value: 'Off' });
    expect(dailyWords(true).value).toBe('On');
  });
});

describe('sourceLink (U1)', () => {
  it('is the releases page without its last part', () => {
    expect(sourceLink('https://github.com/owner/mealwright/releases')).toBe(
      'https://github.com/owner/mealwright'
    );
  });
});

describe('sourceAtVersion (16g)', () => {
  it('is the source at the version tag, in tag form', () => {
    const page = 'https://github.com/sam-kitchen/mealwright/releases';
    expect(sourceAtVersion(page, '0.9.5')).toBe(
      'https://github.com/sam-kitchen/mealwright/tree/v0.9.5'
    );
    expect(sourceAtVersion(page, '0.9.0b1')).toBe(
      'https://github.com/sam-kitchen/mealwright/tree/v0.9.0-beta.1'
    );
  });
  it('is nothing while the address is the placeholder', () => {
    expect(
      sourceAtVersion('https://github.com/placeholder_until_1_0/mealwright/releases', '0.9.5')
    ).toBeNull();
  });
});
