# Single sign-on

Mealwright can let people sign in through your own sign-in server instead of (or as well as) a Mealwright password. It uses OpenID Connect (OIDC), which most self-hosted sign-in servers speak. Authentik, Keycloak and Authelia are examples.

Set it up on a computer, in Settings → Sign-in → Single sign-on. You need to be an admin. The phone shows "Set up on a computer".

## Before you start

- **Switch on the Privacy switch.** Mealwright talks to your sign-in server only while Settings → Privacy → Single sign-on is on. It is off by default. With it off, nothing is looked up or sent, and the setup screen says so.
- **Home network?** If your sign-in server is on your own network (an address like `192.0.2.5`, or a name that points there), Mealwright blocks it unless you add it in Settings → Privacy → Your own network. The setup screen shows the name to add. A server on the open internet needs nothing added.
- **https://.** The sign-in server's address must start with `https://`, unless it is a place you listed in Your own network. A port other than 80 or 443 also needs listing there.
- **Open Mealwright at the address people will use.** The redirect address (below) is made from the address in your browser's address bar. If you set it up at one address and someone signs in at another, they are told to open Mealwright at the address single sign-on was set up for.
- **Keep a way in.** Keep your password sign-in working until you have tested single sign-on (see "Try it").

## 1. Make a client at your sign-in server

In your sign-in server, make a new application, often called a "client" or "provider", of type OpenID Connect / OAuth2:

- **Confidential** (it has a client secret), using the **authorization code** flow. Mealwright also uses PKCE.
- **Redirect URL** (also called callback URL): `https://<your Mealwright address>/auth/callback`. The setup screen shows the exact address under "Give this to your sign-in server", with a Copy button. It must match exactly.
- **Scopes:** Mealwright asks for `openid`, `profile` and `email`. It adds `groups` when the groups come from a claim called `groups` and your server lists that scope (or lists none). It adds `offline_access` when your server lists it, so it gets a refresh token. If your server refuses a sign-in because of `offline_access`, Mealwright tries once more without it.
- **Groups:** if you want groups to decide who is an admin, make sure your server puts the user's groups in the ID token (or its userinfo answer) as a list of names, under the claim name you will give Mealwright (default `groups`).
- Note the **issuer address**, the **client ID** and the **client secret**.

The issuer address is the web address where `/.well-known/openid-configuration` lives, without that ending. Mealwright fetches `<issuer>/.well-known/openid-configuration` and checks that the issuer in it is the same as what you typed.

## 2. Fill in the setup screen

**1 · Your sign-in server**

- **Name on the button:** what people see on the sign-in page: "Sign in with *name*".
- **Issuer address:** from your sign-in server.
- **Client ID** and **Client secret:** from your sign-in server. The secret is stored encrypted on the server, with the key in `data/secret.key`. Leave it blank later to keep the saved one. Back up `secret.key` with your data ([backups.md](backups.md)): without it Mealwright can't read the saved secret, and an admin types it again.

**2 · Who gets in, and as what**

- **Groups come from:** the claim that holds the groups (default `groups`).
- **Group → Admin or Member:** add a row for each group you want to let in, and say whether it becomes Admin or Member. If someone is in more than one group, Admin wins.
- **Anyone else:** "Not let in" (the default) or "Member". Someone in none of your groups is treated this way.
- **Who is linked to whom:** Mealwright never makes an account at a first sign-in. The first time someone signs in with single sign-on, they are linked to the person here whose Mealwright username is exactly their username at your sign-in server (the `preferred_username` claim; spaces around it are ignored, but capitals count, and Mealwright usernames are all lowercase). Never by email address or name. An admin's account is linked this way only when your groups make the newcomer an Admin too. Anyone else waits until an admin says who they are (see "Who is this?" below).
- After that first sign-in, Mealwright finds the person by the sign-in server and its own ID for them (the `sub` claim), so a later change of user name there changes nothing here.
- Their role follows the groups at every sign-in. The household's last admin who can sign in is never made a Member this way.

**3 · Try it, then decide about passwords**

- Save, then press **Test sign-in**. It opens your sign-in server in a new tab, signs in, and shows the result on the setup screen, for example "Test passed: signed in as alex, groups mealwright-admins → Admin." The test changes nothing.
- If the test shows someone who would be an Admin, Mealwright asks "Link *you* to *them*?". Link only if it really is you: from then on, whoever signs in there as that person is you here, an admin.
- **Allow password sign-in:** it can be turned off only after an admin has signed in with single sign-on, so you can't lock yourself out. Off shows only the single sign-on button. If single sign-on can't start for any reason (the Privacy switch is off, the secret is lost, the server isn't on Your own network), passwords work again by themselves. On the server, the `reset-admin` command always works too ([README](../README.md), Troubleshooting).

## "Who is this?"

When someone signs in with single sign-on and matches nobody here, Mealwright lets them in to nothing. They see "Almost there": an admin needs to say who they are. No person is made.

An admin sees "1 sign-in waiting" at the top of **Settings → Household**, with **Who is this?**. It offers:

- **A person of the household:** their login is linked to that account (a person with no login gets one, with no password, made an Admin or a Member as your groups say). An admin is offered only when your groups make the newcomer an Admin too. A shared login, or someone linked to another account already, isn't offered.
- **A new person:** named as your sign-in server names them, with a login linked to that account.
- **Not someone I know: refuse:** that account can't sign in here, and isn't listed again, until an admin links it after all.

After a link, the person signs in with single sign-on again to get in. Only the 20 newest waiting sign-ins are kept. Only an admin of the household sees or answers them, and only those from the sign-in server saved now.

An admin also sees **Single sign-on** on each person's page in Settings → Household:

- **Linked to *lorna.s* on your sign-in server**, with **Unlink**. Unlinking ends that person's single sign-on sign-ins at once; a password they have still works. Their account is never linked automatically again: at its next sign-in it waits for "Who is this?". The household's last admin who can sign in is never unlinked while single sign-on is their only way in: make someone else an admin, or give them a password, first.
- **Not linked**, with **Link…**: pick, from the sign-ins waiting, the one that is this person. Nobody waiting? Ask them to sign in with single sign-on first.

## How long a sign-in lasts

When your sign-in server gives a refresh token, Mealwright checks it about once an hour. If the server says no (the account was removed or disabled there), Mealwright signs that person out too. If the server can't be reached, it tries again later. Mealwright's own limits still apply: signed out after 12 hours idle, or 30 days with "Remember".

When your sign-in server gives no refresh token, Mealwright can't check, so a single sign-on sign-in lasts at most one day, "Remember" or not (cabledrawer 13 Nov). After that, the person goes through your sign-in server again. A password sign-in isn't affected.

**Signing out:** after someone presses **Sign out** in Mealwright, the next "Sign in with …" on that browser asks your sign-in server to ask for the login again (`prompt=login`), so the next person on a shared computer isn't signed in as the last one (cabledrawer 13 Nov). Once someone has signed in with single sign-on on that browser, it no longer asks. Other browsers aren't affected.

Signing out at your sign-in server does not by itself end a Mealwright sign-in. Removing the person in Settings → Household does, at once.

**Taking an admin out at your sign-in server doesn't stop their API tokens on its own.** Make them a Member or remove them in Settings → Household. See [api.md](api.md).

## Delete everything without a password

An admin who signs in only with single sign-on (no Mealwright password, or password sign-in turned off) has no password to type on Settings → Your data → Delete everything. They press **Confirm at your sign-in server** instead (cabledrawer 13 Nov): Mealwright sends them there with `prompt=login` and `max_age=0`, so the server asks them to sign in again and says when they did (the `auth_time` claim). Mealwright accepts it only if:

- it is the same account at your sign-in server that this admin is linked to,
- your groups still make them an Admin,
- `auth_time` says they signed in after pressing the button (a minute's leeway for clocks).

They then have 10 minutes, in the same browser, to type the words and delete. The confirming is used once. If your sign-in server doesn't send `auth_time`, this can't be confirmed: give the admin a password (or turn password sign-in on) for this.

## Notes for particular servers

These are general. Mealwright's tests don't run against any of them, and screens change between versions.

- **Authentik:** make an OAuth2/OpenID provider and an application that uses it. Check that the `groups` scope is included in the scopes it may give (the server's own scope mappings), and copy the issuer from the provider's page.
- **Keycloak:** make an OpenID Connect client with client authentication switched on, and a mapper that adds groups to the token. The issuer includes the realm name. A user without Keycloak's `offline_access` role is refused when Mealwright asks for it; Mealwright then signs them in without a refresh token.
- **Authelia:** add a client under its OpenID Connect settings with the redirect URL above and the same scopes.

TODO(cabledrawer): I wrote the three server notes from general knowledge, not from the code or a test run. The Keycloak refusal and the `groups` scope are in the code (`backend/src/mealwright/sso.py`), but the rest is not. Check them against real setups, or cut them down to the generic steps above.

## If it doesn't work

The sign-in page shows a plain sentence. The common ones:

- "Single sign-on is switched off in Settings → Privacy": turn the switch on.
- "Your sign-in server is on your own network": add it in Settings → Privacy → Your own network.
- "Your sign-in server's address must start with https://": use an `https://` issuer, or list it in Your own network.
- "Mealwright couldn't reach your sign-in server": check the address, and that Mealwright's container can reach it.
- "Your sign-in server doesn't put you in a group Mealwright lets in": check the group names in step 2, and that your server sends groups.
- "Open Mealwright at the address single sign-on was set up for": use the same address you had when you saved the setup, or save it again from the new address.
- "Mealwright can't read the saved client secret": type the client secret again.

Logs hold no tokens, codes, secrets or claims. They name only the account's user name.
