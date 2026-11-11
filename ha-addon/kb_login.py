#!/usr/bin/env python3
"""Automated login to onlinebibliotheek.nl via KB's Auth0 Universal Login.

Since Nov 2026 the account pages redirect to inloggen.kb.nl (Auth0, "New
Universal Login") instead of the old iWelcome/OneWelcome login.kb.nl. This
replicates the browser flow with plain HTTP so the bookshelf can be read from a
stored username + password (no browser, no manual cookie).

Flow:
  0. GET the bookshelf -> 302 inloggen.kb.nl/authorize?... -> 302 /u/login?state=X
     (Auth0 sets its transaction cookies; the page holds a hidden `state` field)
  1. POST /u/login?state=X  form: state, username, password, action=default
     -> 302 /authorize/resume -> 302 boekenplank.logged.in.html?code=...
     -> onlinebibliotheek.nl exchanges the code and sets the TDP session
  2. GET the bookshelf again -> authenticated HTML

Logging is verbose on purpose so a change in the flow is visible in the add-on log.

Usage:
  KB_USERNAME=... KB_PASSWORD=... python3 kb_login.py
  (set KB_DUMP_HTML=/path/page.html to save the fetched bookshelf page)
"""
import html as html_lib
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

# Reuse the browser headers, body reader and parser from the sensor module.
from library_sensor import (
    BOOKSHELF_URL,
    _BROWSER_HEADERS,
    _read_body,
    bookshelf_notice,
    looks_authenticated,
    parse_books,
)

AUTH0_HOST = "inloggen.kb.nl"
AUTH0_ORIGIN = "https://" + AUTH0_HOST


def log(msg):
    print(f">>> {msg}", file=sys.stderr)


def _new_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return opener, jar


def _strip_query(url):
    return url.split("?")[0]


def _open(opener, url, *, data=None, headers=None, method=None):
    """Return (final_url, status, body). HTTP errors are returned, not raised,
    because Auth0 answers a failed login with HTTP 400 + the re-rendered form."""
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={**_BROWSER_HEADERS, **(headers or {})})
    verb = method or ("POST" if data else "GET")
    try:
        resp = opener.open(req, timeout=30)
        body = _read_body(resp)
        final, status = resp.geturl(), resp.status
    except urllib.error.HTTPError as e:
        body = _read_body(e)
        final, status = e.geturl() or url, e.code
    log(f"{verb} {_strip_query(url)} -> HTTP {status}, {len(body)} bytes, "
        f"final={_strip_query(final)}")
    return final, status, body


def _primary_form_fields(page):
    """Hidden inputs of Auth0's primary login form (state, persist, ...)."""
    m = re.search(r'<form\b[^>]*data-form-primary="true"[^>]*>(.*?)</form>', page, re.S)
    form = m.group(1) if m else page
    fields = {}
    for tag in re.findall(r"<input\b[^>]*>", form):
        if 'type="hidden"' not in tag:
            continue
        name = re.search(r'\bname="([^"]+)"', tag)
        value = re.search(r'\bvalue="([^"]*)"', tag)
        if name:
            fields[name.group(1)] = html_lib.unescape(value.group(1)) if value else ""
    return fields


def _has_captcha(page):
    """A real captcha widget element (the JS bundle always mentions the attribute)."""
    return re.search(r"<div\b[^>]*\bdata-captcha-sitekey=", page) is not None


def _auth0_error(page):
    """Extract the user-facing error text Auth0 renders under a field, e.g.
    <span id="error-element-password" data-error-code="wrong-username-credentials">
      <span class="ulp-input-error-icon"></span>Onjuiste gebruikersnaam of wachtwoord</span>"""
    seen = []
    for tag, inner in re.findall(
            r'(<span\b[^>]*\bid="error-element-[^"]*"[^>]*>)'
            r'((?:<span\b[^>]*></span>)?[^<]*)</span>', page):
        code = (re.search(r'\bdata-error-code="([^"]*)"', tag) or [None, None])[1]
        text = html_lib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        msg = f"{text} [{code}]" if text and code else (text or code)
        if msg and msg not in seen:
            seen.append(msg)
    # Drop bare codes that are already shown next to a message.
    seen = [m for m in seen if not any(o != m and o.endswith(f"[{m}]") for o in seen)]
    return "; ".join(seen) or None


def login(username, password):
    """Return (jar, bookshelf_html) on success. Raises RuntimeError otherwise."""
    opener, jar = _new_opener()

    # Step 0 — hit the bookshelf; follow the redirects to the Auth0 login page.
    login_url, status, page = _open(opener, BOOKSHELF_URL)
    if looks_authenticated(page):
        log("bookshelf already authenticated (unexpected for a fresh session).")
        return jar, page
    if urllib.parse.urlsplit(login_url).netloc != AUTH0_HOST or "/u/login" not in login_url:
        raise RuntimeError(
            f"expected a redirect to {AUTH0_ORIGIN}/u/login but ended at "
            f"{_strip_query(login_url)} (HTTP {status}) — the login flow changed again.")
    if _has_captcha(page):
        raise RuntimeError("Auth0 login page shows a captcha — automated login is blocked.")

    fields = _primary_form_fields(page)
    if "state" not in fields:
        raise RuntimeError("no hidden 'state' field on the Auth0 login page.")
    log(f"Auth0 login page reached; form fields = {sorted(fields)}")

    # Step 1 — submit username + password (identifier+password on one page).
    form = {**fields, "username": username, "password": password, "action": "default"}
    final, status, body = _open(
        opener, login_url,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Origin": AUTH0_ORIGIN, "Referer": login_url},
        method="POST")

    host = urllib.parse.urlsplit(final).netloc
    if host == AUTH0_HOST:
        # Still on Auth0: wrong credentials, captcha, MFA, or another prompt.
        err = _auth0_error(body)
        path = urllib.parse.urlsplit(final).path
        if "mfa" in path:
            raise RuntimeError("Auth0 asks for a second factor (MFA) — not supported.")
        if _has_captcha(body):
            raise RuntimeError("Auth0 now requires a captcha — automated login is blocked.")
        raise RuntimeError(f"login rejected by Auth0 at {path} (HTTP {status})"
                           + (f": {err}" if err else ""))

    # Step 2 — the callback should have set the session; fetch the bookshelf.
    html = body
    if not looks_authenticated(html):
        _, _, html = _open(opener, BOOKSHELF_URL)
    if not looks_authenticated(html):
        raise RuntimeError(
            f"Auth0 login succeeded (landed on {_strip_query(final)}) but the "
            "bookshelf is still not authenticated — inspect the step log above.")
    log("authenticated — bookshelf reached.")
    return jar, html


def main():
    user = os.environ.get("KB_USERNAME", "").strip()
    pw = os.environ.get("KB_PASSWORD", "")
    if not user or not pw:
        raise SystemExit("Set KB_USERNAME and KB_PASSWORD environment variables.")
    jar, html = login(user, pw)
    dump = os.environ.get("KB_DUMP_HTML")
    if dump:
        with open(dump, "w", encoding="utf-8") as f:
            f.write(html)
        log(f"bookshelf HTML saved to {dump}")
    books = parse_books(html)
    log(f"Found {len(books)} loaned book(s) ({len(html)} bytes):")
    if not books:
        log(f"bookshelf page says: {bookshelf_notice(html)!r}")
    for b in books:
        print(f"    - {b['title']} — {b.get('author') or '?'} "
              f"({b.get('format') or '?'}, due {b.get('due_raw') or '?'})")
    print(json.dumps(books, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
