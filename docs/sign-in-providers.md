# Sign-in providers (Google, and more later)

`api/auth/oauth.py` implements OAuth 2.0 authorization code + PKCE with
a signed, 10-minute `state` (also echo-checked in the browser). Sessions
are the same access + rotating refresh grant as password sign-in.

## Enable Google

1. Google Cloud Console → APIs & Services → Credentials → *OAuth client
   ID* → Web application.
2. Authorized redirect URI: `{APP_BASE_URL}/auth/callback/google`
   (e.g. `http://localhost:5173/auth/callback/google` in dev).
3. Set `OAUTH_GOOGLE_CLIENT_ID` and `OAUTH_GOOGLE_CLIENT_SECRET`. The
   "Continue with Google" button appears only when both are set.

## Account rules

* Known Google identity → signs in.
* New identity, unknown email (must be Google-verified) → new account,
  email already verified, no password (they can add one via the reset
  link in Settings; delete-account confirms by typing the email).
* New identity, email already has an account → **never merged
  silently**: the person enters that account's password once to link.

## Adding another provider

Add an entry to `PROVIDERS` (authorize/token/userinfo URLs, scopes, and
a `profile()` mapping if the userinfo shape isn't OpenID Connect) plus
`OAUTH_<ID>_CLIENT_ID/SECRET` settings and a mark in `OAuthButtons.tsx`.
Nothing in session handling changes.
