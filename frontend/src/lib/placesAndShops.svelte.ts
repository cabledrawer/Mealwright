// The household's places (Fridge, Freezer, Cupboard, Spice rack…) and shops, fetched
// once and shared by the editor and the pantry.
//
// Forgotten on every way of signing out, so none of them carries over to whoever signs in
// next without a reload: the Sign out button and the sign-out warning (both wipe, wipe.ts),
// a session that ends (a 401, or the live stream's signed_out: below), another tab's wipe
// ((app)/+layout.svelte), and a late answer naming another login ((app)/+layout.ts).

import { ApiError, codeOf, forgetWhenSessionEnds } from './api';
import { addPlace, addShop, getPlaces, getShops } from './client/foods';
import type { Place, PlaceKind, Shop } from './client/types';

class PlacesAndShops {
  places = $state<Place[]>([]);
  shops = $state<Shop[]>([]);
  #loading: Promise<void> | null = null;
  /** Goes up each time they're forgotten, so an answer to an earlier login is dropped. */
  #generation = 0;
  /** Places already asked about by reloadFor(), so one the server lacks isn't asked about again. */
  #asked = new Set<number>();
  /** Places and shops added here, in order, so a fetch asked for before one was added (and
   * answering after it) keeps it. */
  #addedPlaces: Place[] = [];
  #addedShops: Shop[] = [];

  /** Fetch them (once; later calls wait for the same answer). */
  load(force = false): Promise<void> {
    if (!this.#loading || force) {
      const [placesAsked, shopsAsked] = [this.#addedPlaces.length, this.#addedShops.length];
      const loading: Promise<void> = Promise.all([getPlaces(), getShops()])
        .then(([places, shops]) => {
          // Forgotten (signed out) while asking: the answer is the last login's, so it's dropped.
          if (this.#loading !== loading) return;
          this.places = withLater(places, this.#addedPlaces.slice(placesAsked));
          this.shops = withLater(shops, this.#addedShops.slice(shopsAsked));
        })
        .catch((error: unknown) => {
          if (this.#loading === loading) this.#loading = null;
          throw error;
        });
      this.#loading = loading;
    }
    return this.#loading;
  }

  /** A picker was given a place that isn't in the list (made on another phone: nothing tells
   * this one): fetch them all again, once per place. Not asked for yet: the picker's own
   * load() will bring them. */
  async reloadFor(id: number | null | undefined): Promise<void> {
    if (id == null || this.#asked.has(id) || !this.#loading) return;
    const generation = this.#generation;
    await this.#loading.catch(() => {});
    if (generation !== this.#generation || this.places.some((p) => p.id === id)) return;
    this.#asked.add(id);
    await this.load(true).catch(() => {});
  }

  /** Forget them (another login's household may be next): the next load() fetches again. */
  forget(): void {
    this.#generation += 1;
    this.#loading = null;
    this.#asked.clear();
    this.#addedPlaces = [];
    this.#addedShops = [];
    this.places = [];
    this.shops = [];
  }

  /** "+ Shop": adds it, or finds the one already called that. */
  async addShop(name: string): Promise<Shop> {
    const generation = this.#generation;
    const shop = await addShop(name.trim());
    // Forgotten (signed out) while asking: the shop is the last login's, so it isn't kept.
    if (generation !== this.#generation) return shop;
    this.#addedShops.push(shop);
    if (!this.shops.some((s) => s.id === shop.id)) this.shops = [...this.shops, shop];
    return shop;
  }

  /** "+ Place": adds it last, or finds the one already called that (the server says so with a
   * 409 `place_exists`), so the screen can just pick it. A network failure is thrown. */
  async addPlace(name: string, kind: PlaceKind): Promise<Place> {
    const generation = this.#generation;
    let place: Place;
    try {
      place = await addPlace(name.trim(), kind);
    } catch (error) {
      const found = error instanceof ApiError ? existingPlace(error) : null;
      if (!found) throw error;
      place = found;
    }
    // Not fetched yet: fetch them all now (a list holding only this place would look loaded).
    if (!this.#loading && generation === this.#generation) await this.load().catch(() => {});
    // Forgotten (signed out) while asking: the place is the last login's, so it isn't kept.
    if (generation !== this.#generation) return place;
    this.#addedPlaces.push(place);
    if (!this.places.some((p) => p.id === place.id)) this.places = [...this.places, place];
    return place;
  }
}

/** A fetched list, with what was added after it was asked for and isn't in it yet, last. */
function withLater<T extends { id: number }>(list: T[], later: T[]): T[] {
  const missing = later.filter(
    (a, i) => !list.some((x) => x.id === a.id) && later.findIndex((b) => b.id === a.id) === i
  );
  return [...list, ...missing];
}

/** The place a 409 `place_exists` names. */
function existingPlace(error: ApiError): Place | null {
  if (error.status !== 409 || codeOf(error.body) !== 'place_exists') return null;
  const place = (error.body as { place?: Place }).place;
  return place && typeof place.id === 'number' ? place : null;
}

export const placesAndShops = new PlacesAndShops();

forgetWhenSessionEnds(() => placesAndShops.forget());
