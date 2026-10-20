// Whether Recipes has room for its three panes (nav · recipe list · reading pane; spec "Platform
// emphasis" and "Recipe page"). The sidebar is the first pane; the list and the reading pane
// need the width beside it: a list of 300 px at least, a line, and a reading pane of about
// 470 px. Below that (a tablet held upright, a narrow window) the sidebar stays and Recipes shows
// one page at a time, the list and then the recipe, just as on a phone. On a phone (no sidebar)
// it is always one page at a time.

import { sidebar } from './sidebar.svelte';

/** The width of the sidebar (tokens.css: --sidebar-width, --sidebar-collapsed-width). */
const SIDEBAR = 248;
const SIDEBAR_COLLAPSED = 72;
/** The app's desktop breakpoint: from here the sidebar replaces the bottom tabs. */
const DESKTOP = 768;
/** What the list and the reading pane need beside the sidebar. */
export const PANES_MIN_AREA = 776;

/** Whether `viewport` px wide has room for the three panes, with the sidebar open or collapsed. */
export function panesFit(viewport: number, collapsed: boolean): boolean {
  return (
    viewport >= DESKTOP && viewport - (collapsed ? SIDEBAR_COLLAPSED : SIDEBAR) >= PANES_MIN_AREA
  );
}

class RecipePanes {
  width = $state(typeof window === 'undefined' ? 0 : window.innerWidth);

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('resize', () => (this.width = window.innerWidth));
    }
  }

  /** The window has room for the three panes. */
  get fits(): boolean {
    return panesFit(this.width, sidebar.collapsed);
  }
}

export const recipePanes = new RecipePanes();
