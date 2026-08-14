import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

CONFIG_PATH = Path("config/items.json")
OUT_PATH = Path("data/diagnostics.json")
REALM_API_BASE = "https://realm-api.tradeskillmaster.com/public"


def parse_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def find_item(rows, item_id):
    wanted = str(item_id)
    for row in rows:
        for key in ("itemId", "itemID", "id"):
            if row.get(key) == wanted:
                return row
    return None


def request_json(session, url):
    r = session.get(url, timeout=45, allow_redirects=True)
    out = {
        "url": url,
        "http_status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "content_length": len(r.content),
        "body_preview": r.text[:500],
    }
    if r.status_code == 200:
        try:
            out["json"] = r.json()
        except Exception as exc:
            out["json_error"] = repr(exc)
    return out


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from walk(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk(value)


def thunderstrike_matches(payload):
    matches = []
    for obj in walk(payload):
        text = json.dumps(obj, ensure_ascii=False).lower()
        if "thunderstrike" in text:
            matches.append(obj)
            if len(matches) >= 25:
                break
    return matches


def candidate_public_data_urls(match):
    urls = []
    text = json.dumps(match, ensure_ascii=False)
    # Keep explicit known fallbacks, but also derive slugs from discovered fields.
    game_candidates = ["classic", "classic-progression", "classic-anniversary", "anniversary"]
    region_candidates = ["eu"]
    realm_candidates = ["thunderstrike"]

    if isinstance(match, dict):
        for k, v in match.items():
            lk = str(k).lower()
            if isinstance(v, str):
                lv = v.strip().lower().replace(" ", "-")
                if "game" in lk or "version" in lk or "type" in lk:
                    game_candidates.insert(0, lv)
                if "region" in lk and len(lv) <= 10:
                    region_candidates.insert(0, lv)
                if "slug" in lk and "thunderstrike" in lv:
                    realm_candidates.insert(0, lv)

    seen = set()
    for game in game_candidates:
        for region in region_candidates:
            for realm in realm_candidates:
                if not game or not region or not realm:
                    continue
                url = f"https://public-data.tradeskillmaster.com/{game}/{region}/realm/{realm}/items.csv"
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": config["market"],
        "realm_api": {},
        "sources": [],
    }

    session = requests.Session()
    session.headers.update({"User-Agent": "thunderstrike-gold-scanner/0.2"})

    realms = request_json(session, f"{REALM_API_BASE}/realms")
    result["realm_api"]["realms"] = {k: v for k, v in realms.items() if k != "json"}
    matches = thunderstrike_matches(realms.get("json")) if realms.get("json") is not None else []
    result["realm_api"]["thunderstrike_matches"] = matches

    regions = request_json(session, f"{REALM_API_BASE}/regions")
    result["realm_api"]["regions"] = {k: v for k, v in regions.items() if k != "json"}
    region_matches = thunderstrike_matches(regions.get("json")) if regions.get("json") is not None else []
    if region_matches:
        result["realm_api"]["region_thunderstrike_matches"] = region_matches

    urls = []
    for match in matches:
        urls.extend(candidate_public_data_urls(match))
    if not urls:
        urls = candidate_public_data_urls({})

    # Deduplicate while preserving order.
    urls = list(dict.fromkeys(urls))[:40]

    for url in urls:
        src = {"url": url}
        try:
            r = session.get(url, timeout=45, allow_redirects=True)
            src["http_status"] = r.status_code
            src["content_type"] = r.headers.get("content-type")
            src["content_length"] = len(r.content)
            src["body_preview"] = r.text[:300]
            if r.status_code == 200 and "csv" in (r.headers.get("content-type") or "").lower():
                rows = parse_csv(r.text)
                src["row_count"] = len(rows)
                src["columns"] = list(rows[0].keys()) if rows else []
                src["items"] = []
                for item in config["items"]:
                    found = find_item(rows, item["id"])
                    src["items"].append({"id": item["id"], "name": item["name"], "row": found})
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

    print("Realm API status:", realms.get("http_status"))
    print("Thunderstrike matches:", len(matches))
    for m in matches[:5]:
        print("MATCH:", json.dumps(m, ensure_ascii=False)[:1000])
    print("Selected TSM source:", result.get("selected_url"))
    if result.get("selected_items"):
        arcane = next((x for x in result["selected_items"] if x["id"] == 22445), None)
        print("Arcane Dust row:", arcane)


if __name__ == "__main__":
    main()
