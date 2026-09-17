#!/usr/bin/env python3
import html
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
IMAGES_DIR = PROJECT_ROOT / "web" / "images"
DB_DIR = Path(os.environ.get("ANALYTICS_DB_DIR", "/var/lib/petr80-analytics"))
DB_PATH = DB_DIR / "analytics.db"
HOST = "127.0.0.1"
PORT = 8081
MAX_BODY_BYTES = 8192
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_slides() -> list[str]:
    if not IMAGES_DIR.exists():
        return []
    return [
        entry.name
        for entry in sorted(IMAGES_DIR.iterdir(), key=lambda item: item.name.lower())
        if entry.is_file() and entry.suffix.lower() == ".webp"
    ]


def ensure_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                visitor_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                visitor_id TEXT NOT NULL,
                total_slides INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(visitor_id) REFERENCES visitors(visitor_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slide_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                slide_id TEXT NOT NULL,
                slide_index INTEGER NOT NULL,
                total_slides INTEGER NOT NULL,
                viewed_at TEXT NOT NULL,
                UNIQUE(session_id, slide_id),
                FOREIGN KEY(visitor_id) REFERENCES visitors(visitor_id),
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
        """)
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        if "total_slides" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN total_slides INTEGER NOT NULL DEFAULT 0")
        if "platform" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN platform TEXT")
        if "browser" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN browser TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_slide_views_visitor ON slide_views(visitor_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_slide_views_session ON slide_views(session_id)")
        conn.commit()


def valid_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(UUID_RE.fullmatch(value)) and str(uuid.UUID(value)) == value.lower()


def parse_payload(handler: BaseHTTPRequestHandler) -> dict | None:
    try:
        length = int(handler.headers.get("Content-Length", "-1"))
    except ValueError:
        return None
    if length < 0 or length > MAX_BODY_BYTES:
        return None
    try:
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def validate_common(payload: dict) -> tuple[str, str, int] | tuple[None, None, None]:
    visitor_id = payload.get("visitor_id")
    session_id = payload.get("session_id")
    total_slides = payload.get("total_slides")
    if not valid_uuid(visitor_id) or not valid_uuid(session_id):
        return None, None, None
    if not isinstance(total_slides, int) or isinstance(total_slides, bool) or not 1 <= total_slides <= 10000:
        return None, None, None
    return visitor_id, session_id, total_slides


def detect_device_browser(user_agent: str) -> tuple[str, str]:
    ua = user_agent or ""
    if "iPad" in ua:
        platform = "iPad"
    elif "iPhone" in ua:
        platform = "iPhone"
    elif "Android" in ua:
        platform = "Android"
    elif "Windows" in ua:
        platform = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        platform = "macOS"
    elif "Linux" in ua:
        platform = "Linux"
    else:
        platform = "Unknown"

    if "Edg/" in ua or "Edge/" in ua:
        browser = "Edge"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        browser = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        browser = "Chrome"
    elif "Safari/" in ua:
        browser = "Safari"
    else:
        browser = "Unknown"
    return platform, browser


def device_label(platform: str, browser: str) -> str:
    if platform == "Unknown" and browser == "Unknown":
        return "Unknown"
    return f"{platform} / {browser}"


def record_visit(payload: dict, user_agent: str = "") -> tuple[bool, str]:
    visitor_id, session_id, total_slides = validate_common(payload)
    if not visitor_id:
        return False, "invalid visit payload"
    platform, browser = detect_device_browser(user_agent)
    now = iso_now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR IGNORE INTO visitors(visitor_id, created_at) VALUES(?, ?)", (visitor_id, now))
        conn.execute(
            "INSERT OR IGNORE INTO sessions(session_id, visitor_id, total_slides, platform, browser, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (session_id, visitor_id, total_slides, platform, browser, now),
        )
        conn.commit()
    return True, "ok"


def record_slide(payload: dict, user_agent: str = "") -> tuple[bool, str]:
    visitor_id, session_id, total_slides = validate_common(payload)
    slide_id = payload.get("slide_id")
    slide_index = payload.get("slide_index")
    slide_name = Path(slide_id).name if isinstance(slide_id, str) else ""
    slides = list_slides()
    if not visitor_id or not slide_name or slide_name != slide_id or slide_name not in slides:
        return False, "invalid slide payload"
    if not isinstance(slide_index, int) or isinstance(slide_index, bool) or not 0 <= slide_index < total_slides:
        return False, "invalid slide index"
    if slide_index >= len(slides) or slides[slide_index] != slide_name:
        return False, "slide index does not match manifest"
    platform, browser = detect_device_browser(user_agent)
    with sqlite3.connect(DB_PATH) as conn:
        session = conn.execute("SELECT visitor_id, total_slides FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if session and session[0] != visitor_id:
            return False, "unknown session"
        if not session:
            now = iso_now()
            conn.execute("INSERT OR IGNORE INTO visitors(visitor_id, created_at) VALUES(?, ?)", (visitor_id, now))
            conn.execute(
                "INSERT OR IGNORE INTO sessions(session_id, visitor_id, total_slides, platform, browser, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (session_id, visitor_id, total_slides, platform, browser, now),
            )
        conn.execute(
            "INSERT OR IGNORE INTO slide_views(visitor_id, session_id, slide_id, slide_index, total_slides, viewed_at) VALUES(?, ?, ?, ?, ?, ?)",
            (visitor_id, session_id, slide_name, slide_index, total_slides, iso_now()),
        )
        conn.commit()
    return True, "ok"


def empty_stats() -> dict:
    return {
        "total_visitors": 0, "total_visits": 0, "total_slides": len(list_slides()),
        "completed_slideshow": 0, "completion_rate": 0.0, "average_completion": 0.0,
        "median_completion": 0.0, "visitors_reaching_100": 0, "percent_reaching_100": 0.0,
        "distribution": {"0-24": 0, "25-49": 0, "50-74": 0, "75-99": 0, "100": 0}, "visitors": [],
    }


def get_stats() -> dict:
    ensure_db()
    total_slides = len(list_slides())
    with sqlite3.connect(DB_PATH) as conn:
        total_visitors = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
        total_visits = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        visitor_rows = conn.execute("SELECT visitor_id, COUNT(DISTINCT slide_id) FROM slide_views GROUP BY visitor_id").fetchall()
        latest_devices = {
            visitor_id: (platform or "Unknown", browser or "Unknown")
            for visitor_id, platform, browser in conn.execute(
                """
                SELECT visitor_id, platform, browser
                FROM sessions AS current
                WHERE rowid = (
                    SELECT rowid FROM sessions AS recent
                    WHERE recent.visitor_id = current.visitor_id
                    ORDER BY recent.created_at DESC, recent.rowid DESC LIMIT 1
                )
                """
            ).fetchall()
        }
    values = []
    visitors = []
    for visitor_id, viewed in visitor_rows:
        completion = min(100.0, viewed / total_slides * 100.0) if total_slides else 0.0
        values.append(completion)
        platform, browser = latest_devices.get(visitor_id, ("Unknown", "Unknown"))
        visitors.append({"visitor_id": visitor_id, "platform": platform, "browser": browser, "viewed": viewed, "total": total_slides, "completion": round(completion, 1)})
    values_sorted = sorted(values)
    if values_sorted:
        mid = len(values_sorted) // 2
        median = values_sorted[mid] if len(values_sorted) % 2 else (values_sorted[mid - 1] + values_sorted[mid]) / 2
    else:
        median = 0.0
    completed = sum(value >= 100.0 for value in values)
    buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-99": 0, "100": 0}
    for value in values:
        if value < 25: buckets["0-24"] += 1
        elif value < 50: buckets["25-49"] += 1
        elif value < 75: buckets["50-74"] += 1
        elif value < 100: buckets["75-99"] += 1
        else: buckets["100"] += 1
    return {
        "total_visitors": total_visitors, "total_visits": total_visits, "total_slides": total_slides,
        "completed_slideshow": completed,
        "completion_rate": round(completed / total_visitors * 100.0, 1) if total_visitors else 0.0,
        "average_completion": round(sum(values) / len(values), 1) if values else 0.0,
        "median_completion": round(median, 1), "visitors_reaching_100": completed,
        "percent_reaching_100": round(completed / total_visitors * 100.0, 1) if total_visitors else 0.0,
        "distribution": buckets, "visitors": sorted(visitors, key=lambda row: row["completion"], reverse=True),
    }


def stats_text() -> str:
    stats = get_stats()
    lines = [
        "Petr Tabakov 80 - Analytics", "", f"Total visitors: {stats['total_visitors']}",
        f"Total visits: {stats['total_visits']}", f"Total slides: {stats['total_slides']}",
        f"Completed slideshow: {stats['completed_slideshow']}", f"Completion rate: {stats['completion_rate']}%",
        f"Average completion: {stats['average_completion']}%", f"Median completion: {stats['median_completion']}%",
        f"Visitors at 100%: {stats['visitors_reaching_100']}", f"Percentage at 100%: {stats['percent_reaching_100']}%", "",
        "Visitor       Device / Browser          Viewed       Completion", "------------------------------------------------------------------",
    ]
    lines.extend(f"{row['visitor_id'][:8]}...  {device_label(row['platform'], row['browser']):<26} {row['viewed']:>3} / {row['total']:<3}    {row['completion']:>5}%" for row in stats["visitors"])
    return "\n".join(lines) + "\n"


class AnalyticsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/healthz":
            self.send_json({"status": "ok"})
        elif path == "/analytics/stats.json":
            self.send_json(get_stats())
        elif path == "/analytics/stats":
            body = f"<html><body><pre>{html.escape(stats_text())}</pre></body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = parse_payload(self)
        if payload is None:
            self.send_json({"ok": False, "error": "invalid request"}, HTTPStatus.BAD_REQUEST)
            return
        user_agent = self.headers.get("User-Agent", "")
        ok, message = record_visit(payload, user_agent) if path == "/analytics/visit" else record_slide(payload, user_agent) if path == "/analytics/slide" else (False, "not found")
        self.send_json({"ok": ok, "error": message} if not ok else {"ok": True}, 200 if ok else HTTPStatus.NOT_FOUND if message == "not found" else HTTPStatus.BAD_REQUEST)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main() -> None:
    ensure_db()
    server = ThreadingHTTPServer((HOST, PORT), AnalyticsHandler)
    print(f"Serving analytics on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
