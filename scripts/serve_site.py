"""Serve the assembled site locally, the way GitHub Pages will.

`python -m http.server` is not good enough here, for two reasons.

It takes its MIME types from the system, and on Windows that means `.mjs` and `.wasm`
come back as `text/plain` -- which browsers refuse to execute as modules. The page then
fails locally for a reason that has nothing to do with the page.

And Pages serves this site under `/scenet/`, which every version's switcher relies on: it
reads `/scenet/switcher.json`. Served from `/`, the switcher would find nothing. So this
serves under the same prefix, and sends `/` there.

Run from the repository root, after `scripts/build_site.py`:

    uv run python scripts/serve_site.py
"""

import argparse
import functools
import http.server
import io
from http import HTTPStatus
from pathlib import Path
from typing import BinaryIO, ClassVar
from urllib.parse import urlsplit

from site_versions import SITE_PATH

ROOT = Path(__file__).resolve().parent.parent

# What GitHub Pages sends for these, and what browsers require.
EXTRA_TYPES = {
    ".mjs": "text/javascript",
    ".js": "text/javascript",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".whl": "application/octet-stream",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def site_path(request_path: str) -> str | None:
    """The path inside the served directory a request names.

    Args:
        request_path: The request's path, with any query string.

    Returns:
        The path with the site's prefix removed, or None when it is outside the site.
    """
    if not request_path.startswith(SITE_PATH):
        return None
    return "/" + request_path[len(SITE_PATH) :]


class Handler(http.server.SimpleHTTPRequestHandler):
    """A static handler that knows about the file types a modern page actually uses."""

    extensions_map: ClassVar[dict[str, str]] = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        **EXTRA_TYPES,
    }

    def send_head(self) -> io.BytesIO | BinaryIO | None:
        """Send `/` to the site's prefix, and refuse anything else outside it."""
        if site_path(self.path) is None:
            if urlsplit(self.path).path in {"/", SITE_PATH.rstrip("/")}:
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", SITE_PATH)
                self.end_headers()
            else:
                self.send_error(HTTPStatus.NOT_FOUND, f"outside {SITE_PATH}")
            return None
        return super().send_head()

    def translate_path(self, path: str) -> str:
        """Map a path under the site's prefix to the file it names."""
        inside = site_path(path)
        return super().translate_path(path if inside is None else inside)

    def end_headers(self) -> None:
        """Add the headers Pages sets, so local behaviour matches deployed behaviour."""
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Log only failures. A page that loads 200 assets should not print 200 lines."""
        status = str(args[1]) if len(args) > 1 else ""
        if not status.startswith("2") and not status.startswith("3"):
            super().log_message(format, *args)


def main() -> None:
    """Serve a directory over HTTP until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default=str(ROOT / "site"))
    parser.add_argument("--port", type=int, default=8125)
    args = parser.parse_args()

    handler = functools.partial(Handler, directory=args.directory)
    # Threading matters. A single-threaded server deadlocks the moment a browser opens
    # several connections at once, which every modern page does -- and this one fetches
    # a 10 MB WebAssembly runtime alongside a dozen other assets.
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {args.directory} at http://127.0.0.1:{args.port}{SITE_PATH}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
