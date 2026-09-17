#!/usr/bin/env python3
import argparse
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = PROJECT_ROOT / "web" / "images"
DB_PATH = Path(os.environ.get("ANALYTICS_DB_DIR", "/var/lib/petr80-analytics")) / "analytics.db"


def list_slides() -> list[str]:
    if not IMAGES_DIR.exists():
        return []
    return sorted(
        [p.name for p in IMAGES_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".webp"],
        key=lambda name: name.lower(),
    )


def stats() -> dict:
    if not DB_PATH.exists():
        return {
            "total_visitors": 0,
            "total_visits": 0,
            "total_slides": len(list_slides()),
            "completed_slideshow": 0,
            "completion_rate": 0.0,
            "average_completion": 0.0,
            "median_completion": 0.0,
            "visitors_reaching_100": 0,
            "percent_reaching_100": 0.0,
            "distribution": {"0-24": 0, "25-49": 0, "50-74": 0, "75-99": 0, "100": 0},
            "visitors": [],
        }

    conn = sqlite3.connect(DB_PATH)
    total_slides = len(list_slides())
    total_visitors = conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
    total_visits = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    visitor_rows = conn.execute(
        "SELECT visitor_id, COUNT(DISTINCT slide_id) AS viewed FROM slide_views GROUP BY visitor_id"
    ).fetchall()

    completion_values = []
    visitor_data = []
    for visitor_id, viewed in visitor_rows:
        percent = (viewed / total_slides * 100.0) if total_slides else 0.0
        completion_values.append(percent)
        visitor_data.append({
            "visitor_id": visitor_id,
            "viewed": viewed,
            "total": total_slides,
            "completion": round(percent, 1),
        })

    completed = sum(1 for value in completion_values if value >= 100.0)
    average = (sum(completion_values) / len(completion_values)) if completion_values else 0.0
    if completion_values:
        completion_values_sorted = sorted(completion_values)
        mid = len(completion_values_sorted) // 2
        if len(completion_values_sorted) % 2 == 0:
            median = (completion_values_sorted[mid - 1] + completion_values_sorted[mid]) / 2
        else:
            median = completion_values_sorted[mid]
    else:
        median = 0.0

    buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-99": 0, "100": 0}
    for value in completion_values:
        if value < 25:
            buckets["0-24"] += 1
        elif value < 50:
            buckets["25-49"] += 1
        elif value < 75:
            buckets["50-74"] += 1
        elif value < 100:
            buckets["75-99"] += 1
        else:
            buckets["100"] += 1

    return {
        "total_visitors": total_visitors,
        "total_visits": total_visits,
        "total_slides": total_slides,
        "completed_slideshow": completed,
        "completion_rate": round((completed / total_visitors * 100.0) if total_visitors else 0.0, 1),
        "average_completion": round(average, 1),
        "median_completion": round(median, 1),
        "visitors_reaching_100": completed,
        "percent_reaching_100": round((completed / total_visitors * 100.0) if total_visitors else 0.0, 1),
        "distribution": buckets,
        "visitors": sorted(visitor_data, key=lambda row: row["completion"], reverse=True),
    }


def print_summary() -> None:
    data = stats()
    print(f"Total visitors: {data['total_visitors']}")
    print(f"Total visits: {data['total_visits']}")
    print(f"Total slides: {data['total_slides']}")
    print(f"Completed slideshow: {data['completed_slideshow']}")
    print(f"Completion rate: {data['completion_rate']}%")
    print(f"Average completion: {data['average_completion']}%")
    print(f"Median completion: {data['median_completion']}%")
    print(f"Visitors who reached 100%: {data['visitors_reaching_100']}")
    print(f"Percentage of visitors at 100%: {data['percent_reaching_100']}%")
    print("Distribution:")
    for bucket, count in data["distribution"].items():
        print(f"  {bucket}%: {count}")
    print("\nVisitor details:")
    for entry in data["visitors"]:
        print(f"  {entry['visitor_id'][:8]}...  {entry['viewed']} / {entry['total']}  {entry['completion']}%")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show slideshow analytics summary")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args()

    data = stats()
    if args.json:
        import json
        print(json.dumps(data, indent=2))
        return
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
