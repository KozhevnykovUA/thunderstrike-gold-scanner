import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG_PATH = Path("config/items.json")
OUT_PATH = Path("data/diagnostics.json")

CANDIDATE_URLS = [
    "https://public-data.tradeskillmaster.com/classic/eu/realm/thunderstrike/items.csv",
    "https://public-data.tradeskillmaster.com/classic-progression/eu/realm/thunderstrike/items.csv",
]


def parse_csv(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows


def find_item(rows, item_id):
    wanted = str(item_id)
    for row in rows:
        for key in ("itemId", "itemID", "id"):
            if row.get(key) == wanted:
                return row
    return None


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": config["market"],
        "sources": [],
    }

    session = requests.Session()
    session.headers.update({"User-Agent": "thunderstrike-gold-scanner/0.1"})

    for url in CANDIDATE_URLS:
        src = {"url": url}
        try:
            r = session.get(url, timeout=45, allow_redirects=True)
            src["http_status"] = r.status_code
            src["content_type"] = r.headers.get("content-type")
            src["content_length"] = len(r.content)
            src["body_preview"] = r.text[:300]
            if r.status_code == 200:
                rows = parse_csv(r.text)
                src["row_count"] = len(rows)
                src["columns"] = list(rows[0].keys()) if rows else []
                src["items"] = []
                for item in config["items"]:
                    found = find_item(rows, item["id"])
                    entry = {"id": item["id"], "name": item["name"], "row": found}
                    src["items"].append(entry)
                if rows:
                    result["selected_url"] = url
                    result["selected_columns"] = src["columns"]
                    result["selected_items"] = src["items"]
                    result["sources"].append(src)
                    break
        except Exception as exc:
            src["error"] = repr(exc)
        result["sources"].append(src)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Selected TSM source:", result.get("selected_url"))
    if result.get("selected_items"):
        arcane = next((x for x in result["selected_items"] if x["id"] == 22445), None)
        print("Arcane Dust row:", arcane)


if __name__ == "__main__":
    main()
