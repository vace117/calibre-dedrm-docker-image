# Changelog

## V2.3.3

Fix the bookshelf login: KB moved onlinebibliotheek.nl from the iWelcome/OneWelcome
login (`login.kb.nl`) to Auth0 (`inloggen.kb.nl`), so the old flow ended on the
new login page and every refresh failed with "bookshelf still not authenticated".
`kb_login` now fills in the Auth0 login form directly, and reports Auth0's own
message on failure (e.g. "Onjuiste gebruikersnaam of wachtwoord"), plus captcha
or MFA prompts.

## V2.3.2

Auto-download robustness: books that can't be downloaded (read-online only /
reserved) are now reported per-book as "Book … not available for download"
instead of crashing the batch, and book URLs with accented characters (e.g.
"Ik ga tóch iets zeggen") are percent-encoded so they no longer raise a
UnicodeEncodeError. One failing book no longer aborts the others.

## V2.3.1

Add a **"Download loaned e-books to Calibre"** button to the add-on web UI —
manually triggers the loan download/import on demand (shown when
kb_username/kb_password are set), independent of the `auto_download_loans` toggle.

## V2.3.0

Add `auto_download_loans` (default off): automatically downloads each loaned
e-book that isn't in your Calibre library yet — grabs the `.acsm` from the book's
catalogue page and feeds it to the existing decrypt/import pipeline. Skips books
already in the library and re-downloads only once per loan period. Audiobooks are
skipped.

## V2.2.1

Remove the manual `kb_session_cookie` fallback (automatic login covers it) and
change the refresh interval to `library_poll_hours` (default 6) instead of
minutes.

## V2.2.0

Bookshelf sensor now logs in **automatically** with your `kb_username` +
`kb_password` by replicating KB's iWelcome/OneWelcome SSO login over HTTP — no
more manual cookies. The pasted-cookie option remains as an advanced fallback.
(Accounts that enforce 2FA are not supported.) Catalogue URLs are normalised to
absolute links.

## V2.1.1

Bookshelf sensor:

- Send browser-like headers (fixes HTTP 406 from the site's WAF) + gzip support.
- Cache the last successful result in `/data`; when the session expires the
  sensor keeps showing your last known loans (`stale: true`) instead of going
  `unavailable`, so loan info is never lost.
- Robust cookie parsing: accepts a bare `TDP_SESSIONID` value, a `name=value`
  pair, or a full cookie string pasted from devtools.
- Use a cookie jar so cookies the site sets during the login redirect are
  captured and resent.
- Better diagnostics on rejection: logs the redirect target / byte count and
  dumps the raw response to `/data/library_last_response.html` for inspection.

## V2.1.0

Add onlinebibliotheek.nl bookshelf sensor: paste your TDP_SESSIONID cookie
(`kb_session_cookie`) and the addon publishes `sensor.onlinebibliotheek_boekenplank`
listing your loaned books (title, author, format, due date). Refreshes every
`library_poll_minutes` (default 360).

## V1.8.0

Mail server working

## V1.7.0

First working version HA

## V1.9.6

Add ebooks via the same path, not just .ascm.
