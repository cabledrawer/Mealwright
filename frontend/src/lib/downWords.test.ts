import { describe, expect, it } from 'vitest';
import {
  cantReachText,
  downBody,
  downLine,
  downTitle,
  needsServer,
  SERVER_DOWN_TRY_LATER
} from './downWords';

// cabledrawer 30 Oct: "the device has no network → "You're offline…"; the network is fine but the
// server doesn't answer → "Can't reach your Mealwright server…". Same wording on every page."
describe('the words while the server can’t be reached', () => {
  it('no network on this device: “You’re offline.”', () => {
    expect(downTitle(true)).toBe('You’re offline.');
    expect(downBody('Plan', true)).toBe(
      'Plan needs your Mealwright server. Your shopping list works offline.'
    );
    expect(downLine(true, (b) => `Plan changes ${b.when}.`)).toBe(
      'You’re offline. Plan changes when you’re back online.'
    );
    expect(cantReachText(true)).toBe('You’re offline. Check your connection.');
  });

  it('a network, but no answer from the server: “Can’t reach your Mealwright server.”', () => {
    expect(downTitle(false)).toBe('Can’t reach your Mealwright server.');
    expect(downBody('Plan', false)).toBe(
      'Plan comes back by itself when the server answers. Your shopping list works offline.'
    );
    expect(downLine(false, (b) => `it can’t be changed ${b.until}.`)).toBe(
      'Can’t reach your Mealwright server. it can’t be changed until it answers again.'
    );
    expect(cantReachText(false)).toBe('Can’t reach your Mealwright server. Check your connection.');
  });

  it('“+ Add to pantry” and the import screens: the server’s words by cause, the screen’s own offline sentence for the device', () => {
    expect(SERVER_DOWN_TRY_LATER).toBe(
      'Can’t reach your Mealwright server. Try again when it’s back.'
    );
    expect(needsServer(false, 'Importing needs it. Try again when you’re back online.')).toBe(
      SERVER_DOWN_TRY_LATER
    );
    expect(needsServer(true, 'Importing needs it. Try again when you’re back online.')).toBe(
      'Importing needs it. Try again when you’re back online.'
    );
  });

  it('never says “offline” about the server, or “server” about the device', () => {
    for (const rest of [(b: { when: string }) => `Save ${b.when}.`]) {
      expect(downLine(false, rest)).not.toMatch(/offline|back online/);
      expect(downLine(true, rest)).not.toMatch(/server/);
    }
  });
});
