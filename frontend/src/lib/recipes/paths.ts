// Where the editor goes. The recipe's own page (/recipes/{id}) comes with the recipe page pull
// request, so these addresses are written out here and checked by hand, not by the router's
// typed paths.

import { goto } from '$app/navigation';

export const RECIPES = '/recipes';
export const NEW_RECIPE = '/recipes/new';
export const recipePage = (id: number) => `/recipes/${id}`;
export const editPage = (id: number) => `/recipes/${id}/edit`;

export function go(path: string, options: { replaceState?: boolean } = {}): Promise<void> {
  // eslint-disable-next-line svelte/no-navigation-without-resolve -- the paths above are this app's own
  return goto(path, options);
}
