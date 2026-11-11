# Calibre DeDRM — Home Assistant Add-on

Watches `/share/calibre-dedrm/input/` for `.acsm` files, decrypts them to DRM-free ePubs using **libgourou** (native Linux ADEPT — no Wine) + Calibre DeDRM, and writes the output to `/share/calibre-dedrm/books/`.

Optionally imports each book into a Calibre library, pushes it to a send2ereader instance, sends an HA notification, and/or emails the ePub as an attachment.

> **Architecture note:** `amd64` only (libgourou build). Will not run on Raspberry Pi (aarch64/armv7).

---

## First-run setup

First start activates the device with Adobe's servers (~5 seconds). Subsequent starts are instant — activation data is persisted in `/data/adept/`.

Set `adobe_email` and `adobe_password` in the **Configuration** tab before starting. After successful activation the credentials are no longer needed for day-to-day processing; they are only used again if `/data/adept/` is deleted.

---

## Configuration options

### Required (first run only)

| Option | Description |
| --- | --- |
| `adobe_email` | Adobe ID email — required for first-time device activation |
| `adobe_password` | Adobe ID password (masked in UI) |

### Calibre library

| Option | Description |
| --- | --- |
| `calibre_library` | Path to a Calibre library directory to import each book into, e.g. `/share/calibre/library`. The directory is created as a new empty library if it does not exist. Leave empty to disable. |

### Kobo delivery (send2ereader)

| Option | Description |
| --- | --- |
| `send2ereader_url` | URL of the send2ereader add-on, e.g. `http://homeassistant.local:3001` — leave empty to disable |
| `calibre_web_url` | URL of a Calibre-Web instance, e.g. `http://homeassistant.local:8083` — shown as a quick link in the upload UI, leave empty to hide |

### Notifications

| Option | Description |
| --- | --- |
| `notify_services` | List of HA notification service names to ping when a book is ready, e.g. `mobile_app_phone` (omit the `notify.` prefix) — leave empty to disable |

### Email delivery

| Option | Description |
| --- | --- |
| `email_to` | List of email addresses to send the decrypted ePub to as an attachment — leave empty to disable |
| `smtp_host` | SMTP server hostname, e.g. `smtp.gmail.com` — required to enable email delivery |
| `smtp_port` | SMTP port (default `587`, STARTTLS) |
| `smtp_user` | SMTP login username (usually your email address) |
| `smtp_password` | SMTP password or app password (masked in UI) |

### Onlinebibliotheek bookshelf sensor

Publishes a Home Assistant sensor listing the e-books and audiobooks you currently
have on loan from [onlinebibliotheek.nl](https://www.onlinebibliotheek.nl).

| Option | Description |
| --- | --- |
| `kb_username` | Your onlinebibliotheek.nl (KB) login — the add-on logs in automatically via KB's Auth0 login (`inloggen.kb.nl`) |
| `kb_password` | Your onlinebibliotheek.nl password (masked in UI) |
| `library_poll_hours` | How often to refresh the sensor, in hours (default `6`) |
| `auto_download_loans` | Automatically download loaned e-books that aren't in your Calibre library yet (default `false`) |

Set `kb_username` + `kb_password` to enable it. The add-on replicates KB's
Auth0 login (`inloggen.kb.nl`) over HTTP, completes the OAuth redirect, and reads
your bookshelf — no browser or manual cookie needed. Accounts that enforce
two-factor authentication (2FA/OTP) are **not** supported by this flow.

The add-on creates **`sensor.onlinebibliotheek_boekenplank`**:

- **state**: number of books currently on loan
- **attributes**: `books` (list with `title`, `author`, `format`, `due` ISO date,
  `catalogue_id`, `url`), `titles` (flat list of titles), `stale` (bool),
  `last_fetch_success` (timestamp)

The last successful result is cached in `/data/library_boekenplank.json`
(persists across restarts), so if a refresh ever fails (login error, site down)
the sensor **keeps showing your last known loans** with `stale: true` and an
`error` attribute. It only becomes `unavailable` if it has never managed a
successful fetch.

Ready-to-paste Lovelace card + automations (due-soon reminder, session-expired
alert) are in [`examples/lovelace-and-automations.yaml`](examples/lovelace-and-automations.yaml).

**Auto-download (`auto_download_loans: true`):** on each poll the add-on opens
each loaned e-book's catalogue page, grabs its `.acsm` download link, and drops
the `.acsm` into the input dir — the normal pipeline then decrypts it to a
DRM-free ePub (and imports it into `calibre_library` if configured). Books
already in the Calibre library are skipped, and each loan is downloaded only once
per loan period (tracked in `/data/library_downloaded.json`). Audiobooks are
skipped. Note this triggers Adobe fulfillment, hence it is off by default.

---

## Usage

**Browser upload:** Open the add-on's web UI via the sidebar. Drag and drop (or select) an `.acsm` file and click **Upload** — it is queued immediately. If email is configured, a per-address toggle appears so you can choose which addresses receive the book. Configured `send2ereader_url` and `calibre_web_url` appear as quick-link buttons at the bottom of the page.

**Download loaned e-books:** When `kb_username`/`kb_password` are set, the web UI
shows a **Download loaned e-books to Calibre** button that fetches any loaned
e-books not yet in your library on demand (same as `auto_download_loans`, but
manual). It may take a minute while it logs in and downloads.

**Manual drop:** Place `.acsm` files in `/share/calibre-dedrm/input/` via SSH, Samba, or the HA File Editor add-on.

The add-on polls every 30 seconds, processes each file, and writes the decrypted ePub to `/share/calibre-dedrm/books/`. Files that fail are renamed to `.failed`.

---

## Volume layout

| Path in container | Purpose |
| --- | --- |
| `/data/adept/` | libgourou activation data — persisted across restarts |
| `/data/calibre-config/` | Calibre plugin state and DeDRM marker |
| `/share/calibre-dedrm/input/` | Drop `.acsm` files here |
| `/share/calibre-dedrm/books/` | Decrypted ePub output |
| `/share/calibre-dedrm/resources/` | Optional: place `DeDRM_Plugin.zip` / `Obok_plugin.zip` here if the build-time download fails |
| `/media/` | Available for `calibre_library` paths under `/media/` |

---

## Troubleshooting

**`.failed` files in input folder**
Check the add-on log. Common causes: device not activated (wrong credentials), ACSM file has expired (Adobe ACSM files are valid ~60 days), or no internet access to Adobe's fulfillment servers.

**`Invalid activation file` in the log**
A previous activation attempt failed and left a partial `activation.xml`. Delete `/data/adept/` via SSH or the File Editor and restart the add-on with correct credentials.

**Notifications not arriving**
Ensure the service name in `notify_services` matches what HA shows under **Developer Tools → Services** (e.g. `mobile_app_davids_phone`, without the `notify.` prefix).

**Email fails**
The add-on logs the SMTP host, port, and username before each attempt, followed by a specific error (authentication failure, connection refused, message too large, etc.). Gmail requires an [App Password](https://myaccount.google.com/apppasswords) if 2FA is enabled. Maximum attachment size is typically 25 MB — the log will warn if the ePub exceeds this.
