// The Check screen is most of the import page's code, and only needed once a recipe has been read
// (or a draft opened), so both pages load it then (the page size limit). One loader, so the code
// is fetched once. A failed load is forgotten; the browser itself keeps a failed script, though, so the pages' Try
// again reloads the page (a browser test blocks the chunk once to show it).

type Page = typeof import('./ReviewPage.svelte');

/** A loader that remembers a good load and forgets a failed one. */
export function onceLoader<T>(fetchIt: () => Promise<T>): () => Promise<T> {
  let loading: Promise<T> | null = null;
  return () => {
    if (!loading) {
      const attempt = fetchIt();
      loading = attempt;
      attempt.catch(() => {
        if (loading === attempt) loading = null;
      });
    }
    return loading;
  };
}

export const loadReviewPage = onceLoader<Page>(() => import('./ReviewPage.svelte'));

/** Said when the Check screen's code could not be fetched (proposed, for cabledrawer). */
export const REVIEW_LOAD_FAILED = 'Couldn’t open the Check screen. Try again.';
