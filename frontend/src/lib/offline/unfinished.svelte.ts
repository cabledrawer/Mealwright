// "Couldn't finish signing out" (docs/dev/sync-protocol.md section 12): the server answered,
// but didn't end the session (an error, not "can't reach"). Then the cookie still signs this
// browser in, and the sign-in page mustn't send it straight back into the app (which would
// sign it out again, and so on). The sign-in page says so instead, with "Try again".
//
// In memory only: a reload starts again, signs out again, and lands here again, once.

export const signOutState = $state({ unfinished: false });
