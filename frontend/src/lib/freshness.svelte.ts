// Something in the kitchen changed (a food edit, an Undo, a merge): screens that show
// foods or stock look at `kitchen.version` and fetch again when it moves on. Simple and
// enough until live updates (Server-Sent Events) arrive in 0.3.

class Freshness {
  version = $state(0);

  /** Say that foods or stock changed on the server. */
  changed(): void {
    this.version++;
  }
}

export const kitchen = new Freshness();
