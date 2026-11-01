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

  /** Fetch them (once; later calls wait for the same answer). */
  load(force = false): Promise<void> {
    if (!this.#loading || force) {
      const loading: Promise<void> = Promise.all([getPlaces(), getShops()])
        .then(([places, shops]) => {
          // Forgotten (signed out) while asking: the answer is the last login's, so it's dropped.
          if (this.#loading !== loading) return;
          this.places = places;
          this.shops = shops;
        })
        .catch((error: unknown) => {
          if (this.#loading === loading) this.#loading = null;
          throw error;
        });
      this.#loading = loading;
    }
    return this.#loading;
  }

  /** Forget them (another login's household may be next): the next load() fetches again. */
  forget(): void {
    this.#generation += 1;
    this.#loading = null;
    this.places = [];
    this.shops = [];
  }

  /** "+ Shop": adds it, or finds the one already called that. */
  async addShop(name: string): Promise<Shop> {
    const generation = this.#generation;
    const shop = await addShop(name.trim());
    // Forgotten (signed out) while asking: the shop is the last login's, so it isn't kept.
    if (generation !== this.#generation) return shop;
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
    // Forgotten (signed out) while asking: the place is the last login's, so it isn't kept.
    if (generation !== this.#generation) return place;
    if (!this.places.some((p) => p.id === place.id)) this.places = [...this.places, place];
    return place;
  }
}

/** The place a 409 `place_exists` names. */
function existingPlace(error: ApiError): Place | null {
  if (error.status !== 409 || codeOf(error.body) !== 'place_exists') return null;
  const place = (error.body as { place?: Place }).place;
  return place && typeof place.id === 'number' ? place : null;
}

export const placesAndShops = new PlacesAndShops();

forgetWhenSessionEnds(() => placesAndShops.forget());
