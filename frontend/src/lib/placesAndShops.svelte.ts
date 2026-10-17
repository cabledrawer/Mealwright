// The household's places (Fridge, Freezer, Cupboard, Spice rack…) and shops, fetched
// once and shared by the editor and the pantry.

import { addShop, getPlaces, getShops } from './client/foods';
import type { Place, Shop } from './client/types';

class PlacesAndShops {
  places = $state<Place[]>([]);
  shops = $state<Shop[]>([]);
  #loading: Promise<void> | null = null;

  /** Fetch them (once; later calls wait for the same answer). */
  load(force = false): Promise<void> {
    if (!this.#loading || force) {
      this.#loading = Promise.all([getPlaces(), getShops()])
        .then(([places, shops]) => {
          this.places = places;
          this.shops = shops;
        })
        .catch((error: unknown) => {
          this.#loading = null;
          throw error;
        });
    }
    return this.#loading;
  }

  /** "+ Shop": adds it, or finds the one already called that. */
  async addShop(name: string): Promise<Shop> {
    const shop = await addShop(name.trim());
    if (!this.shops.some((s) => s.id === shop.id)) this.shops = [...this.shops, shop];
    return shop;
  }
}

export const placesAndShops = new PlacesAndShops();
