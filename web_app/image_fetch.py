"""Fetch a chart image from a URL the user pasted, without letting the server be
used to reach private networks (SSRF).

Every hop is checked: only http/https on ports 80/443, the hostname must resolve
only to public IP addresses, and the connection is pinned to the address we
checked so a second DNS lookup can't swap in an internal one. Redirects are
followed by hand (at most MAX_REDIRECTS) and each target is checked again.

If the URL is a web page rather than an image, we look for the page's preview
image (og:image / twitter:image), which on chart sites is usually the chart.
"""
import http.client
import io
import ipaddress
import re
import socket
import ssl
from html import unescape
from urllib.parse import urljoin, urlsplit

from PIL import Image

MAX_BYTES      = 5 * 1024 * 1024   # same limit as uploads
MAX_PAGE_BYTES = 1 * 1024 * 1024   # only need the <head> of an HTML page
MAX_REDIRECTS  = 4
TIMEOUT        = 8
USER_AGENT     = 'ChartHawkBot/1.0 (+https://charthawk.info)'
ALLOWED_FORMATS = {'PNG', 'JPEG', 'GIF', 'WEBP'}


class FetchError(Exception):
    """Raised with a short, user-facing message."""


def _check_host(host):
    """Resolve host and return one public IP to connect to, or raise FetchError."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise FetchError("We couldn't find that website. Check the link and try again.")
    ips = {info[4][0] for info in infos}
    if not ips:
        raise FetchError("We couldn't find that website. Check the link and try again.")
    for ip in ips:
        addr = ipaddress.ip_address(ip.split('%')[0])
        if not addr.is_global or addr.is_multicast:
            raise FetchError("That link points to a private address, so we can't open it.")
    return sorted(ips)[0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, ip, **kw):
        super().__init__(host, **kw)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, ip, **kw):
        super().__init__(host, context=ssl.create_default_context(), **kw)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _get(url, max_bytes):
    """GET with SSRF checks on every hop. Returns (final_url, content_type, body)."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise FetchError('Only http and https links are supported.')
        if parts.username or parts.password:
            raise FetchError("Links with a username or password aren't supported.")
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        if port not in (80, 443):
            raise FetchError("That link uses an unusual port, so we can't open it.")
        ip = _check_host(parts.hostname)
        conn_cls = _PinnedHTTPSConnection if parts.scheme == 'https' else _PinnedHTTPConnection
        conn = conn_cls(parts.hostname, ip, port=port, timeout=TIMEOUT)
        path = parts.path or '/'
        if parts.query:
            path += '?' + parts.query
        try:
            conn.request('GET', path, headers={
                'User-Agent': USER_AGENT,
                'Accept': 'image/avif,image/webp,image/png,image/*;q=0.9,text/html;q=0.8,*/*;q=0.5',
            })
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.getheader('Location')
                if not location:
                    raise FetchError("That link didn't lead anywhere we could open.")
                url = urljoin(url, location)
                continue
            if resp.status != 200:
                raise FetchError(f"That link returned an error ({resp.status}).")
            length = resp.getheader('Content-Length')
            if length and length.isdigit() and int(length) > max_bytes:
                raise FetchError('That image is over 5 MB. Try a smaller version.')
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError('That image is over 5 MB. Try a smaller version.')
            ctype = (resp.getheader('Content-Type') or '').split(';')[0].strip().lower()
            return url, ctype, body
        except (socket.timeout, TimeoutError):
            raise FetchError('That website took too long to respond.')
        except ssl.SSLError:
            raise FetchError("We couldn't open a secure connection to that website.")
        except (OSError, http.client.HTTPException) as e:
            if isinstance(e, FetchError):
                raise
            raise FetchError("We couldn't download that link.")
        finally:
            conn.close()
    raise FetchError('That link redirected too many times.')


_META_RE = re.compile(r'<meta\s[^>]*>', re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


def _preview_image_url(page_html, base_url):
    """Find og:image / twitter:image in an HTML page."""
    found = {}
    for tag in _META_RE.findall(page_html):
        attrs = {m.group(1).lower(): unescape(m.group(3) if m.group(3) is not None else m.group(4))
                 for m in _ATTR_RE.finditer(tag)}
        key = (attrs.get('property') or attrs.get('name') or '').lower()
        if key in ('og:image', 'og:image:url', 'og:image:secure_url', 'twitter:image', 'twitter:image:src') and attrs.get('content'):
            found.setdefault(key, attrs['content'])
    for key in ('og:image:secure_url', 'og:image', 'og:image:url', 'twitter:image', 'twitter:image:src'):
        if key in found:
            return urljoin(base_url, found[key].strip())
    return None


def _as_image(body):
    """Return (bytes, media_type) if body is a supported image, else None."""
    try:
        img = Image.open(io.BytesIO(body))
        fmt = img.format
        img.verify()
    except Exception:
        return None
    if fmt not in ALLOWED_FORMATS:
        return None
    return body, f'image/{fmt.lower()}'


def fetch_chart_image(url):
    """Returns (image_bytes, media_type, filename). Raises FetchError."""
    url = (url or '').strip()
    if not url:
        raise FetchError('Paste a link to a chart image.')
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', url) and not re.match(r'^https?://', url, re.IGNORECASE):
        raise FetchError('Only http and https links are supported.')
    if not re.match(r'^https?://', url, re.IGNORECASE):
        url = 'https://' + url
    final_url, ctype, body = _get(url, MAX_BYTES)

    image = _as_image(body)
    if image is None and ('html' in ctype or body.lstrip()[:15].lower().startswith((b'<!doctype', b'<html'))):
        preview = _preview_image_url(body[:MAX_PAGE_BYTES].decode('utf-8', 'replace'), final_url)
        if not preview:
            raise FetchError("That link opens a web page, not an image, and we couldn't find a chart on it. Try right-clicking the chart and copying the image address.")
        final_url, ctype, body = _get(preview, MAX_BYTES)
        image = _as_image(body)

    if image is None:
        raise FetchError("That link isn't an image we can read. Use a PNG, JPG, GIF or WebP.")

    name = urlsplit(final_url).path.rstrip('/').rsplit('/', 1)[-1] or 'chart'
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name)[:80] or 'chart'
    ext = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}[image[1]]
    if not name.lower().endswith((ext, '.jpeg' if ext == '.jpg' else ext)):
        name = name.rsplit('.', 1)[0] + ext
    return image[0], image[1], name
