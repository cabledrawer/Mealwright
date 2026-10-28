// Which copy of a recipe's photo to show: the large copy, or if only that one can't be fetched,
// the list copy (the one All recipes shows), or none if neither can (never a broken-image icon).
// Used by the recipe page and by Check. The addresses that failed are remembered with when: a
// different photo (a new address) gets its own go, and the same one tries again once the
// connection comes back (network.backAgain).

import type { PhotoOut } from '#lib/client/recipes.js';
import { network } from '#lib/network.svelte.js';

export interface ShownPhoto {
  url: string;
  width: number;
  height: number;
}

export class PhotoFallback {
  #failed = $state<{ urls: string[]; back: number }>({ urls: [], back: 0 });
  #photo: () => PhotoOut | null;

  constructor(photo: () => PhotoOut | null) {
    this.#photo = photo;
  }

  #gone(url: string): boolean {
    return network.backAgain === this.#failed.back && this.#failed.urls.includes(url);
  }

  /** The copy to show now, or null when there is none to show. */
  get shown(): ShownPhoto | null {
    const photo = this.#photo();
    if (!photo) return null;
    if (!this.#gone(photo.url)) return { url: photo.url, width: photo.width, height: photo.height };
    if (!this.#gone(photo.list_url))
      return { url: photo.list_url, width: photo.list_width, height: photo.list_height };
    return null;
  }

  /** The picture at `url` couldn't be fetched. */
  fail(url: string): void {
    const urls = network.backAgain === this.#failed.back ? this.#failed.urls : [];
    this.#failed = { urls: [...urls, url], back: network.backAgain };
  }
}
