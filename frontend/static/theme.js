// Runs in <head> before the page is drawn, so it never flashes the wrong theme.
// It's a separate file rather than an inline script, so the strict CSP allows it
// without a hash. src/lib/theme.svelte.ts takes over once the app has started and
// must use the same storage keys and rules.
(function () {
  var root = document.documentElement;
  var choice = null;
  try {
    choice = localStorage.getItem('mealwright.theme');
  } catch {
    // Storage can be blocked (private browsing); fall back to the defaults.
  }
  if (choice !== 'light' && choice !== 'dark') choice = 'auto';
  var dark =
    choice === 'dark' ||
    (choice === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  root.setAttribute('data-theme-choice', choice);
  root.setAttribute('data-theme', dark ? 'dark' : 'light');
})();
