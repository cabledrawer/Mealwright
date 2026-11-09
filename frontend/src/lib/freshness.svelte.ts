// Something in the kitchen changed (a food edit, an Undo, a merge): screens that show
// foods or stock look at `kitchen.version` and fetch again when it moves on. Simple and
// enough until live updates (Server-Sent Events) arrive in 0.3.

class Freshness {
  /** Moves on after any change: lists fetch again. */
  version = $state(0);
  /**
   * Moves on only after a change made somewhere other than an open editor (an Undo, a
   * merge from the list): open editors fetch their food again. Not after the editor's
   * own saves, which already show the server's answer.
   */
  elsewhere = $state(0);
  /**
   * Moves on after a change made on the Settings page (a meal, a shop or a place, an amount
   * setting): Settings' Recent changes fetch again to show it (F176).
   */
  settings = $state(0);

  /** Say that Settings itself wrote something. */
  wroteSettings(): void {
    this.settings++;
  }

  /** Say that foods or stock changed on the server. */
  changed(options: { elsewhere?: boolean } = {}): void {
    this.version++;
    if (options.elsewhere) this.elsewhere++;
  }
}

export const kitchen = new Freshness();
