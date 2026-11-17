// What the "Finish setup" row and the phone list's first values need, read once by the Settings
// layout and shared by the list beside the page (computer) and the list that is the phone's
// /settings page. An admin who skipped set-up sees the row until it is done (cabledrawer 12 Nov);
// nobody is sent back to it.
import { getShops } from '#lib/client/foods.js';
import { getHousehold } from '#lib/client/household.js';
import { getPeople } from '#lib/client/people.js';
import type { Pints } from '#lib/client/types.js';
import { peopleWhoCount, stepsDone } from './finishRing.js';

class SettingsKnown {
  /** Whether set-up was finished (null until the server has said). */
  onboardingDone = $state<boolean | null>(null);
  /** The household's pint, once the server has said. */
  pints = $state<Pints | null>(null);
  /** People who eat here, without shared logins: what the ring counts. */
  eaters = $state<number | null>(null);
  shops = $state<number | null>(null);

  /** Steps of set-up done, for the ring. */
  get done(): number {
    return stepsDone({ people: this.eaters, shops: this.shops });
  }

  /** Read again what the household says; for an admin who hasn't finished, also the ring's counts. */
  async load(admin: boolean): Promise<void> {
    try {
      const household = await getHousehold();
      this.pints = household.pints;
      this.onboardingDone = household.onboarding_done;
    } catch {
      return; // offline or unreachable: nothing shows that needs it
    }
    if (!admin || this.onboardingDone !== false) return;
    await Promise.all([
      getPeople().then(
        (found) => (this.eaters = peopleWhoCount(found.people)),
        () => {}
      ),
      getShops().then(
        (found) => (this.shops = found.length),
        () => {}
      )
    ]);
  }

  forget(): void {
    this.onboardingDone = null;
    this.pints = null;
    this.eaters = null;
    this.shops = null;
  }
}

export const settingsKnown = new SettingsKnown();
