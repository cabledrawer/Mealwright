// The Check screen is most of the import page's code, and only needed once a recipe has been read
// (or a draft opened), so both pages load it then (the page size limit). One loader, so the code
// is fetched once.

let loading: Promise<typeof import('./ReviewPage.svelte')> | null = null;

export const loadReviewPage = () => (loading ??= import('./ReviewPage.svelte'));
