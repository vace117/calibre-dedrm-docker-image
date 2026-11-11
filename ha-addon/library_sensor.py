#!/usr/bin/env python3
"""Read the onlinebibliotheek.nl "Mijn boekenplank" page and publish the loaned
books as a Home Assistant sensor.

Authentication is automatic: kb_login logs in via KB's Auth0 login (inloggen.kb.nl) using the
configured username + password, then this script parses the rendered bookshelf
HTML and pushes the result to Home Assistant via the Supervisor API.

Environment:
  KB_USERNAME         onlinebibliotheek.nl (KB) login
  KB_PASSWORD         onlinebibliotheek.nl password
  SUPERVISOR_TOKEN    Supervisor token for the HA core API (set by the Supervisor)
  SENSOR_ENTITY       Entity id to write (default: sensor.onlinebibliotheek_boekenplank)
  BOOKSHELF_URL       Override the bookshelf URL (default: the public account page)

Usage:
  python3 library_sensor.py              # log in, parse, publish to HA
  python3 library_sensor.py --parse FILE # parse a local HTML file, print JSON (for testing)
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser

BOOKSHELF_URL = os.environ.get(
    "BOOKSHELF_URL", "https://www.onlinebibliotheek.nl/account/boekenplank.html"
)
SENSOR_ENTITY = os.environ.get(
    "SENSOR_ENTITY", "sensor.onlinebibliotheek_boekenplank"
)
# Last successful result is cached here so the loaned books stay available even
# when the session cookie expires or the site is unreachable. /data persists
# across addon restarts.
CACHE_FILE = os.environ.get("CACHE_FILE", "/data/library_boekenplank.json")

# Dutch month abbreviations as they appear in "Geleend tot: zondag 5 jul 2026, 21:11"
_NL_MONTHS = {
    "jan": "01", "feb": "02", "mrt": "03", "apr": "04", "mei": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "okt": "10", "nov": "11", "dec": "12",
}


def _parse_due_date(text):
    """Turn 'zondag 5 jul 2026, 21:11' into ISO '2026-07-05T21:11', or None."""
    if not text:
        return None
    m = re.search(
        r"(\d{1,2})\s+([a-z]{3})[a-z]*\s+(\d{4})(?:,\s*(\d{1,2}):(\d{2}))?",
        text.lower(),
    )
    if not m:
        return None
    day, mon, year, hh, mm = m.groups()
    month = _NL_MONTHS.get(mon)
    if not month:
        return None
    iso = f"{year}-{month}-{int(day):02d}"
    if hh and mm:
        iso += f"T{int(hh):02d}:{mm}"
    return iso


class _BookshelfParser(HTMLParser):
    """Extracts books from the ``ul.plain.rich-list`` on the bookshelf page.

    Each book is a ``<li>`` containing a ``a.distinctparts`` link (catalogue id
    in the href), ``span.creator``, ``span.title``, a format ``p.additional``
    and a "Geleend tot" ``p.additional`` whose ``<strong>`` holds the due date.
    """

    def __init__(self):
        super().__init__()
        self.in_list = False          # inside ul.plain.rich-list
        self.li_depth = 0             # ul/li nesting depth while in the list
        self.books = []
        self._cur = None
        self._capture = None          # which field text we are collecting
        self._buf = []

    @staticmethod
    def _classes(attrs):
        d = dict(attrs)
        return set((d.get("class") or "").split()), d

    def handle_starttag(self, tag, attrs):
        classes, d = self._classes(attrs)
        if tag == "ul" and {"plain", "rich-list"} <= classes:
            self.in_list = True
            self.li_depth = 0
            return
        if not self.in_list:
            return

        if tag == "li":
            self.li_depth += 1
            if self.li_depth == 1:
                self._cur = {
                    "title": None, "author": None, "catalogue_id": None,
                    "url": None, "format": None, "due": None, "due_raw": None,
                }
            return
        if self._cur is None:
            return

        if tag == "a" and "distinctparts" in classes:
            href = d.get("href", "")
            # The live page returns relative hrefs (/catalogus/...); make absolute.
            if href.startswith("/"):
                href = "https://www.onlinebibliotheek.nl" + href
            self._cur["url"] = href
            m = re.search(r"/catalogus/(\d+)/", href)
            if m:
                self._cur["catalogue_id"] = m.group(1)
        elif tag == "span" and "creator" in classes:
            self._capture, self._buf = "author", []
        elif tag == "span" and "title" in classes:
            self._capture, self._buf = "title", []
        elif tag == "p" and "additional" in classes:
            # Format line carries a medium class (ebook / luisterboek / ...);
            # the "Geleend tot" line is a plain p.additional.
            medium = classes - {"additional", "separate", "medium"}
            if medium:
                self._cur["format"] = " ".join(sorted(medium))
            self._capture, self._buf = "additional", []
        elif tag == "strong" and self._capture == "additional" and \
                "geleend tot" in "".join(self._buf).lower():
            # The "Geleend tot:" label and the date <strong> share one <p>.
            self._cur["due_label"] = True
            self._capture, self._buf = "due", []

    def handle_data(self, data):
        if self._capture is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "ul" and self.in_list and self.li_depth == 0:
            self.in_list = False
            return
        if not self.in_list or self._cur is None:
            return

        if self._capture and tag in ("span", "p", "strong"):
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            field = self._capture
            self._capture, self._buf = None, []
            if field == "author" and text:
                self._cur["author"] = text
            elif field == "title" and text:
                self._cur["title"] = text
            elif field == "due":
                self._cur["due_raw"] = text
                self._cur["due"] = _parse_due_date(text)

        if tag == "li":
            if self.li_depth == 1:
                if self._cur.get("title"):
                    self._cur.pop("due_label", None)
                    self.books.append(self._cur)
                self._cur = None
            self.li_depth -= 1


def parse_books(html):
    p = _BookshelfParser()
    p.feed(html)
    return p.books


def bookshelf_notice(html, limit=400):
    """Visible text of the bookshelf section — used to explain a 0-book result
    (empty shelf, a KB warning/outage message, or a changed page layout)."""
    i = html.find("overview bookshelf")
    if i < 0:
        i = html.find("widget-bnl-mb-bookshelf")
    if i < 0:
        return None
    i = html.find(">", i) + 1  # start after the opening tag
    chunk = re.sub(r"<(script|style)\b.*?</\1>", " ", html[i:], flags=re.S)
    text = re.sub(r"<[^>]+>", " ", chunk)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("Vragen over verlengen of inleveren van boeken?", "").strip()
    return text[:limit] or None


def looks_authenticated(html):
    """The bookshelf widget only renders for a logged-in session. If the cookie
    expired, onlinebibliotheek.nl serves the (login) homepage instead."""
    return "widget-bnl-mb-bookshelf" in html or "overview bookshelf" in html


# A non-browser User-Agent / narrow Accept header gets rejected with HTTP 406 by
# the site's WAF, so mimic a real browser.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}


def _read_body(resp):
    """Read a response body, transparently decompressing gzip/deflate."""
    import gzip
    import zlib

    raw = resp.read()
    encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        raw = gzip.decompress(raw)
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def publish_to_ha(state, attributes):
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        print(">>> SUPERVISOR_TOKEN not set — cannot publish sensor.", file=sys.stderr)
        return False
    payload = {"state": state, "attributes": attributes}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://supervisor/core/api/states/{SENSOR_ENTITY}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status in (200, 201)


def load_cache():
    """Return the last successfully fetched payload, or None."""
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(books, fetched_at):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE) or ".", exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"books": books, "fetched_at": fetched_at}, f, ensure_ascii=False)
    except OSError as e:
        print(f">>> WARNING: could not write cache {CACHE_FILE}: {e}", file=sys.stderr)


BASE_ATTRS = {
    "friendly_name": "Onlinebibliotheek boekenplank",
    "icon": "mdi:bookshelf",
    "unit_of_measurement": "books",
}


def publish_books(books, stale, fetched_at, error=None):
    attrs = {
        **BASE_ATTRS,
        "books": books,
        "titles": [b["title"] for b in books],
        "stale": stale,
        "last_fetch_success": fetched_at,
    }
    if error:
        attrs["error"] = error
    return publish_to_ha(len(books), attrs)


def publish_from_cache(error):
    """The live fetch failed — keep showing the last known loans (flagged stale)
    so the loan information is never lost. Falls back to 'unavailable' only when
    nothing was ever cached."""
    cache = load_cache()
    if cache and cache.get("books") is not None:
        books = cache["books"]
        print(f">>> {error} — keeping last known {len(books)} book(s) from {cache.get('fetched_at')}.", file=sys.stderr)
        publish_books(books, stale=True, fetched_at=cache.get("fetched_at"), error=error)
        return
    print(f">>> {error} — no cached data yet, marking sensor unavailable.", file=sys.stderr)
    publish_to_ha("unavailable", {**BASE_ATTRS, "error": error})


def get_bookshelf():
    """Log in via kb_login (KB Auth0 login) and return (cookie_jar, html).
    Raises on failure (kb_login validates that the bookshelf was reached)."""
    user = os.environ.get("KB_USERNAME", "").strip()
    pw = os.environ.get("KB_PASSWORD", "")
    if not (user and pw):
        raise SystemExit(
            "No credentials configured — set kb_username + kb_password in the addon options."
        )
    import kb_login  # lazy import avoids a circular import at module load
    return kb_login.login(user, pw)


INPUT_DIR = os.environ.get("INPUT_DIR", "/share/calibre-dedrm/input")
CALIBRE_LIBRARY = os.environ.get("CALIBRE_LIBRARY", "").strip()
DOWNLOAD_STATE_FILE = os.environ.get(
    "DOWNLOAD_STATE_FILE", "/data/library_downloaded.json"
)


def _load_download_state():
    try:
        with open(DOWNLOAD_STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_download_state(state):
    try:
        os.makedirs(os.path.dirname(DOWNLOAD_STATE_FILE) or ".", exist_ok=True)
        with open(DOWNLOAD_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except OSError as e:
        print(f">>> WARNING: could not write {DOWNLOAD_STATE_FILE}: {e}", file=sys.stderr)


def _in_calibre_library(title):
    """True if a book with this title already exists in the configured Calibre
    library. Best-effort: if calibredb is unavailable or the library is unset,
    return False (we then rely on the download-state file for dedup)."""
    if not CALIBRE_LIBRARY or not title:
        return False
    import subprocess
    try:
        out = subprocess.run(
            ["calibredb", "search", f'title:"{title}"', "--with-library", CALIBRE_LIBRARY],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f">>> WARNING: calibredb check failed ({e}); relying on download state.", file=sys.stderr)
        return False
    # `search` exits 0 and prints ids when found; non-zero / "No books" when not.
    return out.returncode == 0 and out.stdout.strip() not in ("", "No books found")


def _safe_filename(name):
    name = re.sub(r"[^\w\s.-]", "", name, flags=re.UNICODE).strip()
    name = re.sub(r"\s+", "_", name)
    return name or "book"


def auto_download_loans(jar, books):
    """For each loaned book not already in Calibre, download its .acsm into the
    input dir so the existing pipeline decrypts and imports it."""
    import book_download
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    state = _load_download_state()
    os.makedirs(INPUT_DIR, exist_ok=True)
    new = 0
    for b in books:
        cid = b.get("catalogue_id")
        url = b.get("url")
        title = b.get("title") or "book"
        if not cid or not url:
            continue
        fmt = (b.get("format") or "").lower()
        if fmt and "ebook" not in fmt:
            # Audiobooks (luisterboek) etc. are not .acsm-downloadable.
            continue
        # Already downloaded for this loan period (same due date)?
        prev = state.get(cid)
        if prev and prev.get("due") == b.get("due"):
            continue
        if _in_calibre_library(title):
            print(f">>> Skipping '{title}' — already in Calibre library.")
            state[cid] = {"due": b.get("due"), "status": "in_library"}
            continue
        try:
            fallback = _safe_filename(f"{title}-{cid}") + ".acsm"
            name, content = book_download.download_acsm(opener, url, fallback_name=fallback)
            dest = os.path.join(INPUT_DIR, _safe_filename(f"{title}-{cid}") + ".acsm")
            with open(dest, "wb") as f:
                f.write(content)
            print(f">>> Downloaded '{title}' -> {dest} ({len(content)} bytes); queued for import.")
            state[cid] = {"due": b.get("due"), "status": "downloaded", "file": os.path.basename(dest)}
            new += 1
        except book_download.BookNotAvailable:
            # Read-online-only / reserved / expired. Not recorded in state — a
            # re-check is cheap and keeps the reported status accurate.
            print(f">>> Not available for download: '{title}'")
        except Exception as e:
            # Any other failure on one book must not abort the whole batch.
            print(f">>> WARNING: could not download '{title}': {e}", file=sys.stderr)
    _save_download_state(state)
    print(f">>> Auto-download: {new} new book(s) queued.")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--parse":
        with open(sys.argv[2], encoding="utf-8") as f:
            books = parse_books(f.read())
        print(json.dumps(books, indent=2, ensure_ascii=False))
        return

    debug = "--debug" in sys.argv
    # --download-now forces the auto-download regardless of the AUTO_DOWNLOAD_LOANS
    # toggle (used by the "Download now" button in the web UI).
    force_download = "--download-now" in sys.argv

    try:
        jar, html = get_bookshelf()
    except (urllib.error.URLError, OSError, RuntimeError) as e:
        # Network/HTTP/login error — retain the cached loan info instead of losing it.
        publish_from_cache(f"login failed: {e}")
        return

    if debug:
        print(">>> Authenticated OK — bookshelf reached.", file=sys.stderr)

    books = parse_books(html)
    fetched_at = datetime.now().isoformat(timespec="seconds")
    print(f">>> Found {len(books)} loaned book(s) on the bookshelf.")
    if not books:
        print(f">>> 0 books — bookshelf page ({len(html)} bytes) says: "
              f"{bookshelf_notice(html)!r}", file=sys.stderr)
    for b in books:
        due = b.get("due_raw") or "?"
        print(f"    - {b['title']} — {b.get('author') or '?'} ({b.get('format') or '?'}, due {due})")

    save_cache(books, fetched_at)
    if publish_books(books, stale=False, fetched_at=fetched_at):
        print(f">>> Published {SENSOR_ENTITY} = {len(books)}")
    else:
        print(">>> Failed to publish sensor (see warnings above).", file=sys.stderr)
        sys.exit(1)

    if force_download or os.environ.get("AUTO_DOWNLOAD_LOANS", "").lower() in ("1", "true", "yes"):
        auto_download_loans(jar, books)


if __name__ == "__main__":
    main()
