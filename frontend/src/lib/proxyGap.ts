// 502, 503 and 504 come from the reverse proxy (Caddy, nginx…) when it can't reach Mealwright:
// the server is down or restarting. For the app that is "can't reach the server", the same as
// no answer at all (spec section 6, "Server down (F67's cause)", cabledrawer 28 Oct). Kept in its
// own file so api.ts and the online check (network.svelte.ts) share it without importing
// each other.

export const PROXY_GAP: ReadonlySet<number> = new Set([502, 503, 504]);

/** The answer came from the reverse proxy, not from Mealwright. */
export function proxyGap(status: number): boolean {
  return PROXY_GAP.has(status);
}
