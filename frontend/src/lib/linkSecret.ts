// A sign-in or Reset password link is "/join#<secret>" (link hardening, cabledrawer 13 Nov): what
// follows a `#` never leaves the browser, so the secret is never in a request line, a reverse
// proxy's access log or a Referer. The link page takes it from the address, clears it from the
// address bar before anything else (so it isn't left in the history either), and posts it.

/** The secret after the `#`, once: the address bar keeps only the page's own address. */
export function takeLinkSecret(): string {
  // As it is: a real secret is letters, digits, "-" and "_" only.
  const secret = location.hash.replace(/^#/, '');
  if (location.hash) {
    history.replaceState(history.state, '', location.pathname + location.search);
  }
  return secret;
}
