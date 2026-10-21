// Opened as whoever was last signed in on this device before the server had said who is
// signed in (a weak signal: +layout.ts, sync-protocol 11.4). Until it says, nothing the
// server lists may go into this device's copy: its session might be another login's, whose
// list must never be written over this one's. Sending is safe meanwhile, as every batch
// names its login and the server turns away another login's (409 other_login, 11.5).
// (cabledrawer 20 Oct, hand test.)

let held: { until: Promise<void>; release: () => void } | null = null;

/** Hold the server's lists back until releaseServerLists(). */
export function holdServerLists(): void {
  if (held) return;
  let release!: () => void;
  const until = new Promise<void>((done) => (release = done));
  held = { until, release };
}

/** The server has said who is signed in, and the start has acted on it. */
export function releaseServerLists(): void {
  const was = held;
  held = null;
  was?.release();
}

/** Resolves once the server's lists may be read; null when they may be read now. */
export function serverListsHeld(): Promise<void> | null {
  return held?.until ?? null;
}
