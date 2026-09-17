#!/usr/bin/env python3
import json
import os
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_ROOT = PROJECT_ROOT / "web"
IMAGES_DIR = WEB_ROOT / "images"
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
ANALYTICS_BACKEND = "http://127.0.0.1:8081"


def list_slides() -> list[str]:
    if not IMAGES_DIR.exists():
        return []
    return [
        entry.name
        for entry in sorted(IMAGES_DIR.iterdir(), key=lambda item: item.name.lower())
        if entry.is_file() and entry.suffix.lower() == ".webp"
    ]


def json_response(handler, payload: dict, status: int = 200) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def proxy_analytics(handler, method: str, body: bytes = b"") -> None:
    headers = {"Content-Type": "application/json"} if method == "POST" else {}
    user_agent = handler.headers.get("User-Agent")
    if user_agent:
        headers["User-Agent"] = user_agent
    request = Request(
        f"{ANALYTICS_BACKEND}{urlparse(handler.path).path}",
        data=body if method == "POST" else None,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=2) as response:
            payload = response.read()
            handler.send_response(response.status)
            handler.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
    except (OSError, URLError):
        json_response(handler, {"ok": False, "error": "analytics unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)


class SlideshowHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/healthz":
            json_response(self, {"status": "ok", "slides": len(list_slides())})
            return

        if path == "/api/slides":
            slides = list_slides()
            response = {
                "count": len(slides),
                "slides": [{"name": name, "path": f"/images/{name}"} for name in slides],
            }
            json_response(self, response)
            return

        if path in ("/analytics/stats", "/analytics/stats.json"):
            proxy_analytics(self, "GET")
            return

        if path in ("/", "/index.html"):
            self.path = "/index.html"
            return super().do_GET()

        if path.startswith("/images/"):
            return super().do_GET()

        if path.startswith("/css/") or path.startswith("/js/") or path.startswith("/favicon"):
            return super().do_GET()

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/analytics/visit", "/analytics/slide"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 8192:
                    raise ValueError
                body = self.rfile.read(length)
            except (TypeError, ValueError):
                json_response(self, {"ok": False, "error": "invalid request"}, HTTPStatus.BAD_REQUEST)
                return
            proxy_analytics(self, "POST", body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html") or path.startswith(("/images/", "/css/", "/js/", "/favicon")):
            self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SlideshowHandler)
    print(f"Serving slideshow on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server")
        server.server_close()


if __name__ == "__main__":
    main()
