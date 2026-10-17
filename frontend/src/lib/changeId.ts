// A client-made ID for each change (a random UUID). The server uses it to spot a change
// it has already saved, so sending the same change twice (a retry, or later the 0.3
// offline queue) never applies it twice.

/** A version 4 UUID made from 16 random bytes. */
export function uuidFromBytes(bytes: Uint8Array): string {
  if (bytes.length !== 16) throw new Error('A UUID needs 16 bytes');
  const b = Uint8Array.from(bytes);
  b[6] = (b[6]! & 0x0f) | 0x40; // version 4
  b[8] = (b[8]! & 0x3f) | 0x80; // RFC 4122 variant
  const hex = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/**
 * A new change ID. crypto.randomUUID() exists only on https:// and localhost, and the
 * admin can allow plain http:// for testing, so fall back to getRandomValues(), which
 * works everywhere.
 */
export function newChangeId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return uuidFromBytes(crypto.getRandomValues(new Uint8Array(16)));
}
