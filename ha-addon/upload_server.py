#!/usr/bin/env python3
"""Minimal book upload server — served via HA ingress."""
import email.parser
import html
import http.server
import json
import os
import pathlib
import subprocess
import urllib.parse

INPUT_DIR = os.environ.get("INPUT_DIR", "/share/calibre-dedrm/input")
PORT = int(os.environ.get("INGRESS_PORT", "8099"))
LIBRARY_SENSOR = os.environ.get("LIBRARY_SENSOR_PATH", "/library_sensor.py")
# The "Download loaned e-books" button only appears when login is configured.
DOWNLOAD_ENABLED = bool(
    os.environ.get("KB_USERNAME", "").strip() and os.environ.get("KB_PASSWORD", "").strip()
)
EMAIL_TO_LIST = json.loads(os.environ.get("EMAIL_TO_JSON", "[]"))
EMAIL_CONFIGURED = bool(os.environ.get("SMTP_HOST", "").strip()) and bool(EMAIL_TO_LIST)

_QUICK_LINK_SOURCES = [
    ("send2ereader", os.environ.get("SEND2EREADER_URL", "").strip()),
    ("Calibre Web",  os.environ.get("CALIBRE_WEB_URL",  "").strip()),
]


def _build_quick_links() -> str:
    links = [(label, url) for label, url in _QUICK_LINK_SOURCES if url]
    if not links:
        return ""
    items = "\n".join(
        f'  <a class="ql-btn" href="{html.escape(url)}" target="_blank" rel="noopener">'
        f'{html.escape(label)} &#8599;</a>'
        for label, url in links
    )
    return f'\n<div class="quick-links">\n  <span class="ql-label">Open</span>\n{items}\n</div>'


_QUICK_LINKS = _build_quick_links()


def _build_email_toggle() -> str:
    if not EMAIL_CONFIGURED:
        return ""
    if len(EMAIL_TO_LIST) == 1:
        addr = html.escape(EMAIL_TO_LIST[0])
        return f"""
    <label class="toggle-row" for="email_addr_0">
      <span class="toggle-label">Email book when done</span>
      <span class="toggle-switch">
        <input type="checkbox" name="email_addr" value="{addr}" id="email_addr_0" checked>
        <span class="slider"></span>
      </span>
    </label>"""
    rows = "\n".join(
        f'      <label class="email-row">'
        f'<input type="checkbox" name="email_addr" value="{html.escape(a)}" checked>'
        f"<span>{html.escape(a)}</span></label>"
        for a in EMAIL_TO_LIST
    )
    return f"""
    <div class="email-section">
      <div class="email-section-label">Email book to:</div>
{rows}
    </div>"""


_EMAIL_TOGGLE = _build_email_toggle()


def _build_download_section() -> str:
    if not DOWNLOAD_ENABLED:
        return ""
    return """
<form method="post" id="dlform" class="dl-section">
  <input type="hidden" name="action" value="download_loans">
  <div class="dl-label">onlinebibliotheek.nl</div>
  <button type="submit" id="dlbtn" class="secondary">⬇ Download loaned e-books to Calibre</button>
</form>"""


_DOWNLOAD_SECTION = _build_download_section()

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calibre DeDRM</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f0f2f5;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0;
    padding: 20px;
  }}
  .card {{
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 16px rgba(0,0,0,.10);
    padding: 36px 40px 32px;
    width: 100%;
    max-width: 480px;
  }}
  .logo {{
    width: 48px; height: 48px;
    background: #03a9f4;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    margin-bottom: 20px;
  }}
  .logo svg {{ fill: #fff; }}
  h1 {{ font-size: 1.35em; font-weight: 700; margin: 0 0 6px; color: #111; }}
  .sub {{ color: #777; font-size: .9em; margin: 0 0 28px; }}
  .drop-zone {{
    border: 2px dashed #c8cdd5;
    border-radius: 8px;
    padding: 36px 20px;
    text-align: center;
    cursor: pointer;
    transition: border-color .15s, background .15s;
    position: relative;
  }}
  .drop-zone:hover, .drop-zone.over {{ border-color: #03a9f4; background: #f0faff; }}
  .drop-zone input {{
    position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
  }}
  .drop-icon {{ font-size: 2.2em; margin-bottom: 8px; }}
  .drop-label {{ color: #555; font-size: .95em; }}
  .drop-label strong {{ color: #03a9f4; }}
  .file-name {{
    margin-top: 10px; font-size: .88em; color: #333;
    background: #f0f2f5; border-radius: 4px; padding: 4px 10px;
    display: none;
  }}
  .toggle-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 14px;
    padding: 12px 0 0;
    border-top: 1px solid #eee;
    cursor: pointer;
    user-select: none;
  }}
  .toggle-label {{ color: #444; font-size: .93em; }}
  .toggle-switch {{ position: relative; width: 42px; height: 24px; flex-shrink: 0; }}
  .toggle-switch input {{ opacity: 0; width: 0; height: 0; position: absolute; }}
  .slider {{
    position: absolute; inset: 0;
    background: #ccc;
    border-radius: 24px;
    transition: background .2s;
  }}
  .slider::before {{
    content: '';
    position: absolute;
    width: 18px; height: 18px;
    left: 3px; top: 3px;
    background: #fff;
    border-radius: 50%;
    transition: transform .2s;
    box-shadow: 0 1px 3px rgba(0,0,0,.25);
  }}
  .toggle-switch input:checked + .slider {{ background: #03a9f4; }}
  .toggle-switch input:checked + .slider::before {{ transform: translateX(18px); }}
  .email-section {{
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid #eee;
  }}
  .email-section-label {{
    font-size: .8em;
    color: #999;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-bottom: 8px;
  }}
  .email-row {{
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 4px 0;
    cursor: pointer;
    font-size: .92em;
    color: #333;
    user-select: none;
  }}
  .email-row input[type=checkbox] {{
    width: 15px; height: 15px;
    accent-color: #03a9f4;
    cursor: pointer;
    flex-shrink: 0;
  }}
  button {{
    margin-top: 20px;
    width: 100%;
    padding: 11px;
    background: #03a9f4;
    color: #fff;
    border: none;
    border-radius: 7px;
    font-size: 1em;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s;
  }}
  button:hover {{ background: #0290d0; }}
  button:disabled {{ background: #a0d8f1; cursor: default; }}
  .dl-section {{
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid #eee;
  }}
  .dl-label {{
    font-size: .8em;
    color: #999;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-bottom: 2px;
  }}
  button.secondary {{ margin-top: 8px; background: #5c6bc0; }}
  button.secondary:hover {{ background: #3f51b5; }}
  button.secondary:disabled {{ background: #c5cae9; }}
  .msg {{
    margin-top: 20px;
    padding: 12px 16px;
    border-radius: 7px;
    font-size: .92em;
    line-height: 1.45;
  }}
  .ok  {{ background: #e8f5e9; color: #1b5e20; border-left: 4px solid #43a047; }}
  .err {{ background: #fdecea; color: #b71c1c; border-left: 4px solid #e53935; }}
  .quick-links {{
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid #eee;
  }}
  .ql-label {{
    font-size: .8em;
    color: #999;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-right: 2px;
  }}
  .ql-btn {{
    display: inline-flex;
    align-items: center;
    padding: 5px 13px;
    background: #f0f2f5;
    color: #333;
    border-radius: 20px;
    font-size: .88em;
    text-decoration: none;
    transition: background .15s, color .15s;
  }}
  .ql-btn:hover {{ background: #03a9f4; color: #fff; }}
  body {{
    background: #121212;
    color: #e8eaed;
  }}
  .card {{
    background: #1e1e1e;
    box-shadow: 0 2px 16px rgba(0,0,0,.35);
  }}
  h1 {{ color: #f5f5f5; }}
  .sub {{ color: #a6a6a6; }}
  .drop-zone {{ border-color: #555; }}
  .drop-zone:hover, .drop-zone.over {{ background: #102b38; }}
  .drop-label {{ color: #c5c5c5; }}
  .file-name, .ql-btn {{ background: #2b2b2b; color: #e0e0e0; }}
  .toggle-row, .email-section, .dl-section, .quick-links {{ border-color: #383838; }}
  .toggle-label, .email-row {{ color: #d0d0d0; }}
  .slider {{ background: #666; }}
  .email-section-label, .dl-label, .ql-label {{ color: #aaa; }}
  .ok {{ background: #183521; color: #b7e1c0; }}
  .err {{ background: #3a1d1d; color: #ffb4ab; }}
  .ql-btn:hover {{ background: #03a9f4; color: #fff; }}
  .theme-toggle {{
    display: block;
    width: auto;
    margin: 20px auto 0;
    padding: 4px 8px;
    background: transparent;
    color: #aaa;
    font-size: 1.25em;
    line-height: 1;
  }}
  .theme-toggle:hover {{ background: #2b2b2b; color: #fff; }}
  body.light {{
    background: #f0f2f5;
    color: #111;
  }}
  body.light .card {{ background: #fff; box-shadow: 0 2px 16px rgba(0,0,0,.10); }}
  body.light h1 {{ color: #111; }}
  body.light .sub {{ color: #777; }}
  body.light .drop-zone {{ border-color: #c8cdd5; }}
  body.light .drop-zone:hover, body.light .drop-zone.over {{ background: #f0faff; }}
  body.light .drop-label {{ color: #555; }}
  body.light .file-name, body.light .ql-btn {{ background: #f0f2f5; color: #333; }}
  body.light .toggle-row, body.light .email-section,
  body.light .dl-section, body.light .quick-links {{ border-color: #eee; }}
  body.light .toggle-label, body.light .email-row {{ color: #444; }}
  body.light .slider {{ background: #ccc; }}
  body.light .email-section-label, body.light .dl-label, body.light .ql-label {{ color: #999; }}
  body.light .ok {{ background: #e8f5e9; color: #1b5e20; }}
  body.light .err {{ background: #fdecea; color: #b71c1c; }}
  body.light .theme-toggle:hover {{ background: #f0f2f5; color: #333; }}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <svg xmlns="http://www.w3.org/2000/svg" height="28" viewBox="0 0 24 24" width="28">
      <path d="M19 9h-4V3H9v6H5l7 7 7-7zm-8 2V5h2v6h1.17L12 13.17 9.83 11H11zm-6 7h14v2H5v-2z"/>
    </svg>
  </div>
  <h1>Upload Book</h1>
  <p class="sub">Drop an ACSM to decrypt it, or an ebook to import it directly.</p>
  <form method="post" enctype="multipart/form-data" id="form">
    <div class="drop-zone" id="zone">
      <input type="file" name="book" required id="picker">
      <div class="drop-icon">📂</div>
      <div class="drop-label"><strong>Choose file</strong> or drag &amp; drop here</div>
    </div>
    <div class="file-name" id="fname"></div>
    {email_toggle}
    <button type="submit" id="btn">Upload</button>
  </form>
  {download_section}
  {message}
  {quick_links}
  <button type="button" class="theme-toggle" id="theme-toggle" aria-label="Switch to light mode" title="Switch to light mode">☀</button>
</div>
<script>
  var themeToggle = document.getElementById('theme-toggle');
  var savedTheme = localStorage.getItem('calibre-dedrm-theme');
  if (savedTheme === 'light') {{
    document.body.classList.add('light');
    themeToggle.textContent = '☾';
    themeToggle.setAttribute('aria-label', 'Switch to dark mode');
    themeToggle.title = 'Switch to dark mode';
  }}
  themeToggle.addEventListener('click', function() {{
    var light = document.body.classList.toggle('light');
    localStorage.setItem('calibre-dedrm-theme', light ? 'light' : 'dark');
    themeToggle.textContent = light ? '☾' : '☀';
    themeToggle.setAttribute('aria-label', light ? 'Switch to dark mode' : 'Switch to light mode');
    themeToggle.title = light ? 'Switch to dark mode' : 'Switch to light mode';
  }});
  var picker = document.getElementById('picker');
  var zone   = document.getElementById('zone');
  var fname  = document.getElementById('fname');
  var btn    = document.getElementById('btn');
  picker.addEventListener('change', function() {{
    if (picker.files.length) {{
      fname.textContent = picker.files[0].name;
      fname.style.display = 'block';
    }}
  }});
  ['dragover','dragenter'].forEach(function(e) {{
    zone.addEventListener(e, function(ev) {{ ev.preventDefault(); zone.classList.add('over'); }});
  }});
  zone.addEventListener('dragleave', function() {{ zone.classList.remove('over'); }});
  zone.addEventListener('drop', function(ev) {{
    ev.preventDefault();
    zone.classList.remove('over');
    var files = ev.dataTransfer && ev.dataTransfer.files;
    if (files && files.length) {{
      var dt = new DataTransfer();
      dt.items.add(files[0]);
      picker.files = dt.files;
      fname.textContent = files[0].name;
      fname.style.display = 'block';
    }}
  }});
  document.getElementById('form').addEventListener('submit', function() {{
    btn.disabled = true; btn.textContent = 'Uploading…';
  }});
  var dlform = document.getElementById('dlform');
  if (dlform) {{
    dlform.addEventListener('submit', function() {{
      var b = document.getElementById('dlbtn');
      b.disabled = true; b.textContent = 'Downloading… (may take a minute)';
    }});
  }}
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress noisy access log

    def do_GET(self):
        self._html(200, "")

    def do_POST(self):
        ct = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        # The "Download loaned e-books" button posts a urlencoded action.
        if "application/x-www-form-urlencoded" in ct:
            params = urllib.parse.parse_qs(body.decode("utf-8", "replace"))
            if params.get("action", [""])[0] == "download_loans":
                return self._handle_download_loans()

        try:
            msg_bytes = f"Content-Type: {ct}\r\n\r\n".encode() + body
            msg = email.parser.BytesParser().parsebytes(msg_bytes)
            filename = data = None
            selected_emails = []
            for part in msg.walk():
                name = part.get_param("name", header="content-disposition")
                if name == "book":
                    filename = os.path.basename(part.get_filename() or "").strip()
                    data = part.get_payload(decode=True)
                elif name == "email_addr":
                    val = (part.get_payload(decode=True) or b"").decode().strip()
                    if val:
                        selected_emails.append(val)
            if not filename or not data:
                raise ValueError("No file received.")
            _ALLOWED = {".acsm", ".epub", ".pdf", ".mobi", ".azw", ".azw3", ".cbz", ".fb2"}
            if not any(filename.lower().endswith(ext) for ext in _ALLOWED):
                raise ValueError(f"Unsupported file type. Accepted: {', '.join(sorted(_ALLOWED))}")
            dest = pathlib.Path(INPUT_DIR) / filename
            dest.write_bytes(data)
            if EMAIL_CONFIGURED:
                pathlib.Path(str(dest) + ".email_recipients").write_text(
                    "\n".join(selected_emails)
                )
            msg_html = f'<div class="msg ok"><strong>{html.escape(filename)}</strong> queued for processing.</div>'
            self._html(200, msg_html)
        except Exception as exc:
            self._html(400, f'<div class="msg err">Error: {html.escape(str(exc))}</div>')

    def _handle_download_loans(self):
        """Run library_sensor --download-now and report what was queued."""
        try:
            proc = subprocess.run(
                ["python3", LIBRARY_SENSOR, "--download-now"],
                capture_output=True, text=True, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return self._html(504, '<div class="msg err">Download timed out (still running in the background).</div>')
        except Exception as exc:
            return self._html(500, f'<div class="msg err">Error: {html.escape(str(exc))}</div>')

        out = (proc.stdout or "") + (proc.stderr or "")
        lines_out = out.splitlines()
        downloaded = [l.split(">>> Downloaded '", 1)[1].split("'", 1)[0]
                      for l in lines_out if ">>> Downloaded '" in l]
        unavailable = [l.split("Not available for download: '", 1)[1].split("'", 1)[0]
                       for l in lines_out if "Not available for download: '" in l]
        skipped = [l for l in lines_out if "already in Calibre" in l]
        summary = next((l for l in lines_out if "Auto-download:" in l), "")

        if proc.returncode != 0 and not downloaded and not unavailable:
            tail = html.escape("\n".join(lines_out[-6:]) or "no output")
            return self._html(500, f'<div class="msg err">Download failed:<br><pre>{tail}</pre></div>')

        parts = []
        for t in downloaded:
            parts.append(f"⬇ <strong>{html.escape(t)}</strong> queued for import.")
        for t in unavailable:
            parts.append(f'⚠️ Book "<strong>{html.escape(t)}</strong>" not available for download.')
        if not parts:
            parts.append(html.escape(summary.replace(">>> ", "")) or "Nothing new to download.")
        note = f" ({len(skipped)} already in library)" if skipped else ""
        cls = "ok" if downloaded or not unavailable else "err"
        body = "<br>".join(parts)
        return self._html(200, f'<div class="msg {cls}"><strong>Bookshelf checked{html.escape(note)}.</strong><br>{body}</div>')

    def _html(self, code: int, message: str):
        body = PAGE.format(message=message, email_toggle=_EMAIL_TOGGLE,
                           download_section=_DOWNLOAD_SECTION, quick_links=_QUICK_LINKS).encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    pathlib.Path(INPUT_DIR).mkdir(parents=True, exist_ok=True)
    with http.server.HTTPServer(("0.0.0.0", PORT), Handler) as srv:
        print(f">>> Upload server on port {PORT}", flush=True)
        srv.serve_forever()
