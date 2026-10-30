// The words while the server can't be reached, the same on every page, chosen by the cause
// (cabledrawer 30 Oct): "One steady message from the start, chosen by the cause: the device has
// no network → "You're offline…"; the network is fine but the server doesn't answer →
// "Can't reach your Mealwright server…". Same wording on every page, and it stays until
// things change." `device` is network.deviceOffline (the browser says there's no network).

/** The first sentence. */
export const downTitle = (device: boolean): string =>
  device ? 'You’re offline.' : 'Can’t reach your Mealwright server.';

/** The rest of a screen's note, under the title (OfflineNote). */
export const downBody = (screen: string, device: boolean): string =>
  device
    ? `${screen} needs your Mealwright server. Your shopping list works offline.`
    : `${screen} comes back by itself when the server answers. Your shopping list works offline.`;

/** "when you’re back online" / "until you’re back online", or the same for the server. */
export interface Back {
  when: string;
  until: string;
}

const BACK_ONLINE: Back = { when: 'when you’re back online', until: 'until you’re back online' };
const SERVER_BACK: Back = { when: 'when it answers again', until: 'until it answers again' };

/** A one-line note on a screen that still shows (saved copy, sheet): the title, then `rest`,
 *  e.g. downLine(device, (b) => `Plan changes ${b.when}.`). */
export const downLine = (device: boolean, rest: (back: Back) => string): string =>
  `${downTitle(device)} ${rest(device ? BACK_ONLINE : SERVER_BACK)}`;

/** The message of a request that couldn't reach the server (ApiError 0, toasts and notes). */
export const cantReachText = (device: boolean): string =>
  device
    ? 'You’re offline. Check your connection.'
    : 'Can’t reach your Mealwright server. Check your connection.';
