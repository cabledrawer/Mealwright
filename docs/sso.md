# Single sign-on

Mealwright can let people sign in through your own sign-in server instead of (or as well as) a Mealwright password. It uses OpenID Connect (OIDC), which most self-hosted sign-in servers speak. Authentik, Keycloak and Authelia are examples.

Set it up on a computer, in Settings → Sign-in → Single sign-on. You need to be an admin. The phone shows "Set up on a computer".

## Before you start

- **Switch on the Privacy switch.** Mealwright talks to your sign-in server only while Settings → Privacy → Single sign-on is on. It is off by default. With it off, nothing is looked up or sent, and the setup screen says so.
- **Home network?** If your sign-in server is on your own network (an address like `192.168.1.5`, or a name that points there), Mealwright blocks it unless you add it in Settings → Privacy → Your own network. The setup screen shows the name to add. A server on the open internet needs nothing added.
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
- **Make an account on first sign-in:** on, the first time someone from your sign-in server signs in, Mealwright makes their account. Off, an admin first links each person in Settings → Household. If the new person's user name is already taken here, they are refused with a message instead.
- Mealwright finds a person by the sign-in server and its own ID for them (the `sub` claim), never by user name or email, so a sign-in server can't take over a password account by using its name.
- Their role follows the groups at every sign-in. The household's last admin who can sign in is never made a Member this way.

**3 · Try it, then decide about passwords**

- Save, then press **Test sign-in**. It opens your sign-in server in a new tab, signs in, and shows the result on the setup screen, for example "Test passed: signed in as tess, groups mealwright-admins → Admin." The test changes nothing.
- If the test shows someone who would be an Admin, Mealwright asks "Link *you* to *them*?". Link only if it really is you: from then on, whoever signs in there as that person is you here, an admin.
- **Allow password sign-in:** it can be turned off only after an admin has signed in with single sign-on, so you can't lock yourself out. Off shows only the single sign-on button. If single sign-on can't start for any reason (the Privacy switch is off, the secret is lost, the server isn't on Your own network), passwords work again by themselves. On the server, the `reset-admin` command always works too ([README](../README.md), Troubleshooting).

## How long a sign-in lasts

When your sign-in server gives a refresh token, Mealwright checks it about once an hour. If the server says no (the account was removed or disabled there), Mealwright signs that person out too. If the server can't be reached, it tries again later. Mealwright's own limits still apply: signed out after 12 hours idle, or 30 days with "Remember".

Signing out at your sign-in server does not by itself end a Mealwright sign-in. Removing the person in Settings → Household does, at once.

**Taking an admin out at your sign-in server doesn't stop their API tokens on its own.** Make them a Member or remove them in Settings → Household. See [api.md](api.md).

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
